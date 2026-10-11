# Mudos Engineering Backlog

Status reconciled 2026-10-10 against canonical source `122db13` and subsequently
updated with operator physical acceptance and the Library dimension correction
on `dev`. This file is the current status authority. Detailed prior
investigations are preserved verbatim in
[`docs/backlog-archive-20261010.md`](docs/backlog-archive-20261010.md); newer
evidence and this reconciliation rationale are in
[`docs/backlog-reconciliation-20261010.md`](docs/backlog-reconciliation-20261010.md).

## Active defects

### STEAM-RUNTIME-OWNERSHIP-001 — Resident Steam mutates canonical game library outside Acquisitiond

**Status: OPEN · P1 · CONTENT-OWNERSHIP RISK TRACKED; ISOLATION DEFERRED.**
During operator acceptance of STEAM-PLATFORM-001 on 2026-10-11,
Steam's own `content_log.txt` recorded a previously queued Rocket League
(AppID 252950) download beginning at 13:02:20, before Mudos rejected the
13:05:18 installation request. The resident Steam client committed
Linux depot 252961 around 13:06:40-45 (5,997 updated files; approximately
10.8 GB staged). Steam then reported installed content in the appmanifest,
while Acquisitiond contained no corresponding new INSTALL/UPDATE job.
The failed UI request cannot have initiated this transfer. This is distinct
  from the earlier orphaned REMOVE and the newly fixed UI provider-identity
  routing error.

- **Evidence distinction:** confirmed: Steam resumed a previously queued update
  while Rocket League had an inconsistent installation (stub/partial manifest
  and content after repeated install/update/uninstall experiments) and
  independently modified its shared library. Unproven: that Steam routinely
  changes healthy, correctly installed Aurelia-managed games or overrides an
  explicitly selected Windows/Linux payload during ordinary startup/restart.
  The Rocket League incident alone does not establish that general claim.
- **Architecture decision:** retain this issue and the namespace prototype as
  fallback evidence. Filesystem isolation is **not a prerequisite** for current
  Mudos platform-selection acceptance; do not deploy the namespace restriction
  or resume disposable-Steam experiments in this work. The Rocket League
  incident remains real, but does not prove that healthy installations require
  isolation. Steam/Aurelia concurrent content-operation risk remains tracked.

- **Risk:** the authenticated Steam client on Xvfb :99 shares the canonical
  game library with Aurelia. Its autonomous download/update behaviour can
  change installed payloads and platform outside Mudos' explicit Windows/Linux
  selection and Acquisitiond's lifecycle, notifications, progress and
  gameplay/deployment idle checks. Deployment readiness currently treats
  Acquisitiond's idle job snapshot as sufficient acquisition evidence and
  may not detect Steam's own content activity.
- **Read-only evidence (2026-10-11):** `libraryfolders.vdf` registers the
  default `/home/lulu/.local/share/Steam` library (29 manifest files) and a
  second `/home/lulu/Games/Executables/steam` library labelled `Mudos Managed`
  (zero manifests). Aurelia is explicitly configured to use
  `PATHS.steam_library_root`, the default library, not that empty second root.
  Rocket League's manifest is in the default library; its payload is
  `steamapps/common/rocketleague`. Both paths are on the same writable Btrfs
  home subvolume, owned by `lulu`; Steam and Aurelia run as `lulu`, so Unix mode
  bits cannot distinguish their writes. Steam itself has write access to the
  appmanifest, `downloading/252950`, and `common/rocketleague`.
- **Observed queue origin:** Steam's log says `Priority Auto Update`,
  `update disabled for 0 seconds`, followed by download of depot 252961. The
  prior interrupted update was retained in Steam's own schedule while
  suspended; after client startup it resumed and later committed
  `steamapps/downloading/252950` into `common/rocketleague`. The local app
  manifest had `StateFlags=2` (Update Required) before completion; after commit
  it has `StateFlags=4`, `AutoUpdateBehavior=0`, and the Linux depot. Global
  `AutoUpdateWindowEnabled=0` is present, but did not prevent the observed
  scheduler operation. Logs establish the automatic scheduler as the immediate
  cause; they do not establish which earlier event originally queued the
  update. The selected active depot was Linux 252961, not Windows/Proton.
- **Steam launch dependency:** Aurelia 0.1.37 starts `aurelia play <AppID>
  --steam --no-update --script <wrapper>`. `--steam` explicitly bridges to the
  resident host Steam client for Steamworks (and the documented DRM/auth
  integration); `--no-update` suppresses Aurelia's pre-launch update check.
  Aurelia uses the canonical appmanifest/library to enumerate installed games,
  check update manifests and launch. The Steam client is therefore still
  needed, but no evidence says it needs write access to managed game payloads
  for authentication, DRM, or Steamworks. Actual read-only-launch compatibility
  remains to be proven with disposable fixtures.
- **Fallback proposal (not yet justified for deployment):** a per-service systemd mount-namespace
  boundary for `lulu-steam-runtime.service`: expose the canonical managed
  `steamapps` view read-only to every Steam process in its cgroup, while
  keeping Aurelia/Acquisitiond's host view writable. Do not rely on
  `AutoUpdateBehavior`, download-window settings, UI hiding, or `--no-update`
  as an access-control boundary. Determine in isolated fixtures whether Steam
  needs narrowly scoped writable client state (e.g. shader/compat data) and
  whether it can launch already-installed native and Proton titles with the
  manifests/content read-only. If this is incompatible, stop and design a
  distinct client library plus explicit read-only launch view; do not weaken
  the boundary ad hoc. This mount-namespace design is a proposal, not yet
  proven or approved for the live appliance.
- **Synthetic prototype result (2026-10-11):**
  `scripts/steam-ownership-prototype.py` used uniquely named transient systemd
  units and a disposable library under `/tmp/opencode`; no persistent unit or
  production path was used. The successful profile was `ProtectSystem=strict`,
  `BindReadOnlyPaths=<fixture>/steamapps:<same path>`, and distinct tmpfs
  exceptions at the fixture's `steamapps/shadercache` and `compatdata`. Actual
  `/proc/self/mountinfo` from the transient unit showed an RO root and only
  those expected RW children. Payload append/replace, appmanifest rewrite,
  stage create/rewrite, commit, internal/external symlink writes and child
  process writes failed. A hardlink from payload to writable runtime state
  failed with `EXDEV`. A simulated host Acquisitiond write to the same payload
  succeeded outside the unit's mount namespace.
- **Hostile mount test:** a second disposable unit intentionally overlaid
  `steamapps/downloading` with an RW bind. In that case the stage write
  succeeded, demonstrating that a RO parent alone is insufficient. The
  prototype mount validator inspected the actual nested mount table and refused
  it as `writable child mount defeats protected root`. Synthetic regression
  tests also reject missing/duplicate/writable roots, unapproved RW children,
  missing exceptions, unexpected Steam cgroup processes, nested helper
  namespaces without their own RO proof, and unknown/active content-operation
  evidence.
- **Prototype limit / updated proposal:** the test's `ProtectSystem=strict`
  makes host paths read-only, and the shader/compat tmpfs exceptions are
  ephemeral. They prove systemd enforcement only; they are not suitable live
  Steam state. A live profile needs persistent writable client/auth/log/runtime
  state and Proton/shader state isolated on separate filesystems/subvolumes so
  hardlinks cannot lead back to managed content. Current Steam session/config,
  client binaries, logs, caches and game trees share `/home` storage. Exact
  writable paths and normal Steam startup/self-update behavior remain
  unproven. Do not simply add same-filesystem `ReadWritePaths` exceptions.
