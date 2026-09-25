# Mudos Recovery Foundation — Milestone 1

## Trust and process boundary

`mudos-recovery.service` is a loopback-only recovery authority. It starts from
`multi-user.target` and has no dependency on the graphical Mudos session,
Sessiond, Consoled, Acquisitiond, Gamescope, Admin, or network-online.
`mudos-recovery-ui.service` is a separate VT 2 presentation unit that conflicts
with the normal session only when explicitly started. The session's
`OnFailure=` guard starts that UI after the existing three-failures-in-five-
minutes threshold is reached. The guard does not clear failure evidence.

The controller-plane HTTP listener binds only to `127.0.0.1:38124`; it is not
available to another LAN host. Its POST body accepts only `action_id` and
`confirmed`. Action IDs map to fixed units or fixed power operations; callers
cannot select commands, paths, units, arguments, or D-Bus destinations. Every
mutation requires `confirmed: true`. The service runs as `lulu`, and polkit
grants only the exact systemd verbs/units needed by the recovery control/UI
path. The action API also requires a random installation-local bearer token
stored in `/etc/lulu/mudos-recovery-token`, owned by root and readable only by
the `lulu` group. Admin and the standalone UI receive the token through their
service environment; unauthenticated loopback clients cannot issue mutations.
It is not a general command proxy.

Admin remains available as the network/remote read-and-act client. Recovery
mutation routes now require an established Admin password, authenticated
session cookie, and matching `X-CSRF-Token`. An unconfigured Admin page is
read-only. This keeps the useful remote portal while removing the previous
unauthenticated LAN mutation path. The control plane listener remains
loopback-only. The installation-local token is available only to the
appliance-account services and root; compromise of that account is outside
this HTTP boundary.

The standalone UI uses the existing native `lulu-shell` SDL controller bridge,
but sets `LULU_RECOVERY_STANDALONE=1` so controller dispatch does not wait for
the normal Sessiond presentation state. The bridge itself does not require
Sessiond for SDL enumeration, D-pad/action dispatch, or reconnect scanning.
The UI reads and mutates only the recovery control-plane API.

## Initial normalized evidence

`GET /v1/status` returns schema version, overall state, failure history, and
per-component state, summary, observation time, freshness, evidence, redacted
error, safe actions, and impact. Service process state and owner API health are
separate evidence. Unknown/unavailable evidence is represented as `unknown`,
not inferred healthy. Acquisition snapshot count is included only when its
owner API answers. No credentials are loaded for diagnostics.

Initial observations cover the graphical session/Sessiond, Consoled,
Acquisitiond, Admin, InputPlumber, NetworkManager connectivity, BlueZ,
Questarr, Transmission, NZBGet, InputPlumber controller inventory, and basic
free-space on system/home/game roots. Restart actions are initially limited to
Mudos, Consoled, Acquisitiond, and Admin. Power and every restart action have
impact metadata; power actions require explicit confirmation in the local UI
and the authenticated Admin UI.

## Failure handling

The existing failure-history threshold remains authoritative. Sessiond no
longer clears it before a user-requested restart; its existing stable-session
clear remains the success path. On session failure the systemd guard checks
that persisted threshold before starting the independent UI. The standalone UI
conflicts with the normal session on VT 2, ensuring it does not contend for
DRM/VT while the normal session is healthy. Restart Mudos stops the recovery
presentation through that conflict and starts the exact session unit; if the
session fails again, the guard can present Recovery again.

## Known limits in this milestone

- The recovery UI still requires the Linux graphical/DRM/seat path and a
  connected display. TTY/Debug Mode boot and bootloader controller support are
  not implemented here.
- NetworkManager and provider states are observed, not repaired.
- NZBGet API health is represented by unit state because its API requires
  credentials; credentials are deliberately not read by Recovery.
- Filesystem health is not checked or repaired; only free-space/path
  availability is reported.
- InputPlumber inventory reports its canonical GamepadOrder; no controller
  reassign/player mutation is introduced.
- Restarting Mudos may terminate delegated applications and cycle Consoled and
  Acquisitiond. Acquisition job reconciliation remains the responsibility of
  those owners.
- Admin HTTP remains bound to all interfaces for the existing web portal;
  only recovery mutations now require Admin authentication and CSRF. The
  control plane itself is loopback-only.
