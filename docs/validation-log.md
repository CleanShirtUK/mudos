# Mudos Validation Log

## Startup regression diagnosis and fix — 2026-09-22

- The post-cleanup black screen was an exposed VT with a blinking cursor. The
  session and consoled services were alive, but the shell child failed during
  QML component loading and Gamescope subsequently had no child surface.
- The first causal runtime error was:
  `QQmlApplicationEngine failed to load component` followed by
  `StoreHome.qml:256:5: Property value set multiple times`.
  The Home cleanup had left the original `Component.onCompleted:
  rebuildDisplayCards()` and added a second `Component.onCompleted` for Home
  selection capture. QML rejected the component before rendering; this was not
  caused by browser zoom or COMPAT mappings.
- The narrow fix merges startup card rebuilding and selection capture into one
  completion handler. A regression test now asserts a single completion
  handler and that the empty/initial Home model path rebuilds before capturing
  selection state.

## Sunshine/Gamescope DRM ordering — 2026-09-22

- The broken presentation was reproduced with Sunshine started at 09:11:31
  and the refreshed session/Gamescope instance started at 18:45:33. Sunshine
  held `/dev/dri/card1`; seatd recorded Gamescope failing to become DRM master
  and Gamescope repeatedly reported `drmModeAtomicCommit: Permission denied`.
- Stopping Sunshine alone released its DRM descriptors, but an already failed
  Gamescope instance did not recover. Restarting only the session while
  Sunshine was stopped produced a healthy Gamescope owner with no subsequent
  atomic-commit errors.
- Starting Sunshine afterward with unchanged `capture = kms` succeeded. It
  found connector 72 and retained KMS capture while Gamescope retained the
  DRM device. KMS is therefore compatible; the defect was refresh ordering.
- `scripts/dev-runtime.sh` now stops Sunshine before restarting the session and
  starts it again afterward. This preserves the existing KMS setup and avoids
  allowing a refresh to place Sunshine ahead of Gamescope.

## Navigation Controller: All — 2026-09-22

- Added `All` as the default navigation policy in Settings → Controllers.
- All opens and accepts SDL edges from every normalized connected gamepad;
  specific-controller and automatic-fallback policies remain available.
- Player assignments are unchanged and remain owned by the controller registry
  for gameplay/provider use.
- Hotplug and removal update the accepted navigation set without a shell
  restart. Regression coverage includes All, specific selection, assignment
  separation, and runtime controller loss/reappearance.

## Browser and Store UX cleanup — 2026-09-22

- Home Store cards now use the same animated horizontal rail choreography as
  System cards: captured start positions, animated selection progress, motion
  blur, canonical mapping dependencies, and selected-card opacity ownership.
  Home-specific card content and the separate Available-to-Download catalogue
  remain unchanged.
- COMPAT maps Right Stick to native mouse wheel events with a 0.25 deadzone
  (vertical and horizontal), and maps RB to Tab and LB to Shift+Tab. These
  mappings exist only in the browser COMPAT profile, so they do not reach the
  Mudos shell. Browser WebEngine zoom is explicitly set to 125%.
- Custom Store cards expose X / Store Options. The existing attached Mudos
  credential/OSK path edits visible prepopulated name and URL fields. URL edits
  retain http/https normalization and validation; names reject blank or
  overlong values. Steam, Questarr, and Add New Store do not expose options.
- StoreBookmarkBridge now persists name and URL edits and emits the existing
  model-change signal. Removal therefore updates Home immediately, clamps the
  selected card to a surviving neighbour, and remains removed after restart.
- Remote Sunshine/Moonlight validation is deployment-ready; no local physical
  controller was required for this pass. Full suite and shell build completed
  before deployment.

## Questarr authentication lifecycle repair — 2026-09-22

- Live logs showed successful `/api/auth/login` calls approximately every 31
  seconds from both the short `Type=oneshot` reconciler and the downloader
  metadata clients. Each process/client discarded its in-memory JWT after a
  refresh, followed by bursts of several 429 responses within the same
  second. Questarr's login endpoint then rate-limited the repeated
  authentication; no downloader configuration was involved.
- `QuestarrApi` now stores only the ephemeral backend session token and its
  locally decoded JWT `exp` in a mode-0600 cache below `/run/user/<uid>/lulu`.
  The cache is backend-only, never exposed to QML, TOML, or logs. Tokens are
  reused until 30 seconds before expiry. A 401 invalidates the cache,
  authenticates once, and retries the request once.
- HTTP 429 now honors numeric or HTTP-date `Retry-After`; absent that header it
  uses bounded exponential deferral (30 seconds through 300 seconds). The
  result is reported as `deferred` with no destructive provider changes.
- A mode-0600 runtime lock permits at most one reconciliation process. Five
  concurrent synthetic triggers produced one successful pass and four
  `coalesced` deferred results. Two immediate sequential passes reused the
  cached token and did not issue new login requests.
- The read-only downloader metadata path now uses the same API/cache and
  authentication single-flight mechanism, so separate Transmission and NZBGet
  plugin clients also reuse the backend session. After deployment and an
  acquisition-service restart, one login was observed at restart and none
  afterward during the validation window; prior 429 activity was not retried
  in a tight loop.
- Live post-repair reconciliation succeeded. Questarr reported two Mudos
  downloaders (one Transmission and one NZBGet), six Prowlarr indexers (four
  torrent and two Usenet), and stable managed-resource IDs. Existing transfers
  were not cancelled, restarted, or reconfigured; Mario Kart remains under
  its prior paused state.

## Final Lutris provider pass — 2026-09-22

- Inspected live Lutris recipes for OpenTTD, SuperTuxKart, Elder Scrolls:
  Arena, and Quake. Linux, DOSBox, archive, and file operations classify as
  automatic. A Wine `wineexec`/`execute` step is marked only when it maps to a
  local installer file and lacks unattended arguments; Arena's `/SILENT` task
  is not marked. Recipe objects are not mutated.
- Ready-to-Install Lutris source records now use the canonical PC identity and
  the existing Store Install action submits `SubmitPcInstall`. Questarr and
  manual sources use the same transaction.
- Live session D-Bus validation passed: `RequestInteractiveLaunch` produced a
  Gamescope/XWayland foreign-ui surface in COMPAT, and `QuitDelegated`
  terminated the owned group and restored shell/input. The parent cancellation
  callback is transaction-ID based. A live external local Wine installer was
  not available without downloading a commercial payload, so that specific
  Acquisitiond recipe run remains pending.
- ProcessSupervisor now waits for the owned process group rather than the
  original PID and reselects replacement-child surfaces. The fixture supports
  bootstrapper/replacement validation without title or original-PID ownership.
- Interrupted transactions clean only transaction-created canonical state and
  never infer success from files; Lutris registration/finalization remains the
  success authority. Retry uses the existing retryable failure path.
- No legal real Wine graphical fixture was run. Native Wayland delegation is
  deferred as a separate session capability.

## First physical PC/Lutris acceptance — 2026-09-22

- Source used: the retained manual legal/free OpenTTD source at
  `/home/lulu/Games/.acquisition/pc-test/openttd-source`, with
  `provenance=manual`, `ready_to_install=true`, and recipe
  `openttd-v141`. No active acquisition was cancelled or restarted.
- The source was first returned to Ready to Install through the normal Lutris
  uninstall path. The UI bridge's Install boundary then submitted one parent
  `lutris` job for the existing canonical record. The transaction completed,
  registered Lutris ID `1`, and produced one catalogue row
  `lutris:openttd`; no duplicate Questarr/source/Lutris card was created.
- Reinstall exposed two concrete defects during acceptance: stale canonical
  payload files were not removed before retry, and the source-record identity
  could become `lutris:pc:openttd` while the installed record was
  `lutris:openttd`, causing a provider/provider-id uniqueness failure. Both
  were fixed: Ready-to-Install retries remove only the Mudos-owned canonical
  directory, and identity uses the stable Lutris slug when present. A retry
  then completed successfully without another source download.
- The appliance's physical controller was disconnected during this run and
  the desktop browser review channel was unavailable. Keyboard injection into
  the Gamescope shell did not produce a verifiable UI action, so a literal
  controller A-button trace and physical COMPAT mouse test are explicitly
  pending. The installed-state, source-retention, registration, and
  reinstall results were verified from the live appliance state.
- Questarr health: `POST /api/auth/login` succeeded earlier with a JWT, then
  reconciliation hit HTTP 429 rate limiting on that same endpoint. The
  downloader/container remained running and existing transfers were not
  modified. No Questarr PC source was available for this acceptance run, so
  Questarr-to-Ready-to-Install association remains pending independently of
  the successful manual-source lifecycle.
- No real Wine/XWayland installer was available without introducing
  commercial content. Native Wayland remains deferred.

This append-only log is authoritative for later hands-on validation. `PASS`
means the stated evidence exists; pending physical or live-service checks are
not implied to have passed.

## Emulator/controller regression repair

- Automated validation: PASS; `PYTHONPATH=src pytest -q` reports 402 passed.
- Eden policy: restored the live InputPlumber SDL GUID
  `030081b85e0400008e02000001000000` and Nintendo face-button translation
  (`A=1`, `B=0`, `X=3`, `Y=2`). This remains an Eden-native profile and does
  not alter RetroArch's working autoconfig.
- Dolphin policy: profiles are now written below the provider's `--user/Config`
  root, use the stable SDL gamepad name, configure GameCube Port 1, and expose
  an emulated Classic Controller for Wii. Profile generation is idempotent and
  preserves logical player indices.
- RetroArch lifecycle: fixed D-Bus `busctl` state decoding when prior launch
  metadata contains apostrophes (for example `Tony Hawk's`). This was a
  pre-process-launch rejection on the second attempt; the child process itself
  exited cleanly and no forced-kill workaround was added. Automated coverage
  protects the repeat-launch state parser and profile policy.
- Regression boundaries: Eden face-button/GUID policy traces to `59969e5`;
  Dolphin's native-root/config-path issue traces to `77824bb`/`8de4eee`;
  RetroArch repeat-launch failure is a later shared `busctl` serialization
  boundary, not an emulator-specific controller regression.
- Physical validation: pending after deployment; must cover Eden, Dolphin,
  PCSX2, and RetroArch repeated launch/exit without restarting Mudos.

## Eden current-build configuration investigation

- Installed build: `eden-bin 0.2.1-1`, `/opt/eden-bin/eden-bin.AppImage`, SHA-256
  `2fae658397daf13c118082a3eb65d61a6519967b5e22e6667756baecf6000c5a`.
- SDL evidence: indices `0/1/2` are all `Xbox 360 Controller`, each with GUID
  `030081b85e0400008e02000001000000`, 15 buttons, 6 axes, and the live SDL
  mapping `a:b0,b:b1,x:b2,y:b3`. Thus physical Xbox A/B/X/Y are raw SDL
  buttons `0/1/2/3`; the desired Nintendo action requires Eden bindings
  `A=1,B=0,X=3,Y=2`.
- `strace` launch evidence: Eden opened and rewrote
  `/home/lulu/.config/eden/qt-config.ini` and its title override under
  `/home/lulu/.config/eden/custom/0100152000022000.ini`. It did not open the
  Mudos-generated `/home/lulu/.config/lulu/providers/eden/config/qt-config.ini`
  passed in the command line. The `--config` argument therefore does not select
  that file in this installed build.
- Current native donor shape: Eden's canonical file uses
  `engine:sdl,port:N,guid:GUID,...`, `player_N_type`, connected/default metadata,
  and current d-pad key `player_N_button_dup` (not the historical `ddup`). Its
  stale donor values were raw Xbox face bindings and the older GUID, explaining
  both the unswapped face buttons and why the generated Mudos profile had no
  effect.
- Fix: the Eden adapter now writes the provider profile and the actual native
  `/home/lulu/.config/eden/qt-config.ini`, renders the current `port,guid`
  selector order and `dup` schema, and still removes stale keyboard slots.
- Physical validation after this current-build fix remains pending.

## Eden native-donor capture pending

- Latest physical result: FAIL; the generated canonical Eden profile still
  does not produce working independent Player 2/3 input or the expected
  Nintendo face behaviour. No further controller-generator change is justified
  without a physically verified Eden-written donor.
- Failing-state backup: temporary validation capture (original local path omitted).
- Preserved launch command:
  `/usr/bin/eden --appimage-extract-and-run --config
  /home/lulu/.config/eden/qt-config.ini -f --fullscreen --game
  /home/lulu/Games/ROMs/switch/Mario Kart 8 Deluxe
  [0100152000022000][v0].nsp`.
- At capture time InputPlumber exposed `CompositeDevice0/1/2`, SDL indices
  `0/1/2`, and sessiond assigned Mudos players `1/2/3`; CompositeDevice0 was
  the navigation controller. This rules out missing live inventory as the
  immediate explanation.
- Existing Eden snapshots were preserved for comparison, but none is accepted
  as a current physically working donor. A hands-on Eden GUI sequence is still
  required: Player 1 donor, Nintendo face-button donor, Player 2 donor, Player
  3 donor, cold restart, and then the unchanged Mudos launch wrapper.
- No source or deployed runtime change was made for this donor-capture phase.

## Eden face-button override / Player 4 capability

- Latest requested runtime policy restores the Nintendo face values: every slot
  now emits `A=button:1`, `B=button:0`, `X=button:3`, `Y=button:2`.
- The canonical Eden profile is also provisioned with Player 4 as an SDL
  gamepad on `port:3`, using the same stable GUID and face policy, even when
  no fourth physical controller is currently connected.
- This is a requested configuration change, not a physical validation result;
  Mario Kart verification remains pending.

## Eden persisted-profile archaeology

- The missing-profile hypothesis is confirmed by the surviving pre-modularisation
  runtime snapshot. Its provider defined `PROFILE_NAME = "mudos-xbox360"`,
  installed the profile at `~/.config/eden/input/mudos-xbox360.ini`, and
  launched Eden with `-input-profile mudos-xbox360`.