- **Guard prototype:** unintegrated helpers in
  `scripts/steam-ownership-guard-prototype.py` parse real mountinfo, validate the protected
  tree and declared exceptions, examine fixtures for each process/cgroup/mount
  namespace (including pressure-vessel-style nested namespaces), and classify
  Steam content-log/staging evidence as active/idle/unknown only when the
  collector asserts freshness. Six deterministic
  tests pass. The existing `scripts/guarded-deploy.py` is unchanged; no new
  check is enabled against the current production service. Active/queued,
  missing, stale or contradictory evidence must block once a boundary is
  installed and individually validated in each namespace.
- **Disposable real-client compatibility (2026-10-11; partial):** on Lulu, a
  dedicated `steamstage1` Unix account used a separate HOME and Steam config,
  Xvfb `:190`, private D-Bus/runtime state, and separate Btrfs client/library
  subvolumes in transient systemd units. Production Steam remained active and
  no production service, library, credential file, manifest, or game was used.
  The operator authenticated the existing account in the isolated client; one
  clean client restart returned to the signed-in UI. Steam self-update completed
  in the isolated client subvolume. A disposable Braid Linux build (AppID 26800,
  about 164 MB) rendered natively in the unrestricted baseline.
- **Real read-only launch findings:** with `steamapps` read-only and only
  persistent, separate `compatdata`/`shadercache` subvolumes writable, launch
  failed because Pressure Vessel needed its runtime `.ref` and per-run temporary
  state under `common/SteamLinuxRuntime_soldier`. Individual `.ref` file binds
  were insufficient. A later run with that Steam Linux Runtime package on its
  own writable Btrfs subvolume launched and rendered Braid while the game tree,
  appmanifest, and staging directories remained read-only. This is a substantial
  extra writable runtime exception (about 673 MB in this fixture), not an
  approved production layout. Steam logged repeated failed appmanifest writes
  while the read-only game was running; the client remained active without a
  systemd restart loop. Steamworks/DRM were **not proven**: Braid reported that
  its Steam API was not loaded and the overlay did not appear.
- **Write-authority evidence:** in the real restricted namespace, opening the
  game payload, appmanifest, and a new staging path for writing returned
  `EROFS`; hardlinking payload into writable runtime state returned `EXDEV`.
  A separate host-side simulated acquisition process wrote a marker into the
  disposable game directory; Steam could read but not overwrite it, and the
  host removed it. Actual mountinfo showed the `steamapps` root `ro` and only
  the explicit runtime-state subvolumes `rw`. Real Proton, real update/retry,
  real game-manifest rewrite scheduling, Steamworks/DRM, Aurelia launch,
  controller input, and full process-namespace enumeration remain untested.
- **Diagnostic security hardening (2026-10-11):** the real-client task was
  paused after a diagnostic command emitted credential-bearing connection-log
  material in a tool result. The isolated client was signed out in its UI,
  stopped, and its dedicated client/library subvolumes, temporary Unix account,
  and test bridge/export directory were removed. No credential text was added
  to repository files, commits, or retained test exports; the tool transcript
  itself cannot be retracted. Production `lulu-steam-runtime.service` remained
  active with the same invocation and zero restarts. `steam_auth_status.py`
  now reduces appended log bytes to allowlisted status enums only; the Steam
  supervisor discards child stderr, the lifecycle probe no longer emits raw
  argv, and the auth-surface harness projects D-Bus responses and uses static
  errors. Synthetic secret-bearing regression tests cover those output paths.
  The client has now been rebuilt in an empty test subvolume; the operator
  authenticated through the isolated login surface.
- **Stage 1 login environment prepared (2026-10-11):** recreated a fresh
  `steamstage1` account with independent client and disposable-library Btrfs
  subvolumes. Its transient systemd namespace uses `ProtectHome=tmpfs` and
  exposes only the test HOME/library; the production Steam HOME is explicitly
  required to be absent inside that namespace. The test `steamapps` tree is a
  read-only bind. Writable `compatdata`, `shadercache`, and the additional
  `SteamLinuxRuntime_soldier` runtime are separate Btrfs subvolumes mounted at
  exact child paths; their storage is outside the protected library subvolume.
  The runtime remains a required, deliberately narrow exception based on the
  earlier Braid launch evidence, not permission to write game payloads.
- **Boundary self-check:** before Steam starts, the isolated runner verifies
  mount modes, payload and staging write denial (`EROFS`), runtime-state write
  success, cross-subvolume hardlink denial (`EXDEV`), and that a symlink from
  writable compatibility state cannot write to protected payload. The check
  passed. The only test content is a synthetic marker; no game was downloaded
  or installed in this fresh fixture.
- **Login viewer:** the isolated Xvfb `:190` login UI is served over a private
  Unix socket, not a host TCP listener. The socket is accessible to the operator
  account and rejected connections from `steamstage1`; access/request logging
  is disabled, keyboard text is not persisted or passed in child argv, and
  Steam stdout/stderr are discarded. Use an SSH local forward to the remote
  socket, then open `http://127.0.0.1:18765/`. The operator has authenticated;
  all subsequent work remains inside this disposable client/library.
- **Post-login safety checks:** the hardened `steam_auth_status.py` classifier
  returned only `authenticated` for the isolated connection log. No raw
  connection log or authentication response was displayed. Steam Cloud was
  disabled through the isolated client settings before any game launch; a
  narrow parser returned one Cloud boolean, `0`, and the setting remained off
  after an isolated-client restart. Production Steam settings were not touched.
- **Runtime-state persistence:** wrote synthetic canaries through the isolated
  namespace to the separate compatibility, shader-cache, and Steam Linux Runtime
  subvolumes. All three survived an isolated service/client restart and were
  then removed. This validates persistence for those writable exception mounts,
  not Proton prefix correctness or game launch.
- **Game acquisition currently blocked:** requested disposable Braid (26800)
  and Spacewar (480) installs through the authenticated Steam client, but no
  appmanifest or staged game content appeared. No game was launched. The library
  has been returned to the read-only profile; Steam is active in that protected
  namespace with the production HOME hidden. Earlier successful Braid native
  launch evidence remains valid, but Proton, Steamworks/DRM, a real autonomous
  update attempt/denial, and real game-backed persistent-prefix checks remain
  incomplete pending a successful disposable install.
- **Clean-install experiment:** not performed and deferred. The prior
  Steam-client installation did not produce a usable Braid/Spacewar install;
  the later clean Aurelia setup had no registered Steam library or Aurelia
  session. Neither attempt informs ordinary Steam behavior toward a healthy
  Aurelia install. The two-title production observation below is not a
  substitute for a controlled clean install. Do not resume isolated testing as
  part of this task.
- **Clean-environment attempt (2026-10-11; Outcome C):** stopped the prior
  `steam-compat-stage1-real.service` cleanly; production `lulu-steam-runtime`
  remained active with the same invocation and zero restarts. Created fresh,
  private test HOME/config/data/cache directories under
  `/home/.steam-aurelia-clean-20261011`; no production path or credential was
  exposed or copied. With those XDG/HOME paths, official Aurelia 0.1.37
  `libraries --json` returned `{"libraries":[]}`. Its supported interface does
  include `install --platform windows --library <path>`, but the clean client
  has not registered a library, has no Aurelia session, and no owned-game
  entitlement was verified. No Steam client was started in the fresh tree, no
  game was selected or installed, and no update behavior was observed. Stop
  here rather than use a production library, transfer session data, or guess a
  safe title. This attempt does not support either side of the healthy-install
  hypothesis.
- **Interference safeguards (assessment only):** Acquisitiond idle is not proof
  that Steam is idle. Steam's content log, `downloading`/`temp` state, manifest
  state, and active writers/processes can be useful corroborating signals, but
  no supported authoritative idle API has been established; log silence or a
  point-in-time scan cannot close races. Do not add fragile parsing or change
  deployment policy here. Until separately designed, Mudos should avoid
  knowingly overlapping operations when observable Steam content activity is
  present and treat ambiguous evidence as a reason to defer—not as proof that
  isolation is required.
