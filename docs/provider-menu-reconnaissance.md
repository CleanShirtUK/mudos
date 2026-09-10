# Provider Menu Reconnaissance

Status: external-first research record, 2026-09-10. No provider-menu or Guide
implementation is included here. The configured providers are authoritative in
`src/lulu/emulation.py`: RetroArch for NES/Genesis, PCSX2 for PS2, Dolphin for
Wii, and Yuzu for Switch.

## Summary

| Provider | Controller/10-foot menu | Clean external opener | Current conclusion |
| --- | --- | --- | --- |
| Steam game | Steam Overlay is controller-capable; game-specific support varies | No documented external Mudos opener; Steamworks overlay API is in-process | UNKNOWN/PARTIAL |
| RetroArch | Built-in gamepad-controlled menu | `retroarch --command "MENU_TOGGLE;HOST;PORT"` or enabled stdin command interface | IMPLEMENTABLE, not yet integrated |
| PCSX2 | Native Qt menus and Fullscreen UI | No documented external opener found | PARTIAL |
| Dolphin | Desktop Qt menus/settings; no desktop Big Picture UI | No documented external opener found | PARTIAL |
| Yuzu | Historical desktop Qt UI; current installed build/upstream contract unverified | No authoritative current mechanism found | UNKNOWN |

## Steam

### Menu and opener

Steam Overlay is the appropriate native controller-friendly surface for a Steam
game. Valve documents the default `Shift+Tab` shortcut and the in-process
Steamworks call:

```cpp
SteamFriends()->ActivateGameOverlay("settings");
```

The Steamworks call is available to the initialized game process, not as an
external command for Mudos to apply to an arbitrary running title. Steam client
URIs such as `steam://open/bigpicture` exist in the current Mudos deployment,
but are not a documented contract for opening an in-game settings surface and
do not establish deterministic close/return behavior.

Sources:

