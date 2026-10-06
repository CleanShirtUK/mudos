# Active Backlog

Current engineering work is tracked here. Historical reconciliation notes are
retained in `docs/reconciliation-backlog.md` and are not the status authority.

## VALIDATION

### UI-001 — Lock the default visual baseline before theming

**Status:** INITIAL VISUAL PASS — the accepted baseline and final controller-glyph
micro-fix are deployed to `/opt/lulu/dev-current`. A post-deploy Gamescope
physical capture confirms the leftmost status-strip gamepad glyph is fully
visible. `/opt/lulu/current` remains untouched. THEME-001 is implementation-ready;
theme-engine implementation has not begun.

- Stabilize the accepted default UI baseline: neutral charcoal structural
  surfaces, one glass substrate per elevation root, shared expanded framing,
  fixed root-space status chrome, shared row-selection semantics, shell-owned
  controller hints, and reusable empty states. Do not build a theme engine.
- Preserve accepted Home/Recent composition, Settings navigation and panes,
  Library/Store information architecture, system transitions, Guide semantics,
  provider behavior, controller mapping, and lifecycle behavior.
- Corrective pass: status chrome now uses one root-space safe inset
  (`top=expandedShellTop`, `right=expandedShellSideMargin`) without navigation-
  dependent coordinates or a translate. Settings, Utilities, Library, and
  Installable consume shared expanded-surface X/Y/width/bottom roles. Library
  titles sit outside the glass and its substrate starts at the shared surface
  line just above the existing category rail; the list/detail layout and rail
  behavior remain intact. Settings and Utilities rows share selection fill and
  focus-border palette roles. Structural tint/internal pane darkness were
  reduced and glass transmission increased; modal overlay dimming roles remain
  separate and unchanged. Recents capture now unions live delegate bounds with
  settled layout bounds while preserving stable coordinator inputs.
- Expanded-frame convergence follow-up: `ConsoleShell.qml` now owns the common
  title, substrate and hint-band coordinates through `ExpandedSurfaceGeometry`.
  Settings, Utilities, Library and Installable receive the same surface bounds
  and 20-design-pixel inner inset. Library's duplicate 30-pixel `frameMargin`
  has been removed; its category rail remains inside the inset and list/detail
  panes now end at the shared inner bottom boundary. At 1280x720, the common
  title is `(42,28)`, substrate origin/width are `(20,94,1240)`, and the inner
  frame origin/right edge are `(40,114,1240)`; bottom coordinates follow the
  shell's live hint-band top. The full Python suite passes (1,221 tests and 85
  subtests), and the native development build passes with existing compiler
  warnings. Expanded geometry, Settings, Utilities, Library list/spatial QML
  tests pass. Installable projection retains the known provider/platform
  expectation failure (`2` observed, `3` expected). Commit `9332a86` is deployed
  to `/opt/lulu/dev-current`; Sessiond, Consoled, and Acquisitiond are active
  with that runtime configured. `/opt/lulu/current` remains unchanged. Operator
  operator acceptance of the earlier baseline was recorded; the focused final
  glyph correction is covered below.
- Final geometry correction: extend only the common substrate upward by
  `design(8)` while retaining the prior content Y/bottom bounds. The Library and
  Installable category rail now spans its actual symmetric inner frame; the
  status-strip-derived safe-width reserve is removed. Focused geometry, Library,
  Utilities QML tests pass; the focused Console UI Python tests pass. Native
  build and `git diff --check` pass. `qmllint` reports only existing warnings in
  nested delegates and StoreHome. Commit `206b7a7` is deployed to
  `/opt/lulu/dev-current`; Sessiond, Consoled, and Acquisitiond are active from
  that runtime. `/opt/lulu/current` is unchanged.
- Final glyph micro-fix: the clipped icon was the controller/gamepad glyph in
  `SystemStatusStrip.qml` via `StatusGlyph.qml`, not the controller-hint
  `ControllerGlyph.qml`. The leading controller slot clips overflow, and the
  gamepad's measured painted width exceeded its fixed glyph slot at the existing
  target height. `StatusGlyph` now width-fits only when needed and optically
  centers its tight painted bounds inside a 1.5-design-pixel safe inset. The
  focused test exercises the real clipped controller slot, confirms width-fit,
  and checks all four painted edges. Status-strip QML tests pass (9 tests),
  asset-system tests pass (5), focused Console UI Python tests pass (92), native
  build and `git diff --check` pass. The physical capture was inspected after
  deployment; UI-001 is initially passed. Commit `9de4a74` is deployed to
  `/opt/lulu/dev-current`.