- The profile artifact survives at:
  `/home/lulu/.config/eden/input/mudos-xbox360.ini`. An identical read-only
  copy exists in the historical reference tree at
  `/home/lulu/old-reference-releases.20260913/d25d28f766ce26f91f5c131633036309b039d4d9-90cc4e723e42/config/eden/input/mudos-xbox360.ini`.
  Both have SHA-256
  `07f7e3a5dbe6d3b5a5453b8bb3276d6165cc3d96975a047b6697c681887b3184`.
- The profile is a native `[Controls]` single-controller preset. Relevant
  values are the shared SDL GUID
  `030081b85e0400008e02000001000000`, `port:0`, Nintendo face mapping
  `A=button:1`, `B=button:0`, `X=button:3`, `Y=button:2`, SDL trigger axes,
  hat d-pad directions, and native stick definitions.
- The historical `qt-config.ini` snapshot contains the missing binding:
  `player_0_profile_name=mudos-xbox360` (with `player_0_profile_name\default=false`).
  Players 1–9 otherwise have empty profile names. This is an indirect
  player-slot-to-profile reference; the profile mappings are not duplicated in
  each player slot.
- Current `/home/lulu/.config/eden/qt-config.ini` has no nonempty
  `player_*_profile_name` binding. Current Mudos instead writes inline
  `player_*_button_*` values and does not pass `-input-profile`.
- Historical filesystem layout relevant to this mechanism was:
  `~/.config/eden/qt-config.ini`, `~/.config/eden/input/mudos-xbox360.ini`,
  and title overrides under `~/.config/eden/custom/`. No separate Eden
  controller-profile artifact exists in the repository’s tracked git trees or
  in the immutable `/opt/lulu/releases` payloads. The surviving profile is
  machine/runtime state, not a committed source asset.
- The provider source containing this profile-install, profile-selection, and
  `-input-profile` mechanism exists in the historical reference snapshot, but
  no reachable git commit contains `PROFILE_NAME`, `profile_asset_path`, or
  `-input-profile`. Therefore the exact commit where this behavior disappeared
  cannot be established from repository history; it was already absent from the
  tracked source by the earliest reachable provider commits around `588f476`.
- No implementation change was made. The profile was preserved in place and
  the immutable release was not modified. Restoring this mechanism is the next
  narrow implementation candidate, pending explicit approval.

## Eden multi-controller archaeology

- Historical last-known-good multi-controller implementation: `789550f`
  (`feat: assign multiple controllers to Eden`), refined by `20bb85e`,
  `63b8016`, `6adc08b`, `e6831d3`, and `a04f86a`. The modularisation boundary
  was `77824bb`; it changed the provider/config root but did not intentionally
  change the Eden slot contract.
- The exact Nintendo face-button profile is recoverable from
  `59969e5^:src/lulu/switch_provider.py` (the parent of the later SDL mapping
  change). For each populated slot it used `type=0`,
  `connected\\default=false`, `connected=true`, and:
  `A=button:1`, `B=button:0`, `X=button:3`, `Y=button:2`. The same values
  were emitted for every player, not only Player 1.
- Historical three-player effective config was written to the active
  `~/.config/eden/qt-config.ini` immediately before launch, with the reusable
  source profile at `~/.config/eden/lulu-switch.ini`. Its three SDL prefixes
  were identical except for `port:0`, `port:1`, and `port:2`, all using GUID
  `030081b85e0400008e02000001000000` and `engine:sdl`.
- Historical non-face bindings were also explicit: `L=9`, `R=10`, minus `4`,
  plus `6`, stick clicks `7/8`, d-pad buttons `11/12/13/14`, ZL/ZR axes `4/5`,
  and sticks axes `0/1` and `2/3`. The current provider now restores this
  native shape instead of the later raw-Xbox button/axis rewrite.
- Live inventory: three composites are present as
  `CompositeDevice0/1/2`, all persistent identity `045e_0291`; SDL exposes
  three `Xbox 360 Controller` devices with the same GUID and indices `0/1/2`.
  Sessiond assigns them to Mudos players `1/2/3`; CompositeDevice0 remains the
  navigation controller. No duplicate physical assignment was observed.
- Current-vs-historical cause: the reported raw Player 1 mapping and keyboard
  Players 2/3 came from the active Eden profile not representing the full
  historical slot policy. The restored generator now emits each connected
  player as a separate `type=0` SDL slot, with distinct `port` values and the
  Nintendo face mapping, and replaces stale Controls entries so keyboard slots
  cannot survive a reload.
- Exact face-button diff: the pre-repair current generator emitted
  `A=button:0`, `B=button:1`, `X=button:2`, `Y=button:3`; the historical and
  restored contract emits `A=button:1`, `B=button:0`, `X=button:3`,
  `Y=button:2`. This diff is identical for Players 1, 2, and 3; only the SDL
  port changes (`0`, `1`, `2`).

## Torrent provider / Transmission

- Commit: `599a68c`
- Implementation: provider-owned Transmission 4.1 JSON-RPC adapter, durable
  torrent telemetry/artifact fields, restart reconciliation, path-safe delete,
  and provider configuration/provisioning.
- Provisioned version: `transmission-cli 4.1.3-2` from the Arch `extra`
  repository.
- Service: `lulu-transmission.service`, dedicated `lulu-transmission` user,
  enabled and active. RPC listens on `127.0.0.1:9091` and rejects unauthenticated
  requests with HTTP 401. Credentials are generated once and stored through
  `SecretStore`; working daemon settings are not tracked.
- Storage: `/home/lulu/Games/.acquisition/torrents/{incomplete,complete,metainfo,ownership}`.
  Transmission's daemon incomplete directory is separate from the completed
  per-torrent destination. No Steam, ROM, Lutris, or installed-game root is used.
- Automated validation: PASS; full suite and Transmission-focused tests pass.
  Coverage includes JSON-RPC 409 session negotiation, authentication headers,
  magnet/metainfo addition, duplicate hashes, normalization, file selection,
  restart queue recovery, status/progress/rates/ETA fields, ownership and
  traversal/symlink/outside-root deletion safety.
- Live magnet: PASS using the public-domain Big Buck Bunny test torrent
  (`dd8255ecdc7ca55fb0bbf81323d87062db1f6d1c`). It was added through the
  acquisition D-Bus service, received the `mudos` label, appeared in the
  normalized Downloads snapshot, reported progress/rates/ETA, and completed
  at the canonical complete root.
- Live pause/resume: PASS; pause stopped transfer and resume continued the
  same stable hash.
- Live completion: PASS; Mudos marked the acquisition `completed` while the
  daemon remained in provider seeding state. No catalogue/import/install action
  was performed.
- Restart recovery: PASS for Transmission daemon restart during an active
  acquisition; the job retained its hash and resumed observation after the
  daemon returned. acquisitiond service restart also requeued active jobs for
  provider reconciliation rather than converting them to generic failures.
- Remove/delete: PASS; remove deleted the daemon record while preserving the
  completed payload, and DeleteDownload removed only the labelled Mudos payload.
  An outside-root path was refused. Provider roots have an ACL for the Mudos
  service user because Transmission controls its own file modes.
- Questarr: pending future integration. The ownership contract is label-based:
  Mudos persists hashes and uses `mudos`; future Questarr jobs may use `questarr`.
  Mudos does not enumerate or delete unowned daemon torrents.
- Visual validation: pending; no styled UI work was performed. Existing
  provider-neutral Downloads UI remains the only presentation surface.

- Current implementation audit: PASS; Transmission 4.1.3-2 is provisioned as
  `lulu-transmission.service` with localhost-only authenticated RPC on
  `127.0.0.1:9091`. Mudos uses the `mudos` Transmission label and writes a
  hash-keyed ownership sidecar under `.acquisition/torrents/ownership/` with
  job/provider/content identity. Hashes, not numeric Transmission IDs, remain
  the persisted provider identity. Completed torrents are marked downloaded
  while Transmission may continue seeding; delete-local-data plumbing is
  available separately from normal cancellation. Physical end-to-end fixture
  validation remains pending.

## Mudos Transmission provider backlog completion

- Commit: see repository history for the implementation commit
- Package: Arch `transmission-cli 4.1.3-2`; daemon unit:
  `lulu-transmission.service`, running as `lulu-transmission` with state in
  `/var/lib/lulu-transmission`.
- RPC: authenticated JSON-RPC 2.0 on `127.0.0.1:9091/transmission/rpc`,
  whitelist and host-whitelist restricted to localhost. Credentials are mode
  0600 in the daemon settings and mirrored through `SecretStore`; no external
  RPC bind is configured.
- Acquisition layout:
  `/home/lulu/Games/.acquisition/torrents/{incomplete,complete,metainfo,ownership}`.
  Transmission receives `complete` as its download directory and uses its
  separate incomplete directory for staging. Completion means downloaded;
  seeding may continue after the Mudos job is completed.
- Ownership: every Mudos torrent carries the `mudos` Transmission label and a
  hash-keyed JSON sidecar in `ownership/` containing hash, Mudos job ID,
  provider, and content identity. Unlabelled torrents are never adopted.
- Normalized API: `TransmissionClient` owns RPC/session negotiation and
  normalizes hashes, state, progress, rates, files, errors, pause/resume, and
  remove operations. `TorrentProvider` is the JobManager executor boundary.
  Numeric Transmission IDs are never persisted.
- Recovery: persisted hashes are reconciled through `torrent_get`; active,
  paused, completed, missing, and non-owned torrents have deterministic
  outcomes. Recovered provider capability metadata is restored by executor
  registration.
- Test fixture: the Blender Foundation Creative Commons Big Buck Bunny
  torrent, `dd8255ecdc7ca55fb0bbf81323d87062db1f6d1c`. New physical
  end-to-end validation remains pending after this provider audit.
- Physical validation sequence: submit the fixture through acquisitiond; verify
  it appears in global Downloads; observe progress/rates; Pause; Resume;
  restart the Mudos graphical session; restart acquisitiond and verify hash
  reconciliation; complete and verify downloaded/completed while seeding may
  continue; submit a second fixture, Cancel, and verify cancelled disappears
  without Failed/Retry; exercise provider remove-without-delete and the
  backend delete-local-data path separately.

## Controller reconnect hardening

- Commits: `1f1992a`
- Automated validation: PASS; runtime lifecycle validated
- Runtime activated: PASS
- Physical/controller validation: one successful physical reconnect cycle observed; intermittent earlier failure not reproduced; further recurrence observation pending
- Visual validation: pending
- Provider/live-service validation: pending
- Notes: observe for recurrence during hands-on session

## Sunshine virtual gamepad emulator launch regression

- Live failure captured: RetroArch and Eden both stopped before provider
  process creation with `RuntimeError: Mudos has no assigned SDL gamepad
  controllers`; provider index resolution returned no mapping.
- Boundary: Sunshine exposed two distinct virtual evdev/SDL gamepads
  (`event13/js2` and `event14/js3`). The capability generator accepted their
  empty physical paths, but then recursively promoted InputPlumber-generated
  output composites as additional sources. This produced stale players and
  no usable SDL metadata.
- Fix: retain capability-selected virtual sources while excluding generic
  generated evdev outputs, and reconcile stale `Lulu Controller` composites
  during hotplug activation. No vendor, product, GUID, name, or Sunshine
  allowlist was added.
- Runtime: PASS in `/opt/lulu/dev-current`; exactly two active composites
  sourced from `/dev/input/event13` and `/dev/input/event14`, assigned players
  1 and 2. No recursive output composites remain.
- Automated validation: PASS; 414 full-suite tests, 6 subtests.
- Provider validation: PASS; RetroArch launched Sonic the Hedgehog and Eden
  launched Mario Kart 8 Deluxe through the shared `LaunchGame` path, with
  both provider processes created successfully.

## Keyboard Guide development and recovery path

- Failed physical trace: `Ctrl+Alt+G` reached the shell and launched Guide,
  but Guide logged `Guide keyboard grab failed`; no subsequent `Guide input`
  entries appeared. Delegated Gamescope/Steam/emulator focus therefore kept
  Up/Down/Enter/Escape/Backspace.
- Fix: the shell now owns global grabs for the explicit recovery keys only
  while `guideProcess_` is active, translates them over the existing Guide
  stdin IPC to `ui_up`, `ui_down`, `ui_left`, `ui_right`, `ui_accept`, and
  `ui_back`, and releases the grabs when Guide exits.
- Navigation: Up/Down/Left/Right, Enter, Escape, and Backspace are consumed
  at the shell boundary and drive Guide's existing selection/action model;
  no provider-specific or Sunshine-specific path was added.
- Independence: startup does not inspect controller count, SDL state,
  InputPlumber composites, or controller ownership. Existing BTN_MODE Guide
  invocation and controller ownership paths remain intact.
- Build/deployment: PASS; native shell and Guide rebuilt and deployed only to
  `/opt/lulu/dev-current`; immutable releases unchanged.
- Automated validation: PASS; 57 targeted Guide/UI tests and 422 full-suite
  tests, with 6 subtests.

## NZBGet Usenet acquisition provider

- Package/runtime: CachyOS `nzbget 26.2-3.1`, native `/usr/bin/nzbget`,
  enabled as the package `nzbget.service` under the dedicated `nzbget` user.
  No container layer was added.
- Security: JSON-RPC/Web UI is bound to `127.0.0.1:6789`; HTTP Basic RPC
  credentials are generated once, stored through `SecretStore` as
  `usenet/rpc-password`, and the daemon configuration is mode `0600`.
  No LAN firewall exposure was added.
- Storage: `/home/lulu/Games/.acquisition/usenet/{incomplete,complete,nzb,ownership}`;
  NZBGet queue state remains under `/var/lib/nzbget`, while intermediate and
  completed payloads use the canonical Mudos roots.
