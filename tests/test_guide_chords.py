from pathlib import Path
import unittest


class GuideChordSourceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.source = (Path(__file__).parents[1] / "native/lulu-shell.cpp").read_text()

    def test_guide_is_pending_until_release(self) -> None:
        self.assertIn("pendingGuide_ = true", self.source)
        self.assertIn("value == 0.0 && pendingGuide_", self.source)
        self.assertIn("startGuide();", self.source)

    def test_x_consumes_guide_chord_and_calls_keyboard_boundary(self) -> None:
        self.assertIn("SDL_GAMEPAD_BUTTON_WEST", self.source)
        self.assertIn("guideChordConsumed_ = true", self.source)
        self.assertIn('consoled.call(QStringLiteral("ShowKeyboard"))', self.source)
        self.assertIn("continue;", self.source)

    def test_gamepad_osk_does_not_own_guide_chord(self) -> None:
        config = (Path.home() / ".config/gamepad-osk/config")
        if config.is_file():
            self.assertNotIn("toggle_combo = guide+", config.read_text())

    def test_guide_forwards_explicit_edges(self) -> None:
        self.assertIn('" edge=" + edge', self.source)
        self.assertIn("value != 1.0 && value != 0.0", self.source)

    def test_guide_release_path_resets_on_target_loss(self) -> None:
        self.assertIn('guideProcess_->write("reset_edges\\n")', self.source)


if __name__ == "__main__":
    unittest.main()
