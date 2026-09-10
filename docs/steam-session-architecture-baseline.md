# Steam Session Architecture Baseline

This is a dated validated Lulu appliance/Mudos Steam-session ownership baseline.
It describes the `--steam` deployment captured here; it is not evidence that
every current test-machine session uses the same Gamescope invocation.

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

Mudos owns the permanent console Home, its native `STEAM_GAME=769` identity,
and contextual Steam navigation/launch requests.

Steam owns the resident GamepadUI client and all Steam game preparation,
launch, cloud-sync, update, and error UI.

Gamescope owns application presentation and its natural fallback selection.

For Steam titles, Mudos sends:

```text
steam://nav/games/details/<appid>
steam://rungameid/<appid>
```

The details page is intentionally allowed to become visible while Steam starts
the title. Mudos does not wait for or supervise the game launch.

Mudos does not supervise Steam game processes, monitor game exit, manipulate
focus during lifecycle, write Gamescope base-layer properties, run a launch or
return watchdog, or perform post-game recovery. The former lifecycle
supervisor and presentation watchdog remain in the source as disabled
reference implementation. The passive lifecycle probe is development-only.

## Validation

The real duplicate AppID `769` arrangement was tested. At idle, both Lulu and
Steam had `STEAM_GAME=769`, while Mudos was the visible Home surface. During a
Cuphead launch, Gamescope listed AppIDs `268910` and `769` and presented
Cuphead. Exiting Cuphead through its own menu naturally returned to Mudos. A
second Cuphead launch succeeded without restarting Steam, and its exit again
returned to Mudos. No focus or recovery workaround was required.

## Non-Steam Runtime Boundary

The first validated non-Steam provider is RetroArch. Its identity is not
represented as a Steam shortcut and is not assigned through the RetroArch
window. Mudos predeclares a Gamescope AppID priority list of
`4000000001, 769`, then launches unmodified RetroArch in a transient systemd
user scope named `app-steam-app4000000001-<integer>.scope`. Gamescope derives
the runtime AppID from the cgroup, presents the first available priority entry,
and naturally falls through to Mudos when the scope ends.

For RetroArch, Mudos requests graceful termination by stopping the runtime
scope. The scope's SIGTERM path produced clean RetroArch deinitialization,
completed scope termination, no SIGKILL escalation, and natural return to Mudos.
This termination behavior is provider-specific and is not generalized to
future runtimes.

See [the non-Steam architecture baseline](non-steam-runtime-architecture-baseline.md)
and [RetroArch validation](retroarch-runtime-validation-20260909.md) for the
decision and evidence records. Production AppID allocation, other runtime
providers, catalogue integration, and permanent Gamescope package policy remain
unresolved.

Future session startup must establish a deterministic Gamescope control
baseline. The test session contained stale `GAMESCOPECTRL_BASELAYER_WINDOW`
and `GAMESCOPECTRL_BASELAYER_APPID` values; the former was already invalid.
