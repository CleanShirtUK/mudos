# Mudos Validation Log

This append-only log is authoritative for later hands-on validation. `PASS`
means the stated evidence exists; pending physical or live-service checks are
not implied to have passed.

## Torrent provider / Transmission

- Commit: `599a68c`
- Implementation: provider-owned Transmission 4.1 JSON-RPC adapter, durable
  torrent telemetry/artifact fields, restart reconciliation, path-safe delete,
  and provider configuration/provisioning.
- Provisioned version: `transmission-cli 4.1.3-2` from the Arch `extra`
  repository.
- Service: `lulu-transmission.service`, dedicated `lulu-transmission` user,
  enabled and active. RPC listens on `127.0.0.1:9091` and rejects unauthenticated
  requests with HTTP 401. Credentials are generated once and stored through
  `SecretStore`; working daemon settings are not tracked.
- Storage: `/home/lulu/Games/.acquisition/torrents/{incomplete,complete,metainfo,ownership}`.
  Transmission's daemon incomplete directory is separate from the completed
  per-torrent destination. No Steam, ROM, Lutris, or installed-game root is used.
- Automated validation: PASS; full suite and Transmission-focused tests pass.
  Coverage includes JSON-RPC 409 session negotiation, authentication headers,
  magnet/metainfo addition, duplicate hashes, normalization, file selection,
  restart queue recovery, status/progress/rates/ETA fields, ownership and
  traversal/symlink/outside-root deletion safety.
- Live magnet: PASS using the public-domain Big Buck Bunny test torrent
  (`dd8255ecdc7ca55fb0bbf81323d87062db1f6d1c`). It was added through the
  acquisition D-Bus service, received the `mudos` label, appeared in the
  normalized Downloads snapshot, reported progress/rates/ETA, and completed
  at the canonical complete root.
- Live pause/resume: PASS; pause stopped transfer and resume continued the
  same stable hash.
- Live completion: PASS; Mudos marked the acquisition `completed` while the
  daemon remained in provider seeding state. No catalogue/import/install action
  was performed.
- Restart recovery: PASS for Transmission daemon restart during an active
  acquisition; the job retained its hash and resumed observation after the
  daemon returned. acquisitiond service restart also requeued active jobs for
  provider reconciliation rather than converting them to generic failures.
- Remove/delete: PASS; remove deleted the daemon record while preserving the
  completed payload, and DeleteDownload removed only the labelled Mudos payload.
  An outside-root path was refused. Provider roots have an ACL for the Mudos
  service user because Transmission controls its own file modes.
- Questarr: pending future integration. The ownership contract is label-based:
  Mudos persists hashes and uses `mudos`; future Questarr jobs may use `questarr`.
  Mudos does not enumerate or delete unowned daemon torrents.
- Visual validation: pending; no styled UI work was performed. Existing
  provider-neutral Downloads UI remains the only presentation surface.

- Current implementation audit: PASS; Transmission 4.1.3-2 is provisioned as
  `lulu-transmission.service` with localhost-only authenticated RPC on
  `127.0.0.1:9091`. Mudos uses the `mudos` Transmission label and writes a
  hash-keyed ownership sidecar under `.acquisition/torrents/ownership/` with
  job/provider/content identity. Hashes, not numeric Transmission IDs, remain
  the persisted provider identity. Completed torrents are marked downloaded
  while Transmission may continue seeding; delete-local-data plumbing is
  available separately from normal cancellation. Physical end-to-end fixture
  validation remains pending.

## Mudos Transmission provider backlog completion

- Commit: see repository history for the implementation commit
- Package: Arch `transmission-cli 4.1.3-2`; daemon unit:
  `lulu-transmission.service`, running as `lulu-transmission` with state in
  `/var/lib/lulu-transmission`.
- RPC: authenticated JSON-RPC 2.0 on `127.0.0.1:9091/transmission/rpc`,
  whitelist and host-whitelist restricted to localhost. Credentials are mode
  0600 in the daemon settings and mirrored through `SecretStore`; no external
  RPC bind is configured.
- Acquisition layout:
  `/home/lulu/Games/.acquisition/torrents/{incomplete,complete,metainfo,ownership}`.
  Transmission receives `complete` as its download directory and uses its
  separate incomplete directory for staging. Completion means downloaded;
  seeding may continue after the Mudos job is completed.
- Ownership: every Mudos torrent carries the `mudos` Transmission label and a
  hash-keyed JSON sidecar in `ownership/` containing hash, Mudos job ID,
  provider, and content identity. Unlabelled torrents are never adopted.
- Normalized API: `TransmissionClient` owns RPC/session negotiation and
  normalizes hashes, state, progress, rates, files, errors, pause/resume, and
  remove operations. `TorrentProvider` is the JobManager executor boundary.
  Numeric Transmission IDs are never persisted.
- Recovery: persisted hashes are reconciled through `torrent_get`; active,
  paused, completed, missing, and non-owned torrents have deterministic
  outcomes. Recovered provider capability metadata is restored by executor
  registration.
- Test fixture: the public-domain Big Buck Bunny torrent,
  `dd8255ecdc7ca55fb0bbf81323d87062db1f6d1c`, previously validated through
  Transmission. New physical validation remains pending after this provider
  audit.
- Physical validation sequence: submit the fixture through acquisitiond; verify
  it appears in global Downloads; observe progress/rates; Pause; Resume;
  restart the Mudos graphical session; restart acquisitiond and verify hash
  reconciliation; complete and verify downloaded/completed while seeding may
  continue; submit a second fixture, Cancel, and verify cancelled disappears
  without Failed/Retry; exercise provider remove-without-delete and the
  backend delete-local-data path separately.

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

