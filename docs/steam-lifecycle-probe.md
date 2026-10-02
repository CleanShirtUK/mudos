# Steam Lifecycle Probe

## Purpose

`scripts/steam-lifecycle-probe.py` is an external, observability-only diagnostic. It does not launch, focus, select, terminate, or otherwise control Steam, Gamescope, Xwayland, Mudos, or a game. The default expected AppID is Cuphead, `268910`; `--appid` keeps the probe generic.

The intended lifecycle evidence is:

```text
game-surface-seen appid=268910
...
surface-destroyed ... steam_game=268910
game-surfaces-zero appid=268910
```

Those events are derived from X11 surface metadata, not process lifetime.

## Observation mechanisms

The probe polls the Xwayland display with `xprop`:

- `_NET_CLIENT_LIST` supplies top-level X11 window IDs.
- `GAMESCOPE_FOCUSABLE_WINDOWS` supplies Gamescope's `(window, app id, pid)` records and fills gaps in the EWMH client list.
- Each observed window is queried for `STEAM_GAME`, `_NET_WM_NAME`, `WM_NAME`, `_NET_WM_PID`, and `WM_CLASS`.
- `_NET_ACTIVE_WINDOW` records X11 focus changes.
- `GAMESCOPECTRL_BASELAYER_WINDOW` records Gamescope base-layer/presentation selection changes.
- `/proc` is sampled only to record Steam command-line observations such as `-applaunch` or `steam://`; it is not used to decide game start or exit.

The probe reports a surface the first time it observes it. A `surface-created` event with `initial=true` means the window predated probe startup, not that an X11 CreateNotify event was captured. Polling can miss short-lived surfaces and metadata transitions between samples.

## Current environment result

The current bare-metal deployment has `/usr/bin/xprop`, `/usr/bin/xdotool`, `/usr/bin/dbus-monitor`, `/usr/bin/busctl`, and `/usr/bin/gamescope`. The running session shows Gamescope and Xwayland (`gamescope --expose-wayland`, `Xwayland :0`) and Mudos's persistent shell.

Direct inspection from the development shell was rejected with `Authorization required, but no authorization protocol specified` because this shell is not authorized for Lulu's `DISPLAY=:0`. Run the probe as the `lulu` session user, where the existing `DISPLAY=:0` Xauthority/session permissions apply. This is an access limitation, not evidence that `STEAM_GAME` is absent.

No current Mudos source reads `STEAM_GAME`. Existing Gamescope inspection is limited to `GAMESCOPE_FOCUSABLE_WINDOWS` and writes `GAMESCOPECTRL_BASELAYER_WINDOW` in `src/lulu/gamescope.py`. Existing Steam lifecycle observation uses AppID-related process environment and `/proc` PID polling in `src/lulu/steam_provider.py`.

## Experiment commands

From a terminal or maintenance VT, start the probe as the appliance user and preserve its output:

```sh
sudo -u lulu env \
  XDG_RUNTIME_DIR=/run/user/958 DISPLAY=:0 \
  PYTHONPATH=/opt/lulu/lib \
  /opt/lulu/scripts/steam-lifecycle-probe.py --appid 268910 \
  | tee /tmp/lulu-steam-cuphead-lifecycle.log
```

If running from the source checkout instead of an installed image:

```sh
sudo -u lulu env XDG_RUNTIME_DIR=/run/user/958 DISPLAY=:0 \
  PYTHONPATH=src \
  ./scripts/steam-lifecycle-probe.py --appid 268910 \
  | tee /tmp/lulu-steam-cuphead-lifecycle.log
```

Leave it running while launching and normally exiting Cuphead through the existing Lulu UI. Stop it with `Ctrl-C` only after the post-exit Steam/Lulu surface has been observed. Do not use the probe to send controller input or launch the game.

## Files

- Added `scripts/steam-lifecycle-probe.py`.
- Added this document.
- Existing lifecycle, focus, controller, UI, and Steam launch files were not modified.
