import json
import unittest
from pathlib import Path

from lulu.contracts import InputMode, LaunchDescriptor, Presentation, SessionClassification

ROOT = Path(__file__).resolve().parents[1]


class DesktopModeContractTests(unittest.TestCase):
    def test_system_card_routes_to_sessiond_bridge(self):
        shell = (ROOT / "ui/ConsoleShell.qml").read_text()
        catalog = (ROOT / "ui/MudosAssetCatalog.js").read_text()
        self.assertIn('["Settings", "Utilities", "Desktop Mode"]', shell)
        self.assertIn('request("/desktop/enter", "POST"', shell)
        self.assertIn('"Desktop Mode": "desktop"', catalog)

    def test_desktop_descriptor_is_explicit_and_compat(self):
        descriptor = LaunchDescriptor("mudos-desktop", SessionClassification.DESKTOP,
                                      "Desktop Mode", Presentation.FOREIGN_UI)
        self.assertEqual(descriptor.classification.value, "desktop")
        self.assertEqual(descriptor.input_mode, InputMode.COMPAT)
        sessiond = (ROOT / "src/lulu/sessiond.py").read_text()
        self.assertIn("async def RequestDesktopLaunch", sessiond)
        self.assertIn("SessionClassification.DESKTOP", sessiond)

    def test_wrapper_is_nested_and_preserves_user_xdg_and_bus(self):
        wrapper = (ROOT / "scripts/mudos-desktop-session").read_text()
        self.assertIn('outer="${DISPLAY:-:0}"', wrapper)
        self.assertIn('Xephyr "$display"', wrapper)
        self.assertIn('openbox --config-file', wrapper)
        self.assertIn('XAUTHORITY="$auth"', wrapper)
        self.assertNotIn("-ac", wrapper)
        self.assertNotIn("xhost", wrapper)
        self.assertNotIn("XDG_CONFIG_HOME=", wrapper)
        self.assertNotRegex(wrapper, r"\b(HOME|XDG_DATA_HOME|XDG_CACHE_HOME|DBUS_SESSION_BUS_ADDRESS|PIPEWIRE_RUNTIME_DIR)=")
        self.assertIn('"${XDG_RUNTIME_DIR:?}/mudos-desktop"', wrapper)
        self.assertIn("panel_items = PPPPTSC", wrapper)
        self.assertIn("taskbar_mode = single_desktop", wrapper)
        self.assertIn("clock_format =", wrapper)
        self.assertIn("jgmenu_run apps", wrapper)
        self.assertNotIn("systemctl stop", wrapper)

    def test_panel_theme_and_allowlisted_power_boundary(self):
        wrapper = (ROOT / "scripts/mudos-desktop-session").read_text()
        control = (ROOT / "scripts/mudos-desktop-sessionctl").read_text()
        self.assertIn("mudos-desktop-theme", wrapper)
        for role in ("surface", "border", "primaryText", "secondaryText", "accent", "radius"):
            self.assertIn(role, wrapper)
        for item in ("Restart", "Shutdown", "Exit Desktop Mode", "Confirm Restart", "Confirm Shutdown"):
            self.assertIn(item, wrapper)
        self.assertNotRegex(wrapper, r"(?i)log ?out|switch user|lock user session|new session")
        self.assertIn('{"exit", "reboot", "shutdown"}', control)
        self.assertIn("call_quit_active_session", control)
        self.assertIn("call_reboot", control)
        self.assertIn("call_shutdown", control)

    def test_desktop_utility_routes_only_to_mudos_apis(self):
        utility = (ROOT / "scripts/mudos-desktop-settings").read_text()
        self.assertIn('api("/network")', utility)
        self.assertIn('api("/settings?category=Bluetooth")', utility)
        self.assertIn('"/bluetooth/action"', utility)
        self.assertNotRegex(utility, r"(?i)nmcli|bluetoothctl|blueman")

    def test_package_and_release_own_desktop_runtime(self):
        ownership = json.loads((ROOT / "packaging/mudos-ownership.json").read_text())
        packages = ownership["shared_dependencies"]["packages"]
        for package in ("openbox", "tint2", "jgmenu", "xorg-server-xephyr", "xorg-xauth"):
            self.assertIn(package, packages)
        release = (ROOT / "scripts/release.py").read_text()
        for file_name in ("mudos-desktop-session", "mudos-desktop-sessionctl", "mudos-desktop-theme"):
            self.assertIn(file_name, release)


if __name__ == "__main__":
    unittest.main()
