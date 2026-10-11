# Mudos Engineering Backlog

Status reconciled 2026-10-10 against canonical source `122db13` and subsequently
updated with operator physical acceptance and the Library dimension correction
on `dev`. This file is the current status authority. Detailed prior
investigations are preserved verbatim in
[`docs/backlog-archive-20261010.md`](docs/backlog-archive-20261010.md); newer
evidence and this reconciliation rationale are in
[`docs/backlog-reconciliation-20261010.md`](docs/backlog-reconciliation-20261010.md).

## Active defects

### RELEASE-SAFETY-001 — Deployment idle-check failure did not block activation

**Status: OPEN · P1 · GUARD IMPLEMENTED/TESTED; DEPLOYMENT BLOCKED.** On 2026-10-11, a shell
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
- **Current blockers:** on 2026-10-11 Acquisitiond reported a Steam removal in
  `transferring`; Sessiond reported `presentation_ready=false` and no connected
  controller; and the service-configured `/usr/bin/aurelia` reports 0.1.37
  rather than required official 0.1.38. No release was built or activated and
  no service was restarted.
- **Next:** resolve the blockers, fetch/reconcile current `dev`, then run the
  guarded entry point on a safely idle appliance. Do not close until a real
  guarded deployment succeeds.
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

**Status: SOURCE CORRECTION COMMITTED · NOT DEPLOYED; PHYSICAL ACCEPTANCE OPEN.**
Prior LIMBO evidence below is historical and does not
establish the current appmanifest or update state.

- **Source-level finding (read-only, installed Aurelia v0.1.38 source):**
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
- **Next:** deploy only with the guarded workflow after official Aurelia 0.1.38
  compatibility and appliance safety are established; separately re-evaluate
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

**Status: IMPLEMENTED IN SOURCE · PHYSICAL ACCEPTANCE OPEN · P2.** When starting installation of a Steam
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
- **Current integration boundary:** platform chooser and explicit install
  selection remain in source. Update verification uses official Aurelia
  `manifests --json` plus the local appmanifest; no experimental Aurelia
  command is required. These source changes are not deployed. The only
  discovered runtime binary currently reports Aurelia 0.1.37, so required 0.1.38
  compatibility needs actual runtime confirmation.

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