- **Production shared-library baseline (2026-10-11; read-only; no restart):**
  hardened Steam auth status returned only `authenticated`. Official Aurelia
  0.1.37 recognized SILENT HILL 2 (2124490) as installed Windows and Super Meat
  Boy (40800) as installed Linux; both reported `update_available=false` and
  `update_queued=false`. Their appmanifests have `StateFlags=4`; installed
  depots/manifests match Aurelia's current public targets. SILENT HILL 2 has
  depot `2124491=4138456104249046245`, build 17080069, Windows PE executable
  `SHProto/Binaries/Win64/SHProto-Win64-Shipping.exe` (SHA-256
  `c21ae87cdd186ca22760ad7aa66973eaac2a4d9a4e437a3b42daaab08eb729bc`). Super
  Meat Boy has Linux depot `40802=6556596646716197166` plus shared depot
  `98011=915545047853675884`, build 3241924; `amd64/SuperMeatBoy` is ELF
  x86-64 (SHA-256 `91dfebedbdd5add0fb81535d710bb492cabb23244f733162d8984a0b154158b2`).
  Both Aurelia per-game configs have platform preference `null` and runner
  `auto`; no Proton version is forced. The observed installed content is
  Windows/PE for Silent Hill 2 and native Linux/ELF for Super Meat Boy.
  These formats confirm the actual installed platforms; no migration or game
  operation was performed.
- **Historical activity and limits:** for both AppIDs Steam `content_log.txt`
  contains queued-state, scheduler-start and starting-commit records after the
  appmanifest `LastUpdated` values. The log's latest matching events were
  2026-10-11 04:56:03Z (2124490) and 2026-10-10 08:21:28Z (40800). Their
  appmanifest mtimes are later than `LastUpdated` (2026-10-11 03:56:03Z and
  2026-10-10 07:21:28Z respectively). Aurelia's current depot manifest IDs
  still match the installed sets; its global update report is empty, and
  Acquisitiond has zero jobs for either AppID. Tree metadata showed no
  non-generated game files newer than each appmanifest `LastUpdated`; newer
  files were runtime/user metadata or cache files. The log and mtimes are
  evidence consistent with Steam-managed queue/commit activity and manifest
  rewrites, but do not identify the initiating caller or prove historical
  payload bytes changed. No matching Mudos job gives an exact Aurelia install
  completion time, so `LastUpdated` is only a comparison point, not a verified
  Aurelia installation timestamp. No pre-event checksum baseline exists.
  Current depot state/platform remains coherent for both examples.
- **Idle-state reassessment (2026-10-11; read-only):** AppIDs 1712830,
  2225070, and 48000 are not installed in Aurelia and have no appmanifests.
  Their `steamapps/temp/<AppID>` directories exist but are empty, with mtimes
  from Oct 3, Oct 6, and Oct 10; no matching `steamapps/downloading` trees
  exist. Two snapshots 45 seconds apart showed identical directory/file
  metadata, no Steam process with an open writable descriptor under
  `steamapps`, no appended content-log lines, and an unchanged service
  invocation. Aurelia reports all three not queued and the Steam Downloads UI
  showed no downloads. Their latest content-log records are historical:
  scheduler removal for 2225070 (Oct 11 08:20Z), fully-installed state for
  48000 (Oct 11 04:51Z), and old state/other records for 1712830 (Oct 3).
  These three temp entries are **historical empty directory residue**, not
  current operations. For 1712830 the last operation's success/failure versus
  abandonment cannot be established from the retained log; the other two have
  terminal-looking scheduler/state records, but no payload-level completion
  proof. This unresolved historical outcome does not indicate current work.
- **Cause and correction:** the diagnostic prototype reduced the entire
  historical content log as if scheduler/update markers were current, and
  treated any `temp` directory name as activity. That can preserve old
  `Update Started` state indefinitely. Its classifier now treats the log as
  context and requires paired current evidence: current queue observation,
  relevant open write descriptors, staging changes, current appended event
  categories, and a stable service invocation. Old scheduler records and
  unchanged temp entries alone no longer imply activity; missing, malformed,
  restarting, queued, or contradictory evidence remains unknown/active and
  fail-closed. Deterministic tests cover historical completion, stable temp,
  queued work, transfer/staging, commit, writer descriptors, malformed and
  contradictory evidence, and service restart. This is a diagnostic utility,
  **not** part of the `guarded-deploy.py` path; no deployment guard policy or
  new requirement was added.
- **Other historical ambiguity:** AppID 1332010's latest matching
  `downloading` log record is Sep 30; it is not installed and is not queued in
  Aurelia. AppID 7's latest content-log activity is Oct 11 13:02Z and no new
  lines appeared during the paired observation. The Downloads UI was empty,
  and no `steamapps/downloading` payload, relevant write descriptor, or current
  queue evidence was found. These are historical log entries, not current
  operations. The paired point-in-time result is an idle assessment, not an
  absolute guarantee against a later operation; no quiet-log-only or single
  scan guarantee is claimed.
- No Steam restart was performed. Production service invocation
  `972cd8168e4f4108b5928b098617716e`, PID 2071116, and `NRestarts=0` remain
  unchanged. No post-restart comparison is claimed.
- **Disposition:** this production baseline demonstrates that the intended
  Windows and Linux installations are currently recognized and manifest-current
  under the shared writable library. It does not demonstrate that Steam left
  them untouched: historical queue/scheduler/commit events exist, although no
  payload change is proven. Keep namespace enforcement deferred; this evidence
  is not grounds to deploy isolation. Keep the issue open and continue to avoid
  known active/ambiguous content work. The isolated Stage 1 service was
  stopped, its six test Btrfs subvolumes and abandoned empty test tree were
  removed, stale viewer socket was removed, and the dedicated `steamstage1`
  account was retired. Production Steam/Aurelia credentials and content were
  not touched.
- **Readiness-test expectation correction:** the remaining OOBE failure was
  already present at `9dafec0` and came from a stale fixture expectation. The
  test injected only the deprecated legacy `steam` entitlement source, while
  current reconciliation intentionally handles `steam-aurelia`; no readiness
  record should be invented for the unused legacy source. The test now asserts
  that neither its `refresh()` nor interactive `verify_acquisition()` runs.
  The OOBE and complete Steam test suites pass (160 tests, 3 subtests).
- **Deployment relationship:** the existing guarded-deployment contract remains
  unchanged. The diagnostic classifier is not wired into deployment; do not
  introduce a speculative Steam-idle guard requirement. For this maintenance
  pass the fresh paired assessment found no operation that makes interruption
  unsafe, but readiness remains independently governed by the canonical guard.
- **Compatibility with STEAM-PLATFORM-001:** the source fix at `e6532bb`
  discovers platform choices from Aurelia depot metadata and submits the
  selected Windows/Linux value through Acquisitiond. That boundary remains
  compatible: Aurelia/Acquisitiond run outside Steam's restricted namespace
  and retain canonical write access. Steam's own client must not be allowed to
  select or install a platform. Filesystem isolation is not a prerequisite for
  physical platform-selection acceptance; test with controlled fixtures and do
  not perform a real install or migration in this pass.
- **Implementation boundary:** Aurelia and Acquisitiond remain authorities
  for managed game-content operations. Do not delete, migrate, repair,
  chmod/lock, rewrite manifests, remove shared library access, change Steam
  launch flags, or restart Steam solely to test a hypothesis. Any change
  to the client/library boundary must be proven with sandbox or disposable
  fixtures, explicit rollback and operator approval for live game mutation.
  Do not silently suppress Steam update indicators to disguise activity.
- **Long-term risk reduction (not a current acceptance gate):** with Steam authenticated and games launchable, autonomous Steam
  acquisition cannot mutate the managed library; explicit Aurelia
  Windows/Linux installation choice persists through updates; content
  operations appear through Acquisitiond; the online deployment guard
  refuses genuinely ongoing content modifications regardless of process
  ownership; shutdown/restart and rollback are safe. Test with fake
  libraries and isolated fixtures before approving any live installation.
