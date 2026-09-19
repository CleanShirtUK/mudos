# Mudos Validation Log

This append-only log is authoritative for later hands-on validation. `PASS`
means the stated evidence exists; pending physical or live-service checks are
not implied to have passed.

## Controller reconnect hardening

- Commits: `1f1992a`
- Automated validation: PASS; runtime lifecycle validated
- Runtime activated: PASS
- Physical/controller validation: one successful physical reconnect cycle observed; intermittent earlier failure not reproduced; further recurrence observation pending
- Visual validation: pending
- Provider/live-service validation: pending
- Notes: observe for recurrence during hands-on session

## Downloads

- Commit: `423418f`
- Automated validation: PASS
- Runtime activated: PASS
- Physical/controller validation: pending
- Visual validation: pending
- Provider/live-service validation: pending
- Notes: physical controller/UI acceptance remains outstanding

## Managed OSK / credential ownership

- Commits: `75d67c7`, `f5c33d8`, `fb23a9c`
- Automated validation: PASS; service/runtime validation passed
- Runtime activated: PASS
- Physical/controller validation: pending Steam password and controller acceptance
- Visual validation: pending
- Provider/live-service validation: pending
- Notes: do not claim physical acceptance before hands-on test

## Failed downloads / Retry

- Commit: `769fa52`
- Automated validation: PASS; D-Bus RomM retry validated
- Runtime activated: PASS
- Physical/controller validation: pending
- Visual validation: pending
- Provider/live-service validation: live Steam retry validation pending
- Notes: controller retry and live Steam retry remain outstanding

## SteamCMD authentication persistence diagnostics

- Commit: `197b7383`
- Automated validation: PASS; instrumentation active
- Runtime activated: PASS
- Physical/controller validation: not applicable
- Visual validation: not applicable
- Provider/live-service validation: awaiting natural recurrence of unexpected authentication request
- Notes: no test login was performed

## IGDB metadata enrichment

- Commit: `6721edf`
- Automated validation: PASS; 362-test suite passed
- Runtime activated: PASS; mutable development runtime refreshed
- Physical/controller validation: not applicable
- Visual validation: not applicable
- Provider/live-service validation: pending live IGDB credentials and sample verification
- Notes: live IGDB credentials and sample verification remain pending

## ProtonDB metadata enrichment

- Commit: `6721edf`
- Automated validation: PASS; 362-test suite passed
- Runtime activated: PASS; mutable development runtime refreshed
- Physical/controller validation: not applicable
- Visual validation: pending future metadata presentation
- Provider/live-service validation: PASS; unauthenticated endpoint sample AppID `220` returned tier `platinum`, confidence `strong`, score `0.91`
- Notes: AppID-only scope; no ROM/title matching. Catalogue integration remains pending live configured run.

## Provider-owned uninstall flow

- Commit: pending
- Automated validation: pending
- Local disposable-ROM backend validation: pending
- RomM provenance preservation: pending
- Steam provider automated validation: pending
- Physical Game Options validation: pending
- Live Steam uninstall/reinstall: pending explicit acceptance cycle
