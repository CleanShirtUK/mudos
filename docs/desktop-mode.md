# Mudos Desktop Mode (DESKTOP-001)

## Architecture and lifecycle

The System Home card requests `RequestDesktopLaunch` through the console UI bridge. Sessiond launches `scripts/mudos-desktop-session` in its existing supervised process group with `SessionClassification.DESKTOP`, `Presentation.FOREIGN_UI`, and `InputMode.COMPAT`. The nested server window is the single surface selected by the existing Gamescope presentation authority. Sessiond is the lifecycle authority: normal exit, Exit Desktop Mode, or an unexpected Xephyr/Openbox exit completes the owned process group, reselects the Mudos shell, and restores the shell input baseline. Consoled and Acquisitiond are not stopped or restarted.

## Display isolation and account

The wrapper allocates an X display distinct from the inherited outer display and starts Xephyr on the existing Mudos presentation display. Openbox, tint2, jgmenu, and desktop applications receive only the nested `DISPLAY`; Openbox is never pointed at the outer Xwayland. The nested server uses a per-session MIT-MAGIC-COOKIE-1 file in `$XDG_RUNTIME_DIR/mudos-desktop`, mode 0600, and TCP listening is disabled. No `xhost` access override is used. The wrapper runs as the existing `lulu` appliance user and inherits HOME, UID, XDG config/data/cache, user D-Bus, PipeWire, and application state; only generated Openbox/tint2/jgmenu configuration is isolated under the desktop runtime directory.

## Panel and application menu

The V1 panel is tint2 with the jgmenu application menu (`jgmenu_run apps`): app menu, normal XDG application enumeration, window taskbar, system tray, Mudos Wi-Fi and Bluetooth utility launchers, clock, and a Power menu. The per-theme tint2 configuration is generated from the installed tint2 17 default configuration so its full required defaults remain intact; semantic colors/radius and the four Mudos buttons are then applied. Startup is ordered behind successful Xephyr connection and Openbox EWMH readiness. Tint2 stdout/stderr and renderer diagnostics are saved below the per-session runtime directory; tint2 gets one bounded initial retry and one bounded restart after an unexpected exit, while its failure does not stop Openbox or the wallpaper. Standard XDG application desktop files and Flatpak exports are discovered through jgmenu's normal XDG integration; this is not a second Mudos catalogue. The Power menu has only Restart (with explicit confirmation), Shutdown (with explicit confirmation), and Exit Desktop Mode. It has no logout, switch-user, lock, or new-session action. Its control helper accepts only `exit`, `reboot`, and `shutdown`; all operations call existing Sessiond methods.

## Mudos settings and shared authority

`mudos-desktop-settings` is a small GTK presentation over the local console UI bridge. Wi-Fi state and mutations use the existing Consoled `NetworkManagerAdapter` API (including scan, enable/disable, connect, disconnect, and forget). Bluetooth state and operations use the existing Consoled `BluezClient` API. The desktop UI contains no nmcli, bluetoothctl, Blueman, direct system-setting writes, or independent privileged authority. Secured Wi-Fi uses an interactive password prompt; Bluetooth pairing confirmation/input uses Mudos's existing BlueZ pairing action boundary.

## Theme mapping

At entry the wrapper invokes `mudos-desktop-theme`, a small native helper that reads `ThemeManager`'s validated active theme (and therefore inherits its Modern fallback behavior). It emits a limited semantic snapshot used to regenerate tint2 and jgmenu configuration; exact zero radius from 95 stays square. The root is first painted with the active semantic surface as a fallback. `mudos-desktop-wallpaper` then creates a non-focusable X11 desktop-type window, skipped by taskbar/pager and kept below normal windows. Its `DesktopWallpaper.qml` uses the same `OrbitRenderSource.qml`, ThemeManager context, selected `wallpaperShader` QSB, and exact wallpaper palette uniforms as the Mudos shell. The only desktop-specific shader parameters are full visibility/brightness, zero origin, desktop-sized canvas/resolution, and continuously advancing shader time; shell transition choreography is not run. Shader/theme errors leave the semantic root-color fallback visible and do not stop the desktop. The renderer adds no offscreen copy, blur, supersampling, or extra shader pass. Openbox decorations use a stock lightweight theme in V1; fonts use system Sans.

## Packages and ownership

The canonical package set includes Openbox, tint2, jgmenu, Xephyr, xauth, xsetroot, xdpyinfo, xprop, GTK3/PyGObject, and the existing Qt 6 Quick runtime. Fresh-install verification checks the required desktop binaries/packages, and the wallpaper host plus both QML files are included in immutable release payloads. No full desktop environment or notification daemon is installed. The current production selector is not changed by source implementation.

## V1 limitations and acceptance

Third-party application notifications are out of scope; Mudos notifications remain external to the nested X session. Openbox decorations use the available stock theme rather than generated per-theme titlebar assets. The 2026-10-08 development-runtime physical pass verified Gamescope/Xephyr entry and return, visible Modern and 95 QSB wallpapers, panel/taskbar/menu/application launch, theme-derived panel colors/radius, and service continuity. Restart/shutdown were not invoked; those actions remain verified only against mocked/nondestructive Sessiond boundaries unless explicitly authorized.
