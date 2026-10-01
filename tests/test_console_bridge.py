import asyncio
import importlib.util
import http.client
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).parents[1]
SPEC = importlib.util.spec_from_file_location("console_ui_bridge", ROOT / "scripts" / "console-ui-bridge.py")
BRIDGE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(BRIDGE)


class ConsoleBridgeTests(unittest.TestCase):
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
            bridge = BRIDGE.ConsoleUiBridge(asyncio.get_running_loop(), object(), object(), acquisition)
            capability = await bridge.uninstall_capability("steam:40800")
            result = await bridge.uninstall_game("steam:40800")
            await asyncio.sleep(0)
            self.assertEqual(capability, {"supported": True, "installed": True, "provider": "steam"})
            self.assertEqual(result, {"token": "job-1"})
            self.assertEqual(acquisition.uninstalled, ["steam:40800"])

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
    def test_bridge_checks_all_prerequisites_before_launch(self) -> None:
        class ReadyBus:
            def __init__(self) -> None:
                self.calls = []

            async def introspect(self, name: str, path: str) -> object:
                self.calls.append((name, path))
                return object()

        bus = ReadyBus()
        result = asyncio.run(BRIDGE.introspect_lulu_services(bus))
        self.assertEqual(set(result), {"sessiond", "consoled", "acquisitiond"})
        self.assertEqual(len(bus.calls), 3)

    def test_launch_path_decodes_qml_encoded_game_id(self) -> None:
        path = "/launch/steam%3A220780"
        self.assertEqual(BRIDGE.unquote(path.removeprefix("/launch/")), "steam:220780")

    def test_launch_call_has_a_provider_watchdog_timeout(self) -> None:
        source = (ROOT / "scripts" / "console-ui-bridge.py").read_text()
        self.assertIn("timeout = None if game_id.startswith(\"steam:\") else 15", source)
        self.assertIn("str(error) or type(error).__name__", source)

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

    def test_steam_game_uses_session_transaction_not_navigation_only_uri(self) -> None:
        class Session:
            async def call_request_steam_launch(self, appid: str, timeout: int) -> str:
                return BRIDGE.Variant("s", "transaction-token")

        class Consoled:
            async def call_launch_game(self, game_id: str, timeout: int) -> str:
                raise AssertionError("Steam launch bypassed sessiond")

        async def exercise() -> None:
            bridge = BRIDGE.ConsoleUiBridge(asyncio.get_running_loop(), Consoled(), Session())
            result = await bridge.launch_game("steam:40800")
            self.assertIsInstance(result["token"], str)
            self.assertEqual(json.loads(json.dumps(result))["token"], "transaction-token")
            self.assertEqual(result, {"token": "transaction-token", "navigation_only": False})

        asyncio.run(exercise())

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
