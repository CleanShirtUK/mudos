from pathlib import Path
import unittest


ROOT = Path(__file__).parents[1]


class ConsoledStartupTests(unittest.TestCase):
    def test_dbus_name_is_published_before_provider_refresh(self) -> None:
        source = (ROOT / "src/lulu/consoled.py").read_text()
        serve = source[source.index("async def serve()") :]
        self.assertLess(serve.index("await bus.request_name(BUS_NAME)"),
                         serve.index("asyncio.to_thread(catalogue.refresh)"))

    def test_provider_refresh_is_background_work(self) -> None:
        source = (ROOT / "src/lulu/consoled.py").read_text()
        self.assertIn('asyncio.to_thread(catalogue.refresh)', source)
        self.assertIn('ROMM_SYNC_INTERVAL = 15 * 60', source)


if __name__ == "__main__":
    unittest.main()
