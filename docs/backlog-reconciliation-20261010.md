# Backlog reconciliation — 2026-10-10

This report preserves the investigation basis for the concise current
[`BACKLOG.md`](../BACKLOG.md). The previous 1,323-line backlog is preserved
verbatim in [`backlog-archive-20261010.md`](backlog-archive-20261010.md);
historical validation remains append-only in `validation-log.md` and
`astra-execution-log.md`.

## Appliance baseline and evidence limits

- Canonical checkout: `/home/josh/src/lulu`, clean at `122db131e890312ae0292a802d6dddd4f0da2a18`; branch `mudos/modularisation` matches `origin`.
- Active release: `/opt/lulu/current -> /opt/lulu/releases/122db13-candidate-20261010080657`. This is production and includes the notification changes. `/opt/lulu/dev-current` is a separate non-promotable, non-running development tree, marked `promotable=false`, source HEAD `76d3300`, `dirty=false`.
- Services: Sessiond, Consoled, Acquisitiond, InputPlumber, and isolated Steam runtime active. Admin Web inactive. Sessiond reports idle shell, ready presentation; Steam runtime authenticated, restart count zero.
- Display: kernel command line has no `video=DP-1` argument. Commit `76d3300` removed the tracked forced DP-1 setting; the old local Limine override documented in the archived ticket is no longer present at its recorded path. Current `/sys/class/drm/card1-DP-1` is connected/enabled, DPMS On, 1920×1080; Gamescope/Xwayland view is 1920×1080. Current evidence is a logical healthy display only.
- Controller: live Sessiond snapshot has one connected Xbox 360 controller, SDL index 0, one InputPlumber composite and one gamepad target. Recent InputPlumber journal includes transient `No such device`, empty gamepad order, and source-change errors during node churn; the present inventory recovered to one composite/target. No restart or navigation interruption was induced. Operator reports recent boots and navigation have been successful.
- Catalogue/acquisition: local read-only catalogue has provider rows for Steam/Aurelia, RomM, emulators, Flatpak, Lutris, GOG and Epic. Acquisition endpoint reports 95 historical jobs and zero active jobs. No provider refresh, download, install, uninstall, or content mutation was initiated.
- Current boot has BC-250 relink messages (stream down / short blank) but no observed current no-signal report, forced-mode argument, or Sessiond recovery action. Do not infer physical failure from kernel messages alone.
- Focused safe automated run: `PYTHONPATH=src pytest -q tests/test_notification_convergence.py tests/test_recovery_controller.py tests/test_system_settings.py tests/test_downloads_surface.py tests/test_eden_provider.py tests/test_desktop_mode.py tests/test_lutris_install.py` — **66 passed**.
- Full suite: `PYTHONPATH=src pytest -q` — **1,269 passed, 14 failed, 88 subtests passed**. Failures are seven? Eight `test_console_ui.py` stale source-text contracts, two Dolphin fixtures lacking the newly used catalogue-store method, one stale native easing-literal contract, payload manifest checksum mismatch, release fixture not producing `mudos-desktop-wallpaper`, and one Steam OOBE expectation mismatch. These are test/fixture/release hygiene issues, not demonstrated live faults; see test output from this audit/session and current source. No code was modified to hide or fix them.

## Complete former-open-item status matrix