## Downloads retirement and controller viewport

- Commit: `d11fb5c`
- Backend semantics: `ClearFailedJob` marks only a terminal `failed` job as
  `retired`; the job row, error diagnostics, attempt number, and
  `parent_job_id` retry linkage remain persisted. The operation is idempotent
  and rejects queued, active, paused, cancelling, completed, and cancelled
  jobs.
- UI/controller action: X/options is `Clear` for a selected failed job; A
  remains `Retry`. Active and queued rows continue to expose only their normal
  pause/resume/cancel actions.
- Automated validation: PASS; coverage includes retirement
  persistence, retry lineage preservation, idempotent clear, terminal-state
  rejection, filtered retired rows, ListView selection following, and scaled
  card viewport margins.
- Physical validation sequence: open Downloads with Y; create or select a
  failed job; press X and verify `Clear`, then verify the row disappears; press
  X again or revisit the surface and verify no error; retry a separate older
  failed attempt and verify clearing the older row leaves the newer attempt;
  select the first row, repeatedly press Down through the last row, verify each
  card follows into view without clipping, then press Up back to the first row;
  verify first and last selected cards are fully visible; press B and reopen
  Downloads to verify normal back behavior and sensible selection/scroll state.

## Downloads provider mutation lifecycle

- Commit: `6b9d086`
- Steam pause: unsupported. SteamCMD is a foreground process without a safe
  provider pause/resume command in the current executor, so Steam jobs now
  advertise `pause_supported=false` and do not expose a fake Pause action.
- RomM pause: supported through cancellation of the streaming task while its
  provider-owned staging file is preserved; resume starts a fresh stream from
  the staged offset.
- Mutation states: `pausing`, `paused`, `resuming`, and `cancelling` are
  explicit normalized job states. User cancellation reaches `cancelled` and
  marks the row retired without normalizing provider exit into `failed`.
- Physical validation sequence: start a Steam acquisition and verify no Pause
  action is offered; cancel it and verify `Cancelling…`, then disappearance
  without Retry. Start RomM, pause and verify `Pausing…` then `PAUSED`, cancel
  while paused and verify immediate `Cancelling…` followed by disappearance;
  verify Resume is unavailable after cancellation. During each pending state,
  navigate to another row and verify selection does not snap back. Verify the
  selected card remains inside both horizontal and vertical viewport bounds.

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

- Commits: `4db1c41`, `939c341`, `b4bd2fb`, `7198d52`
- Automated validation: PASS; 368 tests passed
- Local disposable-ROM backend validation: PASS; temporary single-file and dedicated-directory fixtures were removed through `JobOperation.REMOVE`; outside-root, root/platform-root, symlink escape, neighbor preservation, and missing-path cases passed
- RomM provenance preservation: PASS by provider-boundary tests/design; removal resolves linked local content and never calls RomM mutation APIs
- Steam provider automated validation: PASS; provider-native `app_uninstall` command construction, canonical manifest ownership check, conflict handling, and no-filesystem-fallback tests passed
- Physical Game Options validation: pending
- Live Steam uninstall/reinstall: PASS at manifest/provider/catalogue level using AppID `263980` (Out There Somewhere). Remove job `job-a9d5047a63ac4f33b89ca6334a62ca74` completed; manifest disappeared and the row became available. Reinstall job `job-264e8703ef5a40cf84e5e5acdc2fbc90` completed; manifest returned and `CanUninstall` reported supported/installed.
- Historical caveat: the pre-`60b6523` acquisition path placed the payload at the configured force-install root while the provider treated the manifest as authoritative; corrected and revalidated below.

## Steam canonical install placement and update semantics

- Commits: `60b6523`, `24d69b1`, `46f1295`, `1da2ba0`
- Root cause: SteamCMD `+force_install_dir` is the application payload directory; passing the Mudos library root placed payload files directly under the library while still producing a manifest.
- Fix: Steam acquisition uses a provider-owned per-job staging directory, validates the Steam-generated AppID/`installdir`, then places only that staged payload under `steamapps/common/<installdir>` and moves the validated manifest into `steamapps`.
- Fresh/update split: a valid existing manifest plus canonical payload selects direct SteamCMD update/validation against that payload; otherwise the provider uses job-attributable staging and atomic same-filesystem promotion.
- Installed-state invariant: manifests with missing, escaping, or invalid `steamapps/common/<installdir>` payloads are no longer reported as installed.
- Existing inventory: AppID `15700` currently has a manifest without its canonical payload directory. Several legacy payload files/directories remain directly under the library root and are mixed (including `steam_appid.txt` for `263980` and a Waveform install script), so no heuristic relocation was performed.
- Live validation: AppID `263980` reinstalled through normal Mudos acquisition job `job-650bd7d8296541248e7fba1c8637bffd`; manifest `installdir=outtheresomewhere`, payload exists at `steamapps/common/outtheresomewhere`, catalogue/provider report installed, and Mudos launch reached the `game` lifecycle using Proton.
- Update-path validation: automated run coverage confirms an existing canonical payload is passed directly as `+force_install_dir`; no staging/fresh-copy promotion is used.
- Live update cycle: not repeated after the latest split because SteamCMD cached authentication expired and no managed Steam password was configured; the current installed title remains canonical and available for a future authenticated update check.
- Authentication observation: cached SteamCMD authentication was reused during the corrected reinstall. A later uninstall attempt prompted for a password after cached auth expired; the managed credential boundary remained active, but no password was configured/submitted and the job timed out without mutation.
- Physical/UI validation: pending.