- Physical validation must cover Recent end-card clipping, status-strip
  placement, Library/Installable rail clearance, Settings glass/focus,
  Utilities layout/media/hints, centered Downloads glass/empty-state/hints,
  Guide materials, and readability over bright and dark backdrop regions.
- Operator acceptance is the closure gate. Record one sweep covering those
  items and confirm that no content surface obscures the global hint band.
- Validation: Python suite passes (1,221 tests and 85 subtests); focused
  console/download UI checks and native development build pass with existing
  compiler warnings. Recent capture-envelope, SettingsSpace, and Utilities QML
  tests pass. The all-QML run reports 138 passed and 10 failures in the known
  Installable projection, native-mapping fixture, and Recent coordinator/model
  groups; no starting-revision comparison isolates those failures.
- Dev runtime refresh succeeded with DP-1 connected. Sessiond, Consoled, and
  Acquisitiond are active; Gamescope and `lulu-shell` run from
  `/opt/lulu/dev-current`. `NON_PROMOTABLE` marks the runtime non-promotable;
  `/opt/lulu/current` still resolves to
  `/opt/lulu/releases/786aba3-candidate-20261004065549` and was not changed.
- Operator recording/acceptance was recorded for the initial baseline. Sweep the Recent
  rightmost-card transition, fixed status backing, aligned Library/Installable/
  Settings/Utilities framing, wave visibility/readability, Settings focus and
  row selection, Library rail clearance, Utilities media/hints, Downloads and
  Guide overlays, and unobscured global hint band. Guide continues to use its
  separate native helper and does not sample the shell's canonical backdrop.
- Guide retains its existing separate native-helper/window architecture and now
  uses the neutral panel/selection palette. It cannot sample the shell's animated
  canonical texture from that isolated process; true backdrop-refraction there
  remains subject to physical review without changing Guide ownership/routing.

### THEME-001 — Theme engine and external theme configuration

**Status:** READY — UI-001 initial visual PASS is recorded and the default
baseline is frozen. Theme-engine implementation has not begun in this patch.

- Future work: build theme selection/configuration on the accepted semantic
  palette, typography roles, and icon authority. UI-001 must not add external
  theme loading or SVG overrides.

## CLOSED

### UNINSTALL-001 — Complete provider-owned uninstall coverage

**Status:** CLOSED — operator accepted the uninstall implementation and dev
validation on 2026-10-06. The earlier shell crash and Aurelia transition defect
were corrected in the dev runtime; the accepted future hide-title UX is tracked
separately below and is not a blocker for this item's closure. `/opt/lulu/current`
was not changed.

- Deployed implementation commit: `98b4667c5fd26335f0cf1517a94f62acb4b936b0`
  (`Complete provider-owned uninstall lifecycle`). The dev runtime reports this
  exact HEAD, `dirty=false`, and `promotable=false`. `/opt/lulu/current` remains
  on its existing immutable candidate release.
- Safe live checks after refresh: Sessiond, Consoled, Acquisitiond, admin, and
  InputPlumber are active; the shell is running from dev-current; Acquisitiond's
  D-Bus capability method is present. Read-only capability calls reported
  supported local, Flatpak, and Mudos-marked GOG uninstall examples, while an
  installed Steam/Aurelia example incorrectly reported unsupported. No uninstall
  request was submitted during those checks.
- **Operator acceptance report (2026-10-06):** the operator reported that
  Steam and Lutris appeared not to offer uninstall, then reported that attempting
  uninstall for an Epic title and a Wii title had the same apparent Mudos crash.
  Read-only service checks afterwards showed Acquisitiond and Sessiond active;
  `lulu-shell` had two `SIGSEGV` core dumps at 04:39:17 and 04:44:51, each with
  Qt Quick frames through `QQuickFlickable::geometryChange` / `setHeight` and
  QML binding evaluation, reached while `SystemStatusBridge` handled an
  Acquisitiond state-snapshot update. This is strong evidence of a shell UI
  crash associated with acquisition snapshot delivery, not evidence of separate
  Epic and local-ROM executor crashes. The exact QML binding/corrupt state is
  still not identified. Later job records show the Epic and Wii/local removal
  jobs reached `completed`; the operator subsequently confirmed the shell did
  not crash during the Aurelia test.
