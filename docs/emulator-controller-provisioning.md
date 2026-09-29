# Emulator Controller Provisioning

Mudos provisions native emulator profiles for the current InputPlumber/SDL
standard gamepad before launching local games. The physical controller is not
referenced by event number, and emulator process/lifecycle ownership is
unchanged.

## Input Contract

InputPlumber exposes one or more player-facing standard gamepad targets.
Mudos reads the live SDL index, GUID, and name immediately before launch;
provider profiles therefore never identify a controller by model, VID/PID, or
`/dev/input/eventN` path. Different players may have different SDL identities.

## PCSX2

PCSX2 2.8.2 uses SDL3 bindings in `PCSX2.ini` under `[Pad1]`. The native
binding syntax is `SDL-1/<semantic-control>` for the first controller exposed
by the current Mudos session. Face buttons retain their native SDL logical
positions; the profile also maps both sticks, triggers, shoulders, d-pad, Start, Select,
and stick clicks. Digital d-pad controls are kept separate from analog stick
controls so resting stick drift cannot produce menu navigation. The Xbox-class
SDL D-pad polarity is provisioned with the provider's observed direction
convention: PCSX2 `Up` consumes `DPadDown`, `Down` consumes `DPadUp`, and the
horizontal pair is similarly exchanged.

The profile is written to the service user's
`~/.config/lulu/providers/pcsx2/config/PCSX2/inis/PCSX2.ini` and preserves
unrelated INI sections.
Managed Flatpak launches pass PCSX2's `-datapath` explicitly to the Mudos-owned
config root; PCSX2 appends its own `PCSX2` subdirectory beneath that root. This
is necessary because Flatpak reserves
`XDG_CONFIG_HOME` for its private tree even when an environment override is
requested. The BIOS directory is separately exposed read-only; BIOS files are
never copied into Flatpak-private storage.

## Dolphin

Dolphin stores its active `GCPadNew.ini`, `WiimoteNew.ini`, `Dolphin.ini`, and
`Hotkeys.ini` under `Config/` in the `--user` directory. Mudos provisions those
files, rather than similarly named files in a separate `dolphin-emu/` tree.
The native GameCube profile's first port
selects the current `SDL/<index>/<name>` identity and uses Dolphin's SDL semantic controls
for face buttons, shoulders, sticks, triggers, d-pad, and Start. Face buttons
retain their native logical mappings; Mudos performs no face-button translation.

The profile is written at
`~/.config/lulu/providers/dolphin/config/Config/GCPadNew.ini` and preserves
other controller slots and unrelated settings. The real-Wii-Remote setting is
stored as `WiimoteSource0 = 2` in `Dolphin.ini` and `Source = 2` in
`WiimoteNew.ini`; standard emulation uses `1` in both settings.
Dolphin's `GFX.ini` is provisioned with `InternalResolution = 3` (3× internal
resolution, the 1080p target) while preserving other graphics settings.

For the Wii validation path, Dolphin's GameCube Port 1 is explicitly set to a
standard GameCube controller with `SIDevice0 = 6`; all four GameCube ports are
enabled and receive Mudos-owned SDL gamepad profiles. Dolphin's continuous
Wiimote scan option remains enabled so Bluetooth passthrough can discover
remotes. The Guide menu's Dolphin-only **Sync Wii Remotes** action sends the
`bracketright` key bound in Dolphin's active `Hotkeys.ini`. This matches the
InputPlumber COMPAT profile's right-brace keyboard event and does not create a
global OS shortcut. Real Bluetooth passthrough remains Dolphin-owned.
The passthrough lease enables Dolphin's Bluetooth passthrough for the launch
but preserves Dolphin's own adapter selection, including **Automatic**.

## Provisioning Boundary

`ensure_provider_controller_config(provider)` is idempotent and is called by
`consoled` immediately before a PS2 or Wii local runtime is started. It only
writes provider-owned native configuration. InputPlumber topology, interception
mode, player assignment, Guide behavior, and process lifecycle remain owned by
their existing services.

## External Sources

- [PCSX2 SDL input source](https://github.com/PCSX2/pcsx2/blob/master/pcsx2/Input/SDLInputSource.cpp)
- [Dolphin SDL gamepad source](https://github.com/dolphin-emu/dolphin/blob/master/Source/Core/InputCommon/ControllerInterface/SDL/SDLGamepad.h)
