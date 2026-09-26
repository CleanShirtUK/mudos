from pathlib import Path
import unittest


ROOT = Path(__file__).parents[1]


class BrowserStoreLifecycleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.shell = (ROOT / "ui" / "ConsoleShell.qml").read_text()
        self.store = (ROOT / "ui" / "StoreHome.qml").read_text()
        self.browser = (ROOT / "ui" / "MudosBrowser.qml").read_text()
        self.session = (ROOT / "src/lulu/sessiond.py").read_text()
        self.consoled = (ROOT / "src/lulu/consoled.py").read_text()

    def test_home_store_cards_are_not_catalogue_cards(self) -> None:
        self.assertIn('title: "Installable"', self.store)
        self.assertIn('title: "Add New Store"', self.store)
        self.assertIn("function homeCards()", self.store)
        self.assertIn("pluginStores", self.store)
        self.assertNotIn('id: "steam", title: "Steam"', self.store)
        self.assertNotIn('id: "questarr", title: "Questarr"', self.store)
        self.assertNotIn('scope === "stores"', self.store)

    def test_browser_enters_and_restores_compatibility_surface(self) -> None:
        self.assertIn('"/browser-surface/active"', self.shell)
        self.assertIn('"/input-mode/compat"', self.shell)
        self.assertIn('"/input-mode/" + encodeURIComponent(browserPriorInputMode)', self.shell)
        self.assertIn('SetDelegatedSurface', self.session)
        opening = self.shell.split("function openBrowser", 1)[1].split("function launchHomeStore", 1)[0]
        self.assertLess(opening.index('request("/input-mode/compat"'), opening.index("browserVisible = true"))
        self.assertIn('JSON.stringify({active: false})', opening)
        self.assertIn("browserInputModePending = false", opening)

    def test_browser_quit_is_guide_owned_and_history_back_is_contextual(self) -> None:
        self.assertIn('browser-quit', self.consoled)
        self.assertIn('delegated_surface", "")) == "browser"', self.consoled)
        self.assertIn("goBackOrClose", self.shell)
        self.assertIn("if (view.canGoBack)", self.browser)
        self.assertIn("releasePage", self.browser)

    def test_external_browser_navigation_uses_generic_handoff_bridge(self) -> None:
        self.assertIn("externalNavigationRequested", self.browser)
        self.assertIn("onNavigationRequested", self.browser)
        self.assertIn('request("/browser-handoff"', self.shell)
        self.assertNotIn("flatpak+https", self.browser)
        self.assertNotIn("flathub", self.browser)

    def test_global_downloads_suspends_and_resumes_browser(self) -> None:
        self.assertIn("browserSuspended = true", self.shell)
        self.assertIn("resumeBrowserSession()", self.shell)
        self.assertIn('contexts = ["shell", "game", "standalone", "store", "downloads", "install", "browser"]',
                      (ROOT / "config/guide/mudos.toml").read_text())

    def test_generic_browser_osk_bridge_handles_editable_types_and_restores_focus(self) -> None:
        browser = (ROOT / "ui" / "MudosBrowser.qml").read_text()
        shell = (ROOT / "ui" / "ConsoleShell.qml").read_text()
        fixture = (ROOT / "tests/fixtures/browser-input.html").read_text()
        self.assertIn("editableFocused", browser)
        self.assertIn("t==='textarea'", browser)
        self.assertIn("type==='password'", browser)
        self.assertIn("isContentEditable", browser)
        self.assertIn("window.__mudosFocusedEditable", browser)
        self.assertIn("commitText", browser)
        self.assertIn("editableCaptureLocked", browser)
        self.assertIn("lockEditable", browser)
        self.assertIn("dispatchEvent(new Event('input'", browser)
        self.assertIn("browserTextInputPending", shell)
        self.assertIn("cancelBrowserTextInput", shell)
        self.assertIn("onEditableFocused", shell)
        self.assertIn("multiline: field.type === \"textarea\"", shell)
        self.assertIn("credentialSubmitInFlight", shell)
        self.assertIn("Keys.onPressed", shell)
        self.assertIn('type="password"', fixture)
        self.assertIn("<textarea", fixture)

    def test_browser_password_value_is_not_read_into_mudos_osk(self) -> None:
        browser = (ROOT / "ui" / "MudosBrowser.qml").read_text()
        shell = (ROOT / "ui" / "ConsoleShell.qml").read_text()
        self.assertIn("value:type==='password'?'':", browser)
        self.assertIn('credentialValue = field.secret ? ""', shell)
        self.assertNotIn("console.log(credentialValue", shell)

    def test_builtin_only_trust_is_not_inferred_from_url(self) -> None:
        shell = (ROOT / "ui" / "ConsoleShell.qml").read_text()
        browser = (ROOT / "ui" / "MudosBrowser.qml").read_text()
        self.assertIn('id === "questarr" ? "questarr"', shell)
        self.assertIn('"http://127.0.0.1:5000"', shell)
        self.assertIn("location.origin!==origin", browser)
        self.assertIn('browserTrustProfile = trustProfile || ""', shell)

    def test_trusted_login_capture_and_autofill_are_not_osk_paths(self) -> None:
        shell = (ROOT / "ui" / "ConsoleShell.qml").read_text()
        browser = (ROOT / "ui" / "MudosBrowser.qml").read_text()
        self.assertIn("trustedLoginForm", browser)
        self.assertIn("trustedCredentialsCaptured", browser)
        self.assertIn("applyTrustedCredentials", browser)
        self.assertIn("/web-credentials/get", shell)
        self.assertIn("/web-credentials/save", shell)
        self.assertNotIn("/keyboard/show", browser)

    def test_trusted_capture_handles_spa_submit_and_success_transition(self) -> None:
        browser = (ROOT / "ui" / "MudosBrowser.qml").read_text()
        self.assertIn("document.addEventListener('submit'", browser)
        self.assertIn("document.addEventListener('click'", browser)
        self.assertIn("!p&&!window.__mudosCredentialCaptureSent", browser)
        self.assertIn("remember()", browser)

    def test_trusted_autofill_uses_react_compatible_native_events_and_retries(self) -> None:
        browser = (ROOT / "ui" / "MudosBrowser.qml").read_text()
        self.assertIn("Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value')", browser)
        self.assertIn("new InputEvent('input'", browser)
        self.assertIn("composed:true", browser)
        self.assertIn("window.__mudosAutofillRequested=false", browser)

    def test_same_origin_spa_navigation_preserves_capture_candidate(self) -> None:
        browser = (ROOT / "ui" / "MudosBrowser.qml").read_text()
        self.assertIn("sameTrustedOrigin", browser)
        self.assertIn("Preserve the", browser)
        self.assertIn("new URL(url.toString())).origin === root.trustedOrigin", browser)

    def test_text_entry_presentation_keeps_attached_targets_visible(self) -> None:
        shell = (ROOT / "ui" / "ConsoleShell.qml").read_text()
        self.assertIn('presentation: "attached"', shell)
        self.assertIn('root.credentialRequest.presentation !== "attached"', shell)
        self.assertIn('root.credentialRequest.presentation === "attached"', shell)

    def test_keyboard_only_enter_escape_drive_shared_request_actions(self) -> None:
        shell = (ROOT / "ui" / "ConsoleShell.qml").read_text()
        self.assertIn("event.key === Qt.Key_Escape", shell)
        self.assertIn("root.submitCredential(true)", shell)
        self.assertIn('keyboard: KeyEnter',
                      (ROOT / "config/inputplumber/profiles/osk.yaml").read_text())

    def test_questarr_capture_does_not_blindly_trigger_reconciliation(self) -> None:
        consoled = (ROOT / "src/lulu/consoled.py").read_text()
        self.assertIn('self.web_credentials.save(profile_id, origin, username, password)', consoled)
        self.assertNotIn('"lulu-questarr-reconcile.service"', consoled)
        reconciler = (ROOT / "scripts/reconcile-questarr.py").read_text()
        self.assertIn('"questarr" not in setup.get("selected_providers", [])', reconciler)
        self.assertIn('readiness.get("status") != "ready"', reconciler)

    def test_browser_osk_cancel_and_repeated_activation_are_explicit(self) -> None:
        browser = (ROOT / "ui" / "MudosBrowser.qml").read_text()
        shell = (ROOT / "ui" / "ConsoleShell.qml").read_text()
        self.assertIn("root.request(\"/credential/cancel\"", shell)
        self.assertIn("browserSurface.clearEditableState()", shell)
        self.assertIn("browserSurface.forceActiveFocus()", shell)
        self.assertIn("running: root.visible", browser)
        self.assertIn("!root.credentialRequest.multiline", shell)
        self.assertIn("TextArea", shell)

    def test_idle_keyboard_state_can_initialize_shared_overlay(self) -> None:
        shell = (ROOT / "ui" / "ConsoleShell.qml").read_text()
        credential = (ROOT / "src" / "lulu" / "credential.py").read_text()
        self.assertIn("import QtQuick.Controls", shell)
        self.assertIn('root.credentialRequest.status === "requested"', shell)
        self.assertIn("multiline: bool = False", credential)
        self.assertIn('else {"status": "idle"}', credential)
        self.assertIn("!!root.credentialRequest.multiline", shell)

    def test_browser_profile_is_named_and_persistent(self) -> None:
        browser = (ROOT / "ui" / "MudosBrowser.qml").read_text()
        architecture = (ROOT / "docs" / "browser-store-architecture.md").read_text()
        self.assertIn('storageName: "mudos-browser"', browser)
        self.assertIn('persistentStoragePath:', browser)
        self.assertIn("ForcePersistentCookies", browser)
        self.assertIn("persistent profile", architecture)

    def test_trusted_web_bridge_rejects_page_origins(self) -> None:
        bridge = (ROOT / "scripts" / "console-ui-bridge.py").read_text()
        self.assertIn("web credential bridge is not available to page origins", bridge)
        self.assertIn('request_origin not in', bridge)


if __name__ == "__main__":
    unittest.main()
