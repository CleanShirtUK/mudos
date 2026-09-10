# Mudos Proton WinePulse Fallback Input

Mudos intentionally provides an always-present virtual capture endpoint because
Proton/WinePulse can incur repeated approximately 30-second startup waits when
no non-monitor capture source exists. This endpoint does not represent a
microphone and does not require physical audio hardware.

The behavior was observed with Cuphead and Oddworld: Abe's Oddysee. With only
monitor sources present, Proton startup stalled repeatedly, FMOD output
initialization failed for Cuphead, and startup took approximately 152 seconds.
Exposing a physical capture source removed the delay. The same behavior matches
ValveSoftware/SteamOS#2504:

https://github.com/ValveSoftware/SteamOS/issues/2504

The production fallback is loaded declaratively by the lulu user's
`pipewire-pulse` drop-in:

`/var/lib/lulu/.config/pipewire/pipewire-pulse.conf.d/lulu-fallback-input.conf`

It loads `module-virtual-source` with:

- source name: `lulu_fallback_input`
- source priority: `priority.session=10`
- no physical microphone dependency

The low priority allows a real capture device to be preferred when present.
The fallback is not a monitor source, does not alter the HDMI playback sink,
and remains available when no physical capture device is attached.

The repository copy is
`packaging/pipewire/lulu-fallback-input.conf`. On a fresh installation,
`scripts/deploy-pipewire-fallback.sh` installs it with the correct lulu
ownership and permissions. Restarting the lulu user's `pipewire-pulse` service
applies the drop-in; no `pactl load-module` command is required.

The virtual-source experiment first restored a monitor-only environment, then
loaded one temporary `module-virtual-source`. `pactl` exposed
`output.lulu_fallback_input` and `wpctl` exposed it as an `Audio/Source` filter.
Cuphead launched in seconds with no FMOD failure or WinePulse timeout.

Cold-boot validation confirmed that the source is recreated automatically with
no physical audio input required. The machine's existing device policy initially
selected the attached Focusrite as the default sink; for the no-physical-input
validation, all USB audio profiles were disabled and HDMI was explicitly set as
the default. In that graph, Cuphead and Oddworld launched normally with active
HDMI audio and no observed WinePulse timeout or FMOD failure. The fallback
configuration itself does not select or reroute playback.
