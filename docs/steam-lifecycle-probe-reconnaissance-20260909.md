# Steam Lifecycle Probe Reconnaissance

Status: research only. This note records the Lulu test-machine deployment state on 2026-09-09,
Gamescope source behavior, and experiments still required. It does not define a
runtime lifecycle implementation.

## Confirmed on the Lulu test-machine deployment

- The active session is user `lulu` (UID 958), session `c302`, running Gamescope
  3.16.25 with embedded Xwayland `:0` and Wayland display `gamescope-0`.
- The live command is `gamescope --backend drm --prefer-output HDMI-A-1
  --expose-wayland --nested-width 1920 --nested-height 1080 -- ...`. It does
  not contain `--steam` or `-e`.
- The idle shell has an X11 window (`qmlscene`, XID `0x400011`) and Gamescope
  root properties `GAMESCOPE_FOCUSED_WINDOW`, `GAMESCOPE_FOCUSABLE_WINDOWS`,
  `GAMESCOPE_FOCUSABLE_APPS`, `GAMESCOPE_PID`, and
  `GAMESCOPECTRL_BASELAYER_WINDOW`.
- In that idle state, `STEAM_GAME`, `STEAM_GAMES_RUNNING`,
  `GAMESCOPE_FOCUSED_APP`, and `GAMESCOPE_FOCUSED_APP_GFX` are absent. This is
  not a game test.
- The current shell is restarted by the session supervisor when its primary
  child exits; Xwayland is also restarted during that cycle. A probe must not
  treat an Xwayland restart or XID change as a game exit without correlating
  session identity.

## Confirmed from Gamescope source and documentation

Gamescope's embedded Steam/Xwayland path uses X11 properties. On each mapped
Xwayland window it reads `STEAM_GAME` as a 32-bit value and, in Steam mode, uses
that value as the window AppID. A later `PropertyNotify` for `STEAM_GAME` updates
the cached AppID and marks focus dirty. Window creation, map/unmap, destroy,
property changes, XDamage, and focus are therefore observable from an external
X11 client connected to the embedded Xwayland display.

The compositor itself determines focus from candidate windows, damage/order,
window type, fullscreen/useless-window rules, overlays, and optional focus
control properties. It publishes the selected XID in
`GAMESCOPE_FOCUSED_WINDOW`. In Steam mode it additionally publishes
`GAMESCOPE_FOCUSED_APP` (input-focus AppID) and
`GAMESCOPE_FOCUSED_APP_GFX` (base/scene AppID). `GAMESCOPE_FOCUSABLE_WINDOWS`
contains `[window, appid, pid]` triplets; `GAMESCOPE_FOCUSABLE_APPS` contains
unique AppIDs. These root properties are better signals for “what Gamescope
selected” than reading an arbitrary window's `STEAM_GAME`.

`STEAM_GAME` is not a Wayland property. It is an Xwayland/X11 window property
written by Steam or by an application/session helper. The corresponding
Wayland surface can be correlated through Gamescope's `WL_SURFACE_ID` handling,
but generic external Wayland clients do not get a stable enumeration of all
surfaces from the standard protocol. Gamescope's private Wayland protocols are
not a lifecycle/event API; `gamescope_control` exposes display, screenshot, and
performance requests, while `gamescope_private` is explicitly unstable and
debug-oriented.

The upstream Gamescope source sets `steamMode` only for `--steam`/`-e`. That
mode controls AppID-based selection and the focused-App root properties. Lulu's
current invocation omits it, so `STEAM_GAME` authority in the current deployment
is unconfirmed and likely incomplete until tested with the exact deployed
invocation.

The upstream ChimeraOS `gamescope-session` documentation confirms the established
convention: a main custom application window uses `STEAM_GAME=769`, while other
windows use a non-769 value; Steam uses the actual game AppID. It describes 769
as the value used for Steam's own window, not as a universally reserved custom
application identifier.

## Observable signal hierarchy

1. Session supervisor/process identity and exit status: authoritative for the
   lifetime of the launched session or Gamescope child, but not sufficient to
   say which Steam game is visible.
2. X11 event stream from embedded Xwayland: use XCB/Xlib to select root
   `SubstructureNotifyMask`, then per-window `PropertyChangeMask` and relevant
   focus/damage events. Query new windows immediately and re-query after
   `STEAM_GAME`, map, unmap, destroy, `_NET_WM_PID`, `WL_SURFACE_ID`, overlay,
   and window-type changes. This avoids polling and captures recreate cycles.
