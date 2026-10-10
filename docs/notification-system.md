# Mudos notifications

Notifications are session-scoped transient events, not persistent records or a
history. Consoled owns the single FIFO presentation queue and the passive
`mudos-notification` process. Both shell-originated feedback and normalized
acquisition events enter that same queue, so their windows cannot overlap.
Queue state is intentionally discarded on restart.

## Event ownership and routes

Acquisitiond's `NotificationBroker` observes authoritative JobManager
transitions and retains the acquisition vocabulary and deduplication key
`job_id:event_type`. It emits `download_started`, `download_finished`,
`installation_succeeded`, and `acquisition_failed`; it seeds current jobs at
startup so historical jobs are never replayed. Provider adapters do not call
notification APIs. Acquisitiond forwards each normalized event to Consoled's
`Notify` D-Bus method; it does not own a presenter.

The shell's narrow `POST /notification` route is handled by
`console-ui-bridge.py`, which validates/forwards through its mandatory Consoled
proxy. The bridge never starts the presenter. Shell events receive generated
monotonic event IDs and are not globally deduplicated, so repeated legitimate
operations (such as two manual refreshes) remain distinct.

## Severity, lifetime, presentation

The accepted severities and automatic lifetimes are fixed: `info` 4 seconds,
`success` 4 seconds, `warning` 6 seconds, and `error` 8 seconds. Payloads require
a non-empty title (at most 120 characters), non-empty body (at most 320
characters), and a known severity. The API does not accept executable paths,
icon paths, or caller-selected lifetimes. Dismissal is automatic and passive;
there is no focus, controller action, dismiss button, or history.

The sole presenter is an external Gamescope overlay using
`WindowTransparentForInput`; it does not own controller input or change focus.
`MudosNotification.qml` communicates a concise title, body, and semantic
severity marker using palette roles. Theme IDs are not inspected. Presenter
launch/write failures are logged and do not fail the originating operation;
queue processing continues. Consoled closes its child on service shutdown and
discards queued transient state on restart. Dismissal is enforced inside the
presenter QML using each event's bounded severity duration; it does not depend
on Consoled remaining alive to send a later hide command. EOF on the control
pipe also hides and exits the presenter, so an orphan cannot retain its last
visible model indefinitely.

## Status-strip geometry handoff

The shell maps the live `SystemStatusStrip` bounds into shell-window coordinates
and publishes them through the existing local HTTP bridge. The bridge validates
the coordinate space, viewport/display dimensions, scale and session token,
then atomically replaces the private
`$XDG_RUNTIME_DIR/mudos-status-geometry.json` record. The native presenter
watches the runtime directory (including atomic rename updates), loads the last
valid record at startup, and retains it while the shell is hidden over a game.
Placement is computed from the actual status-strip right and bottom edges; if
the record is invalid or the notification cannot fit below the strip, the
notification is not shown at a guessed location. Resolution and scale changes
cause the shell to publish a replacement record.

## Shell message inventory (NOTIFICATIONS-001)

Only completed, useful results move to Notifications. Immediate confirmation
prompts remain in the shell's dedicated `interactionPrompt` presentation:
“Press X again to remove …” and “Press A again to confirm …”. Launching,
Running, Returning, utility-launch start, Steam-install handoff, and reset
choreography remain internal lifecycle state and are not notified. Detailed
status/errors remain in their owning Settings, credential, browser, Lutris,
Downloads, and other in-surface components. In particular, acquisition submit
and browser-handoff messages are not duplicated: JobManager transitions are
the global acquisition feedback authority.

Migrated shell results include catalogue/library refresh (success), manual
metadata/Downloads refresh, application launch failure, Bluetooth completion,
credential submission failure, RomM/SteamCMD authentication results, Store
bookmark/name/URL mutations, and onboarding network-connected completion.
The explicit Settings library refresh reports its success/failure; startup and
background catalogue reconciliation stay silent. The generic bottom-right
`root.message` hint-band rendering is removed. The property remains internal
for launch/choreography and unrelated transitions, not as a transient feedback
surface.

Producer-by-producer disposition: refresh results and `request()` launch
failures are passive events; the “Launching application…” utility status and
launch state `Launching`/`Running`/`Returning` are choreography only. Bluetooth
start text was removed and success/failure results are events. Credential
surface-unavailable/rejected and auth completion results are events; credential
entry and provider-specific detailed error surfaces remain contextual. Settings
child messages such as display restart and storage selection/reset stay on
their Settings page. Store removal's “Press X again…” and destructive Mudos
actions' “Press A again…” are interaction prompts; completed bookmark mutations
are events. Game launch, Steam install handoff, reset status, and message clears
are lifecycle choreography. Library/manual metadata/download refreshes are
events. Lutris installation submission and browser acquisition handoff stay
local/are omitted globally because normalized acquisition transitions provide
the notice. Network-connected completion is an event; onboarding navigation
guidance remains local. Generic errors owned by Downloads, Lutris, browser,
Game Options, or a Settings page are not moved merely because the old shell
helper accepted a `failureMessage` argument.

## Deliberate limitations

Notifications do not pause downloads or replace detailed owning-screen
errors. Physical visual and passive-input validation remains distinct from
automated contract and component tests.
