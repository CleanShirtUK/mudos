import importlib.util
from pathlib import Path
import unittest


ROOT = Path(__file__).parents[1]
SPEC = importlib.util.spec_from_file_location("console_ui_bridge", ROOT / "scripts" / "console-ui-bridge.py")
BRIDGE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(BRIDGE)


class ConsoleBridgeTests(unittest.TestCase):
    def test_launch_path_decodes_qml_encoded_game_id(self) -> None:
        path = "/launch/steam%3A220780"
        self.assertEqual(BRIDGE.unquote(path.removeprefix("/launch/")), "steam:220780")

    def test_launch_call_has_a_provider_watchdog_timeout(self) -> None:
        source = (ROOT / "scripts" / "console-ui-bridge.py").read_text()
        self.assertIn("timeout=15", source)
        self.assertIn("str(error) or type(error).__name__", source)


if __name__ == "__main__":
    unittest.main()
