# Emulator Controller Provisioning

Mudos provisions native emulator profiles for the InputPlumber virtual Xbox
controller before launching local games. The physical controller is not
referenced by event number, and emulator process/lifecycle ownership is
unchanged.

## Input Contract

InputPlumber presents the composite target as `Microsoft Xbox 360 Controller`.
The current game profile exposes one player-facing gamepad target. Emulator
profiles therefore use the emulator's SDL gamepad abstraction rather than
`/dev/input/eventN` paths.

## PCSX2

PCSX2 2.8.2 uses SDL3 bindings in `PCSX2.ini` under `[Pad1]`. The native
binding syntax is `SDL-1/<semantic-control>` for the first controller exposed
by the current Lulu session. The profile maps Xbox positional face buttons to
the DualShock 2 layout, both sticks, triggers, shoulders, d-pad, Start, Select,
and stick clicks. Digital d-pad controls are kept separate from analog stick
controls so resting stick drift cannot produce menu navigation. The Xbox-class
SDL D-pad polarity is provisioned with the provider's observed direction
convention: PCSX2 `Up` consumes `DPadDown`, `Down` consumes `DPadUp`, and the
horizontal pair is similarly exchanged.

The profile is written to the service user's
`~/.config/PCSX2/inis/PCSX2.ini` and preserves unrelated INI sections.

## Dolphin

Dolphin's native GameCube profile is `Config/GCPadNew.ini`. The first profile
selects `SDL/0/Xbox 360 Controller` and uses Dolphin's SDL semantic controls
for face buttons, shoulders, sticks, triggers, d-pad, and Start. The Nintendo
face-button convention is shared with Eden: A/B and X/Y are translated from
the Xbox-style virtual target.

The profile is written below the `--user` root at
`~/.config/lulu/providers/dolphin/config/Config/GCPadNew.ini` and preserves
other controller slots and unrelated settings.

For the Wii validation path, Dolphin's GameCube Port 1 is explicitly set to a
standard GameCube controller with `SIDevice0 = 6`. Wii Remote 1 is emulated
(`WiimoteSource0 = 1`) with a Classic Controller extension, using the same
stable SDL gamepad identity. A physical Wii Remote is not required.

## Provisioning Boundary

`ensure_provider_controller_config(provider)` is idempotent and is called by
`consoled` immediately before a PS2 or Wii local runtime is started. It only
writes provider-owned native configuration. InputPlumber topology, interception
mode, player assignment, Guide behavior, and process lifecycle remain owned by
their existing services.

## External Sources

- [PCSX2 SDL input source](https://github.com/PCSX2/pcsx2/blob/master/pcsx2/Input/SDLInputSource.cpp)
- [Dolphin SDL gamepad source](https://github.com/dolphin-emu/dolphin/blob/master/Source/Core/InputCommon/ControllerInterface/SDL/SDLGamepad.h)