- **Approval boundary:** Stage 1 disposable-client testing remains deferred. It remains
  prohibited to change the production unit/mounts, restart production Steam,
  re-register its libraries, or touch installed production content. Preserve
  Rocket League's Linux installation unchanged. No such production action has
  been taken.
- **Dependencies:** STEAM-PLATFORM-001 and STEAM-UPDATES-001 physical acceptance
  do not depend on deployment of filesystem isolation. Steam/Aurelia concurrent
  content-operation risk remains tracked separately.

### RELEASE-SAFETY-001 — Deployment idle-check failure did not block activation

**Status: FIX DEPLOYED/TESTED · P1 · OPERATIONAL ACCEPTANCE COMPLETE.** On 2026-10-11, a shell
deployment command attempted to query Sessiond through `/run/user/958/bus`
from a root process. That root-context connection failed (`Broken pipe` /
`Transport endpoint is not connected`); the same read-only GetState call
succeeds as user `lulu` with `XDG_RUNTIME_DIR=/run/user/958`. The multiline
shell continued to `release.py activate` and restart Sessiond because it had
no fail-fast handling or explicit conditional. Activation and restart therefore
occurred despite the failed idle precondition. Post-action checks found Home
ready, no active game identity, zero active Acquisitiond jobs, and an
authenticated Steam runtime. No game/update was observed interrupted. The
failure was in the deployment orchestration, not a check inside the generic
release builder: `release.py activate` verifies the immutable release and
atomically switches the selector, but intentionally has no session-idle policy.

- **Implemented:** `scripts/guarded-deploy.py` is the canonical online entry
  point. It queries Sessiond, Acquisitiond, and Consoled in `lulu`'s D-Bus
  context; validates service health, idle shell/token/surface state, Steam
  runtime readiness, and every job state; rechecks before activation; and
  checks readiness after a single restart. Post-activation failures trigger one
  rollback attempt. `release.py activate` remains available for offline,
  bootstrap, and recovery use. See `docs/guarded-deployment.md`.
- **Deployment and acceptance:** after diagnosing and correcting service
  restart ordering, the canonical guard activated
  `/opt/lulu/releases/24acb93-candidate-20261011102738` on 2026-10-11.
  Required services are active; Sessiond is in shell with presentation ready,
  a connected Xbox controller, no active identity/token; Steam is ready and
  authenticated; Consoled RPC succeeds; Acquisitiond has no active jobs; the
  Rocket League REMOVE remains failed/non-retryable. The staged release
  verifies and remains the active immutable release. No game-content operation
  was run.
- **Prior blocker evidence:** the orphaned Rocket League row has been safely
  reconciled and Acquisitiond restarted; there are no active acquisition jobs.
  Physical presentation and controller readiness passed at deployment
  attempts. Both attempts restored `/opt/lulu/current` to
  `/opt/lulu/releases/af4ad04-candidate-20261011040541`. The first exposed
  transient Consoled D-Bus readiness; bounded service-probe retries were added.
  The second exposed that Steam runtime authentication may take its allowed
  150 seconds after Sessiond restart, but the guard waited only 30 seconds.
  Its runtime then hit systemd start-limit during repeated rollback restarts.
  The guard's post-activation budget is now 180 seconds, matching the unit's
  `TimeoutStartSec`; its full fail-closed checks are unchanged. Journal
  investigation confirmed Sessiond's shell starts before Consoled and
  Acquisitiond in the guard's former restart order, fails closed on missing
  D-Bus names, and restarts (Steam is `PartOf=Sessiond`). This caused five
  Steam starts across the two attempts within the existing five-start/300s
  limit. Restart order is corrected to Consoled, Acquisitiond, then Sessiond;
  no rate limits were changed. Steam was recovered after confirming no active
  acquisition/game, no orphan Steam/Xvfb, and no existing :99 socket/lock; one
  `reset-failed` plus one normal start reached authenticated READY and remained
  healthy for 20 seconds. The subsequent one-shot guarded deployment used the
  corrected restart order and succeeded; Steam started once for that
  activation, reached authenticated READY, and had `NRestarts=0` afterward.
  `/opt/lulu/releases/24acb93-candidate-20261011102738` remains verified and
  active. Official Aurelia 0.1.37's required interfaces are compatible.
- **Physical acceptance remains separate:** operator-owned Steam platform
  selection and update-lifecycle acceptance remain tracked in their issues;
  these were not part of deployment validation.
- **Preserve legitimate workflows:** keep canonical `release.py activate` as
  the low-level atomic selector operation for intentional offline/bootstrap and
  rollback workflows; do not add an unconditional Sessiond requirement that
  would prevent first install or recovery when services are stopped. Route
  online appliance deployment through the guarded orchestrator; retain the
  existing `install_mudos.py --update` shell-lifecycle guard and test its
  restart/rollback path separately. Do not deploy merely to test a failed guard.
- **Accept:** deterministic tests cover bus transport failure, malformed state,
  non-shell lifecycle, active game identity, active Acquisitiond job, and happy
  online deployment; every rejected case proves activation/restart was not
  invoked. Separate offline activation and rollback tests continue to pass.

### ACQUISITION-REMOVE-001 — Interrupted provider removal could be replayed on restart

**Status: SOURCE FIX COMMITTED/TESTED/DEPLOYED; HISTORICAL JOB RECONCILED;
RESTART SAFETY CONFIRMED.** On 2026-10-11,
Acquisitiond reported job
`job-aea04e11b30a4a66884ffa8b4d31c708` (`steam-aurelia:252950`, REMOVE) as
`transferring`, stage `Downloading depot 252951`, progress 0.001. It was created
at `2026-10-11T07:46:25Z`, last updated at `07:47:13Z`, and has not advanced
since. Its persisted `completed_at=07:46:26Z` contradicts its active state.

- Read-only provider checks find no active Aurelia install (`install list` is
  empty); Aurelia excludes AppID 252950 from `list --installed` and reports
  `available=false`, `install_path=null`. There is no active Aurelia uninstall
  registry exposed by the CLI. No Aurelia CLI child or open file descriptor for
  the game directory was found, and Steam content logs contain no recent
  252950/252951 activity.
- `appmanifest_252950.acf` remains as a stub (`StateFlags=2`, `SizeOnDisk=0`, no
  `InstalledDepots`). `steamapps/common/rocketleague` nevertheless contains
  46,287,043 bytes of Rocket League `.upk`/`.bnk` files, all last modified at
  08:47 local. This is partial residual content, not a fully installed game.
  Another completed Acquisitiond ACQUIRE row for the same AppID records about
  44.6 MB from depot 252951 at that same time, but reports completion while the
  installed-library evidence says not installed. The relationship between the
  two jobs and the residual files is not established.
- **Recovery defect confirmed:** `AcquisitionStore._recover_active()` had
  queued every interrupted operation, and Aurelia REMOVE immediately invoked
  `uninstall`; it had no restart-specific protection. The reason for the
  contradictory historical timestamp and same-AppID ACQUIRE/REMOVE progress
  overlap is not established. Do not infer which operation emitted the depot
  progress or claim the prior uninstall completed.
- **Source correction:** commit `04c80a6` changes startup recovery so all
  interrupted REMOVE operations become non-retryable
  `orphaned-removal-incomplete` failures before executor registration, retaining
  original state/stage/timestamps/progress/provider/origin evidence. The
  Aurelia adapter separately refuses a recovered REMOVE. New explicit removal
  still invokes the normal provider path; interrupted acquire/update recovery
  semantics remain unchanged. Exact offline backup/reconciliation is guarded
  by `reconcile_orphaned_remove()` in `src/lulu/acquisition_store.py`.
