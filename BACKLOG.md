# Mudos Engineering Backlog

Status reconciled 2026-10-10 against canonical source `122db13`, the active
immutable release, safe live appliance inspection, current tests, validation
records, and the operator's recent-use reports. This file is the current status
authority. Detailed prior investigations are preserved verbatim in
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

### LIBRARY-001 — Opening a selected Library dimension

**Status: OPEN · P2, reproduction pending.** Historical operator report: opening
either Provider or Platform card entered Provider regardless of selection.
Current source passes the selected `mode` into `setLibraryDimension`; in-view
dimension switching also exists. Existing tests assert source structure, not a
live controller activation, so the report is not proven stale or fixed.

- **Next:** controller test from Home: select each Library dimension card and
  open it; verify the matching dimension and selected category, then switch
  dimensions in-view and return.
- **Accept:** both entry paths show their selected dimension and in-view
  navigation continues to work. Do not alter known-working in-view behavior.

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

### UI-001 — Default visual baseline acceptance sweep

**Status: IMPLEMENTED — VALIDATION PENDING · P2.** Baseline geometry, status
glyph, common framing, navigation and surfaces are implemented; initial baseline
and glyph checks were accepted. No evidence establishes a complete sweep of the
current production release.

- **Operator check:** controller sweep of Recent right-edge transition, status
  strip, Library/Installable rails, Settings focus/glass, Utilities, Downloads,
  Guide, readable bright/dark backdrops, and unobstructed hint band.
- **Accept:** all listed surfaces remain legible, aligned, navigable, and avoid
  obscuring global hints. Known headless QML fixture failures are tracked under
  operational monitoring, not claimed as visual defects.

### SET-001 — Consolidated System Settings navigation

**Status: IMPLEMENTED — VALIDATION PENDING · P2.** Settings/Utilities structure
and direct Back-to-Home behavior are implemented; operator accepted the latter.
Complete the documented controller/presentation sweep on the active release.

- **Operator check:** System presents only Settings and Utilities; Settings has
  the two-panel layout without a category rail/gap; navigate category/content
  focus and Back; visit Network, Bluetooth, Display, Audio, Controllers, Storage,
  System, nested views, and Utilities. Do not apply settings or pair/eject.
- **Accept:** focus, live models, nested Back and return to Home all work; no
  provider state resets on category changes.

### THEME-001 — Theme engine and theme acceptance

**Status: IMPLEMENTED — VALIDATION PENDING · P2.** ThemeManager, validation,
assets, Settings persistence, motion/material roles, Modern/95, Metalheart and
Frutiger Aero work exist. Modern/95 have operator acceptance; latest stress
themes and complete end-to-end engine coverage do not.

- **Operator check:** inspect actual screens and controller navigation under
  the intended current themes, including Guide and notifications; change theme
  in Settings and verify persistence after normal shell restart; inspect
  Metalheart performance/readability on BC-250.
- **Accept:** no malformed assets, obstructed focus, unreadable states or
  lifecycle regressions; record each theme's accepted scope. Declarative
  multi-stop structural surface material remains optional, not a closure gate.

### LIBRARY-LAUNCH-001 — Library launch/return choreography

**Status: IMPLEMENTED — VALIDATION PENDING · P2.** Source sequences Library
exit, wallpaper content exit, launch overlay, and return restoration; automated
ordering tests exist. No physical acceptance is recorded for the deployed
revision.

- **Operator check:** launch a safe installed title from Library, observe
  Library/home transition ordering, then exit normally.
- **Accept:** no home content appears early; game starts; Mudos returns with
  restored focus, controller navigation, and expected deferred refresh.

### NOTIFICATIONS-001 — Passive notification lifecycle and placement

**Status: IMPLEMENTED — VALIDATION PENDING · P2.** Commits `778fdad` and
`122db13` deployed in active release `122db13-candidate-20261010080657`.
Startup reconciliation is silent; explicit refresh results remain visible;
refresh reconciliation defers during Sessiond gameplay and coalesces until
return; presenter dismisses on bounded severity timeout/producer EOF; geometry
comes from the live status strip and survives games/presenter restart.
Automated focused suite passes. Startup reconciliation produced no presenter;
a runtime notification loaded current geometry. Exact physical placement,
passive input and gameplay behavior await operator observation.

- **Operator check:** confirm alignment to the status strip; trigger one harmless
  notification over shell and while a game is active; verify timeout, no input
  capture, retained geometry after presenter restart/resolution change, and
  deferred provider refresh after normal and abnormal game exit.
- **Accept:** no startup noise; explicit refresh success/failure is retained;
  no notification interaction steals controller input; no guessed placement;
  one coalesced reconciliation runs on shell return.

### EDEN-001 — Eden AppImage migration (remaining controller/lifecycle scope)

**Status: IMPLEMENTED — VALIDATION PENDING · P2.** The external-content/DLC
portion is **accepted**: user reported after reboot that Mario Kart launched
with update/DLC active and updated content visible (validation log 2026-10-03,
fix `f5d1d47`). Do not reopen that portion. Eden input mapping and the full
AppImage migration acceptance remain unverified; earlier records include a
physical input failure and later mapping changes.

- **Operator check:** launch MK8 through current Mudos/Eden path; verify expected
  face/shoulder/menu mapping, rendering, saved profile after Eden restart, clean
  Sessiond/controller return. Do not modify content or NAND.
- **Accept:** required controls work, update/DLC remains active, and shell returns
  normally. Reopen DLC only if a later runtime change regresses it.

### LUTRIS-001 — Mudos-native PC install/add-game flows

**Status: IMPLEMENTED — VALIDATION PENDING · P2.** Operator verified discovery,
required-file selection, installation and launch-attempt UI; search/modal and
controller action fixes were physically exercised. Successful gameplay is not
claimed; the specific Sonic failure remains `LUTRIS-002`.

- **Operator check:** when safe and with approved disposable content, verify
  search/recipe/required-file/install flow, manual registration and unregister
  preserving files. No copyrighted content or operator game data as fixtures.
- **Accept:** complete normal flow, no modal action leaks, and normal shell return.

## Deferred / optional enhancements

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

1. Resolve `LUTRIS-002` and `DOWNLOADS-003` safely if reproduced: protect game
   launch, controller recovery, and return-to-Mudos first.
2. Investigate `DOWNLOADS-001` Clear crash and clipping with synthetic fixtures;
   implement genuine Lutris progress stages (`DOWNLOADS-002`).
3. Complete operator checks for `NOTIFICATIONS-001`, `EDEN-001`,
   `LIBRARY-LAUNCH-001`, `SET-001`, and `UI-001`.
4. Reproduce or retire `LIBRARY-001` through controller-only dimension entry.
5. Implement deferred `UNINSTALL-UX-001` only after its hidden-membership policy
   is decided; then handle optional gameplay-download controls/theme refinements.