- Ownership: Mudos submits category `mudos` and opaque `DupeKey=mudos:<job-id>`;
  sidecars under `ownership/<job-id>.json` retain the logical job and current
  NZBID. Queue/history reconciliation uses DupeKey, never NZBID alone, so
  Questarr/unowned items are ignored.
- Provider: normalized JSON-RPC adapter covers health/version, NZB file/URL
  submission, queue/history normalization, split 64-bit sizes, per-group
  pause/resume, preserve-history cancellation, post-processing stages, and
  queue-to-history recovery.
- Credentials: Usenet server configuration boundary is present under
  `providers.usenet.server`, with host/port/TLS/connections and SecretStore
  username/password references. No news-server credentials are configured.
- Runtime validation: PASS; service and acquisitiond are active, RPC health
  returns version `26.2`, RPC listens only on localhost, and the provider
  registry reports NZBGet Usenet available. No real NZB was submitted because
  the daemon reports zero configured news servers.
- Automated validation: PASS; 9 focused NZBGet tests and 431 full-suite
  tests, with 6 subtests.

## Appliance acquisition Web UIs

- Policy: NZBGet and Transmission administration UIs are standard appliance
  configuration, not development-only or Sunshine-dependent configuration.
  `scripts/provision-acquisition-services.sh` is the shared idempotent entry
  point for normal install/OOBE integration and mutable refreshes.
- Listeners: NZBGet binds `0.0.0.0:6789`; Transmission binds
  `0.0.0.0:9091`. Mudos still uses `127.0.0.1` for both RPC endpoints.
- Security: both services require authentication, Transmission retains its
  RPC whitelist and host whitelist, and UPnP/port forwarding is disabled.
  Credentials remain SecretStore-backed and private daemon configuration is
  mode `0600`.
- Firewall: UFW permits TCP 6789 and 9091 only from the active LAN route's
  subnet and interface. No WAN or router-forwarding rule was added; existing
  Sunshine rules remain intact.
- URLs: `http://<mudos-host>:6789/` and
  `http://<mudos-host>:9091/transmission/web/`. Native TLS is not enabled in
  this configuration; access is restricted by LAN firewall and authentication.
- Runtime validation: PASS for both listeners, Transmission authenticated Web
  UI (`200`) and unauthenticated rejection (`401`), NZBGet authenticated RPC
  health (`26.2`) and unauthenticated rejection (`401`). NZBGet's authenticated
  Web UI returns `503` while no news server is configured, but its auth layer
  and RPC remain healthy; configuring a real news server is required for the
  usable NZBGet dashboard.

## Mudos administration Web UI

- Architecture: standard-library Python `http.server`, server-rendered HTML,
  no database, SPA, Node pipeline, or new runtime dependency. HTTP handlers
  delegate mutations to `ProviderConfigurationService.update_provider()` and
  `SecretStore`; they never edit provider TOML or credential files directly.
- Endpoint/lifecycle: `lulu-admin.service`, unprivileged `lulu` user, bound to
  `0.0.0.0:80` with only `CAP_NET_BIND_SERVICE`; enabled independently of the
  graphical session and restarted on failure.
- Naming/firewall: Avahi advertises `mudos.local`; local resolution was
  verified as `mudos.local -> 192.168.0.245`. UFW permits TCP 80 only from the
  active trusted LAN route. The shared normal entrypoint is
  `scripts/provision-appliance-services.sh`.
- Authentication: one appliance admin credential, stored as a PBKDF2 hash in
  SecretStore namespace `admin`; sessions are expiring HttpOnly/SameSite
  cookies with per-session CSRF tokens. `scripts/bootstrap-admin.sh` performs
  the initial interactive setup. Existing provider secrets are never rendered;
  blank fields preserve them and explicit Clear controls remove them.
- Dashboard/services: core and admin service state plus hostname/LAN
  diagnostics; links are generated from the request host for DUFS (8080),
  NZBGet (6789), Transmission (9091), and Sunshine (47990).
- Providers: shared provider listing/editing is present, including a dedicated
  Usenet server namespace and secret fields. NZBGet and Transmission tests use
  their existing normalized clients; unsupported providers report that no
  normalized health method is available rather than duplicating protocols.
- Validation: focused admin tests pass (4); service active, port 80 bound,
  LAN redirect/auth boundary verified, and mDNS resolution verified. Full
  suite remains required after the final runtime refresh.

## Admin bootstrap runtime fix

- Fixed `scripts/bootstrap-admin.sh` to select the deployed runtime explicitly
  (`/opt/lulu/dev-current/lib` when present, otherwise `/opt/lulu/current/lib`)
  and invoke Python through `sudo -u lulu env` with the same HOME/XDG context
  as `lulu-admin.service`. It no longer relies on caller cwd or ambient
  `PYTHONPATH`.
- Audited the other provisioning helpers: Python-based SecretStore operations
  now use explicit deployed import paths and lulu configuration context rather
  than a development checkout assumption.
- Deployment validation: bootstrap executed from a sanitized environment and
  the resulting PBKDF2 admin credential was read and verified as `lulu`; the
  temporary validation credential was then cleared.

## NZBGet credential administration

- Live NZBGet 26.2 configuration reports `ControlUsername=mudos` and a
  populated `ControlPassword`; the password value is intentionally omitted.
  The effective provider reference is `usenet/rpc-password` in SecretStore,
  with the user provider layer converging on the system reference.
- Added `nzbget_admin.py` and wired the Mudos admin provider form so username
  is editable, password fields are write-only, blank preserves the existing
  secret, and explicit clearing is rejected for the required NZBGet control
  credential. Replacement writes SecretStore, materializes the private
  NZBGet config, and narrowly restarts `nzbget.service` through polkit.
- Runtime validation: replacement and restoration succeeded through the
  shared provider/SecretStore path; the configured credential produced the
  authenticated NZBGet response (`503` because no news server is configured),
  while an incorrect credential produced `401`. RPC health remained `26.2`.
- Persistence: `nzbget.service` is enabled, the credential is persisted in
  SecretStore and private daemon state, and mutable provisioning refreshes
  rematerialize the same reference without exposing its value.

## NZBGet live configuration regression and repair

- Investigation found NZBGet running/listening on `0.0.0.0:6789`, but Mudos'
  current SecretStore password and the live `ControlPassword` were different
  revisions; the Mudos health result was HTTP `401 authentication-failed`.
- The immediate materialization failure was caused by the running admin service
  predating the deployed credential-sync code, combined with its systemd
  sandbox not permitting `/var/lib/nzbget` writes. Its save path changed
  SecretStore but did not update/restart NZBGet. Acquisitiond also held its
  NZBGet client from startup, so it could retain old credentials.
- The Usenet server form had only written provider TOML; it had not rendered
  `Server1.*` into NZBGet. The repaired runtime now contains the requested
  host, port 563, TLS enabled, configured credentials, and 50 connections.
- Repair: admin provisioning now restarts the deployed admin service; the
  service has narrow write access to the NZBGet config, materializes control
  and Server1 settings, restarts NZBGet, and restarts acquisitiond so its
  cached provider client is rebuilt. Polkit grants only the two required unit
  restarts.
- Validation: provider SecretStore and effective config revisions match,
  username matches, NZBGet RPC health returns 26.2, `testserver` returned an
  empty success result for the configured TurboUsenet server, and refresh
  rematerialization preserved the values. No credentials were printed or
  logged.

## NZBGet packaged Web UI repair

- Root cause: the CachyOS package includes `/usr/share/nzbget/webui`, but the
  managed `/var/lib/nzbget/nzbget.conf` had no `WebDir` value. RPC continued to
  work while browser requests returned HTTP 503.
- Package inspection: `/usr/share/nzbget/webui` exists and is readable by the
  `nzbget` service user; `/usr/share/nzbget/nzbget.conf` exists. This package
  does not ship `/usr/share/nzbget/scripts`, so the managed writable
  `/var/lib/nzbget/scripts` remains the correct ScriptDir.
- Materialized settings: `WebDir=/usr/share/nzbget/webui`,
  `ConfigTemplate=/usr/share/nzbget/nzbget.conf`, and
  `ScriptDir=/var/lib/nzbget/scripts`. These are now applied by normal
  provisioning and every admin credential/news-server rematerialization.
- Validation: after restarting only `nzbget.service`, the authenticated Web
  UI returned HTTP 200, invalid credentials returned HTTP 401, RPC health
  returned 26.2, and the TurboUsenet test succeeded. Runtime refresh preserved
  WebDir. No credentials were printed or logged.

## External NZBGet acquisition discovery

- Live fixture observed before mutation: NZBID `1`, name
  `Wii.Sports.USA.Wii-PARADOX-AlteZachen`, empty category, empty DupeKey,
  status `PAUSED`, approximately 2.38% progress, destination under the
  canonical Usenet incomplete directory. The previous Mudos category/DupeKey
  filter therefore ignored it as unowned.
- Added generic acquisition `origin` metadata separate from ownership. Origins
  include `mudos`, `questarr`, and `external`; the live item is represented as
  `external/manual` and is never claimed as Mudos-owned.
- External NZB identities use a stable provider-field fingerprint and durable
  sidecars under the Usenet ownership area. Numeric NZBID is not the sole
  identity and queue-to-history matching ignores FinalDir changes.
- Acquisitiond periodically reconciles external queue/history records.
  External pause, resume, and administrative cancel use the existing generic
  controls without rewriting provenance. Durable records survive acquisitiond
  restart and normal completion/history reconciliation.
- Runtime validation: the live NZB appeared in the global Downloads snapshot as
  provider `usenet`, paused, with progress/rate/destination metadata and
  `origin=external`. Transmission now uses the same generic discovery contract
  with `transmission:<info-hash>` identity and Questarr-label detection. The
  managed daemon currently has zero torrents, so no live Transmission fixture
  was available. Full suite: 443 passed, 6 subtests.

## Transmission credential normalization

- Live authoritative state: Transmission runs as `lulu-transmission.service`
  from `/var/lib/lulu-transmission/settings.json`, with RPC/Web UI
  authentication required and the configured username `lulu-mudos`. The
  daemon password is salted in its private runtime configuration; its
  plaintext value was never reported.
- SecretStore already contained the working authoritative credential under
  `torrent/rpc-username` and `torrent/rpc-password`. No credential replacement
  was necessary; the existing value authenticated successfully before and
  after the dev refresh.
- The provider TOML retains only the existing SecretStore references and
  localhost RPC endpoint. No plaintext password is stored in normal Mudos
  configuration.
- Added `transmission_admin.py` and Transmission-specific admin controls:
  editable RPC username, write-only password replacement, configured status,
  Test Connection, blank-password preservation, and rejection of explicit
  credential clearing. Replacements stop Transmission before private config
  materialization, restart it for Transmission's normal password salting,
  restart Acquisitiond, and trigger the existing Questarr reconciler.
- Provisioning no longer rewrites an unchanged salted password on every
  refresh. Torrent data and settings unrelated to credentials are preserved.
- Runtime validation: Acquisitiond Transmission RPC authentication passed;
  Questarr reconciliation completed with `transmission=updated`; the
  authenticated Transmission Web UI returned HTTP 200 and an incorrect
  password returned HTTP 401. Five existing torrent hashes remained present
  after refresh and service restart. No credential value or hash was printed
  or logged.

## Transmission Admin credential-save transaction repair

- Root cause of the failed save: `lulu-admin.service` had no polkit grant for
  `stop lulu-transmission.service`, so systemd returned `Access denied` with
  exit status 1. The live unit also lacked the required 60-second clean-stop
  timeout; earlier refreshes showed Transmission stop timeouts and SIGKILLs.
- The failed attempt was detected as inconsistent during repair: the runtime
  settings and SecretStore did not authenticate as one pair. A fresh
  known-good credential was restored to both layers before further testing;
  no secret value was printed.
- Added narrowly scoped polkit grants for Transmission stop/start and the
  root-only settings ACL helper. No generic `systemctl` permission was added.
  The Admin service may write only the private settings file through the
  helper-provided ACL; the daemon state directory remains otherwise private.
- Credential replacement is transactional: validate, stop, restore settings
  access, materialize, start, authenticate, commit SecretStore/provider state,
  restart Acquisitiond, and reconcile Questarr. Any failure restores the
  previous runtime and SecretStore state and returns a sanitized Admin error.
- Live validation: two successive password replacements through the deployed
  Admin mutation path succeeded. Each new credential authenticated WebUI/RPC,
  the previous credential returned HTTP 401, Acquisitiond RPC succeeded,
  Questarr reconciliation completed successfully, and all five torrent hashes
  remained present. Runtime refresh preserved the final credential and torrent
  state. No passwords or salted hashes were printed or logged.

## Mudos Admin information architecture and visual redesign

- Audited the previous `/`, `/providers`, `/provider/<id>`, `/test/<id>`, and
  `/services` surfaces. Overview and Services previously duplicated operational
  status and links, while provider forms exposed backend field names and secret
  reference concepts.
- Canonical editing now lives under `/integrations` and
  `/integration/<provider-id>`. `/providers` and `/provider/<id>` remain
  bookmark-compatible redirects. `/services` is operational-only; `/system`
  contains appliance information and boundaries. Credentials have one edit
  location per integration.
- Added a shared Mudos visual system with dark/translucent surfaces, spacing
  and typography tokens, responsive cards, setting rows, badges, notices,
  actions, focus states, and service links. Native keyboard/touch-friendly
  `<details>` help affordances provide accessible explanations without making
  JavaScript required.
- Replaced developer labels with user-facing language including `Server
  address`, `Username`, `Password`, and `Maximum connections`. Secret fields
  remain write-only with configured/unconfigured state and blank-preserves
  guidance. Technical identifiers are behind a Technical details disclosure.
- Save, Test connection, and Open Web UI actions now follow a consistent
  layout. Save failures use sanitized plain-language messages; implementation
  details remain in logs only. Service cards use standardized status language.
- Validation: legacy and canonical unauthenticated routes return the expected
  login redirect; Admin, Transmission, Acquisitiond, and Questarr services are
  active. Full suite: 535 passed, 6 subtests.

