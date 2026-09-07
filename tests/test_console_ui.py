import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
QML = (ROOT / "ui" / "ConsoleShell.qml").read_text()
SHELL_PROFILE = (ROOT / "config" / "inputplumber" / "profiles" / "shell.yaml").read_text()


class ConsoleUiTests(unittest.TestCase):
    def test_qml_preserves_card_to_space_shell_interaction(self) -> None:
        self.assertIn('property var domains: ["Recent", "Library", "Store", "System"]', QML)
        self.assertIn('readonly property string apiUrl:', QML)
        self.assertIn("function activate()", QML)
        self.assertIn("function moveDomain(delta)", QML)
        self.assertIn('text: "Store is unavailable"', QML)
        self.assertIn('text: "System space is not implemented"', QML)
        self.assertNotIn("/dev/input", QML)
        self.assertNotIn("Social", QML)

    def test_shell_profile_routes_semantic_events_to_qt_keys(self) -> None:
        for button, key in (
            ("DPadUp", "KeyUp"),
            ("DPadDown", "KeyDown"),
            ("DPadLeft", "KeyLeft"),
            ("DPadRight", "KeyRight"),
            ("South", "KeyEnter"),
            ("East", "KeyBackspace"),
        ):
            self.assertIn(f"button: {button}", SHELL_PROFILE)
            self.assertIn(f"keyboard: {key}", SHELL_PROFILE)


if __name__ == "__main__":
    unittest.main()
