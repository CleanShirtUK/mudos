# Active Backlog

Current engineering work is tracked here. Historical reconciliation notes are
retained in `docs/reconciliation-backlog.md` and are not the status authority.

## ACTIVE

### UNINSTALL-001 — Complete provider-owned uninstall coverage

**Status:** ACTIVE — generic lifecycle and provider cleanup are implemented in
source; development deployment is deferred while the existing Sonic 3 A.I.R.
test session remains live. Complete dev-current deployment and the finite
physical acceptance checklist below before moving this item to VALIDATION.

- Current game-producing provider matrix:
  - **Steam / Aurelia:** installed Steam catalogue rows currently have no safe
    per-title uninstall through the supported Aurelia API. Report uninstall as
    unsupported; do not fall back to SteamCMD, account sign-out, library
    deletion, or shared-runtime cleanup. Operator removal through Steam must be
    followed by catalogue reconciliation.
  - **Epic / Legendary:** use Legendary's per-app uninstall command only for a
    valid app identity in Mudos' canonical Epic library; reject third-party
    managed titles and paths outside that library. Service-restart replay
    checks Legendary's authoritative installed list and is idempotent when the
    title is already gone.
  - **GOG / gogdl:** gogdl has no uninstall command. Remove only a direct-child
    per-title directory with a matching Mudos ownership marker under the
    canonical GOG library. Never delete a shared prefix or unmarked install.
  - **Flatpak:** use Flatpak/libflatpak's application uninstall operation for
    the user installation; retain Flatpak's app-data policy (no
    `--delete-data`) and reconcile the user-installed app snapshot.
  - **Lutris:** for Mudos recipe installs, remove the Lutris registration and
    then remove only the exact canonical per-game directory with a matching
    recipe ownership marker. For Mudos-registered local/manual games, remove
    the Lutris registration only and preserve all user files. Provider-discovered
    Lutris entries are not uninstallable through Mudos.
  - **Local ROM/emulation content:** use the bounded local-content executor for
    Mudos-catalogued content under its canonical platform root. ROMM is a
    remote library source; when a ROMM title is linked to a local copy, removal
    targets that local copy. ROMM itself has no local uninstall operation.
  - Torrent/Usenet acquisition, launch-only runtimes, shared services, and
    library-only entries do not create provider-owned installed-game payloads
    and are not offered as game uninstall targets.
- Acquisitiond returns a generic provider capability including support,
  reason, explicit-confirmation requirement, measurable-progress state, and
  active-operation state. The game action is backend-gated, confirms before
  submission, and suppresses a duplicate action while a removal is active.
  Removal remains a persisted Acquisitiond job; failed jobs preserve the
  catalogue state and provider reconciliation runs after every terminal result.
- Automated fixture coverage exercises successful and failed removal,
  idempotent retries, active-request deduplication, provider identity,
  reconciliation and path/ownership refusal. No real appliance games were
  uninstalled for this work.
- **Physical acceptance after dev-current deployment:** with a controller,
  open game options for one disposable title in each currently available
  provider; verify unsupported Steam/Aurelia and provider-discovered Lutris
  entries have no enabled Uninstall action; verify supported actions require
  explicit confirmation; verify Back cancels confirmation; verify an active
  removal cannot be resubmitted; verify successful removal updates Library and
  Recents after provider reconciliation; verify a failed provider removal
  reports failure and leaves the installed title represented. Use only
  disposable installs or explicitly approved test titles—never operator game
  data as an unattended fixture. Also physically test a Lutris manual
  registration and confirm its files remain after unregistering.
- Do not deploy while the preserved Sonic 3 A.I.R. game/Zenity session is still
  active: `scripts/dev-runtime.sh refresh` replaces dev-current and restarts the
  session. Resume that development deployment only after the operator has
  explicitly cleared the prior session or it has ended naturally. Production
  `/opt/lulu/current` remains untouched.

### RECENTS-001 — Steam Recents and legacy launch behavior after Aurelia migration

**Status:** OPEN — operator findings recorded; investigation and fixes deferred.

- Steam games launched since the Aurelia implementation are not appearing in
  Recents.
- Some Steam games from before the Aurelia migration still appear in Recents,
  including Super Meat Boy, but launching those entries does not work.
- These are two observed symptoms; their relationship and root cause have not
  been established. Investigate Recents population and launch routing across
  pre-migration and Aurelia-backed Steam entries without assuming they share a
  cause.

### LUTRIS-002 — Sonic 3 A.I.R. launch leaves Mudos unresponsive

**Status:** INVESTIGATING — evidence collected; preserve the current session.