- **Production row reconciliation:** with Acquisitiond stopped and its DB
  writer gone, only the exact authorized row was changed from `transferring`
  to `failed`, stage `orphaned-removal-incomplete`, `retryable=false`, error
  `orphaned-removal-incomplete`, recovery reason
  `administrative-orphan-reconciliation`. The original contradictory
  `completed_at` and other fields remain intact, captured in error details and
  a protected pre-mutation export. The separate ACQUIRE row and all other rows
  were left unchanged. Acquisitiond restarted with no active jobs and no
  uninstall invocation.
- Residual Rocket League files and the stub appmanifest were not changed. Their
  cleanup is separately deferred under `ACQUISITION-REMOVE-002`; keep this issue
  open until the source correction is deployed and restart safety is confirmed
  in that release.

### ACQUISITION-REMOVE-002 — Rocket League residual content after orphan recovery

**Status: DEFERRED · NO CLEANUP AUTHORIZED.** Approximately 46,287,043 bytes of
Rocket League content remain under `steamapps/common/rocketleague`, alongside a
stub appmanifest with `StateFlags=2`, zero size, and no installed depot records.
The files were deliberately preserved during authorized job-state
reconciliation. Do not delete, repair, reinstall, or otherwise mutate these
files without a separate operator decision and a title-specific preservation
plan.

### STEAM-UPDATES-002 — Update in Background leaves a black screen

**Status: FIX DEPLOYED · PHYSICAL RE-ACCEPTANCE REQUIRED.** The Home-return
correction is active in
`/opt/lulu/releases/af4ad04-candidate-20261011040541`. Root cause and corrected
path are documented below. Do not run a real update solely for validation.

- **Accept:** non-destructively verify direct Background and Continue in
  Background paths from Home, Library, and Recents using a synthetic update
  job/fixture. Home must return fully visible and controller-navigable, the
  fixture job must continue, and no launch intent may survive completion,
  errors, or shell restart. Physical UI acceptance remains operator-owned.

### STEAM-UPDATES-003 — Update offered again after a reported completion

**Status: SOURCE CORRECTION COMMITTED/DEPLOYED · PHYSICAL ACCEPTANCE OPEN.**
Prior LIMBO evidence below is historical and does not
establish the current appmanifest or update state.

- **Source-level finding (read-only, official Aurelia v0.1.37/v0.1.38 tags;
  appliance runtime is v0.1.37):**
  `install` auto-selects Windows depots preferentially, with an explicit
  `--platform` override;
  `import` defaults to the host OS unless explicitly told otherwise. The
  per-game platform preference is documented as a launch setting. In contrast,
  `check_for_updates()` trusts `StateUpdateRequired`, otherwise compares local
  installed depot IDs to corresponding remote branch manifests. Update
  execution restricts remote depots to installed IDs when records exist. The
  supported read-only `manifests APPID --json` command provides per-depot,
  per-branch current manifest IDs. Other platform depots alone do not imply an
  update. Mudos now compares these interfaces and verifies after update.
- **Policy:** preserve intended installed content and launch route. Windows
  content launched via Proton remains a valid deliberate configuration and
  must not be migrated because native Linux depots exist. Native Linux content
  should pair with a native Linux launch; Windows-only and inherited SteamCMD
  installs retain Windows content/Proton where applicable. Store-facing
  platform metadata alone cannot establish installed depot policy. Unknown
  identity must be reported as unknown/conflict, not silently considered
  current or updated.
- **Next:** deploy only with the guarded workflow after appliance safety is
  established; separately re-evaluate
  the repeated-update symptom using a safe synthetic fixture. LIMBO was
  deliberately uninstalled through Mudos; its missing appmanifest is expected.
  The Aurelia prototype is historical work only.
- **Evidence (read-only, 2026-10-11):** raw `aurelia --json update` and the
  Mudos live check list LIMBO as `available`. `aurelia --json manifests 48000`
  reports public-branch manifests `48001=1261656871327265848` and
  `48002=6867798692379060871`, which exactly match the installed
  `InstalledDepots` in `appmanifest_48000.acf`. It also reports public-branch
  targets `48004=4729536071049921379` and `48005=5598213330580205879`; Aurelia's
  depot report labels 48004/48005 `os: linux`. Both corresponding target
  manifest files are already in Steam's local depotcache. Steam `content_log`
  records the configuration switching from depots 48001/48002 to 48004/48005
  on Oct 6 and again Oct 10, with a prefetch of 83,407,104 bytes and zero bytes
  to stage. Yet the appmanifest still lists only 48001/48002, buildid and
  TargetBuildID remain `18220724`, and game payload file mtimes remain Oct 6.
  Thus the three terminal LIMBO jobs did not produce an observable installed
  depot-set transition; `provider_state=updated` is not proof that the active
  target depots were installed. Mudos' `_confirm_updated()` only requires a
  subsequent “not available” response and an installed-game row; it does not
  compare target versus installed depot IDs/manifests.
- **Platform/runtime evidence:** Aurelia store `info` lists Windows and macOS,
  while the current depot report labels the target depots Linux. Aurelia's
  library row reports `platform=windows` and an empty `local_manifest_ids`,
  while its catalogue `update_available=false` conflicts with the separate raw
  `aurelia update` report; do not use that catalogue field as freshness
  evidence. The installed game tree contains the Windows `limbo.exe` PE
  executable and no native Linux executable; the latest Mudos launch explicitly uses
  `Proton - Experimental/proton run .../Limbo/Limbo.exe`. This Windows payload
  and Proton route are internally consistent, but differ from the Linux depot
  configuration Steam logged. The evidence points to a platform/depot selection
  mismatch as the likely source of persistent availability; whether Aurelia's
  update command is a no-op, erroneously reports completion, or chooses an
  unintended platform target still requires confirmation from its per-job
  behavior. The same symptom includes completed Trackmania submissions, but
  no shared cause for Trackmania is established.
- **LIMBO recommendation:** do not change its Aurelia platform preference or
  content now. Preserve the installed Windows depots, saves, prefix and Proton
  launch route while the contract is unresolved. Any later Linux-content
  migration needs explicit approval plus a save/prefix inventory, intended
  executable/runtime validation, and a recoverable return plan; this
  investigation authorizes none of those operations.
- **Safety:** do not run `aurelia verify`, submit another update, edit
  appmanifest, pin/suppress updates, switch runtime, or alter game files as an
  investigation probe. Any move from Windows/Proton content to Linux content
  needs a scoped recovery/launch plan and separate operator approval.
- **Accept:** installed depot IDs and manifests match Aurelia's intended
  platform/branch target; an update completion proves the relevant depot
  transition; repeated launch checks no longer prompt when current; and the
  selected runtime launches the matching installed payload.

### STEAM-LIMBO-001 — LIMBO pixel shader error after Steam update

**Status: OPEN · P1 · ERROR NOT CAPTURED; PLATFORM MISMATCH IS A SEPARATE
LEAD; LIMBO DELIBERATELY UNINSTALLED THROUGH MUDOS.** Keep the operator-reported pixel shader error unconfirmed in retained
logs; do not claim a causal link to STEAM-UPDATES-003.

- **Evidence/read-only update:** the operator confirms LIMBO was deliberately
  uninstalled through Mudos. Its missing appmanifest is expected; do not
  reconstruct or repair the installation. The historical installed payload was
  Windows-only (`limbo.exe`
  and `steam_api.dll`); the latest command launches it with the selected
  Proton Experimental script. The launch record names runner `Wine-TKG` while
  its root is the Proton Experimental directory; the effective backend is
  reported as WineD3D baseline with low confidence. Aurelia's store info says
  Windows/macOS, while the current depot API and Steam content log identify
  Linux depots 48004/48005. This is a consistency question, not authorization
  to switch depots or runtime. No exact shader diagnostic or reliable
  pre-update renderer baseline is retained.