## Mudos Admin login regression repair

- Reproduction: authenticated-root requests reached `_dashboard()`, but a
  stale second `_page(title, body)` definition overrode the redesigned helper.
  `_dashboard()` passed `subtitle` and `active`, raising `TypeError` before
  headers were written; Firefox reported `NS_ERROR_NET_EMPTY_RESPONSE`.
- Removed the stale helper and added a top-level request boundary that logs
  method/path and exception type without form bodies or session data, then
  returns a complete sanitized HTTP 500 response.
- Reworked the unauthenticated page into the shared Mudos design: appliance
  identity, short explanation, labeled autofocus password input, keyboard-safe
  submit button, focus styling, and rendered 401 feedback. PBKDF2 handling,
  session cookie flags, CSRF/session ownership, and duration are unchanged.
- Live validation: unauthenticated `/` returns `303 /login`; `/login` returns
  the redesigned page; invalid credentials return rendered HTTP 401 rather
  than closing the connection. The valid-login handler contract is covered by
  tests for session creation, `Set-Cookie`, and redirect to `/`.
- Full suite: 541 passed, 6 subtests. Runtime deployed to
  `/opt/lulu/dev-current`.

## Mudos component/plugin modularisation checkpoint

- Added the unified Component Registry boundary. Built-in emulator providers
  remain built-in descriptors; Steam, Questarr, RomM, and Lutris remain genuine
  plugin deployment boundaries; Transmission and NZBGet are service components.
- Added directional dependency resolution, shared configuration/secret schema,
  safe setup metadata, service/provisioning declarations, and Store-card
  contributions. Questarr requires Lutris plus one downloader; reverse
  selection does not occur.
- Removed Steam/Questarr Store card definitions from StoreHome. The native shell
  consumes declarative component cards, while user bookmarks remain separate.
- SteamCMD now prefers the authoritative `steam/username` SecretStore slot and
  uses the existing secure `steam/password` path. Steam Guard remains ephemeral.
  No safe supported Steam GUI credential-injection mechanism was found, so GUI
  login remains interactive.
- Validation includes synthetic built-in and synthetic plugin components using
  the same registry, schema, dependency, secret, and Store-card APIs. No
  immutable release was modified; deployment is limited to the mutable
  development runtime.

## Downloads

- Commit: `423418f`
- Automated validation: PASS
- Runtime activated: PASS
- Physical/controller validation: pending
- Visual validation: pending
- Provider/live-service validation: pending
- Notes: physical controller/UI acceptance remains outstanding

## Downloads retirement and controller viewport

- Commit: `d11fb5c`
- Backend semantics: `ClearFailedJob` marks only a terminal `failed` job as
  `retired`; the job row, error diagnostics, attempt number, and
  `parent_job_id` retry linkage remain persisted. The operation is idempotent
  and rejects queued, active, paused, cancelling, completed, and cancelled
  jobs.
- UI/controller action: X/options is `Clear` for a selected failed job; A
  remains `Retry`. Active and queued rows continue to expose only their normal
  pause/resume/cancel actions.
- Automated validation: PASS; coverage includes retirement
  persistence, retry lineage preservation, idempotent clear, terminal-state
  rejection, filtered retired rows, ListView selection following, and scaled
  card viewport margins.
- Physical validation sequence: open Downloads with Y; create or select a
  failed job; press X and verify `Clear`, then verify the row disappears; press
  X again or revisit the surface and verify no error; retry a separate older
  failed attempt and verify clearing the older row leaves the newer attempt;
  select the first row, repeatedly press Down through the last row, verify each
  card follows into view without clipping, then press Up back to the first row;
  verify first and last selected cards are fully visible; press B and reopen
  Downloads to verify normal back behavior and sensible selection/scroll state.

## Downloads provider mutation lifecycle

- Commit: `6b9d086`
- Steam pause: unsupported. SteamCMD is a foreground process without a safe
  provider pause/resume command in the current executor, so Steam jobs now
  advertise `pause_supported=false` and do not expose a fake Pause action.
- RomM pause: supported through cancellation of the streaming task while its
  provider-owned staging file is preserved; resume starts a fresh stream from
  the staged offset.
- Mutation states: `pausing`, `paused`, `resuming`, and `cancelling` are
  explicit normalized job states. User cancellation reaches `cancelled` and
  marks the row retired without normalizing provider exit into `failed`.
- Physical validation sequence: start a Steam acquisition and verify no Pause
  action is offered; cancel it and verify `Cancelling…`, then disappearance
  without Retry. Start RomM, pause and verify `Pausing…` then `PAUSED`, cancel
  while paused and verify immediate `Cancelling…` followed by disappearance;
  verify Resume is unavailable after cancellation. During each pending state,
  navigate to another row and verify selection does not snap back. Verify the
  selected card remains inside both horizontal and vertical viewport bounds.

## Managed OSK / credential ownership

- Commits: `75d67c7`, `f5c33d8`, `fb23a9c`
- Automated validation: PASS; service/runtime validation passed
- Runtime activated: PASS
- Physical/controller validation: pending Steam password and controller acceptance
- Visual validation: pending
- Provider/live-service validation: pending
- Notes: do not claim physical acceptance before hands-on test

## Generic WebEngine managed-OSK bridge (2026-09-22)

- Recon: ordinary QML `TextField` entry reaches the existing credential broker
  because the QML field owns focus and the credential focus timer requests the
  managed keyboard. `WebEngineView` only exposed page/view focus in this shell;
  it did not expose the focused HTML element, its type/value, input-method
  hints, or a broker request. No `QInputMethodEvent`/virtual-keyboard request
  from WebEngine reached Mudos' broker. This was the exact failure boundary.
- Native Qt integration: not sufficient in the current Qt 6.11 QML WebEngine
  surface. The public `WebEngineView` has no reliable editable-element bridge
  for this shell, so the native path was not used.
- Fallback: `MudosBrowser.qml` polls `document.activeElement` generically for
  normal text-capable `input`, `password`, `textarea`, and contenteditable
  elements. It retains the focused DOM element, begins the existing Mudos
  credential request/managed OSK, and writes back through the native value
  setter plus `input`/`change` events. No site selectors or submitted values
  are inspected or logged.
- Password handling: password values are never read as an initial value;
  fresh entry uses the existing secret credential mode and masked QML editor.
  Mudos does not persist the value or place it in SecretStore. Browser profile
  persistence remains WebEngine's responsibility.
- Cancellation and ownership: the retained DOM target is locked while the
  asynchronous request is active, preventing focus changes from redirecting
  text. Cancel hides the shared OSK, clears the broker request and target, and
  restores WebEngine focus. Commit dispatches normal input/change events,
  optionally emits Enter semantics, clears transient state, and restores page
  focus. Guide/Downloads and browser quit paths remain global shell actions.
- Automated validation: full suite passed with 455 tests and 6 subtests;
  shell build succeeded; source/payload consistency and `git diff --check`
  passed. Coverage includes the plain/password/textarea fixture, existing
  plain-text value, cancellation, commit, password non-readback, repeated
  activation, focus restoration, Guide, Downloads, browser Quit, and ordinary
  QML credential behavior at the source-contract level.
- Physical validation is still pending and no credential was entered. Exact
  Questarr pass to perform with the controller is: Home → Questarr card →
  focus each Questarr field in turn → activate and enter the Prowlarr URL,
  administrator credentials, Transmission URL/label `questarr`, and NZBGet
  URL/category `questarr`; run each connection test; cancel one field and
  confirm its old value remains; submit one field and confirm page focus
  returns; then verify Guide, Downloads, and browser Quit. Do not record or
  report entered values. Leave import/move/copy/hardlink/delete disabled.

## Shared OSK Enter completion (2026-09-22)

- Generalized the completion contract at the managed credential overlay and
  broker boundary. Single-line requests now consume OSK Enter/Return once,
  submit the current value, retire the request, hide the shared OSK, and then
  let the requester handle the submitted result. This applies equally to
  browser fields, Add New Store, Steam password/Guard requests, provider
  settings, and other generic credential callers.
- Added an explicit request `multiline` flag. Multiline requests use the
  shared multiline editor so Enter remains a newline; submission remains a
  separate completion action. Password requests use the same lifecycle without
  exposing their value in public request state or logs.
- Added single-flight protection and explicit event consumption so repeated
  Enter cannot submit twice and no stale Enter/A is replayed after ownership
  restoration. Cancellation remains a distinct terminal path and preserves
  the original requester value.
- Automated validation: shared broker, overlay, browser fixture, password,
  cancellation, multiline, repeated submission, and ownership-contract tests
  pass. Physical Questarr validation is pending; use the previously documented
  controller-only sequence and do not record credentials.

## Shared OSK startup regression and correction (2026-09-22)

- Immediately after the shared-lifecycle deployment, the display showed the
  underlying VT with a blinking cursor. No restart or state clearing was done
  during diagnosis. `lulu-session@2` and `consoled` were alive, the broker
  reported `{"status":"idle"}`, and no text request or stale OSK ownership
  existed. The shell child and Gamescope presentation had exited, while the
  OSK then exited because its X connection disappeared.
- First concrete error: `QQmlApplicationEngine failed to load component` at
  `/opt/lulu/dev-current/ui/ConsoleShell.qml:1038`: `TextArea is not a type`.
  Sessiond subsequently logged that the Gamescope window was not found. The
  black screen was therefore a shell startup failure, not a stuck keyboard,
  WebEngine surface, or display ownership loss.
- Root cause: the new shared multiline editor added `TextArea` to
  `ConsoleShell.qml` without importing `QtQuick.Controls`. The broker/API
  changes and idle state were not the cause.
- Narrow correction: added the missing `QtQuick.Controls` import and an idle
  startup regression covering hidden overlay/default broker state and safe
  multiline deserialization. No immutable release was changed.

## Trusted Questarr web credentials (2026-09-22)

- The existing WebEngine profile is non-off-the-record by construction: stable
  storage name `mudos-browser`, persistent storage below
  `QStandardPaths::AppDataLocation/browser/storage`, and
  `ForcePersistentCookies`. The live storage directory was empty before this
  feature because no authenticated Questarr browser session had yet been
  created; no token was inspected. A physical login/Quit/reopen/restart
  persistence pass remains required.
- Added the generic trusted profile model. Questarr is authorised only as the
  built-in `questarr` Store descriptor at exact origin
  `http://127.0.0.1:5000`; custom Stores and navigation to other origins do
  not inherit access. SecretStore references are `web/questarr/username` and
  `web/questarr/password`, separate from Prowlarr, Transmission, and NZBGet
  integration credentials.
- The browser adapter detects ordinary username/password controls, requests
  credentials only through the trusted Mudos backend, and autofills without
  invoking the OSK or pressing Login. It captures a candidate only after a
  submitted login form leaves the login state; failed login forms do not
  replace the last known-good values. Replacement and clear are backend
  operations and never expose stored passwords in public state or logs.
- Exact physical validation sequence: launch Questarr from the built-in Home
  card; log in once with the controller; confirm the authenticated page, Quit
  browser, reopen Questarr, and confirm it bypasses login without OSK; restart
  the graphical Mudos session and repeat. Then clear the Questarr web
  credential profile through the backend operation, reopen Questarr, verify
  the login form autofills username/password but does not activate Login,
  activate Login with the controller, and verify a failed login leaves the
  previous known-good credential unchanged. Navigate to an external link and
  to a custom Store pointing at the same URL and verify no autofill occurs.
  Do not record usernames, passwords, tokens, or page credentials.

## Failed downloads / Retry

- Commit: `769fa52`
- Automated validation: PASS; D-Bus RomM retry validated
- Runtime activated: PASS
- Physical/controller validation: pending
- Visual validation: pending
- Provider/live-service validation: live Steam retry validation pending
- Notes: controller retry and live Steam retry remain outstanding

## SteamCMD authentication persistence diagnostics

- Commit: `197b7383`
- Automated validation: PASS; instrumentation active
- Runtime activated: PASS
- Physical/controller validation: not applicable
- Visual validation: not applicable
- Provider/live-service validation: awaiting natural recurrence of unexpected authentication request
- Notes: no test login was performed

## IGDB metadata enrichment

- Commit: `6721edf`
- Automated validation: PASS; 362-test suite passed
- Runtime activated: PASS; mutable development runtime refreshed
- Physical/controller validation: not applicable
- Visual validation: not applicable
- Provider/live-service validation: pending live IGDB credentials and sample verification
- Notes: live IGDB credentials and sample verification remain pending

## ProtonDB metadata enrichment

- Commit: `6721edf`
- Automated validation: PASS; 362-test suite passed
- Runtime activated: PASS; mutable development runtime refreshed
- Physical/controller validation: not applicable
- Visual validation: pending future metadata presentation
- Provider/live-service validation: PASS; unauthenticated endpoint sample AppID `220` returned tier `platinum`, confidence `strong`, score `0.91`
- Notes: AppID-only scope; no ROM/title matching. Catalogue integration remains pending live configured run.

## Provider-owned uninstall flow

- Commits: `4db1c41`, `939c341`, `b4bd2fb`, `7198d52`
- Automated validation: PASS; 368 tests passed
- Local disposable-ROM backend validation: PASS; temporary single-file and dedicated-directory fixtures were removed through `JobOperation.REMOVE`; outside-root, root/platform-root, symlink escape, neighbor preservation, and missing-path cases passed
- RomM provenance preservation: PASS by provider-boundary tests/design; removal resolves linked local content and never calls RomM mutation APIs
- Steam provider automated validation: PASS; provider-native `app_uninstall` command construction, canonical manifest ownership check, conflict handling, and no-filesystem-fallback tests passed
- Physical Game Options validation: pending
- Live Steam uninstall/reinstall: PASS at manifest/provider/catalogue level using AppID `263980` (Out There Somewhere). Remove job `job-a9d5047a63ac4f33b89ca6334a62ca74` completed; manifest disappeared and the row became available. Reinstall job `job-264e8703ef5a40cf84e5e5acdc2fbc90` completed; manifest returned and `CanUninstall` reported supported/installed.
- Historical caveat: the pre-`60b6523` acquisition path placed the payload at the configured force-install root while the provider treated the manifest as authoritative; corrected and revalidated below.