- Steam's missing action was an implementation defect, not intended policy.
  Aurelia supports per-AppID uninstall; Mudos should invoke that API and then
  reconcile Aurelia's installed list. Use the catalogue provider ID as the AppID
  (for example, `1245620` is illustrative, not a hard-coded target). Never
  substitute SteamCMD or direct Steam-library deletion. Lutris uninstall is
  available only for Mudos recipe installs and Mudos-registered
  local/manual registrations; provider-discovered entries intentionally have
  no Mudos uninstall action. Confirm which kind of Lutris entry the operator
  tested before treating that report as a provider implementation defect.
- Source now enables Aurelia uninstall jobs, validates the decimal AppID, calls
  Aurelia's `uninstall <AppID>` command, and confirms the title is absent from
  Aurelia's installed list before completing the job. Fixture coverage passes;
  this correction was deployed to `/opt/lulu/dev-current` on 2026-10-06 by the
  canonical `scripts/dev-runtime.sh refresh`. The non-promotable marker records
  HEAD `864df05d1f66e59c02e6ad437e76e4fd35dbd586`, `dirty=true`, and
  `promotable=false`. Session, Consoled, Acquisitiond, Admin, and InputPlumber
  are active; the shell is running. A read-only `CanUninstall` check for
  installed game `steam:104200` returned `supported=true` with the Aurelia
  description. No uninstall request was submitted and no real title was
  removed. `/opt/lulu/current` remains
  `/opt/lulu/releases/786aba3-candidate-20261004065549`.
- **Aurelia operator test follow-up:** two removal jobs for `Among Us`
  (`steam-aurelia:945360`) and `Baldi's Basics Classic Remastered`
  (`steam-aurelia:1712830`) ran the Aurelia uninstall command and observed both
  AppIDs absent from Aurelia's installed list, but Acquisitiond marked the jobs
  failed with `invalid job transition: starting -> completed`. This was the
  executor's terminal-state bug, not a failure of the provider command. The
  executor now transitions through `finalizing`; a real-JobManager fixture test
  covers the valid lifecycle. Do not retry these AppIDs: they are already
  absent according to the provider's post-command check.
- Do not use real titles for further physical validation unless explicitly
  approved. `/opt/lulu/current` was not changed.
- Follow-up UI observation: the operator reports Steam entries disappear
  immediately after removal, while some other providers remain visible until
  leaving and reopening the menu. The immediate refresh on job submission or
  job completion can race Acquisitiond's asynchronous provider reconciliation.
  `ConsoleShell.qml` now refreshes its Library and Installable projections when
  `CatalogueModel.generation` advances, after Consoled publishes the reconciled
  catalogue. Structural regression coverage passes. The UI follow-up was
  deployed to `/opt/lulu/dev-current` on 2026-10-06 at 04:05:02Z by
  `scripts/dev-runtime.sh refresh`; the `NON_PROMOTABLE` marker records HEAD
  `864df05d1f66e59c02e6ad437e76e4fd35dbd586`, `dirty=true`,
  `promotable=false`. The operator accepted the dev validation and authorized
  closure on 2026-10-06.

- Current game-producing provider matrix:
  - **Steam / Aurelia:** invoke Aurelia's per-title `uninstall <AppID>` operation
    for the installed catalogue row, then reconcile Aurelia's authoritative
    installed list. Validate a decimal AppID and use only Aurelia's canonical
    Mudos Steam-library configuration. Do not fall back to SteamCMD, account
    sign-out, direct library deletion, or shared-runtime cleanup.
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
  provider; verify Steam/Aurelia and supported Lutris entries offer Uninstall,
  while provider-discovered Lutris entries do not; verify supported actions require
  explicit confirmation; verify Back cancels confirmation; verify an active
  removal cannot be resubmitted; verify successful removal updates Library and
  Recents after provider reconciliation; verify a failed provider removal
  reports failure and leaves the installed title represented. Use only
  disposable installs or explicitly approved test titles—never operator game
  data as an unattended fixture. Also physically test a Lutris manual
  registration and confirm its files remain after unregistering.
- The initial development refresh was explicitly authorized and completed; it
  restarted the development session as expected. Production
  `/opt/lulu/current` remains untouched.

## ACTIVE

