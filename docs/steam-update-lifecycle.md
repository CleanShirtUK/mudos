# Aurelia Steam update lifecycle

**Status: source implementation in progress; not physically accepted or deployed.**

## Provider contract observed

The installed Aurelia CLI documents `aurelia update [APP_ID]` as an update
operation and, with no AppID, a report of installed games with available
updates. Its JSON report includes `updates` and `pinned` arrays. The report is
read-only and performs remote manifest checks; ordinary installed catalogue
`update_available` fields are not used as freshness evidence. Mudos coalesces
checks and caches the result for 90 seconds; check failure is `unknown`, never
`current`, and the command has a 25-second bound.

For execution Aurelia is the only update authority. The job is persisted by
Acquisitiond as `JobOperation.UPDATE`, keyed by `steam-aurelia:<AppID>`, and
deduplicated against active update jobs by AppID. Active install/remove
conflicts are rejected. The executor checks the Sessiond-owned current game,
checks the update/pin status again before submitting, and verifies after the
provider command that the update is no longer reported and the title remains
installed before marking completion. Successful completion triggers the
existing Consoled catalogue reconciliation path.

The observed CLI contract does **not** document update progress fields or a
safe cancellation operation. Update jobs therefore advertise no cancellation
or pause support. Progress remains indeterminate unless Aurelia's active install
registry provides measurable fields; those values are not fabricated. The
command is bounded to eight hours. Recovery first adopts an AppID still listed
as active by Aurelia; otherwise an ambiguous still-available update fails
closed rather than being automatically submitted a second time.

## User flow and safety

- A launch request checks update availability before invoking Sessiond. Current
  titles launch normally. Available titles present Update & Launch, Update in
  Background, and Cancel; unknown status offers retry or cancel, not a bypass.
- Update in Background submits no launch continuation. It never launches on
  completion, including after shell or Acquisitiond restart.
- Update & Launch holds an ephemeral shell intent. Leaving the wait surface
  revokes it and converts the job to background-only. Failure, cancellation,
  changed Sessiond ownership, a changed launch generation, and service restart
  all fail closed. Completion consumes intent before requesting one launch.
- Both `steam:<AppID>` and `steam-aurelia:<AppID>` project the same update job.
  Library and Recents use the shared card artwork overlay; Downloads labels the
  job as an update. Provider terminal failures remain visible in Downloads and
  the normal notification broker.

## Validation boundary

Automated tests use fake Aurelia responses and temporary state. No live game
update is started. Before physical acceptance, the operator should use a
disposable installed title with a known update and verify controller selection
of both update choices, progress/indeterminate artwork in Recents and Library,
return-to-Home behavior, and that background completion leaves the game
unlaunched. Do not use Get To Work or the five titles awaiting launch-path review
as update fixtures. Do not deploy during gameplay or another important update.

The UI still requires target-device/QML validation and this implementation has
not yet been released or activated.
