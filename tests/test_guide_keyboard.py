from pathlib import Path
import unittest


ROOT = Path(__file__).parents[1]


class GuideKeyboardRecoveryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.shell = (ROOT / "native/lulu-shell.cpp").read_text()
        self.guide = (ROOT / "native/mudos-guide.cpp").read_text()

    def test_global_ctrl_alt_g_is_owned_by_the_session_shell(self) -> None:
        self.assertIn("XCB_MOD_MASK_CONTROL | XCB_MOD_MASK_1", self.shell)
        self.assertIn("XK_g", self.shell)
        self.assertIn("globalGuideKeycode_", self.shell)
        self.assertIn("startGuide();", self.shell)

    def test_shortcut_does_not_depend_on_controller_or_owner(self) -> None:
        shortcut = self.shell[self.shell.index("if (key->detail == globalGuideKeycode_"):]
        self.assertNotIn("navigationPlayer_", shortcut[:300])
        self.assertNotIn("guideOwnerComposite_", shortcut[:300])
        self.assertIn("if (guideProcess_)", self.shell[self.shell.index("bool startGuide()"):])

    def test_guide_grabs_keyboard_and_consumes_navigation_keys(self) -> None:
        self.assertIn("captureGuideKeyboard", self.shell)
        self.assertIn("xcb_grab_key_checked", self.shell)
        self.assertIn("releaseGuideKeyboard", self.shell)
        for key in ("XK_Up", "XK_Down", "XK_Left", "XK_Right",
                    "XK_Return", "XK_KP_Enter", "XK_Escape", "XK_BackSpace"):
            self.assertIn(key, self.shell)

    def test_shell_global_boundary_translates_recovery_keys_to_guide_ipc(self) -> None:
        self.assertIn("sendGuideKeyboardAction", self.shell)
        self.assertIn('guideProcess_->write(action.toUtf8() + " edge=down\\n")', self.shell)
        self.assertIn('guideProcess_->write(action.toUtf8() + " edge=up\\n")', self.shell)
        self.assertIn("guideKeyboardActions_.contains(key->detail)", self.shell)

    def test_recovery_keys_are_not_forwarded_when_guide_is_inactive(self) -> None:
        key_path = self.shell[self.shell.index("else if (guideProcess_ && guideKeyboardActions_"):]
        self.assertIn("guideProcess_ &&", key_path)
        self.assertIn("sendGuideKeyboardAction", key_path)

    def test_guide_process_death_releases_recovery_grabs(self) -> None:
        self.assertIn("guideProcess_, &QProcess::finished", self.shell)
        self.assertIn("finishGuide();", self.shell)
        finish = self.shell[self.shell.index("void finishGuide()"):self.shell.index("bool startGuide()")]
        self.assertIn("restoreInput();", finish)
        self.assertIn("releaseGuideKeyboard();", self.shell[self.shell.index("void restoreInput()"):])

    def test_keyboard_events_use_the_existing_guide_action_boundary(self) -> None:
        self.assertIn('"ui_up"', self.shell)
        self.assertIn('"ui_down"', self.shell)
        self.assertIn('"ui_accept"', self.shell)
        self.assertIn('"ui_back"', self.shell)
        self.assertIn("handleCommand", self.guide)

    def test_b_dismisses_only_the_guide_surface_and_quit_never_uses_window_owner_pid(self) -> None:
        back = self.guide.split('else if (action == QStringLiteral("ui_back"))', 1)[1].split(
            'else if (action == QStringLiteral("ui_guide"))', 1
        )[0]
        self.assertIn("QCoreApplication::quit();", back)
        self.assertNotIn("executeAction", back)
        self.assertIn('target == "process-group-terminate"', self.guide)
        self.assertIn("Never signal the PID or", self.guide)
        self.assertIn("call_quit_active_session", (ROOT / "src/lulu/consoled.py").read_text())
        compat = (ROOT / "config/inputplumber/profiles/compat.yaml").read_text()
        b_mapping = compat.split("- name: B escape", 1)[1].split("- name: Menu enter", 1)[0]
        self.assertIn("button: East", b_mapping)
        self.assertIn("dbus: ui_back", b_mapping)

    def test_controller_guide_boundary_remains_present(self) -> None:
        self.assertIn('event == QStringLiteral("ui_guide")', self.shell)
        self.assertIn('guideProcess_->write("ui_guide edge=down\\n")', self.shell)
        self.assertIn("SDL_GAMEPAD_BUTTON", self.shell)


if __name__ == "__main__":
    unittest.main()