| ID | Reconciled status | Evidence / remaining work |
| --- | --- | --- |
| DISPLAY-001 | RESOLVED — MONITORING | User reports stable recent reboots/normal use. Forced DP-1 removed by `76d3300`; live command line has no override. Historical no-signal remained real and no automatic physical-link recovery proof exists. Monitor; no destructive test. |
| CTRL-001 | RESOLVED — MONITORING | User reports successful repeated recent boot/navigation. Live one composite/target and SDL index 0. Transient stale-node churn remains in recent log, so race is not proven eliminated. Preserve diagnostics for recurrence; no service restart. |
| RECOVERY-001 | CLOSED | Recovery component reads InputPlumber `GamepadOrder`; Sessiond controller details are also part of recovery evidence. Live counts agree. Existing recovery controller tests included in 66-pass focused run. No Recovery-mode entry was needed or induced. |
| SET-001 | IMPLEMENTED — VALIDATION PENDING | Source and focused tests present; operator already accepted direct Back-to-Home. Still needs safe controller sweep of Settings/Utilities and categories/nested pages; exact procedure in BACKLOG. |
| LIBRARY-001 | OPEN — REPRODUCTION PENDING | Current source maps selected dimension mode and in-view cycling; source-level regression assertions exist. No live controller test was run, so old operator observation remains unresolved. |
| UNINSTALL-UX-001 | IMPLEMENTATION WORK (DEFERRED) | Provider uninstall is closed/accepted, but agreed temporary hide/reconcile/restore UX and hidden-title membership policy are not implemented. |
| RECENTS-001 | CLOSED | Aurelia projection and direct Steam launch recents fixed/tested; no remaining task. |
| LIBRARY-LAUNCH-001 | IMPLEMENTED — VALIDATION PENDING | Source choreography and automated ordering tests exist; still needs a safe live launch/return observation. |
| NOTIFICATIONS-001 | IMPLEMENTED — VALIDATION PENDING | Commits `778fdad`, `122db13` deployed. Startup suppression, gameplay refresh gate/coalescing, timeout/EOF cleanup, geometry record/watch/placement implemented. Automated tests passed; actual placement, passive input, gameplay deferral and resolution/restart behavior remain operator acceptance. |
| LUTRIS-002 | OPEN | Real launch hang/error-dialog observation remains without a demonstrated correction. Need safe disposable reproduction and verify shell recovery; no active game was disturbed. |
| DOWNLOADS-001 | OPEN | Reported clipping and Clear-related crash not root-caused or retested on synthetic failure fixtures. |
| DOWNLOADS-002 | OPEN | Observed Lutris install stages reported only as “Downloading”; useful stage projection remains unimplemented/unverified. |
| DOWNLOADS-003 | OPEN — UNCONFIRMED | Separate operator-reported crash at Lutris install completion; no evidence ties it to LUTRIS-002 and no safe large install was repeated. |
| QUIVER-001 | ABANDONED | Lutris is intended PC installation foundation. Do not recreate Quiver/Questarr work. |
| CTRL-001 | See above | Kept out of active defect queue; monitoring only. |
| LUTRIS-001 | IMPLEMENTED — VALIDATION PENDING | Search, recipe, required-file, install and launch-attempt paths physically exercised. Successful gameplay and manual-source file preservation still need approved disposable/physical check; `LUTRIS-002` separate. |
| EDEN-001 | IMPLEMENTED — VALIDATION PENDING (partial acceptance) | Mario Kart update/DLC accepted by user on 2026-10-03: rebooted Mudos launch showed updated game content. Do not reopen DLC. Controller mapping/complete current AppImage lifecycle remain unaccepted; earlier input failure is in validation history. |
| DESKTOP-001 | ACCEPTED / CLOSED | 2026-10-08 corrective runtime and visual acceptance documented in archive: Modern/95 wallpaper, panel/menu/launchers, Network Settings, panel controls, safe power-menu contents, clean Sessiond return. No restart/shutdown test claimed or required. |
| UI-001 | IMPLEMENTED — VALIDATION PENDING | Baseline and status glyph individually accepted; full screen-by-screen current-release visual sweep remains. |
| THEME-001 | IMPLEMENTED — VALIDATION PENDING | Modern/95 accepted; latest Metalheart/Frutiger and complete theme-engine screen/controller/performance sweep not accepted. Declarative material gap is optional. |
| UNINSTALL-001 | ACCEPTED / CLOSED | Provider-owned uninstall implementation and operator acceptance retained in old backlog/archive. Distinct hide-while-removing requirement is UNINSTALL-UX-001. |
| STEAM-ROUTE-001, STEAM-CATALOGUE-001 | ACCEPTED / CLOSED | Physical route and Aurelia authority checks in validation log; source/current release includes dedupe/alias follow-ups. |
| OVERLAY-001 | ACCEPTED / CLOSED | User physical acceptance documented separately; not an active item. |

## Reconciled special cases and missing items

- **DISPLAY-001:** Historical evidence included a forced output that could keep
  DP-1 logically connected across link loss. That mechanism has been removed
  from current tracked/live boot configuration. User's new stable-operation
  report is material evidence and outweighs stale “still forced” backlog text.
  Since the original failure mechanism is not conclusively eliminated,
  `RESOLVED — MONITORING` is more accurate than either active-critical or
  unqualified closed. No PCI FLR, GPU reset, risky DRM manipulation, kernel
  downgrade, forced-link edit, or source-switch experiment was repeated.
- **CTRL-001:** Current inventory is healthy and user has successful real-world
  boot/navigation reports. Transient InputPlumber churn means this does not prove
  every startup/hotplug race is eliminated. It is monitoring, not an active
  controller incident. Never restart InputPlumber solely to reproduce it.
