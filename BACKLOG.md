# Mudos Backlog — Canonical Source of Truth

**Last reconciled:** 2026-10-04

This file is the authoritative statement of what is currently outstanding in Mudos.

Historical implementation logs, validation logs, defect ledgers, review notes, chat history, and old status fields are **evidence, not backlog state**. An item is not considered outstanding merely because an older document says it is. If live evidence disagrees with this file, update this file immediately in the same change that establishes the new truth.

## Backlog rules

1. Every engineering task must read `BACKLOG.md` before deciding what is outstanding.
2. New defects/features are added here when accepted into scope.
3. Implementation changes must update the corresponding backlog item in the same commit/PR.
4. Do not close an item on source/tests alone when physical acceptance is part of its gate; move it to `VALIDATION` instead.
5. `DEFERRED` and `PARKED` items are intentionally not active work.
6. Old documents under `docs/`, `AURELIA_REVIEW.md`, and historical checkpoints must not silently reopen work.
7. Keep entries concise and factual. Detailed archaeology belongs in the relevant evidence document.
8. When new evidence changes current state, update this file, not only a historical ledger.

### Status vocabulary

- `ACTIVE` — implementation/diagnosis should proceed now.
- `VALIDATION` — implementation exists; a defined acceptance gate remains.
- `BLOCKED` — cannot proceed until the named dependency is resolved.
- `DEFERRED` — valid future work intentionally scheduled later.
- `PARKED` — investigation intentionally stopped.
- `CLOSED` — resolved; retained where useful to prevent stale reopening.
- `SUPERSEDED` — replaced by a newer, narrower item or architecture; retained only to prevent stale reopening.

---

## Current work

### EDEN-001 — Complete Eden AppImage migration

- **Status:** `VALIDATION`
- **Priority:** P0
- **Area:** Eden / Switch provider / Session lifecycle
- **Current truth:** The v0.8.1 official Eden AppImage migration and subsequent external-content configuration work are deployed to `/opt/lulu/dev-current`; `/opt/lulu/current` remains unchanged. The current implementation has passed automated validation (1,169 tests, 85 subtests) and the latest external-content run produced the expected Eden AOC/update discovery evidence.
- **Physical acceptance:** Pending only because the display is currently unavailable. The implementation is believed ready but has not yet been physically accepted.
- **Acceptance gate:** launch Mario Kart 8 Deluxe as v4.0.0 with DLC active; verify Wave 1 content; verify normal controller operation; verify rendering; verify prompt return to Mudos with shell input restored; repeat the visual regression check and confirm no pink/green cast.
- **Promotion:** only after the complete physical gate passes.

### UI-001 — Complete V1 UI and presentation review

- **Status:** `VALIDATION`
- **Priority:** P0
- **Area:** UI / presentation / final acceptance
- **Current truth:** The implementation generally meets the visual brief, but Mudos has not had a deliberate end-to-end presentation review since the major Library/Installable/Settings/provider changes. Historical visual items that are functionally complete should not be reopened individually.
- **Review scope:** Home, Library, Installable, Store, Settings, Guide, Downloads, status bar, glass surfaces, spacing, artwork/media presentation, empty states, OSK presentation, provider/category presentation, and OOBE presentation.
- **Also fold into this pass:** final controller sweep, integration/provider/media checks, and the remaining physical validation that does not justify a standalone engineering item.

### SET-001 — Settings UI overhaul

- **Status:** `ACTIVE`
- **Priority:** P1
- **Area:** Settings
- **Current truth:** System-settings capability is sufficient for V1 and is not an engineering blocker. The Settings UI itself needs a complete overhaul to match the current Library/Installable presentation language.

### STEAM-001 — Restore Steam provider menu/overlay in Guide

- **Status:** `ACTIVE`
- **Priority:** P1
- **Area:** Steam / Guide / Aurelia
- **Current truth:** The Aurelia migration and subsequent Steam cleanup preserved the launch path but lost the previous Steam provider-menu/overlay access from Guide.
- **Requirement:** restore the Steam-specific provider/overlay surface without reopening the superseded Steam lifecycle architecture.