- **Next operator-observed launch:** before starting, record local time and
  current sizes/mtimes of that AppID's `wine_48000.log` and Steam
  `console-linux.txt`/`shader_log.txt`. Ask the operator to preserve the exact
  error text or photo and whether it appears before/after the game window.
  Immediately after a naturally approved launch attempt, copy read-only the
  matching Aurelia session directory (`command.txt`, `effective_launch_config`,
  `effective_env`, `dll_resolution`, `events`, `summary`), bounded new log
  tails, and Sessiond/Gamescope presentation state. Correlate renderer/DLL
  provider and process exit time. Do not trigger a launch for diagnostics.
- **Safety/accept:** no shader-cache clearing, prefix reset, reinstall, or
  graphics-setting changes. Resolve only after the error is captured and a
  controlled, operator-approved launch reaches gameplay with controller, Guide,
  and exit-to-Home verified.


### AURELIA-VERIFY-001 — Aurelia reports executable missing after wrapped launch

**Status: OPEN · P3 · REPORTING ONLY.** For Get To Work AppID 2706170, the
operator confirmed two successful visible Mudos/Aurelia launches, gameplay,
controller operation, Guide open/dismiss, normal exits, and return to Home. The
matching Aurelia summary reports `result=Success` and `verification.status=verified`
but also `verification.detailed_status=game_executable_not_found`. Its effective
launch config describes the wrapped command's executable as `run` (Proton's
subcommand), with `executable_exists=false`; the same session's launch event
contains `AURELIA_LAUNCH_ARGS` with the correct absolute game executable. This is
not stale Aurelia session data: the contradictory fields are in one session.
It is a verification/reporting mismatch from checking the wrapped command rather
than the target executable. Sessiond's active token is expected while the game
runs; its `last_result` was from a previous launch and did not mean this one
failed.

Mudos already suppresses `game_executable_not_found` as a launch failure when
the summary is nominally successful. A focused regression protects this
behavior. Investigate the Aurelia verification detail separately if feasible;
do not reopen, roll back, reinstall, relocate, or otherwise modify the accepted
Get To Work installation.

### STEAM-UPDATES-001 — User-directed Aurelia update lifecycle and card progress

**Status: IMPLEMENTED — PHYSICAL ACCEPTANCE BLOCKED · P1.** Aurelia-backed update availability and persistent
Acquisitiond UPDATE jobs, launch choices, update card progress, Downloads
operation labeling, and success/failure notification handling are implemented
and deployed. Physical acceptance remains pending; do not treat automated tests
as operator acceptance.

- **Next:** obtain physical acceptance for STEAM-UPDATES-002 using a synthetic
  update fixture. Continue the independent, read-only investigations for
  STEAM-UPDATES-003 and STEAM-LIMBO-001; do not submit a real update, change
  installed content, or perform destructive repair without separate operator
  approval.
- **Accept:** meet the lifecycle and recovery requirements in
  `docs/aurelia-launch-investigation-20261010.md`; add focused tests for both
  catalogue identity aliases, shell/daemon restart, deduplication, cancellation,
  failure and launch-intent invalidation before physical acceptance.

### LUTRIS-002 — Sonic 3 A.I.R. launch leaves Mudos apparently unresponsive

**Status: OPEN · P1.** A real install/launch attempt left a live game process
and waiting Zenity error while Sessiond remained in game lifecycle; ROM lookup
failed because the recipe-selected file name/location did not match the game's
expected lookup. The dialog was not visible in the selected Gamescope surface.
The launch failure and its supervision/presentation consequences were not
subsequently shown fixed. No process was interrupted during this audit.

- **Next:** reproduce only with an approved disposable fixture when the appliance
  is idle; capture game stderr, child/window ownership, and Sessiond state.
- **Accept:** the expected ROM is discoverable or a clear recoverable error is
  presented in the Mudos surface; Back/return restores shell and controller
  navigation without a stranded game/dialog process.
- History: `docs/backlog-archive-20261010.md`; related `LUTRIS-001` below.

### DOWNLOADS-001 — Downloads row clipping / Clear stability

**Status: OPEN · P2.** Operator observed wrapped error text clipping a row and
crashes following Clear. Trigger and responsible component remain unisolated;
no safe active-job Clear test was performed.

- **Next:** use a non-destructive synthetic failed-job fixture and inspect
  overflow/layout plus Clear during idle and terminal states.
- **Accept:** wrapped errors remain readable; Clear cannot crash Mudos or remove
  provider/game data; active-operation semantics are explicit.

### DOWNLOADS-002 — Useful Lutris installation progress

**Status: OPEN · P2.** An observed Lutris install showed only “Downloading” while
the recipe was extracting/compiling. Current UI still lacks meaningful
installation-stage presentation; source has no verified stage-to-progress
projection for these phases.

- **Next:** establish which stages Lutris can report reliably without inventing
  percentages; present stage and genuine measurable progress where available.
- **Accept:** downloading, extracting, and compiling are distinguishable; unknown
  progress is not fabricated; cancellation/error details remain accurate.

### DOWNLOADS-003 — Reported Mudos crash after Lutris install completion

**Status: OPEN · P2, unconfirmed cause.** Operator separately reported that
Mudos appeared to crash when the Sonic 3 A.I.R. Lutris install completed. This
was not diagnosed and must not be conflated with the later failed game launch
(`LUTRIS-002`).

- **Next:** correlate service/session journals and process exit only if safely
  reproducible using a disposable install; do not repeat a large install solely
  for this audit.
- **Accept:** completion does not terminate or strand the shell, or a concrete
  fix is regression-tested. Preserve this as unverified until evidence exists.

## Implementation work

### STEAM-PLATFORM-001 — Choose Steam download platform from Installable

**Status: SOURCE FIX IMPLEMENTED · GUARDED DEPLOYMENT BLOCKED · PHYSICAL ACCEPTANCE RETEST REQUIRED · P2.** When starting installation of a Steam
title from the Installable view, let the operator confirm which supported
platform's content should be acquired, rather than silently accepting the
provider's automatic depot/platform choice. This matters for games such as
Rocket League, where an older native Linux build may exist but the operator
typically wants the maintained Windows build launched through Proton.

- **Interaction:** when multiple installable platform variants are genuinely
  supported, present a controller-native choice such as **Windows (Proton)**
  versus **Linux (Native)** before creating the Acquisitiond install job.
  Explain the selected launch route and, where reliably known, meaningful
  compatibility/support caveats. Prefer Windows/Proton for Rocket League if
  appropriate to current supported content; do not impose a blanket Windows
  default on all games or infer support/freshness from depot existence alone.
  Single-platform titles can use the only verified choice; unavailable or
  ambiguous provider metadata must not be presented as a confidently supported
  selection. Cancel returns to Installable without an installation job.
  Mudos now queries Aurelia depot metadata and displays a controller-focused
  modal for multiple platform choices; a single verified platform proceeds
  without an unnecessary chooser. Unknown or malformed metadata stops before
  job submission. No Rocket League-specific recommendation is made without
  reliable support/freshness evidence.
- **Acquisition:** propagate the confirmed choice into Aurelia's supported
  install platform option and persist it with the provider-owned job for
  retry/restart recovery and reconciliation. Do not introduce SteamCMD as an
  installer, duplicate installed titles per platform, or silently switch
  platform during an update. Do not select Linux merely because a native depot
  exists; do not change content already installed without a separately
  approved migration.
  Acquisitiond stores `steam_platform` on the provider-owned install job,
  deduplicates by AppID, rejects conflicting active choices, and retries only
  with the same persisted choice. Aurelia receives explicit `--platform`.
- **Consistency:** the resulting installed payload, chosen Proton/native
  launch route, and all subsequent update checks/updates must refer to the same
  platform. Coordinate with **STEAM-UPDATES-003** and its unresolved upstream
  Aurelia update/check contract: platform confirmation for new installs must
  not imply that the existing update path can reliably honour that choice.
  If update-path consistency is unavailable, surface that limitation rather
  than falsely guaranteeing platform-safe future updates.
