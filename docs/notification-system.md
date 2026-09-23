# Mudos notifications

Mudos notifications are session-scoped transient events, not a second
acquisition database or a notification history. `NotificationBroker` lives at
the normalized `JobManager` boundary in Acquisitiond. It observes meaningful
job transitions and emits generic events:

- `download_started`
- `download_finished`
- `installation_succeeded`

The broker seeds its state from existing jobs at startup, so completed or
active historical jobs are not replayed after a service restart. Each event is
deduplicated by `job_id:event_type` for the lifetime of the service. Provider
names are metadata only; providers do not call UI notification APIs.

## Presentation boundary

Home, Store, Settings, and the shell's QML status surfaces are below a
delegated Gamescope surface. The existing Guide is a modal external overlay
and owns controller input, so it is intentionally not reused for passive
notifications.

The v1 presenter is a separate `mudos-notification` process using the same
Gamescope external-overlay boundary as Guide, but with
`WindowTransparentForInput`. It presents one queued event at a time, keeps the
active surface and input owner unchanged, and dismisses automatically. The
presenter is transient: if it restarts, historical events are not replayed.

The current wording is deliberately concise: “Download started”, “Download
finished”, and “Installed successfully”, followed by the catalogue title or
“is ready to play”.

## Deliberate limitations

Notifications do not pause downloads, own navigation, expose history, or add
actions. “Pause downloads during gameplay” remains a future capability-aware
acquisition-policy feature requiring provider pause capabilities and a clear
distinction between policy-paused and user-paused jobs.
