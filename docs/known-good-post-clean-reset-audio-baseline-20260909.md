# Known-Good Post-Clean-Reset Audio Baseline

Captured 2026-09-09 after a complete Lulu user-session/runtime reset, with
Oddworld Abe's Oddysee (Steam app 15700) running and monitor-speaker audio
working normally. No persistent configuration was changed for this capture.

## Launch Result

- HTTP launch request: `23:50:23.063`
- Steam launch request: `23:50:23.064`, `steam://rungameid/15700`
- Proton/reaper process start: `23:50:23`
- Game playback client: `Oddworld Abe's Oddysee`, process `821084`
- Visible/usable result: essentially immediate, consistent with the known-good
  `<10s` baseline; monitor speakers produced audio.
- Lulu's returned token was `steam://nav/games/details/15700`; the legacy Lulu
  lifecycle remained `shell`, which is not treated as a launch failure.

## `pactl info`

```text
Server String: /run/user/958/pulse/native
Library Protocol Version: 35
Server Protocol Version: 35
Is Local: yes
User Name: lulu
Host Name: lulu-test-env
Server Name: PulseAudio (on PipeWire 1.6.8)
Server Version: 15.0.0
Default Sample Specification: float32le 2ch 48000Hz
Default Channel Map: front-left,front-right
Default Sink: alsa_output.pci-0000_0a_00.1.hdmi-stereo
Default Source: output.lulu_fallback_input
Cookie: 2461:92f5
```

## Short Topology

```text
$ pactl list short cards
1086  alsa_card.pci-0000_0a_00.1                 alsa
1087  alsa_card.pci-0000_0c_00.4                 alsa
1088  alsa_card.usb-MACROSILICON_2109-02        alsa
1089  alsa_card.usb-Focusrite_Scarlett_2i2_USB-00 alsa
1090  alsa_card.usb-Hewlett_Packard_HP_Webcam_HD_4310-02 alsa

$ pactl list short sinks
1100  alsa_output.pci-0000_0a_00.1.hdmi-stereo  PipeWire  s32le 2ch 48000Hz  RUNNING

$ pactl list short sources
36    output.lulu_fallback_input                 PipeWire  float32le 2ch 48000Hz  SUSPENDED
1100  alsa_output.pci-0000_0a_00.1.hdmi-stereo.monitor PipeWire s32le 2ch 48000Hz RUNNING

$ pactl list short sink-inputs
1639  1100  1638  PipeWire  float32le 2ch 48000Hz

$ pactl list short source-outputs
37    4294967295  -  PipeWire  float32le 2ch 48000Hz
```

## Card Profiles

```text
1086 alsa_card.pci-0000_0a_00.1
  Active Profile: output:hdmi-stereo
  Device: Navi 21/23 HDMI/DP Audio Controller

1087 alsa_card.pci-0000_0c_00.4
  Active Profile: off
  Device: Starship/Matisse HD Audio Controller

1088 alsa_card.usb-MACROSILICON_2109-02
  Active Profile: off
  Device: 2109 / USB Device 0x345f:0x2109

1089 alsa_card.usb-Focusrite_Scarlett_2i2_USB-00
  Active Profile: off
  Device: Focusrite Scarlett 2i2

1090 alsa_card.usb-Hewlett_Packard_HP_Webcam_HD_4310-02
  Active Profile: off
  Device: HP Webcam HD 4310
```

## Key State

- Default sink: `alsa_output.pci-0000_0a_00.1.hdmi-stereo`.
- Default source: `output.lulu_fallback_input`.
- HDMI sink identity/state: sink `1100`, ASUS VG249, `s32le 2ch 48000Hz`,
  `RUNNING`; PipeWire node `58`.
- Fallback identity/state: source `36`, `output.lulu_fallback_input`,
  `SUSPENDED`; virtual source stream `input.lulu_fallback_input` is source
  output `37`, corked/passive.
- `auto_null`: absent from sinks and sources.
- Oddworld playback: sink input `1639`, application
  `Oddworld Abe's Oddysee`, process `821084`, uncorked and unmuted, routed to
  sink `1100` (HDMI/ASUS VG249). PipeWire stream node is `86`; streams `88`
  and `91` are active on playback FL/FR.

## `wpctl status`

```text
PipeWire 'pipewire-0' [1.6.8, lulu@lulu-test-env, cookie:610374389]
Clients:
  32 WirePlumber                 pid 814319
  33 pipewire-pulse              pid 814320
  34 pipewire-pulse              pid 814320
  45 WirePlumber [client]        pid 814319
  61 gamescope                   pid 818371
  73 Steam                       pid 818526
  74 xdg-desktop-portal          pid 818583
  77 Steam Voice Settings        pid 818526
  85 Oddworld Abe's Oddysee     pid 821084

Audio:
  Devices: HP Webcam HD 4310, 2109, Focusrite Scarlett 2i2,
           Starship/Matisse HD Audio Controller,
           Navi 21/23 HDMI/DP Audio Controller
  Sinks:
    * 58 Navi 21/23 HDMI/DP Audio Controller Digital Stereo (HDMI) [ASUS VG249]
  Sources:
  Filters:
    loopback-814320-12
    * 36 output.lulu_fallback_input [Audio/Source]
      37 input.lulu_fallback_input [Stream/Input/Audio]
  Streams:
    86 Oddworld Abe's Oddysee
      88 output_FR > ASUS VG249:playback_FR [active]
      91 output_FL > ASUS VG249:playback_FL [active]
```

## Processes and Environment

- PipeWire: `814317`, `/usr/bin/pipewire`.
- WirePlumber: `814319`, `/usr/bin/wireplumber`.
- PipeWire Pulse server: `814320`, `/usr/bin/pipewire-pulse`.
- Steam: `818526`, `/var/lib/lulu/.local/share/Steam/ubuntu12_32/steam`.
- Oddworld launch/reaper: `820811`; actual `AbeWin.exe`: `821084`.
- Relevant Steam/game environment: `XDG_RUNTIME_DIR=/run/user/958`,
  `DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/958/bus`, `DISPLAY=:0`,
  `WAYLAND_DISPLAY=gamescope-0`, `STEAM_GAME_DISPLAY_0=:0`,
  `STEAM_COMPAT_APP_ID=15700`, and `STEAM_COMPAT_CLIENT_INSTALL_PATH=/var/lib/lulu/.local/share/Steam`.
- No explicit `PULSE_*` or `PIPEWIRE_*` variables were present in the Steam
  or game environment; both use Lulu's runtime directory and session bus.

## Revised Conclusion

Observed contrast:

- Pathological session: multi-minute launch, PipeWire stream timeouts, and no
  monitor audio.
- Clean session: `<10s` launch, active HDMI playback, and working monitor
  audio.

The working hypothesis is a poisoned persistent/live PipeWire, WirePlumber,
Pulse-forwarding, Steam/pressure-vessel, or device-policy state that survived
partial runtime repairs and was cleared by the complete session reset. The old
delay is not currently attributed to Gamescope or solely to capture-source
availability.

The next experiment is a USB-switch away/back transition from this exact
healthy state, recording device events, profiles, topology, defaults, and
PipeWire/WirePlumber logs, followed by one Oddworld launch without restarting
the session. Gamescope, SDL, InputPlumber, presentation, and lifecycle code
remain unchanged.
