# Acquisition Job Service Foundation

`acquisitiond` owns provider-neutral acquisition jobs independently of the
shell and session lifecycle. Provider adapters register executors with its
`JobManager`; the service publishes complete JSON snapshots and normalized
state changes on the session D-Bus as `org.lulu.Acquisitiond`.

Steam and RomM executors are registered independently, each serialized at one
active job per provider. Steam cancellation remains unavailable. RomM jobs
stage streamed files and currently also advertise cancellation unavailable;
failed staging files are cleaned before the job is normalized as failed.

## Durable state

`acquisitiond` stores normalized jobs in
`$XDG_DATA_HOME/lulu/acquisition.sqlite3` (normally
`/home/lulu/.local/share/lulu/acquisition.sqlite3`). `LULU_ACQUISITION_DB`
may override this path for controlled validation. Timestamps are UTC ISO 8601
strings with millisecond precision and a `Z` suffix.

The SQLite database is a transactional recovery journal, not a scheduler.
Terminal jobs are retained in deterministic most-recent-first order with a
limit of 200 records; non-terminal jobs are never removed by retention.
Queued jobs resume scheduling after executors register. Jobs found in
`starting`, `transferring`, `finalizing`, `pausing`, `resuming`, or
`cancelling` during startup are recovered by operation type:

- Interrupted acquisitions and updates are queued with recovery reason
  `service-restart`, preserving their provider-specific adoption/reconciliation
  behavior.
- Every interrupted `REMOVE` fails closed as non-retryable with error code
  `orphaned-removal-incomplete`, stage
  `recovery-required-removal-outcome-unknown`, and recovery reason
  `service-restart-removal-unverified`. Original state, stage, timestamps,
  progress, provider state, and origin metadata are retained in error details.
  The job is terminal before executor registration and cannot be queued or
  retried automatically. A new, explicitly submitted removal still follows the
  provider's normal removal path.

Provider staging/content is not deleted by startup recovery. Aurelia removals
cannot be adopted because the supported CLI does not expose authoritative
removal task status. An outcome-unknown removal requires operator diagnosis;
startup must never issue a second uninstall to infer completion.

For a verified orphan while acquisitiond is stopped, the narrowly scoped
`reconcile_orphaned_remove()` maintenance helper in `lulu.acquisition_store`
creates and integrity-checks a SQLite online backup, requires an exact
expected-record match, then performs one checked transaction to record a
non-retryable `orphaned-removal-incomplete` failure with the complete original
row in diagnostic details. It invokes no provider and does not change game
content. The backup must be retained in protected maintenance storage; a
restore requires acquisitiond stopped, preservation of the reconciled database
for forensics, integrity-checking the backup, then replacing the database and
its associated WAL/SHM set from the verified backup.

Retries create a new job with a new ID, incremented `attempt`, and
`parent_job_id` pointing at the failed attempt. Active duplicate suppression
continues to use provider, content identity, and operation.

The native `SystemStatusBridge` now exposes the complete JSON snapshot as
`systemStatus.acquisitionSnapshot` and availability as
`systemStatus.acquisitionAvailable`. QML receives `acquisitionSnapshotChanged`
from the D-Bus `StateChanged` signal. The existing HTTP snapshot is retained
as a low-frequency resynchronization fallback (30 seconds), not the live
progress path. Service disappearance publishes an empty unavailable snapshot;
registration triggers an immediate resynchronization.

Jobs are currently in-memory. Restarting `lulu-acquisition.service` loses
queued and active jobs; no provider work is resumed or silently reconstructed.
The domain model deliberately has stable job IDs, provider correlation IDs,
structured errors, byte counters, and explicit lifecycle stages so a later
persistence/recovery layer can be added without coupling it to QML or
Gamescope.
