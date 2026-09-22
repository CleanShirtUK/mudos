from pathlib import Path
import unittest


ROOT = Path(__file__).parents[1]


class BrowserExplicitActivationTests(unittest.TestCase):
    def test_focused_target_request_is_explicit_and_generic(self) -> None:
        browser = (ROOT / "ui/MudosBrowser.qml").read_text()
        self.assertIn("function requestTextEntryForFocusedElement()", browser)
        self.assertIn("signal editableTargetUnavailable()", browser)
        self.assertIn("window.__mudosFocusedEditable=e", browser)
        self.assertIn("if(!editable)return null", browser)

    def test_programmatic_dom_events_cannot_mark_activation(self) -> None:
        browser = (ROOT / "ui/MudosBrowser.qml").read_text()
        self.assertIn("if(!ev.isTrusted)return", browser)
        self.assertIn("while(e&&!isEditable(e))e=e.parentElement", browser)
        self.assertIn("__mudosExplicitEditableActivation!==e", browser)

    def test_guide_shortcut_reaches_browser_focused_target(self) -> None:
        shell = (ROOT / "ui/ConsoleShell.qml").read_text()
        native = (ROOT / "native/lulu-shell.cpp").read_text()
        self.assertIn("textEntryShortcutSerial", native)
        self.assertIn("browserTextEntryShortcutTimer", shell)
        self.assertIn("browserSurface.requestTextEntryForFocusedElement()", shell)
        self.assertIn("if (root.browserVisible)\n                    browserSurface.requestTextEntryForFocusedElement()", shell)

    def test_repeated_shortcut_uses_one_serial_and_shared_request_guard(self) -> None:
        shell = (ROOT / "ui/ConsoleShell.qml").read_text()
        self.assertIn("serial === root.lastBrowserTextEntryShortcut", shell)
        self.assertIn("credentialRequest.status === \"requested\"", shell)
