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

Do not deploy if any precondition is unknown. Validation on 2026-10-11 found an
inconsistent Rocket League removal job in Acquisitiond, a not-ready Sessiond
shell presentation, and no connected controller. Read-only source and
capability checks subsequently established that official Aurelia 0.1.37
provides the Mudos-required interfaces also present in 0.1.38; the version
difference is not a deployment blocker. No activation was attempted. Reconcile
the orphaned job only through an approved reversible path, restore the physical
display/controller, then rerun the guard during a safe window.
