from pathlib import Path
import asyncio
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from lulu.consoled import ConsoleCatalog, ConsoleInterface

ROOT = Path(__file__).parents[1]


class ConsoledStartupTests(unittest.TestCase):
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

    def test_steam_authentication_uses_shell_credential_broker(self) -> None:
        interface = ConsoleInterface(SimpleNamespace())
        auth = interface._plugins.for_plugin("steam", "authentication")
        self.assertTrue(auth)
        self.assertIs(auth[0].acquisition.credentials, interface.credentials)


if __name__ == "__main__":
    unittest.main()
