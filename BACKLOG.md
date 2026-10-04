# Mudos Backlog — Canonical Source of Truth

**Last reconciled:** 2026-10-04

This file is the authoritative statement of what is currently outstanding in Mudos.

Historical implementation logs, validation logs, defect ledgers, review notes, chat history, and old `Status: Open` fields are **evidence**, not backlog state. An item is not considered outstanding merely because an older document says it is. If live evidence disagrees with this file, update this file immediately in the same change that establishes the new truth.

## Backlog rules

1. Every engineering task must read `BACKLOG.md` before deciding what is outstanding.
2. New defects/features are added here when accepted into scope.
3. Implementation changes must update the corresponding backlog item in the same commit/PR.
4. Do not close an item on source/tests alone when physical acceptance is part of its gate; move it to `VALIDATION` instead.
5. `DEFERRED` and `PARKED` items are intentionally not active work. They require an explicit decision or trigger before implementation resumes.
6. Old documents under `docs/`, `AURELIA_REVIEW.md`, and historical checkpoints must not silently reopen work. Reconcile them against current source/runtime first.
7. Keep entries concise and factual. Put detailed archaeology/evidence in the relevant engineering/validation document and link it from the item.

### Status vocabulary

- `ACTIVE` — implementation/diagnosis should proceed now.
- `VALIDATION` — implementation exists; a defined acceptance gate remains.
- `BLOCKED` — cannot proceed until the named dependency is resolved.
- `DEFERRED` — valid future work intentionally scheduled later.
- `PARKED` — investigation intentionally stopped; do not redesign/reopen without a new decision or new evidence.
- `CLOSED` — resolved. Closed facts may remain here when retaining them prevents stale historical notes from reopening the issue.

---

## Current work

### EDEN-001 — Complete Eden AppImage migration

- **Status:** `ACTIVE`
- **Priority:** P0
- **Area:** Eden / Switch provider / Session lifecycle
- **Current truth:** Mudos has migrated Eden from the Flathub 0.2.1 build (`58c1e20ee5`) to a pinned official x86_64 Clang-PGO AppImage reporting v0.8.1, source commit `d16735f5b618942136d6ab53466e3be0a382c30a`. The AppImage migration, prompt return-to-shell lifecycle fix, and coherent NAND/profile migration repair are deployed to `/opt/lulu/dev-current`. `/opt/lulu/current` remains unchanged and the dev runtime is non-promotable.
- **Latest physical acceptance result:** **FAILED**. Mario Kart 8 Deluxe still launches as **v1.4.0**, not the expected **v4.0.0 + DLC**, and controller input no longer works in Eden. Treat both as current AppImage-migration defects. Do not promote.
- **Known repaired defects:**
  - old Eden 0.2.1 intermittent whole-scene pink/green colour cast in Mario Kart 8 Deluxe;
  - AppImage helper processes delaying return to Mudos after Eden's real Gamescope surface owner exited;
  - additive NAND migration copying legacy saves while skipping conflicting `profiles.dat`.
- **Current defects to diagnose:**
  - **EDEN-001A — external update/DLC discovery:** old and new Eden configs both scan `/home/lulu/Games/ROMs/switch`; the update/DLC NSPs remain there, but Eden v0.8.1 launches MK8 as v1.4.0 rather than v4.0.0 + DLC. Investigate current Eden external-content discovery/attachment semantics and config compatibility before moving files or reinstalling content.
  - **EDEN-001B — controller regression:** controllers worked with the prior Eden runtime but do not work after the AppImage migration. Treat this as a provider/config compatibility regression. Compare v0.2.1 and v0.8.1 controller schema, SDL backend/device enumeration, generated `qt-config.ini`, and the exact runtime environment/InputPlumber devices consumed by Eden. Do not weaken the global controller architecture or add model-specific allowlists as a workaround.
- **Acceptance gate:**
  - no orphaned-profile warning;
  - existing profile and save are present and unchanged;
  - Mario Kart 8 Deluxe launches as v4.0.0 with DLC active;
  - controller operation is normal through Mudos launch;
  - quit returns promptly to Mudos with shell input restored;
  - repeat the visual regression run and confirm no pink/green cast.
- **Promotion:** only after this complete physical gate passes should the Eden migration be promoted into the next immutable release.

### META-001 — Reconcile historical backlog material into this file

