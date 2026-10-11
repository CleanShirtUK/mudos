# Guarded online deployment

Use `sudo /home/josh/src/lulu/scripts/guarded-deploy.py <release-dir>`
for online appliance deployment. `scripts/release.py` remains the low-level
immutable release builder, verifier, and atomic selector; its offline
bootstrap, recovery, and rollback use is intentionally not subject to a
runtime-idle policy.

The guarded entry point verifies the candidate, checks required system units,
queries Sessiond, Acquisitiond, and Consoled over `lulu`'s user D-Bus context,
and fails closed for missing or malformed evidence. Sessiond must report a
ready shell presentation with no active identity, token, or delegated/pending
surface; the isolated Steam runtime must be ready and authenticated, and at
least one controller must be connected. Every
Acquisitiond job is inspected by explicit state; the legacy
`activeDownloadCount` badge is not treated as a running-job count. The check is
repeated immediately before activation. This reduces, but does not eliminate,
the race with new work: there is no lifecycle maintenance lease spanning the
preflight and selector switch.

The Steam content-activity classifier in
`scripts/steam-ownership-guard-prototype.py` is diagnostic-only and is not part
of this guarded deployment path. Do not treat it as an additional deployment
gate or as an authoritative Steam idle API. Any future deployment-policy
change requires separate design and validation; filesystem isolation is not a
prerequisite for current platform-selection acceptance.

After atomic activation, the script restarts `lulu-session@2.service`,
`lulu-consoled.service`, and `lulu-acquisition.service` in that order, checking
each service's D-Bus boundary before proceeding, then polls overall readiness. A post-activation failure causes one
rollback to the prior selected immutable release and one restart attempt. If
rollback itself fails, both failures are reported; the script does not loop
restarts. Negative tests use temporary selectors and mocked commands and never
activate or restart production services.

Restart-probe D-Bus name acquisition is boundedly retried for up to 20 seconds;
the full preflight and post-restart readiness validation remain fail-closed.
Consoled and Acquisitiond are restarted and RPC-checked before Sessiond, because
the shell child introspects both during bootstrap. Sessiond is restarted last:
its `PartOf=` relationship restarts the isolated Steam runtime, and repeated
Sessiond startup failures otherwise propagate unnecessary Steam restarts.
This also ensures the runtime is restarted once per activation/rollback, rather
than while its shell dependencies are still coming up.
The overall post-activation readiness window is 180 seconds, matching the
isolated Steam runtime unit's `TimeoutStartSec=180s` and its authentication
wait budget; the guard never declares readiness until Steam is authenticated.

Do not deploy if any precondition is unknown. On 2026-10-11 the orphaned
Rocket League REMOVE row was reconciled offline after Acquisitiond was stopped
and its writer exited. Its original DB snapshot was backed up and verified;
the row is now a non-retryable diagnostic failure and Acquisitiond restarted
with no active jobs. The source recovery fix is committed, but still requires
guarded deployment. Read-only checks established that official Aurelia 0.1.37
provides the Mudos-required interfaces also present in 0.1.38; its version is
not a deployment blocker. Current remaining preconditions are a connected DRM
presentation output, Sessiond `presentation_ready=true`, and a connected
controller. Reassessed readiness on 2026-10-11: Sessiond is active in shell,
Steam is ready/authenticated, all required services are active, but the guard's
read-only preflight still refuses because it cannot confirm a connected
controller. Candidate
`/opt/lulu/releases/f7624b8-candidate-20261011164454` was built from clean,
committed source and checksum-verified; it remains staged and the prior
selection `/opt/lulu/releases/24acb93-candidate-20261011102738` remains active.
Request physical controller reconnection; do not bypass the gate or attempt
activation while the preflight fails.
No display/InputPlumber configuration changes may be used to bypass these
checks.

On the subsequent guarded recheck, the Xbox 360 receiver remained present
(USB `045e:0291`) and InputPlumber remained active, but Sessiond's composite
controller reported `connected=false`. The canonical
`guarded-deploy.py /opt/lulu/releases/f7624b8-candidate-20261011164454`
command refused with `Sessiond cannot confirm an available controller input`.
No activation or restart occurred. Reconnect/pair the controller physically,
then rerun the guarded workflow; do not alter controller/display configuration
to bypass readiness.
