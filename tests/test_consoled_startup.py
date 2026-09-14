from pathlib import Path
import asyncio
import threading
import unittest

from lulu.consoled import ConsoleInterface

ROOT = Path(__file__).parents[1]


class ConsoledStartupTests(unittest.TestCase):
    def test_dbus_name_is_published_before_provider_refresh(self) -> None:
        source = (ROOT / "src/lulu/consoled.py").read_text()
        serve = source[source.index("async def serve()") :]
        self.assertLess(serve.index("await bus.request_name(BUS_NAME)"),
                         serve.index("await interface.refresh_catalogue()"))

    def test_provider_refresh_is_background_work(self) -> None:
        source = (ROOT / "src/lulu/consoled.py").read_text()
        self.assertIn('asyncio.to_thread(self.catalogue.refresh)', source)
        self.assertIn('ROMM_SYNC_INTERVAL = 15 * 60', source)

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


if __name__ == "__main__":
    unittest.main()