## Steam canonical install placement and update semantics

- Commits: `60b6523`, `24d69b1`, `46f1295`, `1da2ba0`
- Root cause: SteamCMD `+force_install_dir` is the application payload directory; passing the Mudos library root placed payload files directly under the library while still producing a manifest.
- Fix: Steam acquisition uses a provider-owned per-job staging directory, validates the Steam-generated AppID/`installdir`, then places only that staged payload under `steamapps/common/<installdir>` and moves the validated manifest into `steamapps`.
- Fresh/update split: a valid existing manifest plus canonical payload selects direct SteamCMD update/validation against that payload; otherwise the provider uses job-attributable staging and atomic same-filesystem promotion.
- Installed-state invariant: manifests with missing, escaping, or invalid `steamapps/common/<installdir>` payloads are no longer reported as installed.
- Existing inventory: AppID `15700` currently has a manifest without its canonical payload directory. Several legacy payload files/directories remain directly under the library root and are mixed (including `steam_appid.txt` for `263980` and a Waveform install script), so no heuristic relocation was performed.
- Live validation: AppID `263980` reinstalled through normal Mudos acquisition job `job-650bd7d8296541248e7fba1c8637bffd`; manifest `installdir=outtheresomewhere`, payload exists at `steamapps/common/outtheresomewhere`, catalogue/provider report installed, and Mudos launch reached the `game` lifecycle using Proton.
- Update-path validation: automated run coverage confirms an existing canonical payload is passed directly as `+force_install_dir`; no staging/fresh-copy promotion is used.
- Live update cycle: not repeated after the latest split because SteamCMD cached authentication expired and no managed Steam password was configured; the current installed title remains canonical and available for a future authenticated update check.
- Authentication observation: cached SteamCMD authentication was reused during the corrected reinstall. A later uninstall attempt prompted for a password after cached auth expired; the managed credential boundary remained active, but no password was configured/submitted and the job timed out without mutation.
- Physical/UI validation: pending.
## Standard gamepad replacement work — 2026-09-21

- Historical Eden profile investigation paused. The implementation now treats
  every InputPlumber `gamepad` source as a `standard_gamepad`; no vendor,
  product, name, or GUID allowlist remains in the Mudos source path.
- Current fixture: kernel name `Microsoft Xbox Series S|X Controller`, USB
  `045e:0b12`, xpad, `/dev/input/js1` and `/dev/input/event8`, USB path
  `usb-0000:00:10.0-2/input0`, serial `3039373030353434383237313334`.
  InputPlumber exposes source objects `.../source/js1` and `.../source/event8`
  with the same name and `IdVendor=045e`, `IdProduct=0b12`.
- The SDL GUID/index could not be captured while the SDL target was absent from
  the restarted session during this pass; the live launch path now queries
  SDL3 at launch and refuses to substitute a historical GUID. Mudos session
  inventory was empty in that state, so Player 1 and provider physical launch
  validation remain pending.
- Added normalized per-controller SDL name/GUID/index, capability counts,
  connection type, and standard-gamepad eligibility. Eden, Dolphin, RetroArch,
  and PCSX2 consume current per-player identity; Nintendo face mapping remains
  renderer policy. InputPlumber source matching is capability/type based.
- Removed the obsolete Xbox 360 RetroArch udev profile. Synthetic coverage
  covers unknown, Xbox-like, PlayStation-like, generic, mixed-manufacturer,
  differing/same GUID, and replacement identities.

Physical sequence still required after the session exposes the target:
Navigate Mudos; launch RetroArch, exit/relaunch, launch PCSX2, Dolphin, and
Eden/Mario Kart; verify shared fixture and Eden Nintendo labels; disconnect and
reconnect; relaunch and verify no stale Xbox 360 identity. A graphical-session
restart may be required for InputPlumber to publish a newly created target.
## Controller inventory regression investigation and correction — 2026-09-21

- Preserved bad-state evidence before recovery in
  temporary live-regression capture (original local path omitted).
- Kernel and udev saw the USB Series controller as `045e:0b12`,
  `Microsoft Xbox Series S|X Controller`, `/dev/input/event8` and `js1`, with
  12 keys and 8 absolute-axis capabilities reported by InputPlumber.
- Native Mudos navigation was independent and healthy: shell logs recorded
  `SDL gamepad scan count=1` and `SDL gamepad opened Xbox Series X Controller`.
  This explains why navigation worked while the normalized model was empty.
- InputPlumber exposed the physical source (`source/event8`) but
  `GamepadOrder=0` and no composite. The active `/etc/inputplumber` profile
  still contained the historical `045e:02a1` receiver filter; the generic
  profile existed only under `/opt/lulu/dev-current` and was not read by the
  service.
- Sessiond state consequently contained no controllers, no Player 1, and no
  navigation controller. Settings and the status strip both consume this same
  session model, so both correctly displayed zero despite native navigation.
- Non-Steam rejection was exact and shared: `RuntimeError: Mudos has no
  assigned InputPlumber gamepad slots` from `_mudos_provider_device_indices()`.
  Steam bypassed this path and submitted a Steam contextual launch instead.
- Correction: when no InputPlumber composite exists, inventory now exposes a
  capability-verified physical joystick source as a provisional logical
  standard gamepad at runtime slot 0. Composite initialization is skipped for
  that provisional entry. This reunifies inventory, assignment, Settings,
  status, and provider-index lookup without an identity allowlist or emulator
  configuration change.
- After the correction, live session state reports one connected
  `standard_gamepad`, Player 1, navigation controller
  `/org/shadowblip/InputPlumber/CompositeDevice0`, and source identity
  `source:event8`. Independent launch-time SDL inspection reports index `0`,
  name `Xbox Series X Controller`, GUID
  `0300f5a35e040000120b00000b050000`; `_mudos_provider_device_indices()` now
  returns `{1: 0}` and live identity propagation returns those SDL fields.
- Full suite after the correction: 410 passed. No emulator configuration was
  changed or physically launched during this regression recovery pass.

## InputPlumber provisioning and provider-boundary correction — 2026-09-21

- Before this pass, the recovered live state had no fresh RetroArch/Eden
  exception in the journal; the only recorded launch exception was the
  earlier shared `RuntimeError: Mudos has no assigned InputPlumber gamepad
  slots`. The recovered resolver already returned `{1: 0}`, so that blocker
  was confirmed gone before editing the provider path.
- The remaining architectural defect was `_mudos_provider_device_indices()`
  resolving `CompositeDeviceN` slots and matching those paths against session
  state. It now resolves connected assigned `StandardGamepad` entries from
  sessiond, enriches them with live SDL index/GUID/name, and returns SDL
  indices. Composite-backed and provisional raw-source controllers therefore
  use the same provider contract.
- `scripts/dev-runtime.sh refresh` now installs the current system-level
  InputPlumber definition before restarting InputPlumber. `/etc` can no longer
  silently retain the old receiver-only profile during a dev refresh.
- InputPlumber v0.79's schema has no capability predicate: `group: gamepad`
  controls event mapping, while `evdev` matching supports handler/name/phys
  and VID/PID fields. A bare `handler: event*` rule was therefore unsafe and
  created composites for unrelated event devices. The new provisioning helper
  selects event devices by Linux-advertised gamepad/joystick buttons and
  absolute axes, then writes only their physical paths plus `handler: event*`.
  This is manufacturer/GUID-independent; hotplug/replacement remains covered
  by the provisional fallback until the dynamic definition is regenerated.
- Live provisioning now produces one real InputPlumber composite for the
  Series pad from `/dev/input/event8`; Mudos session state identifies its
  persistent source as `Microsoft_Controller_3039373030353434383237313334`.
  Provider resolution returns `{1: 0}` and live SDL metadata is read from the
  active target at launch time rather than from a hardcoded Xbox identity.

## Cold-boot/hotplug regression investigation — 2026-09-21

- Cold-boot evidence was preserved before recovery in
  temporary cold-boot regression capture (original local path omitted).
- Boot started at `16:46:29`. There was no USB controller, no
  `/dev/input/event8` or `js1`, no SDL physical gamepad, and no InputPlumber
  composite (`GamepadOrder=0`). The generated profile existed but was stale:
  `/etc/inputplumber/devices.d/lulu-composite.yaml` was last modified at
  `16:01:38` and referenced the previous USB physical path. No generator
  service or udev hotplug rule existed.
- The provisional fallback incorrectly selected Mudos's virtual
  `gamepad-osk` (`event6`) because it advertised joystick-like capabilities.
  After the correction and refresh, cold state is correctly empty.
- InputPlumber started at `16:46:42`, sessiond/consoled at `16:46:43`, and OSK
  at `16:46:44`. Sessiond only watched `GamepadOrder`; it could reconcile a
  composite that appeared, but nothing regenerated or activated a profile for
  a controller appearing later.
- Added a udev-driven `lulu-inputplumber-hotplug.service`. It regenerates
  capability-selected per-event profiles and invokes InputPlumber's
  `CreateCompositeDevice` D-Bus method for new devices without restarting
  Mudos or sessiond. Profiles require a physical Linux input path and exclude
  virtual OSK devices. InputPlumber's existing D-Bus event monitor then
  promotes the real composite and updates normalized inventory.
- Automated validation after this change: `PYTHONPATH=src pytest -q` reports
  412 passed. Physical add/remove and cold-boot-with-controller sequences
  remain pending because the controller was not physically present after this
  reboot capture; no unplug/replug was performed during evidence collection.

## Cold-boot evidence correction: kernel enumeration failure — 2026-09-21

- The controller was physically connected and powered throughout reboot. The
  failure was not caused by connecting it after Mudos startup.
- Boot journal evidence shows USB port `6-2` repeatedly failed before any
  input device was created: `device descriptor read/64, error -71`,
  `Device not responding to setup address`, and `unable to enumerate USB
  device` at `16:46:41`, followed by retries at `16:47:01`, `16:47:16`, and
  `16:57:43`.
- No `045e:0b12`, xpad attach, `input: Microsoft Xbox...`, `/dev/input/event8`,
  or `js1` event occurred during boot. Consequently SDL, udev input, and
  InputPlumber had no physical controller to discover. InputPlumber started at
  `16:46:42`, after the kernel enumeration failure; sessiond started at
  `16:46:43` and correctly saw no real composite.
- The stale generated profile was therefore downstream evidence, not the
  primary cause. The exact failure boundary was kernel USB enumeration before
  dynamic profile generation. The later hotplug/profile mechanism remains
  necessary for successful enumeration and later reconnects, but cannot repair
  a device that the USB host never exposes to udev.

## Controlled cold boot with receiver removed — 2026-09-21

- The broken Xbox 360 receiver was disconnected before reboot; the Series
  controller remained the only intended gamepad fixture and was connected and
  powered throughout boot.
- Boot began at `17:04:46`. USB port `6-2` again failed descriptor/address
  negotiation (`error -71`), attempted power cycles, and ended with `unable to
  enumerate USB device` at `16:04:59` system journal time. No receiver,
  `045e:0b12`, Series controller identity, xpad attach, input event, or
  joystick was created.
- InputPlumber started at `17:05:00`; it had only non-gamepad sources and
  `GamepadOrder=0`. Sessiond started at `17:05:01` and reported an empty
  controller inventory/navigation identity. SDL reported scan count zero.
- The generated profile was valid and empty (modified `17:04:46`); InputPlumber
  emitted no composite parse warning. The hotplug unit remained inactive because
  the kernel never produced a qualifying input-device event.
- Controlled evidence is preserved at
  temporary controlled-boot capture (original local path omitted).
- This rules out the broken receiver as the contaminating source and confirms
  the current cold-boot failure is upstream of dynamic provisioning,
  InputPlumber, sessiond, status, settings, navigation, and emulator launch.

## Development Sunshine host — 2026-09-21

- Installed the native CachyOS `sunshine` package (`2026.724.5619-1`; the
  installed binary reports Sunshine `2026.516.143833`). Binary:
  `/usr/bin/sunshine`. Lulu uses the mutable development unit
  `lulu-sunshine-dev.service`, separate from the package unit, so Sunshine
  cannot affect the immutable runtime or Mudos lifecycle.
- `scripts/dev-runtime.sh` installs the configuration into
  `/home/lulu/.config/sunshine/` and enables the user unit under
  `default.target`. It captures the existing session with KMS and exposes one
  `Mudos Desktop` stream; it does not create a second desktop/session.
- KMS works against the existing `card1-DP-1` display. The explicit
  `output_name` was removed because this build mapped `DP-1` to an invalid
  monitor identifier; automatic selection reports `Found monitor for DRM
  screencasting`.
- Encoding is explicitly `software`, `ultrafast`, `zerolatency`; HEVC and AV1
  advertisement are disabled; audio is disabled. Sunshine reports
  `Found H.264 encoder: libx264 [software]`. Target Moonlight settings are
  1280x720, 30 FPS, H.264, and 5–8 Mbps.
- Input is enabled with `gamepad = generic`. `/dev/uinput` is accessible to
  `lulu` through a udev ACL; Sunshine has package-provided
  `cap_sys_admin,cap_sys_nice`. No Sunshine-specific Mudos/controller code
  was added. Remote virtual-controller identity and coexistence with a
  physical controller remain pending interactive Moonlight validation.
- LAN policy: Sunshine binds to `192.168.0.245`, uses IPv4, has `upnp =
  disabled`, and exposes the HTTPS web UI at `https://192.168.0.245:47990`.
  No router forwarding or WAN/VPN configuration was added.