- **EDEN-001:** Validation log section “Mario Kart external-content physical
  acceptance — 2026-10-03” explicitly accepts the external-content/DLC fix and
  says no DLC retest is requested absent later code changes. Historical
  controller mapping failures and later changes still warrant a focused
  acceptance check; the ticket is not wholly closed.
- **DESKTOP-001:** Older trailing text claiming visual acceptance pending is
  superseded by the later 2026-10-08 corrective acceptance record in the same
  archived section. Close the tested Modern/95 desktop behavior only; do not
  infer shutdown/restart actions were exercised.
- **NOTIFICATIONS-001:** The two latest commits are in active production. Old
  missing presenter, unlimited lifetime, and absent gameplay gating notes are
  implementation archaeology, not current open bugs. Physical passive overlay
  acceptance remains.
- **RECENTS-001** marked FIXED but buried under ACTIVE is closed; **QUIVER-001**
  remains abandoned, not planned. Both are classified accordingly.
- **SET-001/UI-001/THEME-001:** distinguish implemented behavior and earlier
  partial operator acceptance from the exact uncompleted visual/controller
  sweep; theme material expansion is optional, not a blocker.
- **Steam metadata:** validation record states 69 `steam:` available rows have
  matching Aurelia entitlements and are suppressed from installable view;
  some have distinct metadata/artwork. Metadata-aware merge/removal is optional
  cleanup, not a current correctness defect. No destructive catalogue edit is
  authorized by this audit.
- **BC-250 CU unlock/toolkit profile generation:** search of source, commit
  history and existing backlog found no retained requirement or current ticket
  supporting this as unfinished Mudos work. It is intentionally not re-created
  from a historical mention alone.
- **Gameplay download controls:** previous notification record explicitly says
  gameplay pausing was deferred. Retained as optional policy/UX decision, not
  assumed requirement and not implemented here.
- **Full-suite failures:** promoted to operational monitoring/next-cycle test
  hygiene rather than misrepresented as unrelated forever or silently ignored.
  Failures were reproduced in this audit; scope is described in BACKLOG.

## Physical acceptance still owned by operator

1. Notification overlay exact status-strip placement, passive/non-stealing input,
   timeout, over-game behavior, geometry after presenter restart/resolution
   change, and reconciliation on normal/abnormal game exit.
2. Eden current controller mapping, rendering and clean lifecycle return (DLC
   acceptance remains intact unless code later regresses it).
3. Safe Library launch/return choreography and LUTRIS install/manual-registration
   completion flow using approved disposable content only.
4. Controller sweep of Settings/Utilities and the default visual baseline; theme
   visual/controller/performance acceptance for themes not yet accepted.
5. DISPLAY/CTRL are not demanded as experiments: only report recurrence during
   normal operation and capture passive diagnostics. Do not run risky recovery
   tests to satisfy old closure criteria.

No current reproducible live appliance defect was found during this read-only
reconnaissance. The historically observed Lutris/Downloads/Library defects
remain actionable because they were not shown corrected, but were not safely
reproduced in the idle baseline. The operator's stable display/controller
reports are treated as operational evidence, not proof that all failure races
are impossible.

## Operator acceptance / implementation addendum — 2026-10-10

The following replaces the earlier “physical acceptance still owned by
operator” status above and the corresponding pending rows in the historical
matrix. The original audit evidence remains unchanged for context; current
status authority is `BACKLOG.md`.

- User reports **UI-001**, **SET-001**, both **LIBRARY-LAUNCH-001** physical
  tests, all three **EDEN-001** physical tests, and **NOTIFICATIONS-001** passed
  or were explicitly accepted. Eden acceptance includes rendering, controls,
  persistence across relaunch and clean Mudos return; previously accepted
  update/DLC behavior remains accepted. Notification user acceptance explicitly
  includes lifecycle, refresh deferral and placement. These are recorded as
  physical user evidence, distinct from automated coverage.
- User explicitly deferred **THEME-001** to the global final UI pass and deferred
  final **LUTRIS-001** acceptance to a dedicated provider milestone. Lutris work
  is linked to open `LUTRIS-002` and `DOWNLOADS-001/002/003`; no Lutris work was
  started as part of this update.
- User reconfirmed **LIBRARY-001** physically. Source analysis found mutable MRU
  order and selected-index reset in the landing activation path. The correction
  removes Library-only MRU ordering, fixes card sequence as Platform, Provider,
  Game Mode, Genre, and carries semantic mode identity from the selected card
  into Library activation. In-view wrap/category behavior is preserved. The
  implementation remains pending user physical confirmation of all four entry
  routes; it is not marked accepted.