- After the Sonic 3 A.I.R. installation completed, launching it left Mudos
  apparently unresponsive. The game process is still alive behind a modal
  `zenity` error dialog; Sessiond remains in `game` lifecycle and has not
  recorded a launch result.
- Game logs show engine startup succeeded, then ROM discovery failed. It searched
  Steam's Sega Classics paths for `Sonic_Knuckles_wSonic3.bin`. The selected
  user-provided file is present in the install tree as
  `Sonic and Knuckles & Sonic 3.bin`, so the recipe's copy location/name and the
  game's lookup behavior need investigation.
- Lutris's recipe metadata does not state that target filename: it declares
  `bin: "N/A:Please select the .bin file from Steam"`. Its installer then copies
  `bin` into the app directory without a destination filename. Lutris therefore
  supplied no expected-name hint for Mudos to use; verify a supported target
  location/name before adding any recipe-specific copy/rename behavior.
- Launch diagnostics show Gamescope selected the game's X11 window and unmapped
  the shell. The waiting Zenity process inherited the Gamescope Wayland display,
  but has no visible X11 window. This is consistent with its error dialog being
  outside the selected game surface; confirm the Wayland/Gamescope surface
  behavior before treating that as proven.
- Do not infer that the game binary itself crashed. Preserve the current state
  and logs while tracing launch supervision, dialog visibility/input routing,
  and how the recipe-provided ROM is expected to be located. Do not restart or
  terminate the current game/session without operator authorization.

### DOWNLOADS-001 — Downloads list rendering and clear-action stability

**Status:** OPEN — operator findings recorded; investigation and fixes deferred.

- In the Downloads list, a row's bottom edge can be clipped when its error text
  wraps across too many lines.
- Clearing a download often leads to a crash. The crash trigger and affected
  component have not yet been established.
- These are observations from ongoing physical testing, not confirmed root
  causes. Do not change behavior as part of this finding until it is separately
  taken up for investigation.

### DOWNLOADS-002 — Show useful installation progress in Downloads

**Status:** OPEN — operator finding recorded; implementation deferred.

- During a Lutris installation, the Downloads view displays only “Downloading,”
  including while Lutris is extracting and compiling the recipe payload. Show a
  useful current stage and progress there so the operator can tell what the job
  is doing and whether it is advancing.
- Recorded during physical testing; no UI or progress-reporting changes are
  included in this finding.

### DOWNLOADS-003 — Mudos crash after Lutris install completion

**Status:** OPEN — operator observation recorded; no investigation requested.

- The operator reports that Mudos appeared to crash when the Sonic 3 A.I.R.
  Lutris installation finished downloading. This is recorded as an observation
  only; do not investigate it as part of the current launch-hang diagnosis.

### QUIVER-001 — Quiver acquisition and library provider

**Status:** ABANDONED — Lutris is the selected PC installation foundation.

- Repository and upstream investigation is recorded in
  `docs/quiver-provider-contract.md`. This checkout has no Quiver integration.
- The public project matching the name, Quiver Launcher, has a name-based CLI
  (`--list`, `--download`, `--update`, `--run`, `--uninstall`) and its own
  library/app folders, but no structured acquisition-job API. Questarr is a
  separate, retired integration and must not be restored.
- Before implementation, confirm whether this is the intended Quiver and
  whether Mudos should consume a future/other Quiver API or own a separate
  GitHub/GitLab release acquisition backend. These choices change acquisition,
  catalogue, installation, and launch authority; do not guess or treat the
  upstream GUI's local files as an API.

### CTRL-001 — Prevent controller navigation loss after runtime target churn

**Status:** ACTIVE — physical navigation recovered; startup/runtime cause still
needs a durable fix and regression coverage.

- After the dev-current boot, the Xbox 360 receiver and physical event node were
  present, InputPlumber had one composite, and Sessiond registered one standard
  gamepad. However, SDL enumerated two InputPlumber virtual gamepads for the
  single composite. Sessiond's identity-agnostic target association correctly
  refused to guess, leaving the controller's SDL index unset. The independent
  InputPlumber D-Bus Guide relay could still open Guide, while normal SDL-backed
  navigation stopped responding.
- Restarting InputPlumber (and its dependent Mudos session) cleared the extra
  virtual target. The live state then converged to one physical source, one
  composite, one SDL gamepad, and a valid Sessiond SDL mapping. The operator
  confirmed controller navigation was back. Treat this as runtime recovery,
  not proof that the triggering race is fixed.