### RECOVERY-001 — Recovery UI reports a connected controller as absent

**Status:** OPEN — investigate controller-presence detection and recovery-screen
reporting. Do not treat recovery UI's missing-controller message as authoritative
without comparing it to the controller source.

- Operator report (2026-10-06): Mudos Recovery claimed the controller was not
  present while the controller was connected.
- During recovery triage, `/v1/status` reported the controllers component
  healthy with `connected_count: 1` from `InputPlumber GamepadOrder`, while the
  normal graphical session was stopped. Reconcile the recovery UI's displayed
  controller state with this health snapshot and live input source; add a
  regression test for the mismatch.

### SET-001 — Consolidate System Settings navigation

**Status:** VALIDATION — implementation, automated tests, and dev-current
deployment are complete; physical/presentation acceptance remains.

- **Back-to-Home acceptance: PASS.** Operator confirmed that Back from Settings
  must return directly to normal Home; the standalone two-card System landing
  was removed. The remaining checklist below is still open.

- System exposes only **Settings** and **Utilities**. Settings categories are
  derived from the existing provider-backed pages: Network, Bluetooth, Display,
  Audio, Controllers, Storage, and System.
- Settings uses a two-panel category/content shell without a horizontal category
  rail. Existing category components retain their models, refresh behavior,
  subviews, and mutation/service boundaries.
- Physical/presentation acceptance checklist:
  1. Open System and confirm only **Settings** and **Utilities** are present.
  2. Open Settings; confirm title directly precedes the two panels, with no
     horizontal category rail or reserved gap. Check list density/glyphs,
     panel-level glass, plain setting rows, couch readability, and active border
     contrast while focus moves between panels.
  3. With a controller, move up/down through categories; move right into content;
     navigate controls; use left (or Back where a control consumes left) to
     return to categories. Back from Settings must go straight to normal Home,
     with no intermediate System card landing.
  4. Visit Network, Bluetooth, Display, Audio, Controllers, Storage, and System;
     confirm their live models populate/update and category changes do not reset
     discovered state. Check nested details/subviews and unwind each with Back.
  5. Confirm Utilities still opens and works. Do not apply display modes, eject
     storage, pair/connect devices, or change network settings during this pass.
- `/opt/lulu/current` must remain unchanged.

**Implementation status:** latest commit `9524cc2` removes the standalone
System landing and returns Back directly to Home. Earlier commits implement the
unified Settings shell, category hosts, and corrected dev refresh wiring.
Settings hosts are exclusive by category: System and Bluetooth use SystemSpace,
while Network, Display, Audio, Controllers, and Storage use their existing
dedicated components. Full Python suite: 1,205 passed and 85 subtests; focused
settings QML suite: 5 passed; QML lint and shell syntax checks passed. The final
`/opt/lulu/dev-current` deployment and running ConsoleShell are verified below.
Three failed starts during initial validation entered the existing recovery
latch; after correcting the duplicate QML properties, only that failure history
was cleared and the normal ConsoleShell was restarted. `/opt/lulu/current`
remains on its original immutable release.

### LIBRARY-001 — Open the selected Library dimension

**Status:** OPEN — operator-reported navigation defect; not investigated or
fixed.

- On the Library home, selecting a Provider or Platform card and opening it
  always enters the Provider view, regardless of which card was selected.
- Once the Library view has opened, switching categories within the view works
  normally. Preserve that working behavior while tracing the initial
  card-selection/open transition.
- Acceptance: opening each Provider/Platform card enters its corresponding
  dimension and selected category; in-view category switching continues to
  work in both dimensions.

### UNINSTALL-UX-001 — Hide titles while uninstall runs

**Status:** ACCEPTED — requirements captured; implementation deferred.

- Uninstall must invoke provider removal; catalogue refresh is post-removal
  reconciliation, not the mechanism used to make the title disappear from the
  current Library view.
- Add a **Hide** action under Game Options and a **Show hidden titles in
  library** setting. The setting is deliberately session-only/in-memory, is not
  persisted, and resets to its default after any Mudos session reload. Decide
  the persistence/lifetime policy for individual hidden-title membership
  separately from this setting.
- After the user confirms Uninstall, add that game ID to the same hidden-title
  mechanism before submitting provider removal. It should leave the Library
  view immediately while asynchronous removal runs; do not treat temporary
  hiding as provider success or mutate installed catalogue state early.
