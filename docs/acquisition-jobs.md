# Acquisition Job Service Foundation

`acquisitiond` owns provider-neutral acquisition jobs independently of the
shell and session lifecycle. Provider adapters register executors with its
`JobManager`; the service publishes complete JSON snapshots and normalized
state changes on the session D-Bus as `org.lulu.Acquisitiond`.

Steam and RomM executors are registered independently, each serialized at one
active job per provider. Steam cancellation remains unavailable. RomM jobs
stage streamed files and currently also advertise cancellation unavailable;
failed staging files are cleaned before the job is normalized as failed.

Jobs are currently in-memory. Restarting `lulu-acquisition.service` loses
queued and active jobs; no provider work is resumed or silently reconstructed.
The domain model deliberately has stable job IDs, provider correlation IDs,
structured errors, byte counters, and explicit lifecycle stages so a later
persistence/recovery layer can be added without coupling it to QML or
Gamescope.
