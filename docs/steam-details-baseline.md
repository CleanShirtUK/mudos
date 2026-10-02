# Steam Details Baseline

This is a retained diagnostic record for comparing Steam startup latency while
the Mudos Steam lifecycle owner was removed from the path. It is historical,
not a replacement architecture. The live implementation may have moved beyond
the exact navigation-only behavior recorded below; consult the implementation
inventory and dated Steam architecture evidence for current status.

## Existing behavior bypassed

Before this change, `ConsoleCatalog.LaunchGame` sent Steam titles to
`ConsoleSessiond.RequestSteamLaunch`. That path, in
`src/lulu/process_supervisor.py` and `src/lulu/steam_provider.py`:

- started or reused Steam, then invoked `steam -silent -applaunch APPID`;
- searched `/proc` for AppID-related title processes and filtered runtime/helper processes;
- waited up to the 300-second `observe_launch` orphan watchdog for a title process;
- cleared Gamescope's base-layer selection and switched InputPlumber to GAME;
- selected a Gamescope window using `GAMESCOPE_FOCUSABLE_WINDOWS` and process/PID matching;
- treated disappearance of the discovered title PID as exit;
- switched InputPlumber back to SHELL and selected the Lulu shell window on return;
- restored the session model to SHELL and notified the UI.

The session's independent shell presentation watchdog is also disabled for
this baseline. It normally runs as
`ConsoleSessionInterface._monitor_presentation` every 500 ms;
`ensure_shell_presentation` reads `GAMESCOPE_FOCUSABLE_WINDOWS` and writes
`GAMESCOPECTRL_BASELAYER_WINDOW` when Lulu's shell is not selected. The
implementation remains in `src/lulu/sessiond.py`, but task creation is gated
by `_presentation_watchdog_enabled = False`. No lifecycle task, Steam process
watcher, `/proc` title discovery, launch watchdog, or automatic return path is
created for this navigation request.

## Experimental behavior

At the time of this diagnostic capture, a Steam title's Play action invoked the
Steam CLI with:

```text
steam://nav/games/details/<appid>
```

The process was detached and not waited on. Steam's normal single-client URI
handling was relied upon. This record therefore does not establish the current
Mudos launch contract, which also has a `steam://rungameid` path in
`src/lulu/consoled.py`. The UI skipped launch-state polling for the diagnostic
response. Local/emulator launches used the existing path.

The old implementation is not deleted or commented out. It remains in
`src/lulu/process_supervisor.py` and the Steam lifecycle methods in
`src/lulu/steam_provider.py`; only the Steam selection branch in
`src/lulu/consoled.py` bypasses it. The lifecycle probe remains at
`scripts/steam-lifecycle-probe.py`.

## Files changed

- `src/lulu/steam_provider.py`: add detached GamepadUI details navigation.
- `src/lulu/consoled.py`: route Steam selections to that navigation only.
- `src/lulu/sessiond.py`: disable the active shell presentation watchdog.
- `scripts/console-ui-bridge.py`: identify navigation-only responses.
- `ui/ConsoleShell.qml`: avoid lifecycle polling for navigation-only responses.
- `docs/steam-details-baseline.md`: this record and restoration procedure.

No layout, controller reassignment, emulator, Store, Gamescope configuration,
or probe files were changed. The existing shell process remains resident, and
the controller monitor remains active for shell input bookkeeping; it does not
write Gamescope state.

## Historical Restore Notes

Set `_presentation_watchdog_enabled = True` in `src/lulu/sessiond.py`, then
restore the Steam branch in `src/lulu/consoled.py` to call
`session.call_request_steam_launch(game.provider_id, timeout_ms)` and remove
the navigation-only response handling in `scripts/console-ui-bridge.py` and
`ui/ConsoleShell.qml`. Alternatively, revert only these four source-file
changes after the experiment. Do not remove the lifecycle implementation.

## Manual Cuphead test

1. Restart/redeploy Lulu so the changed `consoled` and UI files are active.
2. Start from Lulu and select Cuphead.
3. Confirm Lulu opens `steam://nav/games/details/268910` in Steam GamepadUI.
4. Confirm Steam shows its normal Play button.
5. Manually press Play and time until Cuphead appears.
6. Exit Cuphead normally and record where Steam/Gamescope leaves the display.
7. Repeat as needed. Lulu is not expected to recover or resume ownership automatically.

For a source checkout session, the relevant launch command is:

```sh
PYTHONPATH=src python -m lulu.consoled
```

Use the normal Lulu session startup for the UI; no new Steam instance or
wrapper should be started by the experiment.
