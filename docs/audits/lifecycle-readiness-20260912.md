# Lifecycle Readiness Audit

Status: repository-derived audit, 2026-09-12. “Ready” means the authoritative
dependency evidence exists, not merely that a process has a PID or a D-Bus name.

## Readiness-State Matrix

| Trigger | Required readiness | Authoritative evidence | Timeout/failure behavior |
| --- | --- | --- | --- |
| sessiond startup | InputPlumber manager and composite topology can be queried | System-bus introspection of `org.shadowblip.InputPlumber` manager, then `GamepadOrder` and composite properties | Bounded D-Bus wait (5s); startup fails instead of presenting a shell with unverified controller routing |
| consoled startup | console-sessiond object is exported and callable | Sessiond object-path introspection, then catalogue refresh before consoled owns its bus name | Bounded D-Bus wait (5s); consoled does not publish a partially wired service |
| UI startup | consoled and sessiond APIs are callable; catalogue has completed its initial refresh | Bridge introspection of both object paths, followed by `Refresh` | Bounded D-Bus wait (5s); bridge exits without starting QML or HTTP surface |
| catalogue view | Response came from consoled and contains the current query result | Successful `ListGames`/`ListPlatformCategories` call; no PID heuristic | HTTP 503 is shown as unavailable; stale QML data is not replaced on failed request |
| Guide | Focused foreign window has a valid PID; controller event path is active | Gamescope focused-window property, `_NET_WM_PID`, and InputPlumber D-Bus event subscription | Guide is not started without a focusable foreign window/PID; action-level D-Bus failures are logged and the guide closes |
| provider launch | Provider has accepted the request and target process is observed | Steam client readiness poll, then AppID candidate process identity; local runtime child creation plus sessiond token | Bounded provider/process watchdog; failure returns lifecycle to shell and records a result |
| Store | Steam gamepad UI has a selectable Gamescope window before Store navigation is sent | Steam client process readiness plus `GAMESCOPE_FOCUSABLE_WINDOWS` matching a gamepad-ui PID | Bounded selection timeout; no Store lifecycle is presented if the window cannot be selected |
| return from game | Primary has exited and shell presentation/input routing has been restored | Process wait, shell window selection, and shell input-mode application | Cleanup is bounded where applicable; failures remain visible in lifecycle logs rather than claiming clean return |
| controller availability | At least one current composite has source devices and a navigation assignment | InputPlumber `GamepadOrder`, `SourceDevicePaths`, and registry reconciliation; native SDL gamepad state for shell events | Disconnect removes navigation ownership; UI remains non-interactive until a controller reconnects |

## Findings And Limits

- The bridge’s original D-Bus wait was correct but local to the bridge. It is now
  shared with consoled and sessiond so dependency consumers do not confuse a
  service name/object race with readiness.
- Steam client PID existence is only used as the prerequisite for client startup.
  Store presentation additionally waits for a focusable Gamescope window. There
  is no supported local acknowledgement that Steam has finished rendering the
  Store page, so that navigation remains an intent and is not overstated as page
  readiness.
- Catalogue data is authoritative only after consoled’s initial synchronous
  refresh. Later QML refresh failures preserve the last successful data and show
  the error path.
- Guide action availability is derived from focused-window context and current
  session state. The native guide has no synchronous readiness handshake for a
  provider’s own menu process; that remains a hardware/runtime validation risk.