- After successful uninstall, refresh/reconcile Library from provider state;
  only after that refresh completes, remove the game ID from the temporary
  hidden set. The title then remains absent because provider reconciliation
  removed it, not because it remains hidden.
- Define and test failure/cancellation behavior so an installed game cannot
  remain invisibly hidden indefinitely. Likely refresh the still-installed
  catalogue and restore visibility after a failed or cancelled removal.
- Turning **Show hidden titles in library** on reveals hidden entries without
  changing their hidden membership; turning it off hides them again. Verify the
  setting resets on session reload while membership follows its separately
  chosen persistence policy.

### RECENTS-001 — Steam Recents and legacy launch behavior after Aurelia migration

**Status:** FIXED — direct Steam-family launch recents and legacy Aurelia identity
projection corrected; full regression suite passed.

- Root causes were separate: direct Steam/Aurelia launches through the UI bridge
  bypassed Consoled's `mark_played` path, while legacy `steam:<AppID>` recents
  remained in the recent query after Library had switched to the Aurelia row.
  The latter recent identity was not launchable through the current Library
  projection when its Aurelia counterpart existed.
- After a Sessiond-accepted Steam or Aurelia launch, the bridge now records the
  launch through Consoled. Legacy play timestamps are projected onto the
  matching installed `steam-aurelia:<AppID>` row; stale entries whose Aurelia
  counterpart is not installed are not exposed as launchable recents.
- Regression coverage verifies both direct-launch recents updates and migration
  of legacy Steam history to the Aurelia identity. Production was not changed.

### LIBRARY-LAUNCH-001 — Preserve launch return choreography from Library

**Status:** FIXED IN SOURCE — dev physical confirmation pending.

- Keep the home content faded out while the Library surface moves offscreen.
  Once Library is hidden, run the wallpaper's `beginContentExit()` animation;
  only after that completes should the launch overlay appear and the game launch.
  The previous handoff faded home content in alongside the Library exit, which
  violated the intended presentation order.
- The UI now chains the wallpaper exit after Library has left and reuses the
  existing hidden-home launch handoff (including its return watcher). Regression
  assertions cover the ordering. Failure-path trace review found that the Library
  fade-out remained at zero through return; the home layer is now restored before
  the coordinator's entrance animation. Focus moves to Recents immediately before
  the launch overlay appears; the existing deferred reconcile/presentation
  animation then runs on return, avoiding per-row Library return animations.
- For the launch-only Library exit, hold the glass backing at expanded dimensions
  and appearance while translating it vertically offscreen with the Library
  surface. Ordinary Back navigation retains the existing scale-to-card transition.
  Regression coverage checks the launch-only geometry; physically verify the
  launch/return choreography in dev-current. Production remains unchanged.

### NOTIFICATIONS-001 — Route transient status messages to Notifications

**Status:** ACTIVE — inventory transient-message producers, then move
bottom-right messages into the Notifications experience.

- Move transient bottom-right messages (including library refresh feedback) into
  the Notifications experience instead of displaying them in the current
  bottom-right message location. Preserve useful feedback and make it available
  through Notifications; inventory the current message producers and define
  notification severity, lifetime, and dismissal behavior during implementation.

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

- **Observed symptom:** The shell/Home screen displayed normally, but D-pad
  navigation stopped responding. Guide still worked through its independent
  InputPlumber D-Bus/OSK route; that did not prove the native SDL navigation
  route was healthy. The controller was a Microsoft Xbox 360 wireless receiver.
- In the earlier occurrence, the receiver and physical event node existed and
  InputPlumber showed one composite, but SDL exposed two InputPlumber-marked
  virtual gamepads for that one composite. Sessiond's identity-agnostic target
  association correctly refused to guess and left the SDL index unset. This
  mismatch is a confirmed failure signature, but it was not present in every
  later snapshot of the recurrence.
- **Known-good recovery (operator confirmed twice, most recently 2026-10-06):**
  after stale InputPlumber event-node/composite churn has settled, restart
  `inputplumber.service`. Its `PartOf` relationship also restarts
  `lulu-session@2.service`; allow the session and Home startup to finish before
  testing. On the successful recovery, the canonical native path was restored:
  `LULU_NATIVE_CONTROLLER=1`, InputPlumber `Default` profile, intercept mode 1,
  OSK hidden, one physical receiver source, one composite, exactly one SDL
  InputPlumber target, and Sessiond `sdl_index=0`. The operator then confirmed
  Home navigation worked. Restarting InputPlumber too early can first attach a
  stale event node; if that happens, let udev/hotplug reconciliation settle and
  repeat the restart rather than treating the transient post-restart state as
  recovered.
