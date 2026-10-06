from pathlib import Path
import asyncio
import tempfile
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from lulu.consoled import (ConsoleCatalog, ConsoleInterface,
                           _BackpressureSafeMessageWriter,
                           _validated_metadata_refresh_stages)
from lulu.catalogue import CatalogueStore
from lulu.plugins.flatpak import FlatpakApplication

ROOT = Path(__file__).parents[1]


class ConsoledStartupTests(unittest.TestCase):
    def test_aurelia_library_entry_routes_launch_game_directly_to_sessiond(self) -> None:
        class Sessiond:
            def __init__(self):
                self.requests = []

            async def call_request_aurelia_launch(self, app_id, timeout_ms):
                self.requests.append((app_id, timeout_ms))
                return "aurelia-session-token"

            async def call_request_steam_launch(self, *_args):
                raise AssertionError("Aurelia library entry fell back to legacy Steam")

        class PluginRegistry:
            def with_capability(self, capability):
                raise AssertionError(f"Aurelia dispatch incorrectly searched {capability} plugins")

        game = SimpleNamespace(
            game_id="steam-aurelia:104200", provider="steam-aurelia",
            provider_id="104200", launchable=True,
        )
        store = SimpleNamespace(
            list_games=Mock(return_value=[game]),
            mark_played=Mock(return_value="catalogue-delta"),
        )
        consoled = ConsoleInterface.__new__(ConsoleInterface)
        consoled.catalogue = SimpleNamespace(store=store)
        consoled._plugins = PluginRegistry()
        consoled.sessiond = Sessiond()
        consoled._publish_delta = Mock()

        async def exercise():
            with patch.object(consoled, "CatalogueChanged", lambda: None):
                result = await ConsoleInterface.LaunchGame.__wrapped__(
                    consoled, "steam-aurelia:104200", 30000)
            self.assertEqual(result, "aurelia-session-token")

        asyncio.run(exercise())
        self.assertEqual(consoled.sessiond.requests, [("104200", 30000)])
        store.mark_played.assert_called_once_with("steam-aurelia:104200")
        consoled._publish_delta.assert_called_once_with("catalogue-delta")

    def test_steam_id_with_aurelia_override_uses_canonical_aurelia_route(self) -> None:
        class Sessiond:
            async def call_request_aurelia_launch(self, app_id, timeout_ms):
                self.request = (app_id, timeout_ms)
                return "aurelia-token"

            async def call_request_steam_launch(self, *_args):
                raise AssertionError("override did not select Aurelia")

        game = SimpleNamespace(
            game_id="steam:104200", provider="steam", provider_id="104200", launchable=True,
        )
        store = SimpleNamespace(
            list_games=Mock(return_value=[game]),
            mark_played=Mock(return_value="catalogue-delta"),
        )
        consoled = ConsoleInterface.__new__(ConsoleInterface)
        consoled.catalogue = SimpleNamespace(store=store)
        consoled._plugins = SimpleNamespace(with_capability=lambda _capability: ())
        consoled.sessiond = Sessiond()
        consoled._publish_delta = Mock()

        async def exercise():
            with patch.dict("os.environ", {"LULU_STEAM_LAUNCH_PROVIDER": "steam-aurelia"}), \
                    patch.object(consoled, "CatalogueChanged", lambda: None):
                result = await ConsoleInterface.LaunchGame.__wrapped__(
                    consoled, "steam:104200", 15000)
            self.assertEqual(result, "aurelia-token")

        asyncio.run(exercise())
        self.assertEqual(consoled.sessiond.request, ("104200", 15000))
        store.mark_played.assert_called_once_with("steam:104200")

    def test_steam_contextual_navigation_result_is_preserved(self) -> None:
        class Provider:
            def __init__(self):
                self.calls = []

            def open_game_details(self, app_id):
                self.calls.append(("details", app_id))
                return f"steam://nav/games/details/{app_id}"

            def launch_gamepad_title(self, app_id):
                self.calls.append(("launch", app_id))
                return f"steam://rungameid/{app_id}"

        game = SimpleNamespace(
            game_id="steam:40800", provider="steam", provider_id="40800", launchable=True,
        )
        store = SimpleNamespace(list_games=Mock(return_value=[game]))
        provider = Provider()
        consoled = ConsoleInterface.__new__(ConsoleInterface)
        consoled.catalogue = SimpleNamespace(store=store, provider=provider)
        consoled._plugins = SimpleNamespace(with_capability=lambda _capability: ())
        consoled.sessiond = None

        result = asyncio.run(ConsoleInterface.LaunchGame.__wrapped__(
            consoled, "steam:40800", 15000))

        self.assertEqual(result, "steam://nav/games/details/40800")
        self.assertEqual(provider.calls, [("details", "40800"), ("launch", "40800")])

    def test_dbus_writer_keeps_connection_alive_on_socket_backpressure(self) -> None:
        class Socket:
            def send(self, _data):
                raise BlockingIOError(11, "Resource temporarily unavailable")

        class Loop:
            def remove_writer(self, _fd):
                raise AssertionError("writer must remain registered while data is pending")

        bus = SimpleNamespace(
            _negotiate_unix_fd=False, _sock=Socket(), _loop=Loop(), _fd=10,
            _finalize=Mock(),
        )
        writer = _BackpressureSafeMessageWriter(bus)
        writer.buf = memoryview(b"pending D-Bus message")

        writer.write_callback()

        self.assertEqual(writer.offset, 0)
        self.assertEqual(bytes(writer.buf), b"pending D-Bus message")
        self.assertIsNone(writer.fut)
        bus._finalize.assert_not_called()

    def test_dbus_writer_resumes_pending_message_after_transient_backpressure(self) -> None:
        class Socket:
            def __init__(self):
                self.calls = 0
                self.sent = bytearray()

            def send(self, data):
                self.calls += 1
                if self.calls == 1:
                    raise BlockingIOError(11, "Resource temporarily unavailable")
                self.sent.extend(data)
                return len(data)

        bus = SimpleNamespace(
            _negotiate_unix_fd=False, _sock=Socket(), _loop=SimpleNamespace(
                remove_writer=lambda _fd: None), _fd=10, _finalize=Mock(),
        )
        writer = _BackpressureSafeMessageWriter(bus)
        writer.buf = memoryview(b"pending D-Bus message")

        writer.write_callback()
        self.assertEqual(writer.offset, 0)
        self.assertEqual(bytes(writer.buf), b"pending D-Bus message")
        writer.write_callback()

        self.assertEqual(bytes(bus._sock.sent), b"pending D-Bus message")
        self.assertIsNone(writer.buf)
        bus._finalize.assert_not_called()

    def test_empty_dbus_provider_means_combined_installable_catalogue(self) -> None:
        store = Mock()
        store.list_available_games.return_value = []

        result = ConsoleCatalog.available_games(SimpleNamespace(store=store), "")

        self.assertEqual(result, [])
        store.list_available_games.assert_called_once_with(None)

    def test_dbus_name_is_published_before_provider_refresh(self) -> None:
        source = (ROOT / "src/lulu/consoled.py").read_text()
        serve = source[source.index("async def serve()") :]
        self.assertLess(serve.index("await bus.request_name(BUS_NAME)"),
                        serve.index("await interface.refresh_catalogue("))

    def test_provider_refresh_is_background_work(self) -> None:
        source = (ROOT / "src/lulu/consoled.py").read_text()
        self.assertIn('asyncio.to_thread(self.catalogue.refresh)', source)
        self.assertIn('ROMM_SYNC_INTERVAL = 15 * 60', source)

    def test_startup_readiness_is_only_installed_local_reconciliation(self) -> None:
        source = (ROOT / "src/lulu/consoled.py").read_text()
        self.assertIn('startup_stages = {"steam", "local"}', source)
        self.assertIn("mark_startup_reconciliation_ready", source)
        synchronize = source[source.index("async def synchronize()"):
                             source.index("asyncio.create_task(synchronize()")]
        self.assertLess(synchronize.index("mark_startup_reconciliation_ready()"),
                        synchronize.index("await interface.refresh_catalogue(stages)"))
        self.assertIn('"romm", "components", "romm-artwork",', source)
        self.assertIn('"protondb", "artwork"', source)
        self.assertIn("GetStartupReadiness", source)

    def test_background_metadata_retry_requires_successful_non_skipped_oobe_validation(self) -> None:
        setup = {"selected_integrations": ["metadata.igdb", "metadata.steamgriddb"],
                 "skipped_integrations": ["metadata.steamgriddb"],
                 "validation": {"metadata.igdb": {"ok": True},
                               "metadata.steamgriddb": {"ok": True}}}
        with patch("lulu.onboarding.onboarding_state", return_value=setup):
            self.assertEqual(_validated_metadata_refresh_stages(), {
                "metadata", "metadata-enrichment", "artwork"})
        setup["validation"]["metadata.igdb"] = {"ok": False}
        with patch("lulu.onboarding.onboarding_state", return_value=setup):
            self.assertEqual(_validated_metadata_refresh_stages(), set())

    def test_installed_flatpak_games_reconcile_without_optional_provider_selection(self) -> None:
        class Adapter:
            provider_id = "flatpak"
            available = True

            async def reconcile(self):
                return (FlatpakApplication(
                    "org.supertuxproject.SuperTux", "SuperTux",
                    branch="stable", arch="x86_64", installed=True,
                    categories=("Game", "ActionGame"), component_type="desktop-application",
                ),)

        class Registry:
            def with_capability(self, _capability):
                return [Adapter()]

        with tempfile.TemporaryDirectory() as directory:
            catalog = ConsoleCatalog.__new__(ConsoleCatalog)
            catalog._plugins = Registry()
            catalog.store = CatalogueStore(Path(directory) / "catalogue.sqlite3")
            catalog.last_delta_batches = []
            catalog.external_entitlements = ()
            catalog.steam_entitlements = None
            catalog.romm = None
            catalog._romm_injected = True
            with patch("lulu.onboarding.onboarding_state", return_value={"selected_providers": []}):
                catalog.refresh({"components"})
            projected = catalog.store.list_games()
            self.assertEqual([(game.provider_id, game.component_classification) for game in projected],
                             [("org.supertuxproject.SuperTux", "game")])

    def test_refresh_callers_share_one_in_flight_reconciliation(self) -> None:
        class Catalogue:
            def __init__(self) -> None:
                self.calls = 0
                self.started = threading.Event()
                self.release = threading.Event()

            def refresh(self) -> list[object]:
                self.calls += 1
                self.started.set()
                self.release.wait()
                return [object()]

        async def exercise() -> None:
            catalogue = Catalogue()
            interface = ConsoleInterface(catalogue)
            first = asyncio.create_task(interface.refresh_catalogue())
            await asyncio.to_thread(catalogue.started.wait)
            second = asyncio.create_task(interface.refresh_catalogue())
            await asyncio.sleep(0)
            self.assertEqual(catalogue.calls, 1)
            catalogue.release.set()
            self.assertEqual(await asyncio.gather(first, second), [1, 1])
            self.assertEqual(catalogue.calls, 1)

        asyncio.run(exercise())

    def test_legacy_steam_credentials_and_steamcmd_backend_are_not_registered(self) -> None:
        interface = ConsoleInterface(SimpleNamespace())
        self.assertFalse(interface._plugins.for_plugin("steam-aurelia", "authentication"))
        self.assertFalse(interface._plugins.for_plugin("steam-aurelia", "acquisition"))

    def test_utilities_projection_and_launch_use_installed_non_game_flatpak(self) -> None:
        class Adapter:
            provider_id = "flatpak"

            async def reconcile(self):
                return (
                    FlatpakApplication(
                        "org.example.Graphics", "Example Graphics", summary="Image editor",
                        branch="stable", arch="x86_64", installed=True,
                        categories=("Graphics",), component_type="desktop-application",
                        description="Layered editing.", developer="Example Studio",
                        screenshots=({"url": "https://example.test/one.png", "caption": "Workspace"},),
                    ),
                    FlatpakApplication("org.example.Game", "Example Game", installed=True,
                                       categories=("Game",), component_type="desktop-application"),
                    FlatpakApplication("org.example.Unknown", "Unknown", installed=True),
                )

            def launch_command(self, application_ref):
                return ["flatpak", "run", application_ref]

        class Session:
            def __init__(self):
                self.context = ""
                self.launch = None

            async def call_set_delegated_launch_context(self, context):
                self.context = context

            async def call_request_utility_launch(self, utility_id, title, command, timeout_ms):
                self.launch = (utility_id, title, command, timeout_ms)
                return "launch-token"

        async def exercise():
            session = Session()
            interface = ConsoleInterface(SimpleNamespace(), sessiond=session)
            interface._plugins = SimpleNamespace(with_capability=lambda _capability: [Adapter()])
            rows = json.loads(await interface.ListUtilities.__wrapped__(interface))
            self.assertEqual([row["application_id"] for row in rows], ["org.example.Graphics"])
            self.assertEqual(rows[0]["classification"], "utility")
            self.assertEqual(rows[0]["developer"], "Example Studio")
            self.assertEqual(rows[0]["screenshots"][0]["url"], "https://example.test/one.png")
            ref = "app/org.example.Graphics/x86_64/stable"
            token = await interface.LaunchUtility.__wrapped__(interface, ref, 15000)
            self.assertEqual(token, "launch-token")
            self.assertEqual(session.launch, (
                "utility:flatpak:org.example.Graphics", "Example Graphics",
                ["flatpak", "run", ref], 15000))

        import json
        asyncio.run(exercise())


if __name__ == "__main__":
    unittest.main()
