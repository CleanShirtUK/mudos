# Aurelia Steam update lifecycle

**Status: update lifecycle baseline deployed; platform-aware adapter changes are
source-only and pending Aurelia contract integration; physical acceptance
pending.**

## Platform-selection and provider-contract work (source-only)

Steam installation selection is now explicit in Mudos source. The Installable
surface asks Aurelia for depots with explicit OS metadata, offers only verified
Windows/Linux choices, skips the chooser for one verified option, and creates no
job for Cancel or unknown metadata. Acquisitiond persists the selected platform
in the provider-owned job, rejects conflicting active submissions, and allows
retry only when the saved platform matches. Aurelia installation receives
`--platform windows|linux`; install reconciliation rejects an unknown or
mismatched installed platform. Existing installations are not migrated.

The Mudos update adapter has been changed to require an Aurelia per-AppID
`platform-state` response containing installed and target depot→manifest maps.
It rejects unknown/conflicting state and only completes an update when Aurelia
reports `current` after execution. Update intent semantics are preserved:
background work remains background-only, including on recovery.

This adapter change is deliberately not activated: production Aurelia 0.1.38
does not expose `platform-state`. A separate Aurelia source branch contains a
candidate contract with explicit platform persistence, strict platform
selection, installed-platform mapping from appmanifest depots, target manifests,
and pre/post-update convergence checks. It passes compile and focused unit
tests, but has not been integrated, released, or activated. The candidate source
is based on the public v0.1.38 tag, and no writable upstream fork was available
or contribution PR created. The local candidate commit is `e5671cd`
(`Add platform-aware Steam update evidence`). Mudos' production check/update path therefore must
remain unchanged until that contract is reviewed and supplied by Aurelia.

## Provider contract observed

The installed Aurelia CLI documents `aurelia update [APP_ID]` as an update
operation and, with no AppID, a report of installed games with available
updates. Its JSON report includes `updates` and `pinned` arrays. The report is
read-only and performs remote manifest checks; ordinary installed catalogue
`update_available` fields are not used as freshness evidence. Mudos coalesces
checks and caches the result for 90 seconds; check failure is `unknown`, never
`current`, and the command has a 25-second bound.

For the deployed baseline, Aurelia is the only update authority. The job is persisted by
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

Automated source validation and QML parsing passed for the deployed baseline.
The new source-only platform work has focused Python, QML syntax/lint, Aurelia
compile, and platform-selection unit-test coverage. No production Aurelia binary
was replaced and no deployment was performed for this milestone. Target-device
controller acceptance remains pending; online deployment also remains blocked
on a fail-closed Sessiond/Acquisitiond idle guard under `RELEASE-SAFETY-001`.
