# Aurelia launch and Steam update investigation — 2026-10-10

## Scope and operational state

This is a read-only investigation. No game was launched during this pass; the
Sessiond shell was idle, the authenticated resident Steam runtime was active, and
no Aurelia play process was running. No install, manifest, prefix, save, or user
data was changed. Do not treat this report as permission to reinstall or delete
anything. Findings are from the current appliance and can change after a repair.

## Get To Work (AppID 2706170)

- Aurelia 0.1.37 `--json list --installed` reports **Get To Work**, installed,
  Windows platform, owned, update unavailable, at
  `/home/lulu/.local/share/Steam/steamapps/common/Get To Work`.
- The catalogue has matching `steam:` and `steam-aurelia:` entries, both marked
  installed/launchable. This is an identity projection, not independent install
  evidence.
- `appmanifest_2706170.acf` exists and agrees on AppID, title and install
  directory (`StateFlags=4`, build `21610838`). The Windows executable exists at
  `Get To Work/Get To Work/Get To Work.exe`, owned by `lulu`, mode 0755. The
  manifest and executable paths under `.local/share/Steam` and
  `Games/Executables/steam` resolve to the same device/inode. Installation
  provenance cannot be established from current metadata: **Aurelia, Steam, or
  SteamCMD origin is unknown**. A shared Steam library or manifest alone does
  not prove provenance.
- Aurelia's latest logged command resolves to the Mudos graphical wrapper, then
  `/home/lulu/Games/Executables/steam/steamapps/common/Proton - Experimental/proton
  run .../Get To Work.exe`; CWD is the install directory. This is a Windows game
  launched through Proton, not a native Linux launch. The effective
  compatibility data path is
  `/home/lulu/Games/Executables/steam/steamapps/compatdata/2706170`; Aurelia's
  logs also identify a separate master prefix under its config directory.
  This prefix arrangement and Steam DRM ownership behavior need comparison with
  the working title before any change. Do not expose or copy Aurelia session
  credentials.
- Four latest per-session summaries report `Failure`, `failed_after_spawn`, exit
  code 1, lifetime about 2000 ms and detail `missing_required_module`. Their
  `events.jsonl` records show successful resolution/preflight/spawn, then early
  exit and launch failure. The log contains missing Proton Wine-Mono/Xalia module
  messages, but available evidence does **not yet prove which missing module is
  fatal** or whether the Proton runtime, its installation, or the game is causal.
  The immediately prior session falsely reported `Success`/`verified` with the
  same short lifetime and a `game_executable_not_found` detail. This establishes
  a launch-verification/reporting inconsistency, not a proven general Sessiond
  cleanup defect. Present live state is back in the ready shell, with no active
  token; no stale Aurelia running record for this AppID was present.
- No available update is reported; a missing update is not supported as the
  explanation. No evidence so far supports deleting/reinstalling game content.
  The narrow next step is diagnostic comparison of the Proton/runtime and
  prefix arrangement with Silent Hill 2 and another accepted Proton title,
  followed by a controlled launch only when the operator confirms it will not
  interrupt play. Avoid blind retries.
- The CLI `play` path in Mudos passes `--steam --no-update --script
  <aurelia-graphical-launch.py>`. The wrapper adds the live Mudos graphical
  environment and execs Aurelia's resolved command. The recorded command is
  consistent with this design; whether `--steam` yields the required DRM
  behavior for this account/game remains to be verified against Aurelia's
  session evidence. Do not change flags based only on the generic Mudos error.

## Read-only installed Steam inventory

Aurelia reports 23 installed game rows. Every one has a corresponding manifest
and an existing install directory on the canonical library. Provenance is
unknown for all; there is no trustworthy per-title marker showing whether
SteamCMD, Steam proper, or Aurelia originally installed it. Manifest presence
and files prove current consistency only at a coarse level, not full depot
integrity. A recursive `.exe` probe is not a launchability test (native games
and unusual layouts can legitimately have none).

