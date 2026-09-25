from pathlib import Path
import unittest


class GuideChordSourceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.source = (Path(__file__).parents[1] / "native/lulu-shell.cpp").read_text()

    def test_guide_is_pending_until_release(self) -> None:
        self.assertIn("pendingGuide_ = true", self.source)
        self.assertIn("value == 0.0 && pendingGuide_", self.source)
        self.assertIn("startGuide();", self.source)

    def test_pending_guide_context_down_consumes_chord_once(self) -> None:
        chord = 'event == QStringLiteral("ui_context") && pendingGuide_'
        self.assertIn(chord, self.source)
        self.assertIn("guideChordConsumed_ = true", self.source)
        self.assertIn('consoled.asyncCall(QStringLiteral("ShowKeyboard"))', self.source)
        self.assertIn('if (value == 0.0)\n                return;', self.source)
        self.assertNotIn('pendingGuide_ && event.gbutton.button == SDL_GAMEPAD_BUTTON_WEST', self.source)

    def test_pending_guide_sequence_suppresses_x_and_guide_release(self) -> None:
        chord = 'event == QStringLiteral("ui_context") && pendingGuide_'
        guide_release = 'if (value == 0.0 && pendingGuide_ && compositePath == guideOwnerComposite_)'
        self.assertLess(self.source.index(chord), self.source.index(guide_release))
        self.assertIn('if (!chordConsumed) {\n                    startGuide();', self.source)
        self.assertIn('else {\n                    guideOwnerComposite_.clear();', self.source)

    def test_context_is_not_forwarded_as_guide_input_without_pending_guide(self) -> None:
        forwarding = self.source[self.source.index('if (guideProcess_ && compositePath == guideOwnerComposite_'):]
        self.assertNotIn('QStringLiteral("ui_context")', forwarding[:500])

    def test_unrelated_input_does_not_consume_pending_guide(self) -> None:
        chord = 'event == QStringLiteral("ui_context") && pendingGuide_'
        guide = 'if (event == QStringLiteral("ui_guide"))'
        self.assertLess(self.source.index(chord), self.source.index(guide))

    def test_gamepad_osk_does_not_own_guide_chord(self) -> None:
        config = (Path.home() / ".config/gamepad-osk/config")
        if config.is_file():
            self.assertNotIn("toggle_combo = guide+", config.read_text())

    def test_guide_forwards_explicit_edges(self) -> None:
        self.assertIn('" edge=" + edge', self.source)
        self.assertIn("value != 1.0 && value != 0.0", self.source)

    def test_duplicate_opening_guide_edges_cannot_close_new_menu(self) -> None:
        guard = "QDateTime::currentMSecsSinceEpoch() < guideIgnoreInputUntilMs_"
        self.assertIn(guard, self.source)
        self.assertIn("guideIgnoreInputUntilMs_ = QDateTime::currentMSecsSinceEpoch() + 350", self.source)
        self.assertLess(self.source.index(guard), self.source.index('guideProcess_->write("ui_guide edge=down\\n")'))

    def test_guide_release_path_resets_on_target_loss(self) -> None:
        self.assertIn('guideProcess_->write("reset_edges\\n")', self.source)


if __name__ == "__main__":
    unittest.main()
