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
- A controlled single launch through Mudos after deploying the reporting fix
  returned to the ready shell with no active token. Aurelia's newest summary
  again says `Failure` / `failed_after_spawn`, exit code 1, lifetime about
  2000 ms, and misleading detail `missing_required_module`. The decisive
  `wine_2706170.log` line is `steam:run_process Failed to create process ...
  Get To Work.exe: 2` (ENOENT). Aurelia attempted
  `/home/lulu/.local/share/Steam/steamapps/common/Get To Work/Get To Work.exe`,
  but the actual file is nested one directory deeper at
  `.../common/Get To Work/Get To Work/Get To Work.exe`. Thus the immediate
  failure is an **installation-layout/launch-resolution mismatch**, not a
  missing update and not evidence of a fatal Mono/Xalia module. The Proton log's
  module warnings were incidental; the final process-create error identifies
  the absent target path.
- The preceding Aurelia session falsely reported `Success`/`verified` with the
  same short lifetime and `game_executable_not_found`. This is also an Aurelia
  verification/reporting inconsistency. Mudos now extracts the structured
  verification detail even when the summary result conflicts or lacks a
  `stage_failure` event. On the controlled retry, Sessiond reported
  `Aurelia CLI exited before a verified game appeared ... Launch verification
  missing required module (exit code 1)`, retired the token and returned to
  shell. The detail is structured but still misleading because Aurelia's
  classifier labels the ENOENT as `missing_required_module`; the raw log gives
  the accurate reason. No stale Aurelia running record was present.
- No available update is reported; missing updates do not explain the failure.
  Installation provenance is unknown, but its nested directory layout is
  inconsistent with Aurelia's resolved executable location. Do not delete or
  move content. The smallest safe next step is to determine whether Aurelia's
  supported `verify`/update operation will reconcile this layout without
  damaging user data, or whether a targeted recoverable migration is needed.
  Obtain operator approval before any write, overwrite, or removal. Compare
  Silent Hill 2 and another accepted Aurelia title for the generic layout and
  path-resolution contract; do not blindly retry.
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

## Acceptance status

The operator has accepted the filesystem repair after two successful physical
Mudos/Aurelia launches, normal gameplay and rendering, controller use, Mudos
Guide open/dismiss, normal exits, and return to Home with controller navigation.
The original Get To Work layout defect is resolved. Do not reinstall, relocate,
roll back, or otherwise modify these game files. The separate Aurelia
verification discrepancy is tracked as `AURELIA-VERIFY-001` below.

## Get To Work layout repair and installed-title launch-target audit — 2026-10-10

### Authority and cause assessment

