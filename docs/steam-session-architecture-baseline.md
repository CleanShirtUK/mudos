# Steam Session Architecture Baseline

This is the validated Lulu Steam/session ownership baseline.

## Startup

The graphical session starts Gamescope with `--steam`. The shell entrypoint
starts the resident Steam client through `steam://open/bigpicture`, then waits
for a real Steam GamepadUI X11 surface: `GAMESCOPE_FOCUSABLE_WINDOWS` must
contain AppID `769`. This is readiness detection, not a fixed startup delay.

After Steam is ready, the session starts `/opt/lulu/bin/lulu-shell` as the
default Home surface.

`lulu-shell` hosts the existing `ConsoleShell.qml`. While the QML window is
hidden, it creates the native X11 window and sets `STEAM_GAME=769` through Qt's
X11 connection and XCB. It then shows the window. Lulu and Steam intentionally
both use AppID `769`.

## Ownership

Lulu owns the permanent console Home, its native `STEAM_GAME=769` identity,
and contextual Steam navigation/launch requests.

Steam owns the resident GamepadUI client and all Steam game preparation,
launch, cloud-sync, update, and error UI.

Gamescope owns application presentation and its natural fallback selection.

For Steam titles, Lulu sends:

```text
steam://nav/games/details/<appid>
steam://rungameid/<appid>
```

The details page is intentionally allowed to become visible while Steam starts
the title. Lulu does not wait for or supervise the game launch.

Lulu does not supervise Steam game processes, monitor game exit, manipulate
focus during lifecycle, write Gamescope base-layer properties, run a launch or
return watchdog, or perform post-game recovery. The former lifecycle
supervisor and presentation watchdog remain in the source as disabled
reference implementation. The passive lifecycle probe is development-only.

## Validation

The real duplicate AppID `769` arrangement was tested. At idle, both Lulu and
Steam had `STEAM_GAME=769`, while Lulu was the visible Home surface. During a
Cuphead launch, Gamescope listed AppIDs `268910` and `769` and presented
Cuphead. Exiting Cuphead through its own menu naturally returned to Lulu. A
second Cuphead launch succeeded without restarting Steam, and its exit again
returned to Lulu. No focus or recovery workaround was required.