- Startup logs showed hotplug reconciliation attempting to consume transient
  stale event nodes, including a short-lived Sunshine virtual-pad node, and
  InputPlumber tearing down/recreating composites. Sunshine's
  `controller = disabled` setting is intentional and must remain unchanged.
  The exact causal sequence is not yet proven; no Lutris implementation change
  has been identified as the cause.
- Diagnose and fix the smallest lifecycle/reconciliation issue that permits
  stale/duplicate InputPlumber targets to outlive their composite. Keep the
  physical Xbox/InputPlumber/composite/Sessiond/native-SDL architecture,
  identity-agnostic standard gamepad support, and single controller path.
  Do not add a controller allowlist, virtual path, or Sunshine input.
- Validate after a cold boot and shell startup: one normalized controller,
  non-null Sessiond SDL association, Guide plus continued D-pad/A/B/Start
  navigation, no duplicate/phantom controller, and Sunshine still disabled.
  Add automated coverage for the discovered runtime mismatch/recovery. Do not
  resume LUTRIS-001 physical acceptance until controller navigation remains
  reliable through the required Home → Installable → Lutris flow.

### LUTRIS-001 — Mudos-native PC game install and add-game flows

**Status:** PASS WITH FOLLOW-UP — operator confirmed the Lutris discovery,
required-file selection, installation, and launch-attempt flow end to end. The
flow mostly works; listed follow-ups remain open, so this item is not closed and
successful gameplay is not claimed.

- Lutris 0.5.22's installer interpreter, game model/config save, database
  inventory, launch-script exporter, and uninstall model are integrated behind
  the existing Acquisitiond/catalogue/Sessiond boundaries. An isolated real
  Lutris test covers native local registration, discovery, launch export, and
  unregistering. The suite also covers recipe requirement parsing, catalogue
  identity, and the shared acquisition lifecycle.
- Installable's controller-X/BTN_WEST action launches controller text entry for
  Lutris search through Mudos' shared contextual options action. The flow
  discovers upstream games/recipes, shows required user-file steps, uses the
  generic Mudos file picker, then calls CreateLutrisInstallSource,
  RegisterPcSource, and SubmitPcInstall. The existing Acquisitiond job and
  LutrisInstallExecutor remain the only installation path.
- Confirmed upstream recipe `sonic-3-air-stable`: Linux runner, download
  `sonic3air_game.tar.gz`, and required user file
  `Sonic_Knuckles_wSonic3.bin`. The real live API search/recipe routes and
  requirement-source validation were exercised; no ROM/game data was copied
  or installed.
- Refreshed non-promotable `/opt/lulu/dev-current`; session, Consoled,
  Acquisitiond, and admin services were active for physical acceptance. The
  operator later supplied a file and explicitly approved its use for the test.
- Physical acceptance exposed that BTN_WEST dispatched to the generic
  `openSelectedGameOptions()` handler while Lutris search was reachable only
  from the Qt `Key_X` path. The shared action now dispatches Installable's
  search flow. The operator confirmed the search window opens and the OSK is
  controllable; the later install attempt confirms the results/recipe flow is
  receiving the controller action.
  Do not install copyrighted game files as part of this action-path check.
- Follow-up OSK testing found Sessiond's profile-drift reconciler overwrote the
  OSK bridge's temporary exclusive InputPlumber profile/intercept mode while
  the keyboard was visible. Sessiond now yields reconciliation only while the
  managed OSK reports visible, allowing its bridge to restore shell input on
  hide. The operator confirmed physical OSK control now works.
- The first physical game search remained on its loading message because the
  new Lutris QML components sent relative XHR paths, which Qt interpreted as
  local-file URLs rather than requests to the shell API. Route search, recipe,
  file-picker, and local-registration XHRs through the configured `apiUrl`, and
  show a useful error if a request fails. Lutris also returns no exact match
  for the dotted `A.I.R.` spelling, so retry dotted abbreviations compacted.
  Regression coverage passes and the fix is refreshed to dev-current; physically
  verify search results and recipe selection.
- Physical retest found native controller actions bypass the Qt key handler's
  Lutris-modal checks: A invoked the root Installable activation and started
  `A Difficult Game About Climbing`. That acquisition completed before it was
  observed. Root controller handlers now delegate A/B to the visible Lutris
  modal and suppress other actions that could affect the covered surface;
  regression coverage passes and the fix is deployed to dev-current. Physically
  retest confirmed A selected the Lutris item rather than the covered Installable
  game.