- Service validation: `lulu-sunshine-dev.service` is active and independent;
  its failure cannot prevent Mudos boot. Idle Sunshine usage was approximately
  0.25–0.38 seconds CPU over the observed startup interval. Streaming CPU,
  encode latency, frame drops, and emulator impact require Moonlight and are
  not claimed as passed.

## Sunshine Web UI LAN timeout repair — 2026-09-21

- Sunshine was listening exactly on `192.168.0.245:47990` TCP, not
  `127.0.0.1` or `0.0.0.0`. The active config remains IPv4, bind address
  `192.168.0.245`, base port `47989`, and `origin_web_ui_allowed = lan`.
- Local tests distinguished the failure boundary: `curl` to
  `https://127.0.0.1:47990/` was correctly refused because Sunshine is
  intentionally LAN-bound; `curl` to `https://192.168.0.245:47990/` completed
  TLS and returned `HTTP/1.1 307` redirecting to `/welcome`.
- `192.168.0.245/24` is currently assigned to `wlan0`, with route
  `192.168.0.0/24 dev wlan0` and gateway `192.168.0.1`.
- UFW was the active firewall implementation. `firewalld` and `nftables`
  services were inactive; UFW had default incoming DROP and no Sunshine rule.
  The existing rules allowed only SSH and an unrelated `8080/tcp` rule on
  `enp4s0`, so inbound TCP `47990` from the LAN was dropped before the fix.
- Added LAN-scoped UFW rules on `wlan0`, source `192.168.0.0/24`: TCP
  `47984:47990` and `48010`; UDP `47998:48000`, `48002`, and `48010`. UPnP,
  WAN access, and router forwarding remain disabled.
- A bounded tcpdump on `wlan0` captured zero packets because no Mac retry
  occurred during its 30-second window. This does not change the firewall
  diagnosis: Sunshine accepted the local LAN-address request, and the
  pre-fix default-DROP policy had no rule for the configured Web UI port.
- `lulu-sunshine-dev.service` remains active. Retry:
  `https://192.168.0.245:47990/`.

## Sunshine LAN CSRF origin provisioning — 2026-09-21

- Added the explicit managed configuration
  `csrf_allowed_origins = https://192.168.0.245:47990` while preserving
  `origin_web_ui_allowed = lan`; no wildcard or global CSRF relaxation was
  used.
- `scripts/dev-runtime.sh` now installs this configuration and runs the
  repository-owned `scripts/configure-dev-sunshine-firewall.sh`. The script
  idempotently provisions the LAN-scoped Sunshine TCP/UDP UFW rules on
  `wlan0`, so the firewall policy is reproducible rather than a one-off
  command.
- After the development refresh and explicit
  `lulu-sunshine-dev.service` restart, Sunshine logged the CSRF origin as
  `[redacted]`, retained the LAN origin policy, and remained active with KMS
  and software H.264 capture. Credentials were not logged.
- The Mac-side login-creation click was not executable from this host; the
  exact configuration load and service restart were verified locally. Retry
  the Web UI from the Mac at `https://192.168.0.245:47990/`; the configured
  origin now matches the browser origin for state-changing requests.
- Mudos browser/store POC: installed CachyOS `qt6-webengine` 6.11.2-1 and its
  Qt 6.11.2 dependencies. Added the persistent `mudos-browser` WebEngine
  profile, Steam and custom Stores collection, QSettings bookmark persistence,
  managed OSK URL entry, and global-control-preserving browser surface. Static
  validation: shell build succeeds and full suite is 447 passed, 6 subtests.
  Physical Steam/WebEngine rendering and OSK validation remain to be completed
  on the BC-250 session after this development-runtime refresh.
 - Development runtime refresh completed at `/opt/lulu/dev-current`; the
  existing single shell process starts successfully with WebEngine linked and
  `lulu-session@2.service` is active. The host reports the known non-fatal
  Radeon VA-API initialization warning. Interactive Steam navigation/OSK
   acceptance still requires a physical controller/display pass.
- Browser lifecycle validation through the live console bridge: browser
  delegated-surface state is exposed to Guide as `browser-quit`; clearing it
  removes the delegated surface and restores the prior input mode. The session
  authority now permits compatibility mode for the browser delegated surface
  after that surface is registered. Runtime services were restarted and are
  active. Physical Home-card and Steam page interaction remains the next
  controller/display pass.

## Questarr integration reconnaissance and initial provisioning

- Upstream Questarr v1.4.2 was inspected from its release source and current
  release metadata. It supports Prowlarr synchronization, Torznab/Newznab,
  Transmission, NZBGet, downloader labels/categories, authenticated test and
  submission APIs, `/api/health`, `/api/ready`, and SQLite persistence.
- Questarr is provisioned as pinned rootful Podman image service
  `lulu-questarr.service`, with persistent data at
  `/var/lib/lulu-questarr/data` and LAN TCP 5000 firewall scope. Acquisition
  paths are currently mounted read-only; automatic import/delete is not enabled.
- Live checks: service active; `/api/health` returned HTTP 200 and
  `{"status":"ok"}`; `/api/auth/status` reports first-run setup is pending.
  `/api/ready` correctly requires authentication.
- Prowlarr remains blocked: no local Prowlarr service/listener or endpoint was
  discoverable. The supplied API-key file was not copied, printed, logged, or
  committed.

## Questarr Prowlarr and loopback correction

- Corrected the fixed Questarr Store card to use the local browser URL
  `http://127.0.0.1:5000/`. The admin Open UI link and normal LAN URL remain
  `http://mudos.local:5000/`; custom Store bookmarks were not changed.
- From the actual Questarr container, authenticated Prowlarr probes succeeded:
  `/api/v1/system/status` returned HTTP 200 and version `2.5.2.5491`; the
  indexer endpoint returned six indexers, four torrent and two usenet.
- Questarr first-run setup is still pending (`/api/auth/status` reports no
  users). Questarr's supported Prowlarr sync endpoint requires JWT auth, so no
  sync or downloader configuration was attempted before account creation.
  The supplied key was never printed, logged, copied, or committed.

## Questarr credential migration and downloader reachability

- Migrated the temporary Prowlarr handoff into the Mudos configuration
  boundary: URL in `/home/lulu/.config/lulu/provider-services.toml`, key in
  SecretStore reference `prowlarr/api-key`. The key is not present in the TOML
  or service journal; the RTF remains only as a removable handoff artifact.
- From the actual host-networked Questarr container, authenticated probes
  succeeded against Transmission at `127.0.0.1:9091/transmission/rpc`
  (Transmission 4.1.3) and NZBGet at `127.0.0.1:6789/xmlrpc`.
- Questarr API configuration remains pending because the administrator
  credential/session is not available to the automation boundary. No SQLite
  bypass, downloader duplicate, or non-destructive import change was made.

## Questarr autofill and service reconciliation follow-up

- SecretStore inspection: `web/questarr/username` and
  `web/questarr/password` are currently **unconfigured**. Values were not
  read, printed, logged, or included in this record; therefore live autofill
  cannot yet occur.
- Autofill/capture repair: the generic browser now captures React SPA login
  submissions through document-level submit and submit-control click hooks,
  retains the candidate until the visible login form leaves the DOM, and
  retries trusted filling if React rerenders the form. Filling uses the native
  input value setter plus bubbling/composed `input` and `change` events. The
  exact trusted profile/origin gate remains unchanged and Login is not pressed
  automatically.
- Installed Questarr v1.4.2 route inspection found `POST /api/auth/login`,
  `GET/PATCH/POST /api/downloaders`, `POST /api/downloaders/:id/test`,
  `POST /api/indexers/prowlarr/sync`, and `GET /api/indexers`. The new
  `lulu-questarr-reconcile` oneshot authenticates with a backend-only JWT,
  never logs or publishes it, and does not edit SQLite.
- Reconciliation ownership uses a stable JSON marker in Questarr's supported
  downloader `settings` field. It creates or updates only marked Mudos
  entries, leaves unmarked equivalent/manual entries alone, tests each managed
  connection, and uses Transmission label/NZBGet category `questarr`.
  Prowlarr sync is optional, non-destructive on outage, and dynamically counts
  returned indexers by protocol.
- Live deployment: PASS; the oneshot is installed/enabled under the mutable
  `/opt/lulu/dev-current` runtime and safely returned `status=unconfigured`
  without making API calls while web credentials were absent. Relevant admin
  provider changes trigger the optional oneshot. Physical authenticated
  capture, API reconciliation, restart idempotency, and indexer counts remain
  pending until the Questarr web account is established. No secret was
  recorded.

## Managed OSK duplicate-input investigation

- Before the fix, COMPAT mapped the same controller edge to both a synthetic
  `keyboard:*` event and a semantic `dbus: ui_*` event. The fullscreen OSK
  consumed the latter through `mudos-osk-bridge` while also receiving the
  former, producing two logical actions from one physical press. This was an
  input-path duplication, not press/release activation or a second controller
  representation. The live inventory had one navigation composite backed by
  the physical controller; the OSK bridge's private uinput device was its
  output, not a second source.
- Follow-up trace: the D-Bus-only profile was loaded and the bridge/private
  gamepad process remained alive, but it did not produce usable OSK navigation.
  The managed OSK implementation is natively keyboard-driven; the D-Bus-only
  actions stopped at the bridge boundary rather than becoming OSK key events.
- Fix: while the managed OSK is visible, the bridge now loads the repository-
  owned `config/inputplumber/profiles/osk.yaml`, which emits only keyboard
  actions (arrows, Enter, Escape, Backspace, Tab, and page controls) and no
  D-Bus or mouse events. On close, it restores the profile captured at the
  ownership transition—not a stale startup profile—and the exact prior
  `InterceptMode`. No debounce timer was added.
- Live deployment: PASS; `/opt/lulu/dev-current` contains the OSK profile and
  bridge. A browser-COMPAT show/hide boundary check observed `osk.yaml` with
  `InterceptMode=2` while visible, then the exact COMPAT profile with
  `InterceptMode=1` after close. Services remained active.
- Automated validation: PASS; focused bridge/boundary tests pass (54 tests),
  and the shell build completed during the development-runtime refresh.
- Physical validation remains pending: repeat single taps, holds, cancel,
  submit, native Add New Store, provider prompts, browser/Questarr, and local
  versus Sunshine input. Do not record entered credentials.

## Questarr post-capture reconciliation validation

- Reconciler execution-context check: as `lulu`, with the deployed service
  environment and `/home/lulu` SecretStore context, both Questarr web
  credential entries report configured. No values were read into the log.
- Runs at 11:50:57, 11:53:13, 11:54:40, and 11:55:55 reported
  `unconfigured`. The manual production run at 12:00:43 reported `status=ok`,
  Transmission/NZBGet created, Prowlarr synced, and six indexers (four
  torrent, two usenet). Authentication through Questarr's normal login API
  succeeded.
- Sanitized Questarr state: exactly two Mudos-managed downloaders,
  `Mudos Transmission` and `Mudos NZBGet`; both connection tests passed.
  `GET /api/indexers` reported six total: four torrent and two usenet. No
  unrelated downloader was modified.
- Immediate second reconciliation created no records and retained the same
  six indexers. After restarting Questarr, reconciliation again passed both
  downloader tests and retained the same indexer counts. No credentials or
  JWTs were recorded.
- Root cause: trusted browser credential capture completed the SecretStore
  transaction but had no lifecycle hook to start the reconciler. The fix is at
  the credential boundary: after a successful Questarr save, consoled
  asynchronously starts `lulu-questarr-reconcile.service`; the UI does not
  wait for network reconciliation. Replacement credentials use the same path.
  A narrow polkit rule permits only `lulu` to start this exact unit.
- Automated validation: PASS; full suite reports 480 passed, 6 subtests, and
  the shell build completed during deployment to `/opt/lulu/dev-current`.

## Managed text-entry presentation and OSK geometry

- Added explicit request presentation metadata: `attached` keeps the
  requester-owned visible field/page in place, while `prompted` shows the
  existing Mudos text prompt. Both use the same broker request ID, buffer,
  password handling, submit/cancel state, and exclusive keyboard ownership.
- WebEngine editable fields, Add New Store, and native settings/plugin editor
  requests use `attached`; SteamCMD and other backend requests retain the
  conservative `prompted` default. Presentation is part of each request, not
  inferred from an application name.
- Attached mode uses a transparent, non-painted QML lifecycle input to receive
  authoritative keyboard events; it does not paint a duplicate field or
  backdrop. Prompted mode retains the masked field and hints. Multiline Enter
  remains insertion; single-line Enter submits and Escape cancels through the
  shared request functions.
- The exclusive InputPlumber keyboard-only profile was not changed. The A/B
  regression was in the presentation event path: the old prompt depended on
  focus/overlay handling that no longer consumed the profile's Enter/Escape
  events. The prompt and attached lifecycle now consume those canonical
  keyboard events directly; no parallel D-Bus/controller output was restored.
- OSK geometry is configured from the deployed runtime at native window size,
  bottom position, 40% viewport width, and an 18-pixel edge margin. The prior
  runtime log showed a 960x412 keyboard at 50% on a 1920x1080 monitor; the
  smaller final layout with `unit_size=0`/native font sizing avoids enlarging a
  low-resolution surface and does not use image filtering or a scale transform.
- Deployment check: `/opt/lulu/dev-current` is active and OSK/shell services
  are active. Automated tests pass. Physical Questarr attached-field,
  native-field, and prompted Steam/headless A/B validation remains to be
  recorded after the next manual controller test; no physical result is
  claimed here.

## Questarr autofill, text-hint, and download permission follow-up

- Autofill root cause: `MudosBrowser.qml` called `u.focus()` after assigning
  trusted credentials. The editable polling bridge treated any newly focused
  editable element as user text-entry intent, so username focus created a
  managed request and opened the OSK. Autofill still uses the native value
  setter and bubbling `input`/`change` events, but no longer focuses the field.
- The editable bridge now requires an explicit activation marker from
  pointer/click or keyboard activation, or from the controller activation
  path. Programmatic focus, autofill, controlled React rerenders, and restored
  browser focus do not create a request. The marker is cleared after use and
  during browser/request cleanup.