- Steam AppInfo (local cache and SteamRaw's published raw AppInfo) declares
  `Get To Work.exe` as the Windows launch executable, with `installdir=Get To
  Work`. Aurelia's effective launch used that declared executable at the
  manifest install root. This was not an Aurelia path-resolution defect.
- The actual Unity executable, `Get To Work_Data`, `D3D12`,
  `MonoBleedingEdge`, `UnityCrashHandler64.exe`, and `UnityPlayer.dll` had all
  been placed together under an additional `Get To Work/` directory. The
  Unity executable/data pairing and declared launch target establish that this
  extra level was misplaced payload, not a legitimate application subfolder.
- Appmanifest build `21610838` names depot `2706171`, manifest
  `3244103568643260567`; the SteamCMD force-install placement correction
  (`60b6523`) predates this manifest's `LastUpdated` time by roughly 16 minutes.
  That timing does not prove which installer created these files. The old
  SteamCMD behavior passed the library root as `+force_install_dir`, a known
  placement defect that could leave payload at the library root; it does not
  explain this exact extra `Get To Work/` directory. SteamCMD attribution is
  therefore **plausible but unconfirmed at the broad historical level, not
  demonstrated for this nested layout**. No install job or provider provenance
  record for AppID 2706170 was found.

### Applied correction and recovery

- Preconditions passed: Sessiond was idle, no matching game/Proton process or
  active Acquisitiond job existed, the tree had no symlinks or mount points,
  every affected entry was owned by `lulu`, the same Btrfs filesystem was used,
  and all six destination names were absent. Appmanifest hash before/after:
  `b3bd39bca0fb9583fb064075315fdb663c9e47648b193220bdc88b51d4cc553e`.
- Used same-filesystem `rename` operations (not copy/overwrite) to move only
  `D3D12`, `Get To Work.exe`, `Get To Work_Data`, `MonoBleedingEdge`,
  `UnityCrashHandler64.exe`, and `UnityPlayer.dll` from
  `common/Get To Work/Get To Work/` to `common/Get To Work/`. Inodes, owners,
  groups, modes and file contents were retained. Executable SHA-256 remained
  `43487711666796d2550a9d2a4249042333d82b59436217fcf29d4c773874af39`.
- Left both `cover.jpg` files, root `steam_appid.txt`, manifest, compatibility
  data/prefix and all saves untouched. Existing saves were found in the
  AppID Proton prefix; no prefix files were modified.
- A private rollback record is at
  `/home/lulu/.local/share/lulu/steam-layout-repairs/2706170-20261010.json`.
  To reverse, ensure the game is not running and each destination is absent,
  then rename each of the six named entries from the install root back into its
  recorded `nested_source`; do not move either cover or `steam_appid.txt`.
  The record includes pre-move inodes, metadata and checksums. No release or
  Mudos source change was needed.
- After the move, Aurelia still listed all 23 games and reported Get To Work
  installed, owned and up to date. The expected executable/data now exist at
  the root. The initial unprivileged probe could not traverse `/home/lulu`;
  this was corrected by checking as the appliance user.

### Controlled Mudos launch outcome

- The initial post-repair Sessiond dispatch selected the corrected absolute
  executable; Aurelia's matching summary recorded `result=Success` and
  `game_executable_not_found`, while Sessiond showed an active Wine process and
  token with presentation readiness not yet established. At that point this was
  correctly treated as pending observation, not as proof of success or failure.
- Subsequent operator-owned physical acceptance supersedes that preliminary
  snapshot: two launches reached normal gameplay and correct rendering, the
  controller and Guide worked, and both sessions exited normally to Home. The
  earlier `game_executable_not_found` is now understood as a contradictory
  Aurelia verification detail; see the later verification-report investigation.

### Read-only audit of all 23 Aurelia-installed titles

Declared launch paths were compared with local paths, accounting for
case-insensitive Windows paths and Linux entry points. This is a path audit,
not a gameplay test. “Present” means at least one declared launch candidate
exists; it does not guarantee runtime success.

| AppID | Title | Declared target (representative) | Local result | Assessment / action |
|---:|---|---|---|---|
| 2497920 | A Difficult Game About Climbing | `A Difficult Game About Climbing.exe` | Present | No equivalent mismatch observed |
| 2835570 | Buckshot Roulette | `Buckshot Roulette_linux/Buckshot Roulette.x86_64` | Not at declared relative path; Linux executable is nested under `Buckshot Roulette/` | Possible layout mismatch; inspect provider's resolved path before any repair |
| 731490 | Crash Bandicoot N. Sane Trilogy | `CrashBandicootNSaneTrilogy.exe` | Present | No equivalent mismatch observed |
| 17300 | Crysis | `bin32/crysis.exe` or `bin64/crysis.exe` | Present (case-insensitive) | No equivalent mismatch observed |
| 268910 | Cuphead | `Cuphead.exe` | Present | No equivalent mismatch observed |
| 381210 | Dead by Daylight | `DeadByDaylight.exe` | Present | No equivalent mismatch observed |
| 1537830 | Disney Speedstorm | `Disney_Speedstorm_x64_rtl.exe` (or alternate) | Present | No equivalent mismatch observed |
| 1097150 | Fall Guys | `FallGuys_client.exe` | Present | No equivalent mismatch observed |
| 2706170 | Get To Work | `Get To Work.exe` | Present after correction | **Accepted:** two physical Mudos launches and normal return; no further file changes |
| 3240220 | Grand Theft Auto V Enhanced | `PlayGTAV.exe` | Present | No equivalent mismatch observed |
| 366040 | Iggy's Egg Adventure | `Binaries/Win32/IEA.exe` | Not found at declared path; saved data is also present in install tree | Possible layout/metadata mismatch; do not move or remove; investigate provider resolution and protect saves |
| 48000 | LIMBO | `Limbo.exe` | Present (case-insensitive) | No equivalent mismatch observed |
| 307780 | Mortal Kombat X | `Binaries/retail/MK10.exe` (or launcher) | Present | No equivalent mismatch observed |
| 1290000 | PowerWash Simulator | `PowerWashSimulator.exe` | Present | No equivalent mismatch observed |
| 252950 | Rocket League | `Binaries/Win64/RocketLeague_EAC.exe` (or alternate) | Not found at declared path; manifest tree contains nested `rocketleague/` payload and its own `steamapps` | Possible nested/legacy layout; provider's exact target is already reported missing in launch logs; investigate separately, no repair |
| 2124490 | SILENT HILL 2 | `SHProto.exe` (or packaged alternate) | Present | Comparison title only; not launched |
| 40800 | Super Meat Boy | `SuperMeatBoy` | Present | No equivalent mismatch observed |
| 1755580 | The Jackbox Party Starter | `Launcher.sh` | Present | No equivalent mismatch observed |
| 220780 | Thomas Was Alone | `thomasWasAlone` | Present (case-insensitive) | No equivalent mismatch observed |
| 2225070 | Trackmania | `Trackmania.exe` | Present | No equivalent mismatch observed |
| 11020 | TrackMania Nations Forever | `TmForever.exe` or `TmForeverLauncher.exe` | Not found at declared root paths | Possible legacy/nested layout; inspect full target resolution before classifying; no repair |
| 837470 | Untitled Goose Game | `Untitled.exe` | Not found at declared root path | Possible mismatch; inspect full target resolution before classifying; no repair |
| 1356240 | Who Wants To Be A Millionaire? | `WWTBAM.exe` | Present | No equivalent mismatch observed |

Four additional launch candidates need focused resolution (Buckshot Roulette,
Iggy's Egg Adventure, TrackMania Nations Forever, Untitled Goose Game); Rocket
League is a fifth known target-path concern with a prior Aurelia failure log.
These are **not** declared corrupt and none was modified. Native Linux targets
were checked as Linux binaries rather than treated as missing `.exe` files.
No evidence supports mass migration or a global repair at this time.

### Physical acceptance and verification-report investigation

The operator reports full physical acceptance after the layout correction:
two Mudos/Aurelia launches; normal gameplay and correct rendering; controller
use; Mudos Guide opened/dismissed; normal exit each time; return to Home with
controller navigation. This closes `AURELIA-LAUNCH-001`. The operator explicitly
directed that the game files must not be reinstalled, relocated, or otherwise
modified again. Retain the rollback record and do not use it absent a new
operator request.

The earlier apparent post-repair failure was a **verification/reporting
mismatch**, not stale Sessiond state and not a confirmed launch failure. The
matching Aurelia session `1791629428124-e8076d4a` has `result=Success`,
`verification.status=verified`, and `launch_final_status: Launch successful`,
but also contradictory `verification.detailed_status=game_executable_not_found`.
Its `effective_launch_config.json` records `game.executable_path=run` and
`executable_exists=false`; that is Proton's subcommand as exposed by the
graphical-launch wrapper. In the same session the `SpawnProcess` event contains
the correct `AURELIA_LAUNCH_ARGS` value:
`run /home/lulu/.local/share/Steam/steamapps/common/Get To Work/Get To Work.exe`.
Steam AppInfo and the actual payload both confirm that target exists. The
operator's two successful visible launches provide physical confirmation that
the wrapper ultimately executes the game successfully. The likely cause is
Aurelia's health check evaluating the wrapper-resolved command (`run`) as if it
were the game executable, rather than the target carried in its launch
arguments; this is strongly evidenced but the health-check implementation is
not owned by Mudos, so exact upstream code attribution remains unconfirmed.

Sessiond's active launch token while gameplay is in progress is expected and
does not indicate failure. Its `last_result` shown in the earlier state was
from the preceding launch, while the current `active_identity` represented the
live Wine preloader/game session. Do not infer failure from that combination.
Mudos's `launch_failure_detail()` already ignores
`game_executable_not_found` in a nominal-success summary; a focused regression
was added to ensure this contradictory summary is not surfaced as a failure.
Track investigation of the Aurelia-side detail under `AURELIA-VERIFY-001`,
without reopening the accepted layout repair.

The five other audit candidates (Buckshot Roulette, Iggy's Egg Adventure,
Rocket League, TrackMania Nations Forever, Untitled Goose Game) remain
read-only findings requiring focused launch-path resolution. Do not modify them
without approval. `STEAM-UPDATES-001` remains a separate implementation effort;
no implementation was started. No runtime change, game launch, release build,
or service restart was performed to record operator acceptance.