| AppID | Title | Aurelia state / update | Initial read-only assessment |
| --- | --- | --- | --- |
| 2497920 | A Difficult Game About Climbing | Installed / none | Manifest and directory present; provenance unknown |
| 2835570 | Buckshot Roulette | Installed / none | Manifest and directory present; no `.exe` at shallow probe; needs launch-resolution check |
| 731490 | Crash Bandicoot N. Sane Trilogy | Installed / none | Manifest and directory present; provenance unknown |
| 17300 | Crysis | Installed / none | Manifest and directory present; provenance unknown |
| 268910 | Cuphead | Installed / none | Manifest and directory present; provenance unknown |
| 381210 | Dead by Daylight | Installed / none | Manifest and directory present; provenance unknown |
| 1537830 | Disney Speedstorm | Installed / none | Manifest and directory present; provenance unknown |
| 1097150 | Fall Guys | Installed / none | Manifest and directory present; provenance unknown |
| 2706170 | Get To Work | Installed / none | Early Proton exit; see diagnosis above |
| 3240220 | Grand Theft Auto V Enhanced | Installed / none | Manifest and directory present; provenance unknown |
| 366040 | Iggy's Egg Adventure | Installed / none | Manifest and directory present; provenance unknown |
| 48000 | LIMBO | Installed / none | Manifest and directory present; provenance unknown |
| 307780 | Mortal Kombat X | Installed / none | Manifest and directory present; provenance unknown |
| 1290000 | PowerWash Simulator | Installed / none | Manifest and directory present; provenance unknown |
| 252950 | Rocket League | Installed / none | Manifest and directory present; provenance unknown |
| 2124490 | SILENT HILL 2 | Installed / none | Manifest and directory present; comparison title; do not launch during this investigation |
| 40800 | Super Meat Boy | Installed / none | Manifest and directory present; no `.exe` at shallow probe; needs launch-resolution check |
| 1755580 | The Jackbox Party Starter | Installed / none | Manifest and directory present; no `.exe` at shallow probe; needs launch-resolution check |
| 220780 | Thomas Was Alone | Installed / none | Manifest and directory present; no `.exe` at shallow probe; needs launch-resolution check |
| 2225070 | Trackmania | Installed / none | Manifest and directory present; provenance unknown |
| 11020 | TrackMania Nations Forever | Installed / none | Manifest and directory present; provenance unknown |
| 837470 | Untitled Goose Game | Installed / none | Manifest and directory present; provenance unknown |
| 1356240 | Who Wants To Be A Millionaire? | Installed / none | Manifest and directory present; provenance unknown |

The heuristic flagged four directories without a shallow `.exe`; treat this as
**inconclusive**, not evidence of missing content. No title should be repaired,
removed, or migrated based on this inventory alone. Runtime/DLC/tool manifests
also exist in the library but are not among Aurelia's 23 installed game rows.

## Steam/Aurelia update lifecycle — requirements before implementation

This is generic Steam/Aurelia capability work, distinct from the deferred
**Pause Downloads During Gameplay** policy. Acquisitiond persisted jobs remain
the source of truth; do not add a second UI-owned progress state.

### Launch-time choices

When an update is available, offer **Update & Launch**, **Update in Background**,
and **Cancel**. Expose **Play Without Updating** only when Aurelia/provider
semantics affirm it is safe. Prevent duplicate submissions for a title with an
active update.

- **Update & Launch:** enqueue an Acquisitiond update and launch through the
  ordinary Sessiond/Aurelia route only after successful completion and only
  while the original launch intent remains valid.
- **Update in Background:** enqueue and immediately return to Mudos. Record this
  origin on the persisted job; it must never launch on completion, including
  after Mudos or Acquisitiond restart.
- **Cancel:** return without queueing an update or launching.
- Cancellation/failure, session replacement, or loss of launch intent must
  invalidate Update & Launch's continuation. Respect provider pause/cancel
  capability; do not imply unsupported controls.

### Progress projection and completion

- Project the persisted Acquisitiond job on artwork in both Recents and Library.
  Show percentage only for genuine measurable progress; otherwise show an
  indeterminate radial state. Map downloading, verifying, applying, and
  completion when Aurelia reports those stages.
- Resolve `steam:` / `steam-aurelia:` identities to one update job and one visual
  indicator, without changing normal art, focus, selection, or controller
  navigation.
- Rehydrate overlay state after shell restart from persisted jobs. Clear it at
  terminal completion, issue a normal **Update Complete** notification, and
  reconcile catalogue installed/launchable state.
- Background-origin jobs never auto-launch. Update & Launch starts only after
  successful completion and a still-valid original intent. Persist enough
  origin/intent identity to make restart behavior deterministic and testable.

## Remaining validation

No physical launch acceptance, controller check, Gamescope presentation check,
or second-attempt consistency check was performed. Before any launch trial,
confirm the appliance is idle and collect matching details for Get To Work,
Silent Hill 2, and a previously accepted Aurelia Proton game. Prioritize the
false-success/early-exit reporting mismatch and identify the fatal module before
changing game files, prefixes, runner configuration, or Aurelia flags.
