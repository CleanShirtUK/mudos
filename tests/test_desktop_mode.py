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
        self.assertIn("/etc/xdg/tint2/tint2rc", wrapper)
        self.assertIn("panel_items = PPPPTSC", wrapper)
        self.assertIn("time1_format =", wrapper)
        self.assertIn("jgmenu_run apps", wrapper)
        self.assertNotIn("systemctl stop", wrapper)

    def test_wallpaper_reuses_theme_manager_shader_contract(self):
        wallpaper = (ROOT / "ui/DesktopWallpaper.qml").read_text()
        shared = (ROOT / "ui/OrbitRenderSource.qml").read_text()
        host = (ROOT / "native/mudos-desktop-wallpaper.cpp").read_text()
        manager = (ROOT / "native/theme-manager.cpp").read_text()
        self.assertIn('import "."', wallpaper)
        self.assertIn("OrbitRenderSource", wallpaper)
        self.assertIn('settings.value("appearance/theme", "modern")', manager)
        self.assertIn("mudosTheme.wallpaperShader", shared)
        self.assertIn("mudosTheme.wallpaper", shared)
        for uniform in ("u_resolution", "u_origin", "u_canvas", "u_time", "u_brightness",
                        "u_visibility", "u_primary", "u_secondary", "u_surface", "u_error"):
            self.assertIn(uniform, shared)
        self.assertIn('wallpaper.frag.qsb', (ROOT / "themes/modern/theme.json").read_text())
        self.assertFalse((ROOT / "themes/modern/wallpaper/wallpaper.frag").exists())
        self.assertIn("_NET_WM_WINDOW_TYPE_DESKTOP", host)
        self.assertIn("_NET_WM_STATE_SKIP_TASKBAR", host)
        self.assertIn("_NET_WM_STATE_SKIP_PAGER", host)
        self.assertIn("_NET_WM_STATE_BELOW", host)
        self.assertIn("WindowDoesNotAcceptFocus", host)
        self.assertNotRegex(host + wallpaper, r'(?i)(theme|activeId).*==.*("modern"|"95"|"metalheart"|"frutiger-aero")')

    def test_wrapper_orders_readiness_wallpaper_and_panel_and_isolates_failures(self):
        wrapper = (ROOT / "scripts/mudos-desktop-session").read_text()
        self.assertLess(wrapper.index('xdpyinfo >/dev/null\n'), wrapper.index('openbox --config-file'))
        self.assertLess(wrapper.index("Openbox did not become ready"), wrapper.index('wallpaper=$!'))
        self.assertLess(wrapper.index('wallpaper=$!'), wrapper.index('tint2 -c "$config/tint2/tint2rc"'))
        self.assertIn('DISPLAY="$display" XAUTHORITY="$auth"', wrapper)
        self.assertIn("QT_QPA_PLATFORM=xcb", wrapper)
        self.assertIn('logs/tint2.log', wrapper)
        self.assertIn('logs/wallpaper.log', wrapper)
        self.assertIn("retrying once", wrapper)
        self.assertIn("desktop remains available", wrapper)
        self.assertIn("wallpaper renderer exited", wrapper)
        self.assertIn('children+=("$wallpaper")', wrapper)
        self.assertIn('children+=("$panel")', wrapper)
        self.assertIn('for pid in "${children[@]}"; do kill "$pid"', wrapper)
        self.assertIn("panel_restarted=0", wrapper)
        self.assertIn("panel_restarted=1", wrapper)

    def test_tint2_generated_options_are_valid_and_menu_is_allowlisted(self):
        wrapper = (ROOT / "scripts/mudos-desktop-session").read_text()
        for valid in ("task_font =", "task_font_color =", "time1_format =", "time1_font =",
                      "button_font_color =", "panel_items = PPPPTSC"):
            self.assertIn(valid, wrapper)
        self.assertIn("/etc/xdg/tint2/tint2rc", wrapper)
        self.assertIn("panel_size = 100% 36", wrapper)
        for invalid in (r"(?m)^font =", r"(?m)^font_color =", "clock_format =", "button_text_color ="):
            self.assertNotRegex(wrapper, invalid)
        self.assertEqual(wrapper.count("panel_items = PPPPTSC"), 1)
        self.assertIn("jgmenu_run apps", wrapper)
        power = wrapper.split("(root/'power.csv').write_text", 1)[1].split("(root/'jgmenurc')", 1)[0]
        self.assertIn("Restart,", power)
        self.assertIn("Shutdown,", power)
        self.assertIn("Exit Desktop Mode", power)
        self.assertNotRegex(power, r"(?i)log ?out|switch user")

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
        for package in ("openbox", "tint2", "jgmenu", "xorg-server-xephyr", "xorg-xauth",
                        "xorg-xsetroot", "xorg-xdpyinfo", "xorg-xprop", "qt6-base", "qt6-declarative"):
            self.assertIn(package, packages)
        release = (ROOT / "scripts/release.py").read_text()
        for file_name in ("mudos-desktop-session", "mudos-desktop-sessionctl", "mudos-desktop-theme", "mudos-desktop-wallpaper"):
            self.assertIn(file_name, release)
        self.assertIn("ui/DesktopWallpaper.qml", release)


if __name__ == "__main__":
    unittest.main()
