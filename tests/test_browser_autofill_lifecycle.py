from pathlib import Path
import unittest


ROOT = Path(__file__).parents[1]


class BrowserAutofillLifecycleTests(unittest.TestCase):
    def test_autofill_does_not_focus_or_activate_editable_bridge(self) -> None:
        browser = (ROOT / "ui/MudosBrowser.qml").read_text()
        autofill = browser[browser.index("function applyTrustedCredentials"):browser.index("function clearTrustedCredentialCandidate")]
        self.assertNotIn("u.focus()", autofill)
        self.assertIn("input", autofill)
        self.assertIn("change", autofill)
        self.assertIn("__mudosExplicitEditableActivation", browser)

    def test_editable_bridge_requires_explicit_activation(self) -> None:
        browser = (ROOT / "ui/MudosBrowser.qml").read_text()
        self.assertIn("pointerdown", browser)
        self.assertIn("if(isEditable(e))window.__mudosExplicitEditableActivation=e", browser)
        self.assertIn("__mudosExplicitEditableActivation!==e", browser)
        self.assertIn("window.__mudosExplicitEditableActivation=null", browser)

    def test_text_hints_are_prompted_request_only(self) -> None:
        shell = (ROOT / "ui/ConsoleShell.qml").read_text()
        self.assertIn('visible: root.credentialRequest.presentation !== "attached"', shell)
        self.assertIn('visible: root.credentialRequest.presentation === "prompted"', shell)
        self.assertIn("credentialTextArea.forceActiveFocus()", shell)

    def test_transmission_gets_only_acquisition_group_access(self) -> None:
        script = (ROOT / "scripts/provision-transmission.sh").read_text()
        self.assertIn('usermod --append --groups "$lulu_user" "$user"', script)
        self.assertIn("SupplementaryGroups=$lulu_user", script)
        self.assertNotIn("chmod -R 777", script)