- **Detailed 2026-10-06 timeline:** The boot following removal of the forced
  headless-display kernel argument started InputPlumber at 04:10:12 and the
  graphical session at 04:10:13. Early InputPlumber discovery raced transient
  event nodes (including stale Sunshine virtual-pad nodes); logs showed
  `No such device`, failed target attachment/channel-closed errors, and
  composite teardown/recreation. At 04:21:04, restarting InputPlumber initially
  recreated a composite from stale `event17`; that composite failed at 04:21:27.
  The hotplug reconciliation service ran at 04:21:30 and discovered the real
  Xbox receiver at `/dev/input/event9`; Sessiond then corrected the profile and
  obtained SDL association index 0. A later restart at 04:35 attached directly
  to `event9` and remained stable.
- **Important recovery detail:** An attempted runtime-only override
  `LULU_NATIVE_CONTROLLER=0` plus the `Lulu SHELL` keyboard-emulation profile
  did not restore Home navigation. It was removed. The final successful
  recovery used the packaged/canonical `LULU_NATIVE_CONTROLLER=1` native-SDL
  architecture and its `Default` InputPlumber profile. Do not leave the runtime
  override in place or interpret Guide/OSK operation as proof of D-pad routing.
- A separate probe found the OSK hidden while InputPlumber was temporarily in
  intercept mode 2; restoring mode 1 and reloading `Lulu SHELL` alone did not
  restore Home navigation. On final recovery, OSK was hidden and intercept mode
  1. Record this as a potentially relevant stale-state observation, not as the
  proven root cause. Direct `evtest` captures and broad D-Bus monitoring during
  this incident did not provide a decisive physical D-pad event trace; the
  source event was grabbed by InputPlumber, so absence of events in those
  captures is not evidence that the controller itself was defective.
- **Current evidence / open cause:** On recovery, checks showed one SDL gamepad
  (`Xbox 360 Controller`, udev-marked InputPlumber target), one composite
  sourced from `/dev/input/event9`, one target gamepad, one Sessiond SDL slot at
  index 0, profile `Default`, intercept mode 1, and OSK `hidden`. Before the
  final recovery those same counts/mappings could appear healthy while the
  operator still reported no Home navigation. Therefore target count and SDL
  association are necessary diagnostics but are not sufficient acceptance;
  the root trigger and the reason a stable-looking intermediate state failed
  remain unproven.
- **Runbook for recurrence:** First record `date`, `systemctl status
  inputplumber.service lulu-session@2.service lulu-osk@2.service`, and the
  relevant boot journal before restarting anything. Check
  `sudo inputplumber devices list`, `sudo inputplumber targets list`, and
  `sudo inputplumber sources list`; inspect
  `journalctl -b -u inputplumber.service -u lulu-session@2.service` for
  `No such device`, `Gamepad order: []`, stale event numbers, composite
  teardown/recreation, and target attach failures. Read Sessiond's `GetState`
  and verify one connected controller with a non-null `sdl_index`; count SDL
  gamepads as user `lulu` (not the desktop operator, whose device permissions
  can produce a false empty inventory). Check the composite `ProfileName`,
  `InterceptMode`, its `TargetDevices`, and the OSK bridge socket `status`
  together. A hidden OSK with intercept mode 2 is suspicious; mode 1 is the
  expected shell state. Preserve the controller setup's canonical
  `LULU_NATIVE_CONTROLLER=1`; do not use the unsuccessful mode-0 runtime
  workaround. If logs show stale-node churn, let the hotplug reconciliation
  finish, restart InputPlumber once, wait for Home startup to complete, then
  check the state again and ask the operator to verify D-pad navigation. Record
  both the resulting diagnostics and physical confirmation; a healthy-looking
  inventory alone does not close this issue.
- Sunshine's `controller = disabled` setting is intentional and must remain
  unchanged. No Sunshine input, controller allowlist, or synthetic/virtual
  controller path is an acceptable workaround. No Lutris implementation change
  has been identified as the cause. No source change was made for this recovery;
  `/opt/lulu/current` was not changed.
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
