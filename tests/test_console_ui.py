import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
QML = (ROOT / "ui" / "ConsoleShell.qml").read_text()
SHELL_PROFILE = (ROOT / "config" / "inputplumber" / "profiles" / "shell.yaml").read_text()


class ConsoleUiTests(unittest.TestCase):
    def test_qml_preserves_card_to_space_shell_interaction(self) -> None:
        self.assertIn('title: "Recent"', QML)
        self.assertIn("property bool expanded: false", QML)
        self.assertIn("function activateCard(index)", QML)
        self.assertIn("function goBack()", QML)
        self.assertIn('text: "Expanded space proof"', QML)
        self.assertNotIn("/dev/input", QML)

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