- [Steam Overlay](https://partner.steamgames.com/doc/features/overlay)
- [ISteamFriends::ActivateGameOverlay](https://partner.steamgames.com/doc/api/ISteamFriends#ActivateGameOverlay)
- [Steam overlay callbacks](https://partner.steamgames.com/doc/api/ISteamFriends#GameOverlayActivated_t)

### Ownership and return

Opening Steam Overlay leaves the game process running. Steam documents
`GameOverlayActivated_t` for games that need to pause/resume, but not a
cross-process controller ownership protocol. Mudos would need to transfer
InputPlumber ownership to the overlay/game-compatible route and restore it on
overlay close. Big Picture/URI navigation should not be treated as equivalent
to an in-game menu.

### Provisioning

Steam and the game must run under the same Lulu appliance account, with the
overlay enabled for the title. Whether an individual title supports usable
controller overlay navigation remains provider/game-specific.

## RetroArch

### Menu and opener

RetroArch has a native controller-controlled menu while content remains loaded.
Its documented command interface supports:

```text
MENU_TOGGLE
```

The cleanest external mechanism is the UDP command client:

```text
retroarch --command "MENU_TOGGLE;127.0.0.1;55355"
```

The running instance must provision `network_cmd_enable = true` and the matching
`network_cmd_port`. RetroArch also supports newline commands on stdin with
`stdin_cmd_enable = true`; that is less suitable for the current Mudos launch,
which deliberately uses `stdin=DEVNULL`. A controller hotkey such as
`input_menu_toggle_gamepad_combo = 4` (`Start + Select`) is documented, but is a
fallback behind IPC because it depends on input routing and timing.

### Ownership and return

The menu does not unload content. `MENU_TOGGLE` returns to gameplay, and
`menu_pause_libretro = true` can pause the core while the menu is visible.
Mudos would need to route controller input to the RetroArch menu and restore the
previous route when it closes. `CLOSE_CONTENT` is a separate command; with
`quit_on_close_content = true`, it exits RetroArch and supports the already
validated Mudos return path, but it is not a provider-menu action.

### Provisioning

For a future Mudos provider-menu integration, provision the network command
interface, a fixed per-runtime port policy, and optionally
`menu_pause_libretro = true`. The current Mudos RetroArch launch already
provisions `quit_on_close_content = true` for the separate Quit action.

Sources:

- [RetroArch command documentation](https://raw.githubusercontent.com/libretro/RetroArch/master/docs/retroarch.6)
- [RetroArch command definitions](https://raw.githubusercontent.com/libretro/RetroArch/master/command.h)
- [RetroArch command implementation](https://raw.githubusercontent.com/libretro/RetroArch/master/command.c)
- [RetroArch defaults](https://raw.githubusercontent.com/libretro/RetroArch/master/config.def.h)

## PCSX2

PCSX2-Qt provides native desktop menus and a native Fullscreen UI with settings,
states, and power controls. The Fullscreen UI is an internal application mode,
not a separately invokable external process. No documented IPC/API or stable
external command for opening that UI while a game is running was found.

Mudos therefore has no confirmed clean opener. A future integration would need
an upstream-supported command or a provider-configured hotkey; synthetic input
should not be selected without further evidence. PCSX2 has no documented
cross-process ownership transfer. Closing/powering off ends the VM; ordinary
resume means relaunching, potentially with a saved state.

No additional Mudos provisioning requirement is established.

Source: [PCSX2 Qt MainWindow](https://github.com/PCSX2/pcsx2/blob/master/pcsx2-qt/MainWindow.cpp)

## Dolphin

Dolphin has native desktop Qt menus and settings while a game runs, including
pause, stop, reset, save/load state, controller, graphics, audio, and hotkey
settings. Its documented boot path is the existing `dolphin-emu -e <disc>`.

### Desktop Big Picture verification

Current upstream DolphinQt does **not** provide a desktop Big Picture or
controller-oriented fullscreen frontend. Fullscreen changes the render surface;
it does not transform the desktop game list and menus into a 10-foot UI. This
was verified against the upstream DolphinQt main-window/menu sources, not a
third-party launcher.

No documented external command/API for opening Dolphin's menus was found.
Hotkeys are native and configurable, but invoking one externally would be
synthetic input and is not recommended as the first design.

Dolphin has no documented cross-process ownership transfer. Pause can preserve
the running session; stop or close ends emulation and returns to the game list
or requires relaunch. No additional Mudos provisioning requirement is
established.

Sources:

- [Dolphin MainWindow](https://github.com/dolphin-emu/dolphin/blob/master/Source/Core/DolphinQt/MainWindow.cpp)
- [Dolphin MenuBar](https://github.com/dolphin-emu/dolphin/blob/master/Source/Core/DolphinQt/MenuBar.cpp)

## Yuzu (Configured Switch Provider)

The repository configures Yuzu at `/usr/bin/yuzu` and launches it with the
package path. Yuzu's former upstream repository and documentation are no longer
available as authoritative live sources. Historical Yuzu behavior included
desktop Qt menus, controller settings, hotkeys, pause, and stop, but exact
current menu invocation and close/resume behavior are build-specific and not
verified here.

No current documented IPC/API, command interface, or safe external menu opener
was established. Controller ownership transfer and return are likewise
UNKNOWN. No provisioning should be added until the installed Yuzu build or a
maintained successor provides an authoritative mechanism.

Historical references:

- [Former Yuzu repository](https://github.com/yuzu-emu/yuzu)
- [Former Yuzu quickstart](https://yuzu-emu.org/help/quickstart/)

## Current Runtime Failures

These are recorded independently of provider-menu reconnaissance and are not
diagnosed by this document:

- PS2/PCSX2: does not launch.
- Switch/Yuzu: does not launch.
- Wii/Dolphin: launches; controller mapping is incomplete; the current close
  path presents a mouse-dependent confirmation.

## Proposed Mudos Boundary

Do not implement this boundary yet. The minimal future provider capability is:

```text
supports_provider_menu(provider) -> bool
open_provider_menu(provider) -> result
```

Guide should show the provider-menu entry only when the selected provider
supports a documented opener. Provider implementations should own their
mechanism and report whether opening succeeded; Mudos/session handling should
own controller transfer and restoration. A future Guide+button shortcut may
invoke the same action, but no chord is specified here.
