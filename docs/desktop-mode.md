# Mudos Desktop Mode (DESKTOP-001)

## Architecture and lifecycle

The System Home card requests `RequestDesktopLaunch` through the console UI bridge. Sessiond launches `scripts/mudos-desktop-session` in its existing supervised process group with `SessionClassification.DESKTOP`, `Presentation.FOREIGN_UI`, and `InputMode.COMPAT`. The nested server window is the single surface selected by the existing Gamescope presentation authority. Sessiond is the lifecycle authority: normal exit, Exit Desktop Mode, or an unexpected Xephyr/Openbox exit completes the owned process group, reselects the Mudos shell, and restores the shell input baseline. Consoled and Acquisitiond are not stopped or restarted.

## Display isolation and account

The wrapper allocates an X display distinct from the inherited outer display and starts Xephyr on the existing Mudos presentation display. Openbox, tint2, jgmenu, and desktop applications receive only the nested `DISPLAY`; Openbox is never pointed at the outer Xwayland. The nested server uses a per-session MIT-MAGIC-COOKIE-1 file in `$XDG_RUNTIME_DIR/mudos-desktop`, mode 0600, and TCP listening is disabled. No `xhost` access override is used. The wrapper runs as the existing `lulu` appliance user and inherits HOME, UID, XDG config/data/cache, user D-Bus, PipeWire, and application state; only generated Openbox/tint2/jgmenu configuration is isolated under the desktop runtime directory.

## Panel and application menu

The V1 panel is tint2 with the jgmenu application menu (`jgmenu_run apps`): app menu, normal XDG application enumeration, window taskbar, system tray, Mudos Wi-Fi and Bluetooth utility launchers, clock, and a Power menu. Standard XDG application desktop files and Flatpak exports are discovered through jgmenu's normal XDG integration; this is not a second Mudos catalogue. The Power menu has only Restart (with explicit confirmation), Shutdown (with explicit confirmation), and Exit Desktop Mode. It has no logout, switch-user, lock, or new-session action. Its control helper accepts only `exit`, `reboot`, and `shutdown`; all operations call existing Sessiond methods.

## Mudos settings and shared authority

`mudos-desktop-settings` is a small GTK presentation over the local console UI bridge. Wi-Fi state and mutations use the existing Consoled `NetworkManagerAdapter` API (including scan, enable/disable, connect, disconnect, and forget). Bluetooth state and operations use the existing Consoled `BluezClient` API. The desktop UI contains no nmcli, bluetoothctl, Blueman, direct system-setting writes, or independent privileged authority. Secured Wi-Fi uses an interactive password prompt; Bluetooth pairing confirmation/input uses Mudos's existing BlueZ pairing action boundary.

## Theme mapping

At entry the wrapper invokes `mudos-desktop-theme`, a small native helper that reads `ThemeManager`'s validated active theme (and therefore inherits its Modern fallback behavior). It emits a limited semantic snapshot. Tint2, jgmenu, and the desktop root use surface/background, border, primary/secondary text, accent/focus, and panel radius; exact zero radius from the 95 theme stays square. Openbox uses a stock lightweight theme in V1; native glass and shader wallpaper are intentionally not reproduced. Fonts use the system Sans fallback.

## Packages and ownership

The canonical package set includes Openbox, tint2, jgmenu, Xephyr, xauth, xsetroot, xdpyinfo, GTK3/PyGObject, plus the existing Mudos runtime. No full desktop environment or notification daemon is installed. All wrapper, helper, generated theme binary, and desktop launchers are included in immutable release payloads. The current production selector is not changed by source implementation.

## V1 limitations and acceptance

Third-party application notifications are out of scope; Mudos notifications remain external to the nested X session. Openbox decorations use the available stock theme rather than generated per-theme titlebar assets. Desktop Mode needs physical acceptance for Gamescope nesting, keyboard/mouse/controller behavior, panel/taskbar behavior, application launching, theme appearance, repeated entry/exit, and continued downloads/services. Restart/shutdown must only be verified against mocked/nondestructive Sessiond boundaries unless explicitly authorized.
