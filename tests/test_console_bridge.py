import asyncio
import importlib.util
import http.client
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import Mock, patch

from lulu.consoled import ConsoleInterface


ROOT = Path(__file__).parents[1]
SPEC = importlib.util.spec_from_file_location("console_ui_bridge", ROOT / "scripts" / "console-ui-bridge.py")
BRIDGE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(BRIDGE)


class ConsoleBridgeTests(unittest.TestCase):
    def test_shell_notification_validates_and_forwards_through_consoled(self) -> None:
        class Consoled:
            async def call_notify(self, *args):
                self.received = args
                return True

        async def exercise() -> None:
            consoled = Consoled()
            bridge = BRIDGE.ConsoleUiBridge(asyncio.get_running_loop(), consoled, object())
            result = await bridge.notify({"title": "Library refreshed", "body": "Up to date",
                                          "severity": "success"})
            self.assertEqual(result, {"accepted": True})
            self.assertEqual(consoled.received[:3], ("Library refreshed", "Up to date", "success"))
            with self.assertRaises(ValueError):
                await bridge.notify({"title": "Title", "body": "Body", "severity": "urgent"})

        asyncio.run(exercise())

    def test_lutris_search_retries_dotted_abbreviations_in_compact_form(self):
        search = BRIDGE.ConsoleUiBridge.lutris_search.__get__(object(), BRIDGE.ConsoleUiBridge)
        result = {"name": "Sonic 3 A.I.R", "slug": "sonic-3-air"}
        with patch("lulu.lutris_adapter.LutrisAdapter.search", side_effect=((), (result,))) as mocked:
            rows = search("Sonic 3 A.I.R.")

        self.assertEqual([call.args[0] for call in mocked.call_args_list], [
            "Sonic 3 A.I.R.", "Sonic 3 AIR",
        ])
        self.assertEqual(rows[0]["slug"], "sonic-3-air")

    def test_lutris_recipe_discovery_exposes_provider_requirements(self):
        recipe = SimpleNamespace(
            game_slug="example-game", installer_slug="example-linux", title="Example",
            runner="linux", requirements=(SimpleNamespace(
                file_id="rom", filename="source.rom", label="Source ROM",
                required=True, local=True),),
        )
        with patch("lulu.lutris_adapter.LutrisAdapter.search", return_value=(
                {"name": "Example", "slug": "example-game", "year": 2000,
                 "coverart": "art", "banner_url": "banner", "ignored": "private"},)):
            rows = BRIDGE.ConsoleUiBridge.lutris_search.__get__(object(), BRIDGE.ConsoleUiBridge)("Example")
        self.assertEqual(rows[0]["slug"], "example-game")
        self.assertNotIn("ignored", rows[0])
        with patch("lulu.lutris_adapter.LutrisAdapter.recipes", return_value=(recipe,)):
            recipes = BRIDGE.ConsoleUiBridge.lutris_recipes.__get__(object(), BRIDGE.ConsoleUiBridge)("example-game")
        self.assertEqual(recipes[0]["requirements"], [{
            "file_id": "rom", "filename": "source.rom", "label": "Source ROM",
            "required": True, "local": True,
        }])

    def test_generic_file_picker_is_bounded_and_skips_symlinks(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "Games").mkdir()
            (root / "source.rom").write_bytes(b"rom")
            (root / "escape").symlink_to("/etc")
            with patch.object(BRIDGE, "PATHS", SimpleNamespace(home=root)):
                result = BRIDGE.ConsoleUiBridge.generic_file_listing(str(root))
                with self.assertRaisesRegex(ValueError, "outside"):
                    BRIDGE.ConsoleUiBridge.generic_file_listing("/etc")
            self.assertEqual({item["name"] for item in result["entries"]}, {"Games", "source.rom"})

    def test_lutris_recipe_install_reuses_register_and_submit_acquisition_calls(self):
        async def exercise():
            class Acquisition:
                def __init__(self): self.calls = []
                async def call_create_lutris_install_source(self, *args):
                    self.calls.append(("create", args)); return '{"source":"json"}'
                async def call_register_pc_source(self, value):
                    self.calls.append(("register", value)); return "lutris-recipe:game:recipe"
                async def call_submit_pc_install(self, source_id, title):
                    self.calls.append(("submit", source_id, title)); return "job-1"

            acquisition = Acquisition()
            bridge = BRIDGE.ConsoleUiBridge(asyncio.get_running_loop(), object(), object(), acquisition)
            bridge._refresh_after_acquisition = lambda *_: asyncio.sleep(0)
            result = await bridge.install_lutris_recipe({
                "title": "Example", "game_slug": "game", "installer_slug": "recipe",
                "files": {"rom": "/home/lulu/roms/source.rom"},
            })
            await asyncio.sleep(0)
            self.assertEqual(result, {"token": "job-1"})
            self.assertEqual([call[0] for call in acquisition.calls], ["create", "register", "submit"])
            self.assertEqual(acquisition.calls[-1], ("submit", "lutris-recipe:game:recipe", "Example"))

        asyncio.run(exercise())

    def test_shell_bootstrap_does_not_refresh_catalogue_and_acquisition_is_optional(self):
        source = (ROOT / "scripts" / "console-ui-bridge.py").read_text()
        bootstrap = source[source.index("async def main()"):
                           source.index('if __name__ == "__main__":')]
        self.assertNotIn("call_refresh(", bootstrap)
        self.assertNotIn("call_refresh_stages(", bootstrap)
        self.assertIn('OPTIONAL_LULU_DBUS_OBJECTS["acquisitiond"]', bootstrap)
        self.assertIn("ConsoleUiBridge(asyncio.get_running_loop(), consoled, sessiond)", bootstrap)
        self.assertIn('name="optional-acquisitiond-connect"', bootstrap)
        self.assertIn("asyncio.create_subprocess_exec(shell, qml, env=environment)", bootstrap)
        self.assertNotIn("await connect_optional_acquisitiond()", bootstrap)

    def test_launch_status_normalizes_session_lifecycle_without_fake_progress(self) -> None:
        async def exercise():
            class Sessiond:
                async def call_get_state(self):
                    return json.dumps({
                        "lifecycle": "starting", "primary_id": "steam:123",
                        "launch_token": "token", "session_title": "Fixture",
                        "launch_cancellable": True,
                    })

            bridge = BRIDGE.ConsoleUiBridge(asyncio.get_running_loop(), object(), Sessiond())
            bridge.launch_logs.start("steam:123")
            bridge.launch_logs.note("Steam", "Proton runtime preparation started")
            status = await bridge.launch_status()
            self.assertEqual(status["stage"], "runtime_preparation")
            self.assertEqual(status["provider"], "steam")
            self.assertEqual(status["title"], "Fixture")
            self.assertEqual(status["lines"][-1], status["detail"])
            self.assertIsNone(status["progress"])
            self.assertTrue(status["cancellable"])

        asyncio.run(exercise())

    def test_launch_status_does_not_offer_unsupported_local_cancellation(self) -> None:
        async def exercise():
            class Sessiond:
                async def call_get_state(self):
                    return json.dumps({
                        "lifecycle": "starting", "primary_id": "local:wii:fixture",
                        "launch_token": "token", "launch_cancellable": False,
                    })

            bridge = BRIDGE.ConsoleUiBridge(asyncio.get_running_loop(), object(), Sessiond())
            status = await bridge.launch_status()
            self.assertEqual(status["stage"], "launching_executable")
            self.assertFalse(status["cancellable"])
            self.assertIsNone(status["progress"])

        asyncio.run(exercise())

    def test_steam_authentication_failure_can_be_retried_after_auth_is_fixed(self) -> None:
        async def exercise():
            class Consoled:
                async def call_resolve_steam_install(self, _game_id): return "123"

            class Acquisition:
                def __init__(self): self.retried = None
                async def call_get_snapshot(self):
                    return json.dumps({"jobs": [{
                        "job_id": "old-failed-job", "provider": "steam",
                        "content_identity": "steam:123", "state": "failed",
                        "retryable": False,
                        "error": {"code": "authentication-required"},
                    }]})
                async def call_retry_job(self, job_id):
                    self.retried = job_id
                    return "new-retry-job"

            acquisition = Acquisition()
            bridge = BRIDGE.ConsoleUiBridge(asyncio.get_running_loop(), Consoled(),
                                             object(), acquisition)
            bridge.list_available_games = lambda _provider: asyncio.sleep(0, result=[{
                "game_id": "steam:123", "provider": "steam", "title": "Fixture",
            }])
            result = await bridge.install_game("steam:123")
            await asyncio.sleep(0)
            self.assertEqual(result, {"token": "new-retry-job"})
            self.assertEqual(acquisition.retried, "old-failed-job")

        asyncio.run(exercise())

    def test_retired_authentication_failure_allows_a_fresh_acquisition(self) -> None:
        async def exercise():
            class Consoled:
                async def call_resolve_steam_install(self, _game_id): return "2124490"

            class Acquisition:
                def __init__(self): self.submitted = None; self.retried = None
                async def call_get_snapshot(self):
                    return json.dumps({"jobs": [{
                        "job_id": "old-failed-job", "provider": "steam",
                        "content_identity": "steam:2124490", "state": "failed",
                        "retired": True, "retryable": False,
                        "error": {"code": "authentication-cancelled", "retryable": False},
                    }]})
                async def call_submit_job(self, provider, identity, title):
                    self.submitted = (provider, identity, title)
                    return "fresh-job"
                async def call_retry_job(self, job_id):
                    self.retried = job_id
                    raise AssertionError("retired failed attempts must not be retried")

            acquisition = Acquisition()
            bridge = BRIDGE.ConsoleUiBridge(asyncio.get_running_loop(), Consoled(),
                                             object(), acquisition)
            bridge.list_available_games = lambda _provider: asyncio.sleep(0, result=[{
                "game_id": "steam:2124490", "provider": "steam", "title": "Silent Hill 2",
            }])
            result = await bridge.install_game("steam:2124490")
            await asyncio.sleep(0)
            self.assertEqual(result, {"token": "fresh-job"})
            self.assertEqual(acquisition.submitted, ("steam", "steam:2124490", "Silent Hill 2"))
            self.assertIsNone(acquisition.retried)

        asyncio.run(exercise())

    def test_selected_mapping_candidate_preserves_its_igdb_identity(self) -> None:
        class Consoled:
            def __init__(self): self.selected = None
            async def call_set_metadata_match(self, *values): self.selected = values

        async def exercise():
            consoled = Consoled()
            bridge = BRIDGE.ConsoleUiBridge(asyncio.get_running_loop(), consoled, object())
            await bridge.set_metadata_match("steam:26800", {
                "provider": "igdb", "metadata_game_id": "2853", "canonical_title": "Braid",
            })
            self.assertEqual(consoled.selected, ("steam:26800", "igdb", "2853", "Braid"))

        asyncio.run(exercise())

    def test_artwork_candidate_passes_the_chosen_role_and_source_identity(self) -> None:
        class Consoled:
            def __init__(self): self.selected = None
            async def call_select_presentation_artwork(self, *values): self.selected = values

        async def exercise():
            consoled = Consoled()
            bridge = BRIDGE.ConsoleUiBridge(asyncio.get_running_loop(), consoled, object())
            await bridge.select_presentation_artwork(
                "steam:26800", "preview_still", "https://igdb.example/screen.jpg")
            self.assertEqual(consoled.selected, (
                "steam:26800", "preview_still", "https://igdb.example/screen.jpg"))

        asyncio.run(exercise())

    def test_selected_recents_card_artwork_passes_chosen_source_url(self) -> None:
        class Consoled:
            def __init__(self): self.selected = None
            async def call_select_artwork(self, *values): self.selected = values

        async def exercise():
            consoled = Consoled()
            bridge = BRIDGE.ConsoleUiBridge(asyncio.get_running_loop(), consoled, object())
            await bridge.select_artwork("steam:26800", "https://sgdb.example/card.png")
            self.assertEqual(consoled.selected,
                             ("steam:26800", "https://sgdb.example/card.png"))

        asyncio.run(exercise())

    def test_game_options_uses_normalized_uninstall_capability_and_operation(self) -> None:
        class Acquisition:
            def __init__(self):
                self.uninstalled = []

            async def call_can_uninstall(self, game_id):
                return json.dumps({"supported": True, "installed": True,
                                   "provider": "steam" if game_id.startswith("steam:") else "unknown"})

            async def call_uninstall_game(self, game_id):
                self.uninstalled.append(game_id)
                return "job-1"

            async def call_get_snapshot(self):
                return json.dumps({"jobs": [{"job_id": "job-1", "state": "failed"}]})

        async def exercise():
            acquisition = Acquisition()
            class Consoled:
                def __init__(self): self.refreshed = []
                async def call_refresh_stages(self, stages): self.refreshed.append(stages)
            consoled = Consoled()
            bridge = BRIDGE.ConsoleUiBridge(asyncio.get_running_loop(), consoled, object(), acquisition)
            capability = await bridge.uninstall_capability("steam:40800")
            result = await bridge.uninstall_game("steam:40800")
            await asyncio.sleep(0)
            self.assertEqual(capability, {"supported": True, "installed": True, "provider": "steam"})
            self.assertEqual(result, {"token": "job-1"})
            self.assertEqual(acquisition.uninstalled, ["steam:40800"])
            self.assertEqual(consoled.refreshed, [[
                "steam", "gog", "epic", "local", "lutris", "romm", "components",
            ]])

        asyncio.run(exercise())

    def test_keyboard_bridge_routes_show_hide_and_status_to_consoled(self) -> None:
        class Consoled:
            def __init__(self): self.calls = []
            async def call_show_keyboard(self): self.calls.append("show"); return True
            async def call_hide_keyboard(self): self.calls.append("hide"); return False
            async def call_keyboard_visible(self): self.calls.append("status"); return True

        async def exercise():
            consoled = Consoled()
            bridge = BRIDGE.ConsoleUiBridge(asyncio.get_running_loop(), consoled, object())
            self.assertEqual(await bridge.keyboard("show"), {"visible": True})
            self.assertEqual(await bridge.keyboard("status"), {"visible": True})
            self.assertEqual(await bridge.keyboard("hide"), {"visible": False})
            self.assertEqual(consoled.calls, ["show", "status", "hide"])

        asyncio.run(exercise())
    def test_bridge_checks_core_prerequisites_before_launch(self) -> None:
        class ReadyBus:
            def __init__(self) -> None:
                self.calls = []

            async def introspect(self, name: str, path: str) -> object:
                self.calls.append((name, path))
                return object()

        bus = ReadyBus()
        result = asyncio.run(BRIDGE.introspect_lulu_services(bus))
        self.assertEqual(set(result), {"sessiond", "consoled"})
        self.assertEqual(len(bus.calls), 2)

    def test_launch_path_decodes_qml_encoded_game_id(self) -> None:
        path = "/launch/steam%3A220780"
        self.assertEqual(BRIDGE.unquote(path.removeprefix("/launch/")), "steam:220780")

    def test_launch_call_has_a_provider_watchdog_timeout(self) -> None:
        source = (ROOT / "scripts" / "console-ui-bridge.py").read_text()
        self.assertIn("route = resolve_game_launch_route(", source)
        self.assertIn("timeout = 15", source)
        self.assertIn("str(error) or type(error).__name__", source)

    def test_malformed_steam_launch_id_is_rejected_before_session_dispatch(self) -> None:
        class Session:
            async def call_request_steam_launch(self, *_args):
                raise AssertionError("malformed Steam ID reached Sessiond")

        async def exercise() -> None:
            bridge = BRIDGE.ConsoleUiBridge(asyncio.get_running_loop(), object(), Session())
            with self.assertRaisesRegex(ValueError, "positive integer"):
                await bridge.launch_game("steam:not-an-appid")

        asyncio.run(exercise())

    def test_state_path_reads_authoritative_session_state(self) -> None:
        source = (ROOT / "scripts" / "console-ui-bridge.py").read_text()
        self.assertIn('if urlparse(self.path).path == "/state":', source)
        self.assertIn("call_get_state()", source)

    def test_metadata_options_paths_use_the_service_boundary(self) -> None:
        source = (ROOT / "scripts" / "console-ui-bridge.py").read_text()
        for path in ("/metadata/search", "/metadata/match/", "/metadata/title/", "/metadata/artwork/"):
            self.assertIn(path, source)
        for method_name in ("call_search_metadata", "call_set_metadata_match", "call_set_title_override",
                            "call_clear_title_override", "call_suppress_artwork", "call_restore_artwork"):
            self.assertIn(method_name, source)

    def test_library_refresh_includes_native_storefront_install_projection(self) -> None:
        source = (ROOT / "scripts" / "console-ui-bridge.py").read_text()
        self.assertIn('["steam", "gog", "epic", "local", "romm", "artwork"]', source)


    def test_launch_endpoint_returns_bridge_result_without_double_wrap(self) -> None:
        class Logs:
            def start(self, game_id: str) -> None:
                pass

            def note(self, source: str, line: str) -> None:
                pass

        class FakeBridge:
            launch_logs = Logs()

            def call(self, operation, timeout=None):
                return asyncio.run(operation)

            async def launch_game(self, game_id: str) -> dict[str, object]:
                self.asserted_game_id = game_id
                return {"token": "transaction-token", "navigation_only": False}

        fake = FakeBridge()
        previous = getattr(BRIDGE.ApiHandler, "bridge", None)
        BRIDGE.ApiHandler.bridge = fake
        server = BRIDGE.ThreadingHTTPServer(("127.0.0.1", 0), BRIDGE.ApiHandler)
        thread = BRIDGE.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            connection = http.client.HTTPConnection("127.0.0.1", server.server_address[1])
            connection.request("POST", "/launch/steam%3A40800")
            response = connection.getresponse()
            body = json.loads(response.read())
            connection.close()
        finally:
            server.shutdown()
            server.server_close()
            thread.join()
            if previous is None:
                del BRIDGE.ApiHandler.bridge
            else:
                BRIDGE.ApiHandler.bridge = previous

        self.assertEqual(response.status, 200)
        self.assertIsInstance(body["token"], str)
        self.assertEqual(body["token"], "transaction-token")
        self.assertIs(body["navigation_only"], False)
        self.assertNotIsInstance(body["token"], dict)
        self.assertEqual(fake.asserted_game_id, "steam:40800")

    def test_statistics_overlay_endpoint_cycles_saved_mode(self) -> None:
        class FakeBridge:
            def call(self, operation, timeout=None):
                return asyncio.run(operation)

            async def cycle_statistics_overlay_mode(self):
                return "minimal"

        fake = FakeBridge()
        previous = getattr(BRIDGE.ApiHandler, "bridge", None)
        BRIDGE.ApiHandler.bridge = fake
        server = BRIDGE.ThreadingHTTPServer(("127.0.0.1", 0), BRIDGE.ApiHandler)
        thread = BRIDGE.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            connection = http.client.HTTPConnection("127.0.0.1", server.server_address[1])
            connection.request("POST", "/settings/statistics-overlay", body="{}",
                               headers={"Content-Type": "application/json"})
            response = connection.getresponse()
            body = json.loads(response.read())
            connection.close()
        finally:
            server.shutdown()
            server.server_close()
            thread.join()
            if previous is None:
                del BRIDGE.ApiHandler.bridge
            else:
                BRIDGE.ApiHandler.bridge = previous

        self.assertEqual(response.status, 200)
        self.assertEqual(body, {"mode": "minimal"})

    def test_legacy_steam_game_uses_consoled_canonical_launch_boundary(self) -> None:
        class Session:
            async def call_request_steam_launch(self, *_args):
                raise AssertionError("legacy Steam launch was called")

        class Consoled:
            async def call_launch_game(self, game_id: str, timeout: int) -> str:
                self.request = (game_id, timeout)
                return "aurelia-token"

        async def exercise() -> None:
            consoled = Consoled()
            bridge = BRIDGE.ConsoleUiBridge(asyncio.get_running_loop(), consoled, Session())
            result = await bridge.launch_game("steam:40800")
            self.assertIsInstance(result["token"], str)
            self.assertEqual(json.loads(json.dumps(result))["token"], "aurelia-token")
            self.assertEqual(result, {"token": "aurelia-token", "navigation_only": False})
            self.assertEqual(consoled.request, ("steam:40800", 15000))

        asyncio.run(exercise())

    def test_legacy_identity_uses_consoled_canonical_launch_boundary(self) -> None:
        class Session:
            async def call_request_steam_launch(self, *_args):
                raise AssertionError("Aurelia route fell back to Steam")

        class Consoled:
            async def call_launch_game(self, game_id: str, timeout: int) -> str:
                self.request = (game_id, timeout)
                return "aurelia-token"

        async def exercise() -> None:
            session = Session()
            consoled = Consoled()
            bridge = BRIDGE.ConsoleUiBridge(asyncio.get_running_loop(), consoled, session)
            with patch.dict(BRIDGE.os.environ, {}, clear=True):
                result = await bridge.launch_game("steam:104200")
            self.assertEqual(result, {"token": "aurelia-token", "navigation_only": False})
            self.assertEqual(consoled.request, ("steam:104200", 15000))

        asyncio.run(exercise())

    def test_aurelia_catalogue_identity_uses_consoled_launch_boundary(self) -> None:
        class Session:
            async def call_request_steam_launch(self, appid: str, timeout: int) -> str:
                raise AssertionError("Aurelia catalogue identity fell back to legacy Steam")

        class Consoled:
            async def call_launch_game(self, game_id: str, timeout: int) -> str:
                self.request = (game_id, timeout)
                return "aurelia-token"

        async def exercise() -> None:
            session = Session()
            consoled = Consoled()
            bridge = BRIDGE.ConsoleUiBridge(asyncio.get_running_loop(), consoled, session)
            with patch.dict(BRIDGE.os.environ, {}, clear=True):
                result = await bridge.launch_game("steam-aurelia:104200")
            self.assertEqual(result, {"token": "aurelia-token", "navigation_only": False})
            self.assertEqual(consoled.request, ("steam-aurelia:104200", 15000))

        asyncio.run(exercise())

    def test_http_and_dbus_dispatch_same_canonical_aurelia_routes(self) -> None:
        async def exercise(game_id, provider, override):
            class Session:
                def __init__(self):
                    self.requests = []

                async def call_set_delegated_launch_context(self, _context):
                    return None

                async def call_request_aurelia_launch(self, app_id, timeout):
                    self.requests.append((app_id, timeout))
                    return "same-aurelia-token"

            session = Session()
            game = SimpleNamespace(
                game_id=game_id, provider=provider,
                provider_id="104200", launchable=True,
            )
            games = [game]
            if game_id == "steam:104200":
                games.append(SimpleNamespace(
                    game_id="steam-aurelia:104200", provider="steam-aurelia",
                    provider_id="104200", launchable=True,
                ))
            store = SimpleNamespace(
                list_games=Mock(return_value=games),
                mark_played=Mock(return_value="catalogue-delta"),
            )
            consoled = ConsoleInterface.__new__(ConsoleInterface)
            consoled.catalogue = SimpleNamespace(store=store)
            consoled._plugins = SimpleNamespace(with_capability=lambda _capability: ())
            consoled.sessiond = session
            consoled._publish_delta = Mock()
            bridge = BRIDGE.ConsoleUiBridge(asyncio.get_running_loop(), consoled, session)
            async def launch_through_consoled(identity, timeout):
                return await ConsoleInterface.LaunchGame.__wrapped__(
                    consoled, identity, timeout)
            consoled.call_launch_game = launch_through_consoled
            with patch.dict(BRIDGE.os.environ, override, clear=True), \
                    patch.object(consoled, "CatalogueChanged", lambda: None):
                http_result = await bridge.launch_game(game_id)
                dbus_result = await ConsoleInterface.LaunchGame.__wrapped__(
                    consoled, game_id, 15000)

            self.assertEqual(http_result["token"], dbus_result)
            self.assertEqual(session.requests, [("104200", 15000), ("104200", 15000)])
            self.assertEqual(store.mark_played.call_count, 2)

        async def run():
            await exercise("steam-aurelia:104200", "steam-aurelia", {})
            await exercise("steam:104200", "steam", {})

        asyncio.run(run())

    def test_local_cancellation_uses_consoled_process_boundary(self) -> None:
        class Session:
            async def call_cancel_launch(self) -> None:
                raise AssertionError("local cancellation bypassed consoled")

        class Consoled:
            async def call_cancel_local_launch(self) -> None:
                self.cancelled = True

        async def exercise() -> None:
            consoled = Consoled()
            bridge = BRIDGE.ConsoleUiBridge(asyncio.get_running_loop(), consoled, Session())
            bridge.local_token = "local:123"
            await bridge.cancel_launch()
            self.assertTrue(consoled.cancelled)
            self.assertIsNone(bridge.local_token)

        asyncio.run(exercise())

    def test_managed_game_cancellation_ignores_stale_local_token(self) -> None:
        class Session:
            def __init__(self) -> None:
                self.cancelled = False

            async def call_get_state(self) -> str:
                return json.dumps({
                    "lifecycle": "game",
                    "session_kind": "game",
                    "primary_id": "epic:installed-game",
                })

            async def call_cancel_launch(self) -> None:
                self.cancelled = True

        class Consoled:
            async def call_cancel_local_launch(self) -> None:
                raise AssertionError("managed game cancellation used Consoled")

        async def exercise() -> None:
            session = Session()
            bridge = BRIDGE.ConsoleUiBridge(asyncio.get_running_loop(), Consoled(), session)
            bridge.local_token = "stale-token-from-prior-game"
            await bridge.cancel_launch()
            self.assertTrue(session.cancelled)
            self.assertIsNone(bridge.local_token)

        asyncio.run(exercise())

    def test_local_game_cancellation_uses_consoled_before_token_is_returned(self) -> None:
        class Session:
            async def call_get_state(self) -> str:
                return json.dumps({
                    "lifecycle": "starting",
                    "session_kind": "game",
                    "primary_id": "local:nes:game",
                })

            async def call_cancel_launch(self) -> None:
                raise AssertionError("local runtime cancellation bypassed Consoled")

        class Consoled:
            def __init__(self) -> None:
                self.cancelled = False

            async def call_cancel_local_launch(self) -> None:
                self.cancelled = True

        async def exercise() -> None:
            consoled = Consoled()
            bridge = BRIDGE.ConsoleUiBridge(asyncio.get_running_loop(), consoled, Session())
            await bridge.cancel_launch()
            self.assertTrue(consoled.cancelled)

        asyncio.run(exercise())

    def test_cancellation_log_entry_is_emitted_once(self) -> None:
        class Session:
            async def call_cancel_launch(self) -> None:
                return

        async def exercise() -> None:
            bridge = BRIDGE.ConsoleUiBridge(asyncio.get_running_loop(), object(), Session())
            bridge.launch_logs._active = True
            await asyncio.gather(bridge.cancel_launch(), bridge.cancel_launch(), bridge.cancel_launch())
            lines = bridge.launch_logs.snapshot()["lines"]
            self.assertEqual(sum("Cancelling launch" in line for line in lines), 1)

        asyncio.run(exercise())

if __name__ == "__main__":
    unittest.main()