- Submit/Cancel visibility was coupled to the active credential overlay but
  the hint itself had no prompted-presentation visibility gate. It could remain
  painted while the browser path was active. The hint now requires an active
  `prompted` request; attached requests paint no standalone text controls.
- Download evidence: Questarr `POST /api/downloads` returned success and
  handed the torrent to Mudos Transmission with the `questarr` label. The
  subsequent failure came from Transmission's own log: it could not create
  `/home/lulu/Games/.acquisition/torrents/incomplete/<job>` with `Permission
  denied (13)`. Questarr then reported the downloader-aborted error. This was
  downloader storage access, not Questarr staging or post-processing/import.
- Before correction, Transmission ran as UID 957/GID 956 with no `lulu`
  supplementary group; the acquisition parent is `lulu:lulu` mode 2770.
  Questarr's torrent/usenet mounts remain read-only. The narrow correction adds
  only `lulu-transmission` membership in the `lulu` group, preserving daemon
  ownership of its provider root and avoiding broad Games-tree write access.
  A live UID-boundary check can now create/remove a probe below the incomplete
  directory, and no new Transmission permission errors appeared after restart.
- Existing Questarr submissions were accepted and Transmission jobs carried
  the `questarr` label; a clean post-fix physical Questarr acquisition result
  and corresponding Mudos Downloads origin record remain pending because no new
  physical selection was performed in this validation pass.
- Automated validation: full suite **488 passed, 6 subtests**; development
  runtime deployment and shell build completed successfully.

## WebEngine explicit text-entry activation follow-up

- Regression diagnosis: the tightened editable bridge only emitted a request
  from its polling timer after seeing an activation marker. Genuine clicks
  could occur before that hook was installed, while Guide+X still used the
  native global `ShowKeyboard` path and never queried the browser's focused
  DOM target. Programmatic focus remained correctly excluded.
- Added `requestTextEntryForFocusedElement()`, which inspects only the current
  generic editable DOM target and feeds the existing attached request lifecycle.
  The bridge accepts trusted pointer/click/keyboard activation only; synthetic
  DOM events are rejected with `isTrusted`. Controller A continues to use the
  direct browser activation path, so it does not require a second press.
- Guide+X now increments a native `textEntryShortcutSerial`. QML consumes that
  serial while the browser is visible and invokes the focused-target query;
  non-editable targets produce no request and hide any transient global OSK.
  Repeated serials and active-request guards prevent duplicate requests.
  Normal Guide handling and the exclusive OSK profile were preserved.
- Attached presentation remains page-visible with no standalone prompt or
  persistent Submit/Cancel hints. Automated coverage now reports **492
  passed, 6 subtests** and deployment completed to `/opt/lulu/dev-current`.
  Physical Questarr and local-fixture click/A/Guide+X validation remains to be
  recorded; no physical result is claimed in this pass.

## Switch content reconnaissance

- Live Questarr v1.4.2 evidence corrected the earlier architecture: Questarr
  is actively acquiring Switch base content, updates, and DLC-bearing releases.
  The authenticated parent game observed was **Super Smash Bros. Ultimate**;
  Questarr game ID and all individual download records were retained without
  logging credentials or tokens.
- Questarr exposes one parent `gameId` for the records and one downloader job
  per selected result.  The observed records include separate torrent jobs
  titled `NSP + Update + DLCs`, a completed `NSP + Update + DLCs` job, and
  separate Usenet attempts for the base and update release names.  The
  observed `downloadType` is the downloader protocol (`torrent` or `usenet`),
  not the content role.  Questarr therefore supplies authoritative parent
  identity and release/download identity, but this fixture does not expose a
  separate role field on each download record.  Composite release metadata is
  intentionally treated as ambiguous by Mudos rather than silently becoming
  a base component.
- The normalized `GameContentComponent` model now preserves source, parent
  identity, role, source ID, title ID, version, filename/path, provider job ID,
  and installed state.  Both RomM and Questarr are designed to feed this same
  boundary while retaining provider-specific metadata.  RomM file parsing now
  preserves category, title ID, and version fields when present.
- Current Questarr downloader reconciliation preserves the parent association
  only in Questarr and the downloader marker/job identity in Mudos.  A
  completed component handoff still needs explicit role/title-ID metadata and
  a Switch installer before it can safely attach updates/DLC to an installed
  Eden title.  No files were imported or moved in this reconnaissance pass.

## Switch Mario Kart lifecycle validation

- Pre-uninstall ownership was limited to the canonical Mudos Switch root:
  base `0100152000022000` and DLC `0100152000023001`.  The update
  `0100152000022800` remained under `ROMs/switch/install/` staging and was not
  treated as installed.  Eden per-title configuration and NAND were not
  treated as Mudos-owned content.  Existing Eden user save files for
  `0100152000022000` were recorded and preserved.
- Component-aware uninstall was submitted through the normal Acquisitiond
  `UninstallGame` path.  It completed one remove job, deleted the owned base
  and DLC files, left staging untouched, and did not modify Eden NAND, config,
  shaders, or saves.  Reconciliation reported the local title missing and
  RomM records available.
- Switch local scanning now groups base/update/DLC files under one local
  identity and persists component paths, roles, title IDs, and Mudos ownership.
  RomM Switch records with the same parent title converge to one catalogue
  source identity while retaining combined provider record provenance; this
  prevents component rows from becoming Library games.
- The first single-parent RomM content-set reinstall transaction was submitted
  through Acquisitiond using RomM records 243/244/245.  It failed before
  transfer because the configured RomM request for the current file endpoint
  was unavailable (`GET /roms/717/files/content/...`).  No manual copy or
  RomM mutation was performed, so the required reinstall and Eden runtime
  proof remain outstanding.  Base launch, active update version, and DLC
  recognition are therefore not claimed.
- Full automated validation after these changes: **498 passed, 6 subtests**.

## RomM content-route correction

- Live RomM OpenAPI reports version **5.2.0**.  The actual Mario Kart parent
  ROM is RomM ID `366`; its structured files are file IDs `922` (category
  `game`), `923` (category `update`), and `924` (category `dlc`).  ROMs `243`,
  `244`, and `245` are separate single-file sibling records; `366` is the
  curated multi-file content set.
- The working installed route is
  `/api/roms/{rom_id}/content/{file_name}?file_ids={file_id}`.  The schema's
  `/api/roms/{file_id}/files/content/{file_name}` route returns 404 through
  this deployment.  The earlier Mudos request used file ID `717` as though it
  were a ROM ID and generated `/api/roms/717/files/content/...`; that was both
  the wrong route and the wrong ID namespace.  The `/api` prefix itself was
  present in the actual configured client URL; it was omitted only from the
  diagnostic path text.
- RomM client downloads now use the existing authenticated API root and parent
  ROM route with `file_ids`.  Content-set jobs enumerate structured `game`,
  `update`, and `dlc` files, preserve file IDs/categories/versions, and keep
  one parent acquisition job.
- The resumed Mario Kart parent job is actively transferring RomM ROM 366's
  base component.  It has passed HTTP routing and reached approximately 6.9%
  during validation; the update/DLC children have not started yet.  The
  pre-existing `ROMs/switch/install/` update and DLC files remain untouched.
- Full automated validation after the route correction: **499 passed, 6
  subtests**.  Development runtime was refreshed at `/opt/lulu/dev-current`.
- The first corrected-route transfer exposed and reproduced a second defect in
  the content-set executor: it finalized the parent after the base child and
  then attempted to start the update child (`finalizing -> starting`).  The
  executor now keeps one parent lifecycle across all selected files and only
  enters finalizing after the complete set.  The failed attempt's hidden
  Mudos-owned partial was retired; no canonical file, save, Eden state, or
  RomM source was changed.
- A new normal Acquisitiond `SubmitContentSet` retry was submitted for ROM
  366.  Full automated validation after this correction: **500 passed, 6
  subtests**.  Runtime refreshed at `/opt/lulu/dev-current`; completion and
  Eden runtime checks remain pending while the large base component transfers.

## Initial PC acquisition/Lutris reconnaissance (2026-09-22)

- Mario Kart RomM acquisition was explicitly paused through Acquisitiond before
  this work; no RomM source, canonical Switch file, save, or Eden state was
  modified.
- Live Questarr is v1.4.2. Its durable PC handoff fields are parent `gameId`,
  game title/platforms, per-download UUID, downloader protocol, downloader
  hash/job, release title, status, and file size. Transmission uses label
  `questarr`; NZBGet uses category `questarr`. The current live fixture is
  Switch-only, so no PC acquisition was submitted.
- Mudos now has a read-only Questarr metadata association boundary keyed by
  `(protocol, downloader hash)`, and a provider-neutral `PcInstallSource`
  inspector for manual or completed Questarr payloads. Incomplete payloads are
  not installable; inspection does not execute files or mount images.
- Native Lutris was not previously installed. The Arch `extra/lutris` package
  was provisioned reproducibly; installed version is **0.5.22**. Recon found
  `lutris.api.search_games`, `get_game_installers`, the
  `ScriptInterpreter`/`LutrisInstaller` engine, Lutris database registration,
  and CLI `--output-script`/`-b`. Mudos's adapter isolates these APIs.
- Initial automated PC-source and Questarr metadata tests are in place. The
  full install transaction, controller action, legal PC fixture acquisition,
  headless installer proof, runner installation, catalogue registration, and
  launch/uninstall round-trip remain before exposing Install in the UI.
## PC/Lutris installation round-trip — 2026-09-22

- Installed legal/free OpenTTD with Lutris recipe `openttd-v141` and runner
  `linux` as one parent Acquisitiond job at
  `/home/lulu/Games/Executables/lutris/openttd`.
- Lutris registration was read back as ID `1`, slug `openttd`, and the
  canonical install directory. Mudos converged one `lutris:openttd` identity
  with the original manual source retained.
- Headless execution used Lutris `ScriptInterpreter`, native `Downloader`,
  runner preparation, and Lutris `syncdb`; no Lutris GTK frontend was created.
  Display probing logs no-display warnings but creates no user-facing window.
- Lutris `Game.write_script` generated a frontend-free launcher preserving the
  Lutris runner/configuration. It launched through the existing Mudos session
  and was terminated for the controlled exit test. Guide/input handoff and a
  real child Windows installer surface remain unclaimed tests; unresolved
  Lutris prompts are stopped rather than automated.
- Uninstall removed the Lutris registration and canonical payload, left shared
  runners and `/home/lulu/Games/.acquisition/pc-test/openttd-source` intact,
  and the reinstall completed from that source without redownloading it.
- Five non-Mario Questarr transfers were paused through Acquisitiond for the
  validation window. Resume was attempted through Acquisitiond afterward, but
  all five transitioned to `failed` because the Transmission provider was not
  available; no payloads were cancelled or removed. Mario Kart job
  `job-c00b1926f1be400c8e29b3c0156693ef` remains paused and unchanged.
- Full suite: `508 passed, 6 subtests passed`.
## Transmission outage and Lutris session ownership — 2026-09-22

- The five affected Questarr torrent hashes were preserved and inspected:
  `b30f0f85d1b4e412713f9cfc790306b6bb59c131`,
  `75002b2f7ab78258f095c8693b5bc929f4894780`,
  `fc047392130715319e65988008b7984c27c2740d`,
  `f479ab86a92278a772ab5e7fb592240d1f7c1312`, and
  `a1e34cbb9bd5725bf1ca75ca00c07e9832f2b7cd`.
- `lulu-transmission.service` had been stopped during a runtime restart; its
  10-second default systemd stop timeout expired, SIGKILL terminated the old
  daemon, and Acquisitiond observed `ConnectionRefusedError` on RPC. The new
  daemon loaded all six existing torrents, listened on TCP 9091/51413, and
  authenticated successfully using the configured secret. This was not an RPC
  credential failure or torrent loss. Provisioning now declares a 60-second
  stop timeout.
- No torrent was cancelled, removed, or re-added. Once RPC recovered,
  Acquisitiond reconciled the five records by their existing hashes. The Smash
  record retained its approximately 10.15 GiB partial progress; the other
  four remained existing provider records at zero progress. Mario Kart remained
  separate and paused.
- A regression test exposed and fixed the narrow state-machine defect where
  `RESUMING -> PAUSED` was not permitted. Provider mutation failure now records
  `resume-failed` and remains paused/recoverable rather than becoming terminal
  transfer failure.
- Lutris launches now enter the existing ProcessSupervisor with the catalogue
  game identity and an owned process group. Guide Quit uses the existing
  `process-group-terminate` action. A live OpenTTD attempt showed the remaining
  environmental issue: Gamescope did not expose an OpenTTD focusable window
  under the service launch environment, so the launch was rejected before
  presentation and the owned process group was explicitly cleaned up. This is
  not yet a passing Guide/window-delegation result.
- Interactive installer delegation, COMPAT handoff, install cancellation, and
  restart recovery remain unproven. Controller-native Lutris Install remains
  disabled.
## Lutris delegated presentation boundary — 2026-09-22

- The failed OpenTTD presentation was caused by the ProcessSupervisor child
  inheriting `console-sessiond`'s service environment rather than the
  graphical `consoled` environment. The session service had the runtime bus
  variables but no `DISPLAY`, `WAYLAND_DISPLAY`, or `XAUTHORITY`; the child
  therefore ran but did not create a Gamescope-observable surface.
- Existing emulator launches were not an equivalent comparison: consoled
  launches those processes directly with its graphical environment and then
  registers the process with sessiond. This explained why the emulator path
  worked while the first Lutris ProcessSupervisor path timed out.
- Added an explicit, allow-listed `DelegatedLaunchContext` handoff from
  consoled to sessiond. It carries discovered runtime values (`DISPLAY`,
  `WAYLAND_DISPLAY`, `XDG_RUNTIME_DIR`, session bus, `XAUTHORITY`, and basic
  user/session values) only for the owned child. It does not copy arbitrary
  service environment or secrets and does not create another compositor.
