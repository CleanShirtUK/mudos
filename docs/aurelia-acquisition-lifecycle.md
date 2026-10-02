# Experimental Aurelia acquisition lifecycle

This note records the lifecycle of the opt-in `steam-aurelia` acquisition
adapter. Aurelia remains an experimental acquisition backend; this does not
enable it system-wide, change the production Steam/SteamCMD provider, or connect
launch to Sessiond. Plaintext Aurelia session persistence remains the explicit
temporary POC trade-off documented in `aurelia-auth-storage.md`.

## Daemon ownership and endpoint

The pinned Aurelia source at
`50c44d33b97f4aee6fe694e90c464951970d9fd8` describes a persistent daemon that
holds one Steam CM session and serves ordinary CLI commands over local IPC.
Normal CLI commands connect to the daemon and auto-start it if unavailable;
the child is detached from the short-lived CLI process, so it normally remains
after that command exits. `aurelia daemon list` and `aurelia daemon stop [PID]`
are local process-management commands. The daemon has an Aurelia-provided
version/PID marker next to its socket, but there is no lock keyed by
`AURELIA_CONFIG_DIR`.

On Unix, the endpoint is selected in this order:

1. `AURELIA_DAEMON_SOCKET`, when explicitly set;
2. `${XDG_RUNTIME_DIR}/aurelia-${uid}.sock`;
3. `${TMPDIR:-/tmp}/aurelia-${uid}.sock` when no XDG runtime directory exists.

Consequently, a single Aurelia config directory can be used by more than one
daemon if callers use different runtime/socket environments. Conversely,
separate configs under the same uid and socket share the daemon process/session.
The daemon server checks for a listening instance before binding and checks
again on bind failure, but its Unix listener removes a stale socket path before
binding; the upstream source does not implement an OS-level instance lock.

Mudos Acquisitiond has `XDG_RUNTIME_DIR=/run/user/958`. Its Aurelia adapter now
normalizes that runtime and the corresponding default socket explicitly, and
serializes the first auto-starting request within the single Acquisitiond
adapter instance. The opt-in provider's 3-second external-job reconciler is the
first operation that normally starts the daemon; it does so only when the
plugin registers the experimental executor. Health/status and job commands
then use the same endpoint. The adapter does not stop an idle daemon on each
command.

The observed processes were not three copies of one appliance daemon:

- PID `2982749` was the Acquisitiond-owned `lulu` daemon on
  `/run/user/958/aurelia-958.sock`, inside
  `/system.slice/lulu-acquisition.service`.
- PID `2971218` was an idle interactive-shell `lulu` daemon on
  `/tmp/aurelia-958.sock`; its caller omitted `XDG_RUNTIME_DIR`. Its install
  list was empty. It was retired with Aurelia's PID-scoped `daemon stop`, not
  killed directly.
- PID `2928856` was a different-uid `josh` daemon using its own config and
  `/run/user/1000/aurelia-1000.sock`; it is not the `lulu` session.

The service uses systemd's default `KillMode=control-group`. On Acquisitiond
restart/stop, systemd reaps the daemon and any CLI children in that service
cgroup; the next enabled-provider command starts a replacement, which restores
the session from Aurelia's persistent state. A daemon that independently exits
while Acquisitiond remains up is started again by the next CLI request. Thus
the intended Mudos model is one authoritative daemon per the service's fixed
runtime socket, scoped to Acquisitiond's systemd lifecycle—not a daemon per CLI
request and not one daemon per config directory.

## Acquisition progress and durable job fields

The official Aurelia install progress event is emitted as NDJSON on stderr with
these top-level fields:

```json
{"event":"progress","state":"downloading","bytes_downloaded":123,"total_bytes":456,"percent":26.97,"depot_id":1,"depot_bytes_downloaded":123,"depot_total_bytes":456,"depot_percent":26.97,"speed_bps":1000,"eta_seconds":1,"file":"..."}
```

The exact values depend on the game/depot; `queued`, `downloading`,
`verifying`, and `moving` are the progress phases. The terminal install result
is separate JSON on stdout (`event=result`, `status=installed`, `app_id`); it
does not contain the install destination. Aurelia's installed-game listing
reports `install_path`, which is the evidence-backed source for Mudos' final
destination. `install list` reports active `app_id`, `name`,
`downloaded_bytes`, `total_bytes`, `percent`, `status`, and `is_downloading`.

Mudos' `DownloadJob` and SQLite store already represent/persist provider job
identity, bytes, normalized progress, rate, ETA, provider state, destination,
completion path, and backend. The adapter already read the progress stream and
passed the counters to `JobReporter`, but its final progress update supplied
default `None` byte counters, replacing the values just before persistence.
That finalization now preserves the last Aurelia byte totals. On successful
completion, the adapter also persists AppID/backend/provider state and the
`install_path` returned by Aurelia when available; it does not invent a path.

## Cancellation and restart boundary

`aurelia install stop APPID` returns an `event=stopping` acknowledgement after
setting Aurelia's abort flag; that response alone does not mean the operation
has stopped. Mudos now polls `install list` until the AppID disappears before
returning from its provider cancellation handler. Acquisitiond transitions to
`cancelled` only after that handler returns and the CLI progress relay is
cancelled. The controlled runtime cancellation test remains a required gate.
Upstream's install operation preserves partial files; this adapter does not
delete them. A cancellation test must inspect only the selected test AppID's
files and manifest.

An active acquisition does **not** currently survive an Acquisitiond restart
as an adoptable Aurelia job with the pinned official CLI. Acquisitiond and its
Aurelia daemon are in the same systemd control group, so a service restart
terminates the daemon/runtime along with the D-Bus service. Separately, if a
forwarded install command's client disconnects while the daemon is still alive,
Aurelia's server aborts that command future; dropping its `InstallGuard` raises
the install abort flag and removes the AppID from the daemon's active-install
registry. The store recovers the Mudos job as queued, but `install list` can no
longer prove/adopt that work. Blind resubmission could race with provider-side
partial files. Therefore active-job restart/adoption is not claimed or tested
until a separately reviewed persistent job runner or an upstream CLI lifecycle
change exists. A completed job and the persisted authentication session do
survive Acquisitiond restart.

## D-Bus timeout investigation

The earlier post-install D-Bus timeouts did not correspond to an Acquisitiond
crash, restart loop, provider-registration failure, or recorded service error.
After restart, concurrent `GetActiveDownloadCount`, `GetSnapshot`, and
`GetAureliaBackendStatus` calls completed in 9–16 ms; the snapshot was about
79 KB, with 60 job rows and about 5.7 KB of aggregate origin metadata. The
timeouts could not be reproduced safely with no active install. No arbitrary
D-Bus timeout increase was made. Their precise cause remains undetermined and
should be revisited if they recur with timestamps and service/D-Bus diagnostics.