- **Accept:** Steam titles offering Windows and Linux variants expose the
  appropriate choices; Rocket League can be explicitly selected for
  Windows/Proton without accidentally obtaining its legacy Linux payload;
  selected platform is passed to Aurelia, retained through install/job
  recovery and reflected in the launch route; cancellation creates no job;
  identity aliasing and existing-library reconciliation remain correct; no
  platform change or unexpected duplicate update occurs after installation.
  Use synthetic provider/depot fixtures and controller-QML tests before
  physical acceptance; do not install or overwrite live titles without
  operator approval.
- **Physical acceptance failure (2026-10-11 13:05):** the UI bridge's existing
  `/launch-log` captured `selected game_id=steam-aurelia:252950` followed by
  `HTTP install failed: acquisition is not retryable`. This proves the
  `/install/<game_id>` request was reached and rejected; no new Acquisitiond
  job was submitted. QML selected the chooser only for `provider == "steam"`,
  while Aurelia catalogue identities use `provider == "steam-aurelia"`; the
  platform-discovery endpoint was therefore skipped. This is not evidence that
  residual files caused the rejection.
- **Installation-state side event:** Steam `content_log.txt` records an
  already-queued AppID 252950 update running from 13:02:20 and committing
  depot 252961 at 13:06:40-45 (BuildID 25641912, 5,997 updated files,
  10,795,936,576 staged bytes). At 13:06:45 the appmanifest became StateFlags=4
  with that installed depot and the content directory measured about 10.8 GB.
  This occurred through Steam's own update queue after the runtime restart; the
  Acquisitiond history contains no new install/update job. The investigation
  did not submit a live install or mutate game files. Current Rocket League
  files/appmanifest are now installed-state evidence and must not be cleaned up
  or changed under this issue.
- **Fixes in source:** platform discovery and installation now recognize both
  `steam` and `steam-aurelia` catalogue providers, route Aurelia installs through
  `SubmitSteamInstall` with a verified platform, and only consider failed
  `acquire` jobs for generic acquire retries. The original failed REMOVE can
  no longer block an unrelated fresh install. HTTP rejection JSON is parsed;
  discovery failures remain visible in the focused chooser and rejected install
  requests produce a normal error notification with the backend cause, without
  claiming success or changing controller focus. These fixes are included in
  the verified staged candidate described in `docs/validation-log.md`; they are
  not active until guarded deployment succeeds. Do not retry live Rocket League
  installation.
- **Next physical acceptance:** after the fix is activated through the guarded
  workflow, use a synthetic `steam-aurelia` Installable fixture and mocked
  backend. With the controller, verify Windows/Linux choices appear; cancel and
  confirm zero job submissions. Then force platform discovery to return 409 and
  verify its cause is visible and Cancel stays focused; separately force the
  install POST to return 409 and verify the exact backend error notification,
  retained Installable focus, and no success/new job. Do not select the now-
  installed live Rocket League entry or start a live install. Any future
  Windows/Proton migration needs separate operator approval and a recovery plan.
- **Safe physical-test procedure:** use a test-only ConsoleShell instance with a
  synthetic Installable row (`provider=steam-aurelia`,
  `game_id=steam-aurelia:fixture-platform-choice`) and a loopback mock for
  `/steam/platforms/<encoded-game-id>` and `/install/<encoded-game-id>`; do not
  route either request to the production bridge. Return both `windows` and
  `linux` from platform discovery. With the Xbox controller, press A on the
  fixture, confirm both options, move focus between them, then Cancel and assert
  zero install requests/jobs. In a separate discovery-error case, return HTTP
  409 JSON `{"error":"fixture discovery rejected"}` and verify the visible
  reason, no install request, and usable focus. In a separate install-error
  case, choose a platform and have only the mock `/install` return HTTP 409 JSON
  `{"error":"fixture install rejected"}`; verify that exact backend reason,
  retained Installable focus, failed (not successful) UI state, and zero jobs.
  The mock must log/assert every request and must not proxy/fallback to the
  production API. The real Installable catalogue and any real AppID are never
  used in these cases. The repository currently has bridge unit tests and the
  focused QML error-reason test, but no deployed fixture/mock UI endpoint; do
  not improvise a production endpoint or run these actions against a live title.
- Official Aurelia 0.1.37/0.1.38 interface compatibility remains verified
  read-only; no binary was changed.

### ACQUISITION-INSTALL-001 — Failed REMOVE blocks fresh Aurelia install

**Status: SOURCE FIX IMPLEMENTED/TESTED; DEPLOYMENT AND LIVE ACCEPTANCE BLOCKED.**
The Installable bridge's generic acquisition path selected any failed job with
the same provider/content identity, without checking operation. For
`steam-aurelia:252950`, it matched the historical failed, non-retryable REMOVE
and raised `acquisition is not retryable` instead of submitting a new,
platform-specific INSTALL. Acquisitiond itself already has a dedicated
`SubmitSteamInstall` boundary that treats INSTALL/REMOVE/UPDATE correctly.

- The bridge now routes both Steam catalogue provider aliases through that
  boundary and filters generic failed retries to `operation == "acquire"`.
- Tests prove the failed REMOVE is not retried, invalid/missing platform or
  discovery does not submit a job, and provider/retry conflicts propagate the
  original cause to the UI.
- Do not repair or roll back the now-installed Rocket League content under this
  defect. Any platform migration or recovery plan requires a separate operator
  decision and evidence-based, title-specific plan.

### UNINSTALL-UX-001 — Hide a title while provider uninstall runs

**Status: OPEN · P3, explicitly deferred requirement.** Provider-owned uninstall
exists (`UNINSTALL-001` is closed), but the accepted UX contract is not
implemented: hide the selected title immediately after confirmation, reconcile
after success, and restore visibility after failure/cancellation. “Show hidden
titles” is session-only; membership persistence/lifetime still needs a decision.

- **Next:** implement temporary hide state tied to the removal job and define
  membership persistence before shipping.
- **Accept:** title disappears immediately; success leaves it absent through
  provider reconciliation; failure/cancel restores an installed title; setting
  resets on session reload; no catalogue state is falsified.

## Validation pending

## Deferred / optional enhancements

### STEAM-UPDATES-UX-001 — Radial update indicator spins its labels

**Status: DEFERRED · P3 · FOLLOW-UP VISUAL PASS.** Physical video of
Update & Launch shows the percentage and stage badge rotating with the
indeterminate radial arc; the off-bounds stage badge can overlap the
game title/explanatory text. In `ui/UpdateRadialProgress.qml`,
`NumberAnimation on rotation` animates the entire root Item rather
than only the ring; the badge is anchored below the component without
reserving layout space. The component is shared by the waiting screen,
Library and Recents. **Do not fix this during the current lifecycle
investigation.**

- **Follow-up accept:** only the arc rotates when indeterminate;
  percentage and stage label stay upright; determinate angle resets
  correctly; parent layouts reserve label space; verify all three
  surfaces, scaling/themes, and reduced-motion behavior.

### THEME-001 — Theme engine final UI validation

**Status: DEFERRED · P3.** The user deliberately deferred remaining theme-engine
and theme-specific checks to the global final UI pass. Existing Modern/95
acceptance and implementation evidence remain valid. Do not start theme work or
additional theme acceptance before that pass.

### LUTRIS-001 — Dedicated Lutris engineering and validation milestone

**Status: DEFERRED · P2.** The user explicitly deferred final Lutris acceptance.
This is a separate provider milestone, not a simple sign-off. It must include
`LUTRIS-002` and related `DOWNLOADS-001/002/003` defects; those remain listed as
open defects above. Do not close Lutris or begin its implementation in unrelated
work. See the archived investigation for prior installation/search acceptance.