### EMU-001 — Restore functional emulator provider settings and native UI access

- **Status:** `ACTIVE`
- **Priority:** P1
- **Area:** Eden / Dolphin / PCSX2
- **Current truth:** Eden and Dolphin provider settings are still not sufficiently functional/surfaced, and PCSX2 still has the historical synthetic Escape/provider-menu regression.
- **Requirement:** provide a coherent Mudos-owned settings/provider path for Eden and Dolphin and resolve the PCSX2 provider/pause-menu path using the historical known-good behaviour rather than redesigning the control path blindly.

### OSK-001 — Restore managed OSK input and text-entry flow

- **Status:** `ACTIVE`
- **Priority:** P1
- **Area:** OSK / text entry / Guide / Flathub
- **Current truth:** Multiple OSK regressions are present:
  - Guide + X no longer opens the OSK;
  - Flathub does not automatically invoke the OSK when a text field receives focus;
  - OSK input does not live-update the active text field;
  - a previously fixed duplicate/multiple-button-press regression has returned.
- **Requirement:** recover the historical duplicate-input fix by comparing the current implementation with the known-good commit, then restore the complete text-entry flow.

### LIB-001 — Finish Installable navigation/category behaviour

- **Status:** `ACTIVE`
- **Priority:** P1
- **Area:** Library / Installable
- **Current truth:** Basic scrolling and category navigation work, but the current Aurelia provider model requires further refinement.
- **Requirements:** LT/RT should page through the list; switching category must preserve the user's position within that category; complete the remaining provider/category presentation tweaks introduced by Aurelia.
- **Related presentation checks:** screenshot/media availability and list/glass presentation belong in UI-001 unless a new functional defect is found.

### HOME-001 — Define the no-installed-games empty state

- **Status:** `ACTIVE`
- **Priority:** P2
- **Area:** Home / Library
- **Current truth:** There is still no deliberately designed empty state for an appliance with no installed games.

### STORE-001 — Add external store shortcuts

- **Status:** `ACTIVE`
- **Priority:** P2
- **Area:** Store
- **Current truth:** Flathub and Installable shortcuts are correct. The missing destinations are simple external shortcuts to Steam, GOG, and Epic Games; Mudos does not provide purchasing there.
- **Constraint:** do not redesign the Store surface around purchasing.

### OOBE-STEAM-001 — Revalidate Steam OOBE end to end

- **Status:** `ACTIVE`
- **Priority:** P0
- **Area:** OOBE / Steam / Gamescope / resident Steam runtime
- **Current truth:** Resident host Steam is proven to authenticate and remain online on isolated `DISPLAY=:99`, while games remain on the Mudos Gamescope display. The runtime architecture is accepted, but Steam OOBE has changed and needs a complete end-to-end pass.
- **Requirement:** during Steam sign-in, surface Steam through Gamescope on the main display; once authentication completes, move/return Steam to the resident `:99` display and leave it resident for normal runtime.

### PACK-001 — Re-run destructive fresh-install/OOBE acceptance

- **Status:** `ACTIVE`
- **Priority:** P0
- **Area:** Installer / OOBE
- **Current truth:** The canonical installer has previously passed a destructive rehearsal, but OOBE has changed since then. A new clean-appliance acceptance is required, with particular attention to the current Aurelia and Steam OOBE paths and removal of obsolete Questarr assumptions.
- **Gate:** complete fresh install, first-run OOBE, provider setup, Steam/Aurelia setup, service readiness, persistence, and return to normal runtime.

### UNINSTALL-001 — Complete provider-owned uninstall coverage

- **Status:** `ACTIVE`
- **Priority:** P1
- **Area:** Providers / acquisition / uninstall
- **Current truth:** Provider-owned uninstall is only partially complete. A provider-by-provider sweep is required to establish that each supported provider owns and correctly executes its uninstall path.

### PROTONDB-001 — Complete ProtonDB live/presentation validation

