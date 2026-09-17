# Audio settings

Lulu uses PipeWire with WirePlumber and the `pipewire-pulse` compatibility
service. Audio settings use the user-session Pulse API (`pactl --format=json`)
through `src/lulu/audio_manager.py`; QML does not run audio commands and no
elevated permission is required. PipeWire/WirePlumber own device persistence,
default restoration, and stream routing.

The normalized model contains output and input devices with stable server IDs,
friendly names, type, availability, active/default state, volume, and mute.
The Consoled D-Bus boundary exposes snapshots and mutations for selecting
outputs/inputs, changing volume, and setting mute. The localhost UI bridge
delivers this model to the controller-first `AudioSettings.qml` page. It
refreshes once per second while visible so external volume, default, restart,
and hotplug changes become authoritative without aggressive background work.

Controller behavior is deliberately small: A selects an output/input or
increments the volume row, Left/Right changes the selected device by 5 points,
and A on the mute row toggles the current output. Volume is clamped to 0–100.
The current Lulu hardware exposes one HDMI/DisplayPort output (`ASUS VG249`)
and a virtual `lulu_fallback_input`; no physical microphone or second output
was available for switching validation. Input controls are present and handle
the virtual/no-input case cleanly. UI, Guide, notification, and theme sounds
remain out of scope.

Physical validation passed in the development runtime: output enumeration and
selection, repeated volume changes, audible mute/unmute behavior, Back,
reopen/state restoration, and existing Internet, Guide, Provider, game launch,
OSK, and status-strip smoke checks. Automated adapter coverage includes
normalization, defaults, volume/mute/output mutations, monitor filtering, and
service-unavailable handling.