3. Gamescope root properties: consume `GAMESCOPE_FOCUSED_WINDOW` and, only when
   present and in Steam mode, `GAMESCOPE_FOCUSED_APP`/
   `GAMESCOPE_FOCUSED_APP_GFX`; consume `GAMESCOPE_FOCUSABLE_WINDOWS` to retain
   the window/AppID/PID mapping. Subscribe to root `PropertyNotify` and take a
   coherent snapshot after each event.
4. Per-window `STEAM_GAME`: useful attribution and a candidate trigger, but not
   by itself proof that the window is foreground, presented, or still alive.
5. Process/cgroup evidence: Gamescope can derive AppIDs from Steam cgroup names
   (`app-steam-app<appid>-...scope`) or the Steam reaper command line. This is a
   useful fallback/cross-check, not a visual-present signal.
6. PipeWire Gamescope stream metadata: Gamescope exposes the focused AppID in
   its stream format metadata. This can indicate the AppID associated with the
   captured/presented stream, but adds PipeWire plumbing and is not a window
   creation/destruction event source.

## Failure modes and hypotheses

- Proton and native games should converge on Steam's X11 AppID property, but
  the exact timing and window ownership differ; verify both. Proton may create
  Wine/Xwayland windows before the final main window.
- Launchers, Steam launch-option dialogs, and Steam UI windows can be mapped
  before the game and can carry different or absent properties. A transient
  window must not start or end a game lifecycle by itself.
- Multiple windows can share an AppID. Track a set of windows per AppID and use
  Gamescope's focused/base window for foreground attribution.
- Main-surface destruction/recreation can create a false exit if identity is
  tied to XID. Preserve the AppID/session candidate across short gaps and use
  destroy plus replacement/focus evidence.
- Steam overlays (`STEAM_OVERLAY`) and external overlays
  (`GAMESCOPE_EXTERNAL_OVERLAY`) are deliberately separate focus/layer cases;
  they can be visible without being the game. Do not count them as a new game.
- Steam itself and legacy Big Picture use special handling. Gamescope source
  maps a window marked `STEAM_BIGPICTURE` to AppID 769. That makes 769 suitable
  for compatibility with a persistent custom shell only as a convention, not as
  an authoritative “game running” value. It risks conflating shell, Big Picture,
  and any custom client that adopts it.
- All behavior above is source-confirmed, but the behavior of the installed Lulu
  invocation with real Steam windows is still a hypothesis because `--steam` is
  currently absent.

## Recommended experiments

Run these as a separate probe session, with no production behavior changes, and
capture timestamped X11 events, root-property snapshots, window properties,
`_NET_WM_PID`, `WL_SURFACE_ID`, process/cgroup state, and Gamescope logs:

1. Establish baseline with Lulu shell only; verify whether a harmless test
   window with `STEAM_GAME=769` is selected in the current invocation. Repeat in
   an isolated Gamescope invocation with `--steam` to separate deployment from
   Gamescope semantics.
2. Test one Proton game and one native Linux game, recording window creation,
   property timing, focus-property changes, process/cgroup identity, and exit.
3. Repeat with a game launcher, a Steam launch-option dialog, overlay open/close,
   and a game that recreates its main window. Test multiple simultaneous windows
   for one AppID.
4. Compare `GAMESCOPE_FOCUSED_WINDOW`, `GAMESCOPE_FOCUSED_APP`, and PipeWire
   focused-App metadata against the actually displayed surface. Include Steam
   Big Picture and Steam idle states.

## Implication for a future lifecycle supervisor

Do not make `STEAM_GAME=<appid>` the sole authoritative primitive yet. The
likely design boundary is an event-driven X11 observer plus Gamescope focused
root-property snapshots, correlated with session/process identity and tolerant
of XID/surface recreation. `STEAM_GAME` can become the AppID attribution signal
after the experiments establish that Lulu runs Gamescope in the required Steam
mode and that the observed transition matrix is stable. Keep 769 provisional
and avoid using it as proof that a real game is running.

## References

- This deployment snapshot: Gamescope 3.16.25, observed command and X11 properties on
  2026-09-09.
- ValveSoftware/gamescope source: `src/steamcompmgr.cpp`, `src/main.cpp`, and
  `src/Utils/Process.cpp` at the current upstream checkout.
- ValveSoftware/gamescope README: embedded Xwayland model and command options.
- ChimeraOS/gamescope-session README: `STEAM_GAME`, 769, `gamescope-fg`, and
  Gamescope session conventions.
- ChimeraOS/gamescope-session-steam session definition: Steam session environment
  and `CLIENTCMD` convention.