- **Status:** `ACTIVE`
- **Priority:** P1
- **Area:** Project governance / backlog accuracy
- **Current truth:** Mudos has several historical sources that mix implemented, partially implemented, physically unvalidated, deferred, and genuinely open work. This has caused stale issues to be reported as current work.
- **Sources to reconcile:**
  - `docs/visual-polish-log.md`
  - `docs/oobe-defect-ledger.md`
  - `docs/reconciliation-backlog.md`
  - `docs/astra-execution-log.md`
  - `docs/validation-log.md`
  - `AURELIA_REVIEW.md`
- **Rule:** do **not** bulk-copy their old `Open`, `Pending`, or limitation lists here. Check each candidate against current source, current runtime evidence, later commits, and physical acceptance. Add only work that is still genuinely outstanding.
- **Done when:** all surviving current work from those documents is represented here and the older documents explicitly remain historical/evidence-only.

---

## Deferred / parked

### ACQ-001 — Pause downloads during gameplay

- **Status:** `DEFERRED`
- **Area:** Acquisition / Settings
- **Current truth:** notification v1 is implemented independently. Gameplay download pausing remains a future generic acquisition policy.
- **Required semantics:** capability-aware provider pause support; distinguish policy-paused jobs from user-paused jobs; resume only jobs paused by the gameplay policy when gameplay ends.
- **Trigger to resume:** final Settings/acquisition-policy pass.

### EMU-PCSX2-001 — PCSX2 provider/pause-menu regression archaeology

- **Status:** `PARKED`
- **Area:** PCSX2 / provider menu / synthetic input
- **Current truth:** physical keyboard Escape opens PCSX2's pause/FullscreenUI menu; `OpenPauseMenu = Keyboard/Escape` is therefore correct. Persistent uinput keyboard exists, udev/InputPlumber recognise it, and Gamescope has its event node open, but synthetic Escape does not open the menu.
- **Constraint:** historical evidence says this path worked previously. Treat as regression archaeology; do not redesign the PCSX2 control path or temporarily remap the hotkey without an explicit decision to reopen it.

### HW-BC250-001 — Add BC-250 VRAM temperature telemetry to cooling policy

- **Status:** `DEFERRED`
- **Area:** BC-250 hardware / fan control
- **Current truth:** ordinary hwmon exposes GPU edge, CPU/Tctl, motherboard and NVMe temperatures but no VRAM sensor. Lulu is on BIOS P3.00 and runs both `bc250-fancurve.service` and `cyan-skillfish-governor-smu.service`. Community tooling can read GDDR6 temperature through SMU/UMC MR3, but SMU access must be coordinated with the existing governor.
- **Reason deferred:** the Mario Kart colour-cast investigation no longer points to VRAM overheating; the rendering defect disappeared after moving away from Eden 0.2.1.
- **Trigger to resume:** hardware telemetry/fan-policy enhancement work, not Eden fault diagnosis.

---

## Closed facts retained to prevent stale reopening

### STEAM-DBD-001 — Dead by Daylight reports Steam offline

- **Status:** `CLOSED`
- **Area:** Steam / Aurelia / resident Steam integration
- **Current truth:** this historical limitation was fixed by running Steam on its own resident surface/runtime. Do **not** report Dead by Daylight's old Steam-offline result as an outstanding issue unless a new physical regression is observed.

### EDEN-MK8-001 — Mario Kart 8 Deluxe intermittent pink/green whole-scene cast

- **Status:** `CLOSED`
- **Area:** Eden / Vulkan rendering
- **Current truth:** the symptom occurred on Eden 0.2.1 (`58c1e20ee5`). After migration to the newer official Eden AppImage, four consecutive races completed without the bug. The hardware/cooling configuration was otherwise unchanged, strongly tying the symptom to the old Eden rendering path rather than BC-250 VRAM cooling.
- **Note:** EDEN-001 still requires a post-repair visual recheck as part of full migration acceptance; that does not reopen this old 0.2.1 rendering defect by itself.

---

## Historical documents

The following remain useful for archaeology, implementation detail, and evidence, but are **not authoritative backlog state**:

- `docs/visual-polish-log.md`
- `docs/oobe-defect-ledger.md`
- `docs/reconciliation-backlog.md`
- `docs/astra-execution-log.md`
- `docs/validation-log.md`
- `AURELIA_REVIEW.md`

When one of these reveals genuinely surviving work, add or update a canonical item above with its **current** state rather than relying on the historical wording.