- The next Lutris install failed because `/home/lulu/Games/Executables/lutris`
  was owned by root, preventing Acquisitiond (user `lulu`) from creating the
  game directory. Corrected ownership on that parent directory only; preserved
  its mode and all existing game files. The failed Sonic job created no partial
  destination. The operator later explicitly authorized use of their provided
  Sonic file and requested another test.
- The retry exposed Lutris's scalar file declaration format (`{"bin":
  "N/A:Please select the .bin file from Steam"}`), which the requirement parser
  had skipped. It is now surfaced as a required local-file selection and mapped
  under the recipe's `bin` ID; focused regression tests pass and the correction
  is refreshed to dev-current. The operator selected their file in the UI.
- Physical testing found the install action was not visible beneath the required
  file row. It is now a dedicated visible row immediately after the file list,
  with controller navigation and activation coverage. The operator confirmed
  the row is now visible and requested another install test. The first retried
  job was cancelled during compilation; its logged missing-source error
  coincided with transaction cleanup removing the build directory, so it is
  inconclusive. The operator reports the current test was started from the UI;
  the install completed and the operator attempted launch. The build succeeded,
  but ROM discovery failed and the game left a Zenity error dialog waiting while
  the shell appeared unresponsive; see LUTRIS-002. This confirms the install and
  launch-attempt path, not successful gameplay.
- Full Python suite and QML checks pass. The checkout still has unrelated
  pre-existing modifications; dev runtime records `dirty=true` and must never
  be promoted.

### EDEN-001 — Eden AppImage migration acceptance

**Status:** ACTIVE. Do not close or promote until both regressions are fixed and
the operator completes physical acceptance.

- **EDEN-001A — MK8 update/DLC discovery:** The v0.8.1 runtime loads its config
  below `XDG_CONFIG_HOME/eden`, which for Mudos is
  `~/.config/lulu/providers/eden/config/eden/qt-config.ini`. The prior adapter
  edited `~/.config/eden/qt-config.ini`; the runtime config had
  `Paths\\external_content_dirs\\size=0`. v0.8.1 scans configured NSP/XCI
  directories into an in-memory `ExternalContentProvider`; there is no
  persistent external-content database/index. Point the adapter at the active
  provider config and ensure the ROM directory is registered there. Do not
  move, reinstall, register, or delete update/DLC NSP files during diagnosis.
- **EDEN-001B — controller input:** Use the generic live SDL/InputPlumber
  identity and Eden's native serialization contract; do not add controller
  allowlists or pin event device numbers. The original Mudos face-button map
  (A/B/X/Y = SDL buttons 0/1/2/3) is the correct baseline and must be retained.
  Eden's v0.8.1-authored `gp1` donor was preserved at
  `/home/lulu/.config/lulu/providers/eden/config/eden/input/gp1.ini.eden-v0.8.1-donor`;
  the updated `gp1.ini` now contains the original Mudos-generated mapping.
  Donor profile checksum: `6d9a889c66df2ac7561dbb9681e6e73ca9110dab2ed75d5ced3e91db274b4537`.
  Updated profile checksum: `8447a50eade12c04794a930cdb9364d312ff8eda77caaef2d53f46e9cdbc551b`.
  Physical ABXY correctness remains an operator-confirmed fact, not something
  inferred from Eden's saved mapping.
- Keep the existing pinned AppImage, coherent NAND/profile state, keys and
  firmware, Gamescope ownership, Mudos controller assignment policy, and
  prompt Eden-to-Mudos lifecycle return.
- Preserve the old Flatpak tree as read-only donor evidence. Leave
  `/opt/lulu/current` untouched; development deployment is restricted to
  `/opt/lulu/dev-current` and remains separate from promotion.
- Required operator acceptance: MK8 v4.0.0 with existing DLC active, controller
  input, clean lifecycle return, rendering, and remaining requested checks.

**Implementation status:** The adapter now targets the provider XDG config Eden
actually reads, registers the Switch ROM directory there, and retains the
original Mudos button map. Runtime-path regression coverage is implemented; the
full test suite passes (1,169 tests and 85 subtests). Commit `fe840db` was
deployed to `/opt/lulu/dev-current` on 2026-10-04. The dev tree is explicitly
`promotable=false` and records `dirty=true` because pre-existing, uncommitted
session/lifecycle work was included in the dev refresh. `/opt/lulu/current`
still points to the immutable candidate release. Physical acceptance has not
occurred.

**Next:** Obtain operator acceptance on dev-current for MK8 v4.0.0 plus DLC,
controller input, clean lifecycle return, rendering, and remaining requested
checks. Keep EDEN-001 ACTIVE until those checks pass. Do not promote this dirty
dev runtime.
