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

After atomic activation, the script restarts `lulu-session@2.service`,
`lulu-consoled.service`, and `lulu-acquisition.service` in that order, checking
each service's D-Bus boundary before proceeding, then polls overall readiness. A post-activation failure causes one
rollback to the prior selected immutable release and one restart attempt. If
rollback itself fails, both failures are reported; the script does not loop
restarts. Negative tests use temporary selectors and mocked commands and never
activate or restart production services.

Restart-probe D-Bus name acquisition is boundedly retried for up to 20 seconds;
the full preflight and post-restart readiness validation remain fail-closed.
This handles systemd returning before a restarted service has reacquired its
D-Bus name without treating a timeout or malformed response as readiness.
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
controller. No display/InputPlumber configuration changes may be used to
bypass those checks.