- **Status:** `VALIDATION`
- **Priority:** P2
- **Area:** Metadata
- **Current truth:** ProtonDB enrichment is implemented. Remaining live/presentation checks belong in the final V1 testing pass.

### ADMIN-001 — Validate Admin integration/service statuses

- **Status:** `VALIDATION`
- **Priority:** P2
- **Area:** Admin
- **Current truth:** The Admin status model is implemented; the remaining work is a complete connected/not-connected status validation sweep.

### OOBE-006 — Keep Steam username visible while typing

- **Status:** `ACTIVE`
- **Priority:** P2
- **Area:** Steam OOBE / text entry
- **Current truth:** The Steam username field is still incorrectly masked while being entered and should remain visible during entry.


### LUTRIS-001 — Manual user-provided Lutris installation flow

- **Status:** `ACTIVE`
- **Priority:** P1
- **Area:** Lutris / acquisition / installation
- **Current truth:** Mudos does not yet have a complete user-facing flow for supplying files for a manual Lutris installation.
- **Requirement:** provide a controller-first/user-friendly flow for selecting or supplying the required installation files, handing them to the Lutris provider, and completing the installation into the canonical Mudos game layout.

### QUIVER-001 — Quiver acquisition and library provider

- **Status:** `ACTIVE`
- **Priority:** P1
- **Area:** Quiver / acquisition / library
- **Current truth:** Quiver is intended to become a first-class Mudos acquisition and library provider.
- **Requirement:** integrate Quiver into the provider model so its acquisition state and resulting games are represented consistently in Mudos's library and installation flows.

### BOOT-001 — Restore automatic Limine default-entry selection

- **Status:** `ACTIVE`
- **Priority:** P1
- **Area:** Boot / Limine
- **Current truth:** Recent Limine work has left the boot menu waiting for manual selection instead of automatically selecting the Mudos default entry.
- **Requirement:** restore automatic selection of the configured/default Mudos entry while retaining the intended Limine boot-menu behaviour.


### REMOTE-001 — Restore remote display acceptance path

- **Status:** `ACTIVE`
- **Priority:** P0
- **Area:** Acceptance testing / remote display
- **Current truth:** The Lulu hardware is now physically downstairs, so controllers can be connected directly to Lulu. We therefore only need a remote video view on Aslik while the TV is occupied.
- **Immediate requirement:** restore the existing development-only Sunshine host as a display-only acceptance aid. Do not rely on Sunshine for controller input; local controllers remain directly attached to Lulu.
- **Preferred future UX:** investigate a browser-based viewer at `mudos.local` so Aslik can view the Lulu display without a native streaming client. This is a convenience layer, not a prerequisite for acceptance.
- **Acceptance:** stream the live Mudos/Gamescope display to Aslik reliably while the TV remains in use, with no impact on the local controller path or Mudos session lifecycle.

---

## Deferred / parked

### ACQ-001 — Pause downloads during gameplay

- **Status:** `DEFERRED`
- **Area:** Acquisition / Settings
- **Current truth:** Gameplay download pausing remains a future generic acquisition policy. It is not a V1 blocker.
- **Trigger:** final Settings/acquisition-policy work.

### HW-BC250-001 — Add BC-250 VRAM temperature telemetry to cooling policy

- **Status:** `DEFERRED`
- **Area:** BC-250 hardware / fan control
- **Current truth:** The old Mario Kart colour-cast investigation no longer points to VRAM overheating; the symptom was tied to the old Eden 0.2.1 rendering path.
- **Reason deferred:** useful hardware enhancement, but **not a V1 blocker**.

---

## Closed facts retained to prevent stale reopening

### STEAM-DBD-001 — Dead by Daylight reports Steam offline

- **Status:** `CLOSED`
- **Current truth:** The historical Steam-offline problem was resolved by the resident isolated Steam runtime. Disney Speedstorm has also passed as a Steam-dependent physical control test.

### EDEN-MK8-001 — Mario Kart 8 Deluxe intermittent pink/green whole-scene cast

