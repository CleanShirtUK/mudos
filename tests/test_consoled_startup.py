from pathlib import Path
import unittest


ROOT = Path(__file__).parents[1]


class ConsoledStartupTests(unittest.TestCase):
    def test_dbus_name_is_published_before_provider_refresh(self) -> None:
        source = (ROOT / "src/lulu/consoled.py").read_text()
        serve = source[source.index("async def serve()") :]
        self.assertLess(serve.index("await bus.request_name(BUS_NAME)"),
                        serve.index("catalogue.refresh()"))


if __name__ == "__main__":
    unittest.main()