### GAMEPLAY-DOWNLOADS-001 — Download behavior during gameplay

**Status: DEFERRED · P3.** Previously agreed gameplay download-management
controls/policy have not been specified sufficiently to implement safely.
Current notification work intentionally does not pause downloads.

- **Next:** only with approval, define whether jobs continue, pause, or expose
  controller-accessible management during games; specify provider capability
  behavior and resume policy. Not a normal-operation blocker.

### THEME-STRUCTURE-001 — Declarative multi-stop structural materials

**Status: OPTIONAL · P4.** Theme gap audit identifies richer declarative
multi-stop material profiles as a future capability. Current supported theme
model is functional; this is not required for acceptance.

### Legacy Steam available-row metadata merge

**Status: OPTIONAL · P4; no active defect.** Validation on 2026-10-10 found
69 available legacy `steam:` rows with matching Aurelia entitlements. They are
suppressed in favor of Aurelia in the installable view; some retain distinct
metadata/artwork, so they were deliberately not deleted. A metadata-aware merge
is optional cleanup only. See `docs/validation-log.md` Steam catalogue audit;
do not remove rows without comparing and preserving metadata.

## Resolved / closed / superseded

| ID | Outcome and evidence |
| --- | --- |
| AURELIA-LAUNCH-001 | **ACCEPTED / CLOSED.** Get To Work's layout correction is accepted after two operator-confirmed Mudos/Aurelia launches, normal gameplay/rendering, controller use, Guide open/dismiss, normal exits, and return to Home with controller navigation. No reinstall or further game-file changes authorized. Preserve the rollback metadata and five other read-only audit findings in `docs/aurelia-launch-investigation-20261010.md`. The separate reporting discrepancy is `AURELIA-VERIFY-001`. |
| DISPLAY-001 | **RESOLVED — MONITORING.** Recent operator reports: normal operation and recent reboots have not reproduced loss. Current command line has no forced `video=DP-1`; source removal is `76d3300`. DP-1 currently connected/enabled, DPMS On, 1920×1080. Historical no-signal/relink evidence remains real; no risky recovery experiments are required. Monitor recurrence; see below. |
| CTRL-001 | **RESOLVED — MONITORING.** Operator reports recent reboots/navigation successful. Current read-only snapshot: one connected Xbox composite, one SDL target, Sessiond `sdl_index=0`; no current duplicate target. Recent InputPlumber logs do show transient stale-node `No such device`/empty gamepad order, so race elimination is not proven. Do not restart InputPlumber to test. |
| RECOVERY-001 | **CLOSED.** Current Recovery implementation reports InputPlumber GamepadOrder and exposes Sessiond controller evidence separately; source/tests cover the health state. Current authoritative Sessiond and InputPlumber inventories agree on one connected controller. No current mismatch observed; no recovery-mode transition was induced. |
| RECENTS-001 | **CLOSED.** Aurelia identity projection and direct Steam-family launch recents fixed and regression-tested; implementation/history retained in archive. |
| NOTIFICATIONS-001 startup warnings | **SUPERSEDED.** Earlier presenter startup/lifetime warnings are replaced by `778fdad`/`122db13`; remaining work is physical acceptance above, not implementation. |
| LIBRARY-001 | **ACCEPTED / CLOSED.** After the controller-route and landing-reference fixes were deployed, the user physically confirmed the four landing cards now pass. Implementation, regressions, candidate checksum, activation, and prior failed checks are recorded in `docs/validation-log.md`. |
| UNINSTALL-001 | **ACCEPTED / CLOSED.** Provider-owned removal implementation and operator acceptance are documented in archive; distinct temporary-hide UX remains `UNINSTALL-UX-001`. |
| QUIVER-001 | **ABANDONED.** Lutris is selected PC install foundation; Questarr remains retired. No implementation work. |
| DESKTOP-001 | **ACCEPTED / CLOSED.** 2026-10-08 runtime and visual/controller-oriented checks accepted the Modern and 95 wallpaper/panel behavior, menu/launchers, Network Settings, power menu (without invoking power), and clean Sessiond return. No restart/shutdown test was requested. |
| UI-001 | **ACCEPTED / CLOSED.** User reports the default UI visual baseline passed the physical acceptance sweep. This is separate from automated tests. |
| SET-001 | **ACCEPTED / CLOSED.** User reports consolidated System Settings passed physical acceptance. |
| LIBRARY-LAUNCH-001 | **ACCEPTED / CLOSED.** User reports both physical Library launch/return tests passed. |
| EDEN-001 | **ACCEPTED / CLOSED.** User reports all three physical tests passed: Mario Kart rendering, controller mapping, persistence across relaunch, and clean return. Earlier update/DLC acceptance remains valid. |
| NOTIFICATIONS-001 | **ACCEPTED / CLOSED.** User explicitly accepts deployed lifecycle, refresh-deferral, and status-strip positioning changes. This does not reopen or invalidate prior automated results. |
| STEAM-ROUTE-001 / STEAM-CATALOGUE-001 | **ACCEPTED / CLOSED.** Physical route checks and Aurelia installed-state authority documented in validation log; current release includes follow-up duplicate legacy metadata deduplication. |
| OVERLAY-001 | **ACCEPTED / CLOSED.** User accepted Statistics Overlay behavior and supported launch coverage; details in archive/validation log. |

## Operational monitoring

- **DISPLAY-001:** forced DP-1 was removed from tracked source and current boot
  arguments; operator reports stable operation. Historically, forced output
  could mask a physical link-loss signal, and BC-250 relink failures occurred.
  Current safe observation is only a healthy logical connected output, not proof
  the panel receives an image. If no-signal recurs, record timestamp, journal,
  sysfs and Sessiond state before any action. Do not repeat PCI FLR/GPU reset,
  disruptive DRM manipulation, or source-switch experiments merely to close it.
- **CTRL-001:** recent InputPlumber transient-node churn indicates a possible
  boot/hotplug race. On recurrence, capture service journal, InputPlumber source,
  composite/target counts, and Sessiond SDL association before recovery. Do not
  interrupt working navigation or restart InputPlumber for reconnaissance.
- **Full suite:** latest source suite is **1,269 passed, 14 failed, 88 subtests
  passed**. Failures: eight stale UI source-text expectations, two Dolphin
  fixtures missing `list_catalogue_games`, native build easing literal,
  payload checksum manifest, release fixture missing built wallpaper artifact,
  and Steam OOBE expectation mismatch. These are reproducible test/release
  hygiene defects, but not evidence of a live appliance fault. Keep visible for
  next engineering cycle; do not mix fixes into this reconnaissance.
- **Appliance baseline (2026-10-10):** canonical clean checkout `122db13`, same
  `origin/dev`; `/opt/lulu/current` resolves to
  `/opt/lulu/releases/122db13-candidate-20261010080657`. Development runtime
  exists but is non-promotable, marked `dirty=false`, source HEAD `76d3300`, and
  is not the running shell. Sessiond, Consoled, Acquisitiond, InputPlumber and
  isolated Steam runtime are active; shell lifecycle is idle/ready; Steam is
  authenticated. One controller is connected. Catalogue has records across
  Steam/Aurelia, RomM, emulators and other providers; Acquisitiond reports 95
  historical jobs and zero active jobs. No game/download was interrupted.

## Recommended next-cycle order

1. Complete the user physical acceptance of `LIBRARY-001` across all four
   dimensions; retain the fixed order regardless of result.
2. Address `LUTRIS-002` and `DOWNLOADS-001/002/003` within the dedicated,
   explicitly deferred Lutris milestone; do not fold this into unrelated work.
3. Implement `UNINSTALL-UX-001` only after its hidden-membership policy is
   decided.
4. Resume theme validation only as part of the global final UI pass; gameplay
   download controls and theme material expansion remain deferred/optional.
