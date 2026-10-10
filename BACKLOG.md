# Mudos Engineering Backlog

Status reconciled 2026-10-10 against canonical source `122db13` and subsequently
updated with operator physical acceptance and the Library dimension correction
on `dev`. This file is the current status authority. Detailed prior
investigations are preserved verbatim in
[`docs/backlog-archive-20261010.md`](docs/backlog-archive-20261010.md); newer
evidence and this reconciliation rationale are in
[`docs/backlog-reconciliation-20261010.md`](docs/backlog-reconciliation-20261010.md).

## Active defects

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

### LIBRARY-001 — Library dimension navigation

**Status: IMPLEMENTED — PHYSICAL ACCEPTANCE PENDING · P2.** The operator
confirmed the defect still occurs after the first deployed correction: all four
cards entered Platform. Follow-up diagnosis found the controller confirm path
called the shell's generic `activate()` directly; unlike pointer activation, it
did not dispatch the selected landing card's semantic key, so the current
default dimension remained Platform. The correction routes controller confirm
through the selected card's `activateSelected()` and opens the Library surface
only after the semantic key is set. A follow-up deployment then exposed a
missing shell property/instance assignment for `libraryHomeLandingRef`, which
prevented controller confirm from reaching that method. The reference is now
declared and assigned when `LibraryHome` completes. Cards retain fixed
Platform, Provider, Game Mode, Genre order; in-view dimension switching remains
separate.

- **Operator check:** from Home, open each card, verify its matching Library
  dimension, Back to Home, and confirm positions/selection do not jump; repeat
  selections, exercise in-view dimension/category navigation, and verify normal
  Library launch/return.
- **Accept:** all four dimensions open correctly on repeated entry; card order
  and selection persist across returns; in-view navigation, Back, and launch/
  return remain correct. Keep pending until the user confirms all four.

## Deferred / optional enhancements

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
| DISPLAY-001 | **RESOLVED — MONITORING.** Recent operator reports: normal operation and recent reboots have not reproduced loss. Current command line has no forced `video=DP-1`; source removal is `76d3300`. DP-1 currently connected/enabled, DPMS On, 1920×1080. Historical no-signal/relink evidence remains real; no risky recovery experiments are required. Monitor recurrence; see below. |
| CTRL-001 | **RESOLVED — MONITORING.** Operator reports recent reboots/navigation successful. Current read-only snapshot: one connected Xbox composite, one SDL target, Sessiond `sdl_index=0`; no current duplicate target. Recent InputPlumber logs do show transient stale-node `No such device`/empty gamepad order, so race elimination is not proven. Do not restart InputPlumber to test. |
| RECOVERY-001 | **CLOSED.** Current Recovery implementation reports InputPlumber GamepadOrder and exposes Sessiond controller evidence separately; source/tests cover the health state. Current authoritative Sessiond and InputPlumber inventories agree on one connected controller. No current mismatch observed; no recovery-mode transition was induced. |
| RECENTS-001 | **CLOSED.** Aurelia identity projection and direct Steam-family launch recents fixed and regression-tested; implementation/history retained in archive. |
| NOTIFICATIONS-001 startup warnings | **SUPERSEDED.** Earlier presenter startup/lifetime warnings are replaced by `778fdad`/`122db13`; remaining work is physical acceptance above, not implementation. |
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