- With the context applied, OpenTTD launches successfully through Lutris,
  ProcessSupervisor, and the existing Gamescope presentation path. Gamescope's
  `GAMESCOPE_FOCUSABLE_WINDOWS` reported the owned OpenTTD child/window PID
  relationship, proving the presentable surface was XWayland-observable in
  this environment. No SDL backend override is used.
- The owned process group was terminated during the bounded test; sessiond
  returned lifecycle to `shell`, input mode to `shell`, presentation to
  `shell`, and no OpenTTD process remained. The native Guide target is
  `process-group-terminate`; a physical Guide-button invocation was not
  automated in this shell test.
- Synthetic interactive installer delegation and COMPAT lifecycle remain
  pending. Controller-native Lutris Install remains disabled.
## Synthetic interactive child delegation — 2026-09-22

- Added `scripts/interactive-installer-fixture.py`, a real external GTK child
  with Complete and Cancel controls and distinct exit results. It is not a QML
  surface and is not a Lutris frontend.
- The naturally selected GTK backend was native Wayland and did not appear in
  the current Gamescope XWayland focusable-window metadata. This was observed
  directly rather than treated as a timeout-only failure. Running the same
  fixture with its explicit test-only `GDK_BACKEND=x11` mode produced an
  XWayland surface through the existing Gamescope session.
- `RequestInteractiveLaunch` uses the same allow-listed graphical context,
  ProcessSupervisor process group, Gamescope association, and sessiond path as
  Lutris games. A live success run entered `presentation=foreign-ui`,
  `delegated_surface=install`, and `input_mode=compat`; the child exited 0 and
  sessiond restored shell presentation/input with no child remaining.
- A live cancellation run used `QuitDelegated`, terminated only the owned
  process group, and restored shell state. The result was signal 15 rather than
  an installation failure. The native Guide action target remains
  `process-group-terminate`.
- A parent shell fixture that waited for the child and continued after its
  successful exit proved child completion does not automatically end the
  owned parent process. The parent continued and then returned to shell.
- The remaining unproven seam is connecting this session transaction to an
  actual Lutris ScriptInterpreter interactive command and parent Mudos install
  job continuation/cancellation. Controller-native Install remains disabled.
## ScriptInterpreter-backed interactive Lutris transaction — 2026-09-22

- The integration point is Lutris 0.5.22's `installer.commands.execute`
  boundary. Ordinary commands remain upstream. Only an explicit recipe
  `env.MUDOS_INTERACTIVE=1` marker routes a potentially graphical `execute`
  command through `RequestInteractiveLaunch`; archive extraction, file writes,
  runner setup, and other commands are untouched.
- A controlled recipe used pre-step `write_file`, the real external GTK
  fixture via Lutris `execute`, and post-step `write_file`. It ran through the
  real `ScriptInterpreter`, `LutrisAdapter`, and one Mudos parent install job.
  Both pre and post markers were created, and Lutris registration/finalization
  completed.
- During the child, the parent normalized job state entered
  `awaiting_interaction`; after child success it returned to installing and
  continued through ScriptInterpreter rather than treating child exit as
  installation completion.
- Guide cancellation was exercised against the owned interactive child. The
  process group terminated, the session returned to shell/normal input, the
  post-step was not created, the parent job became `cancelled` when marked
  cancelling by the acquisition path, and the source remained present.
- Child failure is classified separately from explicit cancellation by the
  session `ProcessResult` outcome. Explicit cancellation raises the normalized
  `JobCancelled` path; unexpected child exit raises a Lutris install error.
- Native Wayland GTK remains outside the current Gamescope XWayland metadata;
  the synthetic proof uses its explicit X11 test mode. No global backend
  override was added and no real Wine interactive recipe was used.
- Controller-native Install remains disabled pending a production recipe
  policy for marking graphical `execute` commands and a complete real
  Acquisitiond Guide-cancellation integration test.

## Initial Flatpak provider plugin

- Reconnaissance on the live CachyOS appliance found no `flatpak` executable,
  libflatpak library, or `gi.repository.Flatpak` typelib. There was no system
  or lulu-user Flatpak installation, remote, runtime, or application to
  migrate. No Flatpak state or download state was changed.
- Added the Flatpak adapter boundary, user-scope ownership policy, stable
  `flatpak:<application-id>` identity, system/user duplicate reconciliation,
  AppStream metadata hooks, game-category filtering, update commit comparison,
  cancellation/reconciliation semantics, application-data-preserving
  uninstall, and generic supervised launch capability.
- Added the `flatpak` plugin component with Flathub Store contribution,
  provisioning requirements, generic Admin/Services metadata, and idempotent
  controlled provisioning script. StoreHome, ComponentRegistry setup
  enumeration, and generic session code require no Flatpak-specific UI branch.
- Flathub browser install handoff was left for a future generic artifact
  capability; no DOM scraping was introduced. Real OpenTTD validation remains
  blocked until the native Flatpak dependency is provisioned.

## Flatpak live completion validation

- Provisioned through `scripts/provision-flatpak.sh`: Flatpak `1:1.18.2-1.1`,
  Python GObject `3.56.3-1`, libflatpak GI namespace `1.18`; supporting
  packages were `ostree 2026.4-1`, `libmalcontent 0.14.0-4`, and
  `composefs 1.0.8-1.1`.
- Flathub was added idempotently to the lulu user scope. A second provisioning
  run left the remote set unchanged; no system remote or application was
  removed. No graphical software centre was installed.
- Native GI discovery read the real Flathub AppStream catalog and found
  `org.openttd.OpenTTD` with summary, `stable`, `x86_64`, Flathub origin,
  `Game`/`Simulation` categories, commit, and icon URL. Classification came
  from AppStream categories, not an OpenTTD exception.
- Native `Flatpak.Transaction` was used for the real Mudos JobManager path.
  The install ran as one parent acquisition job, reached transferring and
  finalizing, downloaded 161,162,832 bytes, resolved runtimes internally, and
  reconciled to user-scope installation. The second install was submitted
  through Acquisitiond after a clean provider uninstall.
- Catalogue reconciliation produced exactly one
  `flatpak:org.openttd.OpenTTD` record with provider `flatpak`, user scope,
  Flathub remote, stable branch, installed state, and launchable state. After
  uninstall it reconciled to available/not-installed; after reinstall it
  returned to the same identity without duplication.
- ProcessSupervisor launch was exercised through sessiond with
  `flatpak run org.openttd.OpenTTD`. The observed tree was an owned Flatpak
  `bwrap` group containing the session helper/proxy and `openttd`; its PGID
  matched the Mudos launch identity. Guide exposed the generic process-group
  Quit action and the Guide helper termination path removed the sandbox and
  returned the session to shell. No unrelated Flatpak process was targeted.
- The fixture presented through the existing X11/XWayland-compatible session
  path. No native external-Wayland delegation was claimed or redesigned.
- Normal Mudos uninstall removed the application deployment but did not pass
  `--delete-data`; `~/.var/app/org.openttd.OpenTTD` remained. Shared runtimes
  were not cleaned up automatically. Reinstall preserved the same provider
  identity and data directory.
- Native update inspection compared immutable installed and remote commits; the
  live fixture was current, so no artificial downgrade was performed. Native
  transaction cancellation and partial-operation reconciliation are covered by
  adapter semantics/tests; no bandwidth-wasting cancellation was forced after
  the completed fixture transaction.
- Flathub's real Install route redirects to a generic
  `flatpak+https://dl.flathub.org/repo/appstream/<application-id>.flatpakref`
  URI. No DOM scraping or Flathub-specific WebEngine branch was added; a
  reusable browser artifact/URI handoff remains follow-up work.
- Changed the declarative Flathub card fallback glyph to Nerd Font `f324`.

## Generic browser handoff validation

- The pre-change physical failure was traced to an external `flatpak+https`
  launch escaping Mudos; the live process evidence included `/usr/bin/xdg-open
  flatpak+https://...flatpakref` and the software-manager helper. No
  Acquisitiond job or catalogue record was created.
- Added declarative `BrowserHandoffContribution` registry metadata with schemes,
  handler ID, artifact types, and trusted source origins. Flatpak claims only
  `flatpak+https` from the Flathub Store origin; disabled components no longer
  claim it. Synthetic registry coverage proves an unrelated scheme can be
  claimed without a provider branch in browser code.
- MudosBrowser now reports generic external navigation requests, including
  disposition and source origin, and ignores/rejects the external navigation
  instead of falling through to a desktop handler. The bridge delegates to the
  generic registry and returns immediate `Preparing installation…` feedback.
- Acquisitiond stages and validates the HTTPS flatpakref, enforces a 2 MiB
  limit, rejects malformed refs/non-HTTPS repositories, and submits the same
  Flatpak JobManager/native transaction path used by normal installs. Duplicate
  URI submissions resolve to the same stable provider identity/job conflict.
- A live SuperTux handoff through the bridge produced one parent job,
  transferred 316,022,046 bytes, completed natively, and reconciled
  `flatpak:org.supertuxproject.SuperTux` as an installed Game/ActionGame/
  ArcadeGame catalogue entry. The fixture launched successfully through
  ProcessSupervisor as `bwrap` → `supertux2`; it was left installed.
- The remaining physical acceptance step is to repeat the click from the
  Flathub page after the final dev-runtime refresh, confirming the QML
  navigation signal rather than the direct bridge probe.

## Browser handoff event correction

- Physical retry exposed the exact failure: Qt emitted the external navigation
  callback, but this Qt build does not expose `QUrl.scheme` as a QML property.
  The handler threw `TypeError` before dispatch, and the old fallback launched
  `/usr/bin/xdg-open flatpak+https://...` / `shelly-ui`.
- The handler now derives the scheme from `QUrl.toString()`. The live bridge
  then accepted the handoff and created the normal Flatpak job. The first
  accepted SuperTux repeat correctly failed only because SuperTux was already
  installed; expected cancelled navigation was surfaced as `net::ERR_ABORTED`.
- Suppressed that expected navigation error and made completed-install
  handoffs idempotent. Repeated SuperTux handoff now returns `Already installed`
  without creating another job.
- Full suite after the correction: 556 passed, 6 subtests passed.

## Immutable pre-notification checkpoint

- Checkpoint commit: `3e23e545fbaceca6fbf61c30f5a580c27615b7dd`.
- Tag: `mudos-flatpak-plugin-checkpoint-20260922-final`.
- Immutable release: `/opt/lulu/releases/3e23e54-candidate-20260922234735`.
- Release manifest and immutability were verified. `/opt/lulu/current` was
  left unchanged; `/opt/lulu/dev-current` remained the mutable runtime.
- Full pre-notification suite: 557 passed, 6 subtests passed.

## Notification system

- The existing Guide is a modal, input-owning external overlay. Notifications
  use a separate passive `mudos-notification` external overlay with transparent
  input, so Home, browser, Settings, and delegated surfaces share one global
  presentation boundary without changing focus or navigation ownership.
- Acquisitiond observes normalized JobManager transitions through a
  session-scoped broker. Startup state is seeded, repeated states are ignored,
  and no historical notification queue is replayed.
- v1 event types are `download_started`, `download_finished`, and
  `installation_succeeded`. Gameplay download pausing is explicitly deferred.

## Notification live integration regression

- The first real browser-triggered Flatpak install created a normal
  Acquisitiond JobManager job. Its state sequence was
  `queued -> starting -> transferring -> finalizing -> completed`.
- NotificationBroker observed the transitions and generated all three generic
  event IDs. The presenter was launched for each event but exited because its
  native default pointed at `/opt/lulu/ui/MudosNotification.qml`; the deployed
  file is under `/opt/lulu/dev-current/ui`.
- Fixed the presenter environment to derive `LULU_NOTIFICATION_UI_FILE` from
  `LULU_INSTALL_ROOT`. No provider-specific notification path was added.
- Revalidated with OpenTTD: uninstall through the normal acquisition endpoint,
  then trusted Flathub browser handoff
  `flatpak+https://dl.flathub.org/repo/appstream/org.openttd.OpenTTD.flatpakref`.
  Job `job-f4431d16479449a58b1296bda086601d` completed successfully and the
  presenter remained alive without QML or connection-reset errors.

## Round 2 acceptance source corrections — 2026-09-26

- GOG/Epic manual Library refresh omitted their provider-owned catalogue
  stages. The Library refresh now includes both; a GOG fixture traverses
  Acquisitiond completion reconciliation, the installed marker, provider
  catalogue projection, Library state, launch descriptor, and Sessiond launch
  dispatch.
- The NZBGet appliance investigation recorded above established the physical
  cause: an older Admin service revision and a sandbox denying writes to
  `/var/lib/nzbget`, plus missing Server1 materialization and stale
  Acquisitiond credentials. Current source has the narrow optional write
  allowance and materialize/restart path; saves now also wait for authenticated
  NZBGet RPC after restart. This development host has no NZBGet config and an
  inactive unit, so appliance-state replay is not claimed here.
- RomM PS1 acquisition now preserves CUE/BIN track sets, extracts safe ZIP
  disc archives, and creates a RetroArch M3U target for multi-disc sets.
  Local discovery validates every referenced CUE track and suppresses duplicate
  per-disc cards when a playlist owns the set.
- Browser visibility now waits until Sessiond has accepted the delegated
  surface and compatibility input mode; failed entry rolls back ownership and
  input mode. Guide Quit is Sessiond-identity-owned, not based on the focused
  X11 PID. Controller/display interaction remains physical acceptance.
- Presentation-media retry batches are bounded and ordered by durable attempt
  age. Downloads lays out six normal rows, places controller hints at the
  panel bottom, and has a geometry regression for row/hint overlap.
- Source validation: Python **856 passed + 25 subtests**, Python compilation,
  native build and CTest **1/1** passed. Full QML: **124 passed, 9 established
  baseline failures**. No immutable candidate or reinstall was performed.