- **Status:** `CLOSED`
- **Current truth:** This was an Eden 0.2.1 rendering-path defect. It is not a BC-250 VRAM-cooling V1 blocker.
- **Note:** EDEN-001 still includes a final visual regression check.

### EMU-002 — Dolphin quit confirmation

- **Status:** `CLOSED`
- **Current truth:** Dolphin quits without the old confirmation requirement.

### PROV-002 — Epic/GOG artwork and metadata

- **Status:** `CLOSED`
- **Current truth:** The historical artwork/metadata defect is resolved.

### OOBE-002 — Epic/GOG setup presentation

- **Status:** `CLOSED`

### OOBE-003 — Individual integration API-key screens

- **Status:** `CLOSED`

### OOBE-004 — Final OOBE completion status

- **Status:** `CLOSED`

### OOBE-005 — Integration Test and Save / failure flow

- **Status:** `CLOSED`

### ADMIN-002 — Combine Integrations and Services

- **Status:** `CLOSED`

### VP-001 through VP-004, VP-006, VP-008, VP-009, VP-010, VP-012, VP-016, VP-017

- **Status:** `CLOSED`
- **Current truth:** These historical visual defects were confirmed complete during reconciliation. Remaining presentation judgement belongs to UI-001.

### VP-015 — Metadata alignment beneath preview artwork

- **Status:** `SUPERSEDED`
- **Current truth:** The original requirement no longer represents the current presentation model.

### EMU-LEGACY-001 — A/B and X/Y remapping requirement

- **Status:** `SUPERSEDED`
- **Current truth:** This standalone remapping feature is no longer wanted.

---

## Retired / superseded historical scope

The following historical items were explicitly reconciled during the 2026-10-04 rapid-fire pass and must not be treated as outstanding work:

- Questarr: **abandoned entirely**. Remove Questarr from future scope rather than carrying old setup/authentication work forward.
- SteamCMD authentication persistence diagnostics: superseded by Aurelia for Steam game launch; do not reopen as a game-launch requirement.
- Steam canonical install placement/update semantics: superseded by Aurelia.
- Old Steam lifecycle/UI-bridge ownership ambiguity: superseded by the current Aurelia + resident Steam architecture.
- Old local-runtime/emulator lifecycle gap: considered clean; remaining emulator work is captured by EMU-001.
- Old RetroArch audio validation blocker: obsolete.
- Old Gamescope control-state/package-policy ambiguity: obsolete.
- Synthetic AppID namespace investigation: obsolete.
- Old broad provider-menu review: superseded by STEAM-001 and EMU-001.
- Old controller composite-persistence ambiguity and low-level InputPlumber boundary items: superseded by the current controller architecture; remaining physical controller validation belongs in UI-001.
- Old Store placeholder task: superseded by STORE-001.
- Old generic Settings capability gap: system capability is sufficient for V1; remaining work is SET-001's UI overhaul.
- Historical cold-boot/hotplug, standard-gamepad, and controller-inventory investigations: no longer standalone engineering tasks; remaining acceptance belongs in UI-001.
- Historical OOBE credential/presentation items already marked CLOSED above remain closed.

---

## Final V1 gate

Publication remains gated on the **comprehensive V1 user-testing and UI presentation pass**. That pass must cover the implemented system as a whole rather than resurrecting historical defect lists: Eden, Steam/Aurelia, controller behaviour, provider/media presentation, OOBE, Settings, Library/Installable, Admin, Downloads, delegated surfaces, launch/exit/recovery, and the final visual review.

---

## Historical documents

The following remain useful for archaeology and evidence, but are **not authoritative backlog state**:

- `docs/visual-polish-log.md`
- `docs/oobe-defect-ledger.md`
- `docs/reconciliation-backlog.md`
- `docs/astra-execution-log.md`
- `docs/validation-log.md`
- `AURELIA_REVIEW.md`

Old `Open`, `Pending`, `Blocked`, or `Not tested` entries in those documents do not reopen work unless a new current backlog item is created.
