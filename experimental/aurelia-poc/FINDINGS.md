# Aurelia Steam-backend feasibility findings

Assessment expanded on 2026-10-02 from the committed POC. Upstream inspected:
`Drackrath/Aurelia@50c44d33b97f4aee6fe694e90c464951970d9fd8` (v0.1.37).

## Bottom line

**Promising backend candidate; not yet a demonstrated replacement.** Aurelia
successfully built and, with a separate empty configuration directory, read the
existing Steam library and recognized Mudos-known installed games. It did so
without an Aurelia session, daemon, SteamCMD, or changes to the production
provider. Its install progress and cancellation are materially more structured
than Mudos' current SteamCMD output parser. It does **not** currently provide a
strong provider lifecycle API: it is a CLI over a daemon-relayed socket, launch
is a blocking command with no documented preparation event stream, and its
running record is PID-based.

No install, update, DLC mutation, login, game launch, stop, import, relink, move,
or production provider change was performed. Aurelia had no pre-existing
session/config in `/home/lulu/.config/Aurelia`; we did not authenticate. The
live launch test therefore remains unproven and would cross into an account and
process-affecting action requiring deliberate approval.

The added `experimental/aurelia-poc/adapter.py` is an opt-in CLI bridge, not
production integration. Its read-only `snapshot` path was run successfully
against the isolated appliance config as `lulu`; it returned the library list,
installed JSON, AppID availability, Proton info, install jobs, and running
state. Install NDJSON progress is relayed as normalized JSON events, while
mutation/launch commands are gated behind explicit flags. Those mutative code
paths were not exercised.

## Current Mudos boundary

| Capability | Current Mudos Steam implementation |
|---|---|
| Authentication | `SteamProvider` starts/reuses desktop Steam for interactive Store use. `SteamAuthentication` reports that client state separately from acquisition readiness. |
| Credentials / Guard | `SteamCmdExecutor` uses Mudos `SecretStore`/`CredentialBroker`; SteamCMD has a separate account/session and Guard approval/code flow. The entitlement source uses configured SteamID/Web API key for owned-game snapshots. |
| Library / installed state | `SteamProvider.list_installed()` parses local `appmanifest_*.acf`, validates install directories, and scans Mudos' `~/Games/Executables/steam` plus desktop Steam roots. |
| Metadata / ownership | ACF data supplies installed title, AppID, location and last-played. `SteamEntitlementSource` separately reconciles owned AppIDs; `CatalogueStore.reconcile_steam*` turns these into `steam:<appid>` rows. |
| Install / update / cancellation | `SteamCmdExecutor` runs SteamCMD in its own process group, parses textual output into generic `JobReporter` states. It declares `supports_pause = False`; task cancellation terminates its process group. Install state is Mudos `JobManager`/`AcquisitionStore` state. |
| DLC | No equivalent first-class Steam DLC provider lifecycle surfaced in the inspected Steam adapter; DLC is not proven by this POC. |
| Proton / launch | Launch goes through Steam URI/client, which owns normal Steam preparation and Proton selection. Mudos does not currently substitute an Aurelia/UMU chain. |
| Progress / launch readiness | Acquisition has parsed SteamCMD progress. Launch is observed by polling `/proc` for Steam AppID environment and non-runtime processes; there is not a structured Steam launch event channel. |
| Running / stop / ownership | `ProcessSupervisor` and Sessiond observe the app process/client, own presentation/input lifecycle, and stop/clean up client state. Sessiond is the shell lifecycle authority. |
| Errors / logs | SteamCMD output is parsed into normalized `SteamCmdError`; launch evidence comes from process observation and Mudos logs rather than a provider event feed. |

Relevant source: `src/lulu/plugins/steam/{provider,cmd,auth,entitlements}.py`,
`src/lulu/process_supervisor.py`, `src/lulu/sessiond.py`,
`src/lulu/catalogue.py`, and `src/lulu/acquisitiond.py`.

## Aurelia source inspection

Upstream cloned and built at
`Drackrath/Aurelia@50c44d33b97f4aee6fe694e90c464951970d9fd8` (v0.1.37).
`cargo build --release --locked` succeeded (3m22s); only upstream dead-code and
future-compatibility warnings were emitted.

- **CLI and daemon:** one Rust CLI. The optional persistent daemon holds one
  authenticated Steam CM connection and accepts forwarded argv over a Unix
  socket using a framed stdin/stdout/stderr/exit protocol. It is not an
  application-facing typed RPC/event API. Commands auto-spawn/forward by
  default; POC set `AURELIA_NO_DAEMON=1`, `AURELIA_NO_SPAWN=1` and a private
  `AURELIA_DAEMON_SOCKET`.
- **JSON:** `--json` is command-specific JSON, not a unified provider schema.
  Install progress is NDJSON on stderr and terminal JSON on stdout. CLI failures
  carry process exit status and human/typed-error output; consumers still need
  command-specific parsing and normalization.
- **Auth/session:** commands may restore an Aurelia refresh-token session from
  its config dir, or local library discovery can read Steam's local caches
  without logging in. `login` writes Aurelia session material. No session was
  present, so no auth was attempted.
- **Library/ownership:** `libraries` scans Aurelia config, Steam roots,
  `libraryfolders.vdf` references, and connected drives. `list --installed`
  merges local owned/cache data with an ACF scan; `available APPID` checks local
  manifest/files. It handles multi-library and duplicate paths, but this is
  still local-cache/manifest interpretation, not an independently validated
  Mudos ownership authority.
- **Install/update:** `install APPID` performs real Steam protocol content work
  and writes install metadata/files. `install list` returns in-flight state;
  `install stop APPID` aborts the registered job. Progress states include
  `queued`, `downloading`, `verifying`, `moving`; fields include byte totals,
  percent, current depot/file, rate, and ETA. Updates are separately queryable
  (`update`) and executable. This is more useful than scraped SteamCMD text,
  but does not by itself distinguish every Mudos launch phase.
- **DLC:** `dlc APPID` discovers DLC; `enable`/`disable` mutate an appmanifest.
  Install code notes that DLC follows the base app library, and has special
  Steam restart behavior on Windows. Not exercised.
- **Runtimes:** `config protons` listed installed runtimes and Aurelia's
  configured default. Proton install is an Aurelia-owned download/install
  operation. Launch supports native/Proton, explicit `--proton`, optional
  `--umu`, and `--steam` (host Steam integration). Do not combine Mudos/UMU
  ownership with Aurelia's own UMU wrapper without one party owning the whole
  command/environment/process lifecycle.
- **Launch/running/stop:** `play APPID` performs preparation then blocks until
  the game exits; successful JSON is emitted at completion, not at the point
  the game becomes visible. Source has internal launch-stage logs (including
  `stage_start`, `process_spawn_attempt`, and a process-spawn event), but the
  CLI does not expose a structured live launch-status/event endpoint. Running
  state is a JSON file with app ID/name/PID and optional Wine prefix. `running`
  reports tracked Aurelia launches; `stop` signals the recorded process and
  optionally sweeps Wine processes in a per-game prefix. It cannot authoritatively
  track games launched outside Aurelia; PID reuse/staleness and the boundary of
  child processes require scrutiny.
- **Logs/errors:** Aurelia has per-launch structured event logs and native
  stdout/stderr capture. CLI JSON errors are useful but are not a stable,
  versioned Mudos event contract. The exact command spec/environment is logged
  internally; POC deliberately did not launch and expose potentially sensitive
  environment values.
- **Steam file side effects:** source explicitly reads/writes ACF manifests,
  installs depots and Proton under Steam library paths, and has optional
  in-Wine Steam/UMU behavior. `import`, `relink`, `move`, DLC toggles, and
  install/update cannot be treated as harmless discovery operations.

## Live evidence

All Aurelia invocations ran as user `lulu`, with config under
`<private-temporary-directory>/aurelia-poc-live/config`, mode 0700 directory / 0600 config,
and these environment values: `HOME=/home/lulu`,
`AURELIA_CONFIG_DIR=<private-temporary-directory>/aurelia-poc-live/config`,
`AURELIA_DAEMON_SOCKET=<private-temporary-directory>/aurelia-poc-live/daemon.sock`,
`AURELIA_NO_DAEMON=1`, `AURELIA_NO_SPAWN=1`. No credentials were passed.

Exact safe commands (binary is a separately built Aurelia executable):

```text
aurelia --version                       -> aurelia 0.1.37 (exit 0)
aurelia --json libraries               -> two paths: /home/lulu/.local/share/Steam,
                                            /home/lulu/Games/Executables/steam (exit 0)
aurelia --json list --installed        -> exit 0
aurelia --json available 40800         -> available=true, path=.../Super Meat Boy (exit 0)
aurelia --json config protons          -> default=experimental; Steam runtimes:
                                            Proton - Experimental, Proton Hotfix (exit 0)
aurelia --json install list            -> [] (exit 0)
aurelia --json running                 -> {"running":[]} (exit 0)
```

The filtered `list --installed` output correctly included known Mudos rows:

```json
[
  {"app_id":26800,"name":"Braid","is_installed":true,"platform":"linux"},
  {"app_id":224760,"name":"FEZ","is_installed":true,"platform":"windows"},
  {"app_id":40800,"name":"Super Meat Boy","is_installed":true,"platform":"linux"},
  {"app_id":220780,"name":"Thomas Was Alone","is_installed":true,"platform":"linux"}
]
```

Reported paths were in `/home/lulu/.local/share/Steam/steamapps/common/...`.
The Mudos library is registered in `libraryfolders.vdf`. A follow-up mount
inspection corrected the earlier POC's “hardlinked” interpretation: the
desktop Steam `steamapps` path is a **Btrfs bind mount** of
`/home/lulu/Games/Executables/steam/steamapps`, not a set of hardlinks or a
second copy. `findmnt -T` reported the desktop path mounted from
`/dev/nvme0n1p2[/@home/lulu/Games/Executables/steam/steamapps]`; the canonical
path itself resolves through `/home`. The identical device/inode with `nlink=1`
for AppID 40800's manifest and game executable is consistent with that bind
mount. Consequently the canonical Mudos `steamapps` tree is the backing storage
authority, while Steam/Aurelia may report its desktop alias as the game path.
This improves compatibility prospects, but no Aurelia write was attempted.

The POC config explicitly set `steam_library_path` to the canonical Mudos path.
Aurelia source uses that setting as the default install destination, and accepts
an explicit `--library` override. **Do not rely on the discovered default**:
`LauncherConfig::default()` uses `detect_steam_path()` (the desktop Steam root
on this host), and duplicate alias scans can report a path under
`~/.local/share/Steam`. A production adapter must pin the config to the
canonical Mudos path and treat the desktop path as a mount alias, not another
library to reconcile or delete.

Known installed Mudos AppIDs checked against `CatalogueStore`/local Mudos
manifest enumeration included 26800, 224760, 40800, and 220780. The returned
installed state and titles matched those local records. This establishes
installed discovery and basic local metadata, **not** remote store metadata,
Steam account ownership, launchability under Aurelia, nor entitlement parity.

The adapter's exercised form was:

```sh
python3 ./aurelia-poc-adapter.py \
  --binary /path/to/aurelia \
  --config-dir /path/to/private/aurelia-config \
  snapshot --app-id 40800
```

It emitted machine-readable outer JSON with per-command exit codes and source
JSON. In that result `availability.data.available` was `true`, `installed`
contained AppID `40800` with `is_installed: true` and `is_owned: true`,
`install_jobs.data` was `[]`, and `running.data.running` was `[]`.

One successful Mudos launch was found in existing journal history for AppID
40800 (Super Meat Boy): Mudos observed its AppID process and observed its exit
at `2026-10-01 21:48:33.643` and `21:48:36.725` local time. That makes it a
candidate for a later controlled Aurelia launch, not proof Aurelia can launch
it. There was no Aurelia session, so `info`, `dlc`, and launch/authenticated
protocol calls were intentionally not attempted. No Aurelia process/daemon
remained after the safe read commands.

## What this proves about a launch screen

1. **Preparation begins:** CLI invocation is a boundary, but no stable event is
   exposed for each phase before `play` returns.
2. **Install vs launch preparation:** install is a separate command and
   install progress has distinct states; `play` may automatically update or
   prepare runtime/game. Mudos can distinguish command intent, not all work
   nested within launch.
3. **Proton downloading:** runtime install exists as a separate operation with
   CLI progress, but no demonstrated unified launch event says “Proton setup
   has begun” for automatic preparation.
4. **Launch command started:** process spawn is visible in Aurelia internal
   logs; no tested machine-readable live event feed ties that to Mudos.
5. **Game running:** Aurelia's tracked running JSON file/PID is available, but
   is not equivalent to authoritative window/presentation readiness.
6. **Cancel launch:** install has a cancellation command. There is no distinct
   documented cancel-preparation operation for a blocking `play`; stopping a
   game record is not demonstrated as safe/complete for all pre-running stages.
7. **Stop game:** supported for an Aurelia-launched process, with optional
   force. It cannot own the Mudos Sessiond lifecycle automatically.
8. **Failed vs slow launch:** exit status and logs eventually distinguish
   failure; without live phase events, Mudos still needs timeout/progress policy.
9. **Structured progress:** install yes; launch only internal event logs and
   command blocking, not a screen-ready stream.
10. **Future screen:** install screen can consume Aurelia NDJSON after a thin
    normalizer. A launch screen needs a proper upstream event/status API or
    continued measured observation; do not fabricate launch progress.

## Smallest clean integration boundary

If pursued, keep Mudos' provider interface and make `SteamProvider` select an
`AureliaBackend` behind an explicit opt-in configuration. Mudos should remain
the authority for catalogue identity/ownership reconciliation, user-visible
jobs/cancellation, Sessiond presentation/input ownership, and errors normalized
into stable Mudos contracts. Aurelia should own one coherent Steam operation
and process subtree (including either its native Proton path or its UMU path),
not be nested under a second Mudos UMU/Proton launch owner.

Before launch migration, either obtain an upstream structured event protocol
(phase, command spawn, running identity, terminal error, cancellation) or design
an adapter that captures Aurelia logs and process state without racing Sessiond.
For install/update, map Aurelia's real NDJSON fields into JobManager without
relabeling bytes or inventing phases. Preserve Steam GUI as explicit fallback;
avoid simultaneous writers to appmanifests and Steam library state.

Potentially removable only after parity testing: Mudos SteamCMD process/output
parser, separate acquisition auth/Guard path, Steam GUI launch dispatch for
games moved to Aurelia, and AppID process polling/log heuristics. Not removable
without redesign: Mudos credentials/ownership policy, catalogue reconciliation,
job UX/cancel contract, Sessiond/Consoled lifecycle and presentation/input
ownership, error normalization, and fallback.

## Risks and gates

- **Experimental beta / dependency:** upstream is explicitly beta and fast-moving;
  pin a commit, review releases, test compatibility and provide disable/fallback.
- **License:** current upstream tree declares GPL-3.0 (its LICENSE describes
  earlier MIT-licensed history and a later GPL transition). A subprocess
  boundary may differ from linking/derivative integration, but no legal
  conclusion is made. Have counsel review distribution, packaging, modifications,
  notices, source obligations, and the exact pinned tree before shipping.
- **Unofficial Steam protocol:** Aurelia and `steam-vent` implement protocol
  behavior outside Valve's supported client API; protocol/auth changes can
  break or risk accounts.
- **Account/ToS/VAC:** no account-affecting test was done. Review Valve terms,
  Steam Guard/session handling, account security, game-specific anti-cheat and
  VAC implications before use; do not assume headless/third-party launch is
  safe for every title.
- **Steam file mutation:** Aurelia directly modifies Steam manifests/content,
  and current Mudos exposes the canonical `steamapps` tree to desktop Steam via
  a bind mount. Establish backup,
  locking, atomicity, recovery, and one-writer policy first.
- **Steamworks/DRM:** standalone launches may differ; Aurelia has optional host
  Steam/in-Wine integration, but compatibility is game-specific. Shared-account,
  DRM, overlay, cloud, and anti-cheat behavior remain untested.
- **Proton/UMU:** choose a single owner and compare actual process trees,
  environment, prefix, Gamescope presentation, and stop behavior with a
  controlled known-good game. This POC did not do that.
- **Lifecycle:** daemon is command relay rather than versioned provider RPC;
  launch status is not an authoritative event feed; PIDs/running records need
  stale/reuse/descendant analysis. Mudos still owns shell lifecycle.
- **Storage:** discovery found the Mudos path registered; the duplicate desktop
  path is a bind-mounted alias of canonical `steamapps`. Aurelia reported that
  alias for existing apps. No import/relink or write test was performed.
  Targeted install must be separately controlled.
- **Recovery:** keep current provider available; never automatically switch a
  game or migrate library state. Provide per-provider opt-in, disable switch,
  independent backups, and tested rollback before any appliance deployment.

## Expanded assessment (2026-10-02)

### 1. Authentication and session ownership — the strongest case for Aurelia

**Source-level evidence:** Aurelia implements Steam CM authentication in its
Rust client (`steam-vent`): password login, QR login, refresh-token restore,
Steam Guard email/device codes, and Steam Mobile device confirmation. Its JSON
login protocol emits challenge/Guard events instead of requiring Mudos to scrape
a SteamCMD prompt. OpenID proves browser identity only and does not mint the CM
session; the optional web token is short-lived/web-audience and does not replace
the client session needed for library/install/launch.

A full session is persisted as `session.json` under Aurelia's config dir
(`~/.config/Aurelia` by default; `AURELIA_CONFIG_DIR` can isolate it). It
contains a refresh token/account identity. After a successful full login,
Aurelia enables ChaCha20-Poly1305 encryption with a random key stored in the OS
keyring. If the keyring is unavailable, the code explicitly falls back to
plaintext JSON and owner-only mode `0600`; that fallback, keyring availability
in a headless systemd user service, backup/recovery, and session-file ownership
must be policy decisions, not assumptions. No token or secret was read,
printed, copied, or persisted during this assessment.

The daemon watches the session file's mtime, restores a changed/new token, and
shares one live Steam connection across forwarded CLI calls. It periodically
probes connection liveness and reconnects after confirmed loss. Restore errors
are classified and retried with backoff; `login --health` reports authenticated
state and `login --reconnect` forces a daemon reconnect. A missing, expired, or
rejected refresh token becomes an auth error; it does not silently obtain a new
password/Guard factor. Re-login and any new Guard/device approval remain an
interactive account step. QR challenges and Guard events are machine-readable,
so Mudos could route them through its existing `CredentialBroker`/Guide surfaces.

**Single owner conclusion:** Aurelia plausibly can be the sole Mudos CM-session
owner for enumeration, ownership/library refresh, acquisition, DLC state, and
standalone launch. Those callers must share the same config directory, UID,
daemon socket, and persistent daemon. `AURELIA_NO_DAEMON` is not suitable for
the production operation path: it creates independent connections and makes
install-list/cancel state process-local. The POC used that flag only for
read-only discovery. An Aurelia service plus Mudos adapter is needed to manage
daemon startup, health, update/restart, logs, socket permissions, and credential
handoff. The daemon is a command relay, not a stable typed API.

This would replace the **SteamCMD password/session/Guard machinery** and could
replace Mudos' separate Web API-key ownership source after ownership parity is
validated. It would not necessarily remove Steam GUI: Aurelia's `--steam`
launch option starts/reuses host Steam for Steamworks, and Family-Shared games
require Steam integration. The optional in-Wine Steam runtime is a further
Steam-client path with its own prefix/session needs. The graphical client may
also remain for Store/Big Picture/overlay use. Therefore this can reduce
independent auth mechanisms from GUI + SteamCMD + Web API key to Aurelia CM plus
an optional Steamworks client, but cannot yet claim “one Steam auth everywhere”.

**Live evidence:** there was no existing authenticated Aurelia session in the
default user config, so no sign-in or account request was made. On 2026-10-02,
`aurelia --json login --health` against the empty isolated POC config returned
`logged_in:false`, `account:null`, `steam_id:null`, `web_token:false`,
`daemon:false`. No credentials were supplied and no session file was created.
This confirms only the logged-out path—not successful auth, Guard, token
survival, or refresh behavior.

### 2. Canonical library and storage compatibility

The canonical Mudos path remains `~/Games/Executables/steam`. On this host its
`steamapps` subtree is the backing tree exposed to desktop Steam by a Btrfs bind
mount at `~/.local/share/Steam/steamapps`; `libraryfolders.vdf`, manifests,
game files, `compatdata`, `shadercache`, and the standard Steam library layout
are therefore shared through the mount. Existing Steam appmanifests are native
Steam metadata and Aurelia parses/writes that format. This is a conventional
Steam library layout from Aurelia's perspective; there is no evidence a storage
migration is needed.

`libraries` and installed discovery demonstrably saw the Mudos path and games.
`install_game()` defaults to `LauncherConfig.steam_library_path`, accepts
`--library`, creates `steamapps/common/<installdir>`, writes ACF metadata, and
for DLC writes into the base game's directory/manifest. With an explicit
canonical path this is source-supported as compatible. **It is not live-proven
safe**: no Aurelia install/update touched files, and the bind mount plus the
running Steam client's own cache/writes create concurrency/atomicity risks.
Some `steamapps` metadata resides at the Steam root outside this mount (for
example client `appcache`/`userdata`), which Aurelia also discovers from the
desktop Steam install root.

Required storage gate: run all Aurelia operations with the explicit Mudos
canonical library; verify exact destination, appmanifest and content before /
after on a controlled disposable AppID or independently backed-up test game;
verify mount identity survives any installer/packaging/service start; establish
one-writer coordination with Steam GUI and Mudos. Never use Aurelia
`import`/`relink`/`move` as a substitute for this validation. Avoid any cleanup
logic that treats the desktop alias as duplicate physical content.

### 3. Installation, update, DLC, and Acquisitiond fit

**Source-supported surface:** install by AppID/platform/library; dry-run size
estimate; update check and per-AppID update; integrity verify; pause/pin/branch
and other operations exist in Aurelia, but pause/resume semantics should not be
assumed equivalent to Mudos job semantics. Install progress is genuine
provider-reported state: NDJSON on stderr with state (`queued`, `downloading`,
`verifying`, `moving`), aggregate/depot bytes and totals, percentages, speed,
ETA, depot ID and current file; terminal result JSON is on stdout. The adapter
can map these to `JobReporter` without calling bytes-on-disk “wire bytes”.
`install list` provides active job status; `install stop APPID` sets the
registered operation abort flag. In the daemon mode, separate forwarded calls
share that process-global registry.

Failure behavior is partly good and partly a gap. Size check can report
insufficient free space; depot/CDN errors try hosts and ultimately emit a
failed progress state/command error. A partial install writes an incomplete
manifest (`StateUpdateRequired`, not fully installed), so installed discovery
does not falsely mark it ready. The source reuses an existing install
directory and download code has hash-checked chunk reuse, making retry/resume
plausible. There is no demonstrated durable job journal/recovery contract
across Aurelia daemon/process death: active install state is an in-memory
registry, so a daemon crash may leave partial files and an incomplete manifest
without a Mudos-owned job row. Retrying may reuse chunks; exact recovery and
cleanup need a controlled interruption test. Mudos' Acquisitiond already
provides durable jobs, cancellation, retry and state-change signals, but the
Steam plugin currently registers its own executor and process-group cancellation.
An Aurelia executor must reconcile Aurelia's active jobs after restarts and
must not report a canceled job until Aurelia has stopped writing.

**DLC:** Aurelia resolves DLC IDs/names and their parent; reports per-DLC
`owned`, `installed`, `disabled`; installs DLC into the base game's install
directory and registers DLC depots with `dlcappid` in the base ACF; and supports
enable/disable. This is a useful component-level substrate. Its commands are
per AppID, not a Mudos logical-title transaction: it does not itself present a
single “base game + selected component set” acquisition job with ordered
dependencies, aggregate progress/cancel, or Mudos catalogue parent/component
identity. The Mario Kart-style requirement should map to one Mudos title with
base/update/DLC components retained separately, while calls to Aurelia remain
per-AppID and are sequenced by an Acquisitiond content-set executor. Base must
be installed before DLC; the source explicitly rejects DLC without a base ACF.
Mudos currently has `SubmitContentSet` scaffolding but it is RomM-only, and
Steam's `CatalogueGame.from_steam()` currently models one AppID row. That
grouping is Mudos adapter/catalogue work, not a fundamental Aurelia blocker.

Known gaps: no live authenticated download, cancellation, update, DLC query or
mutation was performed. Offline/cache listing and inspected source do not prove
entitlements, depot availability, resume semantics, or behavior against this
Steam account. No appmanifest was altered.

### 4. Launch lifecycle and Sessiond ownership

Aurelia can run native games or select a Windows launch option and invoke a
configured Proton/Wine runner; `play` can perform pre-launch update (best effort
for owned titles; mandatory for Family-Shared), optional Steam DRM-ticket
preflight, cloud save sync, runtime/prefix setup, and then wait for the child to
exit. `--no-update` suppresses owned-game update but not the Family-Shared
requirement. The CLI reports final `finished` JSON after game exit; launch error
has nonzero exit/typed error. Its internal event logs identify pipeline stages,
spawn attempt, verification and exit, and it writes a running record.

Coarse truthful Mudos states are viable without rich telemetry:

| Mudos state | Evidence Mudos could use |
|---|---|
| requested | Sessiond launch request/token accepted |
| preparing | Aurelia play request accepted; keep shell/presentation under Sessiond |
| launching | Aurelia's per-AppID `running` record/process evidence appears; this is spawn evidence, not visible-window readiness |
| running | Mudos Gamescope/window observer confirms game presentation; Aurelia AppID state can corroborate |
| exited | `play` returns and Mudos observes the AppID process/presentation gone |
| failed | CLI exits nonzero before running, or short-lived process exits during the configured health window; report exact known failure only |
| cancelled | Mudos cancellation requested and Aurelia stop/cancel plus process reap confirmed |

“Preparing” may remain a coarse wait state; do not assert shader compilation,
Proton download or runtime setup unless a progress event proves it. Failed vs
slow cannot be determined from absence of `running` alone; Mudos needs bounded
startup policy and process/error evidence. Rich internal events could be
exposed upstream through a stable lifecycle NDJSON/RPC interface, but Mudos
should not scrape log files as a production contract.

**Ownership complication:** with the Aurelia daemon enabled (necessary for one
shared authenticated session), the `play` command is executed inside the daemon
and the client process only relays stdio/exit. Sessiond cannot treat the
short-lived CLI client's PID/process group as the game owner. It must correlate
AppID and Aurelia's running/process state, invoke Aurelia stop on cancellation,
wait for actual game descendants to be gone, and retain its own launch token
until presentation/input are restored. A dedicated upstream launch RPC that
returns an operation ID/PID and accepts cancel/status would simplify this, but
coarse polling plus the Mudos Gamescope observer may suffice. Never let Aurelia
own Sessiond lifecycle, Gamescope, input, or return-to-shell policy.

Mudos Sessiond already owns launch token, coarse lifecycle, presentation, input
mode, cancellation, process supervision, and Home return. Consoled dispatches
Steam and calls Sessiond; `ProcessSupervisor` currently requests Steam URI,
observes AppID processes, and selects/returns Gamescope presentation. A thin
`AureliaBackend` should expose start/wait/status/stop and never bypass Sessiond.
Production configuration would opt in per Steam provider, leaving the current
Steam client backend available for fallback.

### 5. Proton / runtime / launch compatibility

Aurelia's standalone default resolves native Linux vs Windows depot/launch
options, chooses explicit/per-game/global Proton, prepares Aurelia's configured
prefix, builds a command and directly spawns it. Its Windows runner uses a
`proton run` path, Steam AppID and compatdata environment; optional `--umu`
uses `umu-run` with `GAMEID`/`PROTONPATH`. It scans installed Valve Proton from
the configured library `steamapps/common` and custom tools under Steam's
`compatibilitytools.d`; Aurelia can install Valve Proton and community builds.
Its `--steam` option may start host Steam for Steamworks, or use its separate
in-Wine Steam runtime according to policy. The source contains explicit prefix,
Steamworks and runtime-policy handling.

Current Mudos Steam launches are delegated by `steam://rungameid/<appid>` to
the official desktop Steam client. That means the current working launch path
uses Steam's per-game compatibility configuration, container/runtime behavior,
shader cache, Steam Input/overlay, and Steam client lifecycle. Mudos does not
currently put Steam games through its non-Steam UMU wrapper; the UMU code in
Mudos is for other launch backends. Aurelia standalone Proton/UMU is therefore
not proven equivalent merely because the same Proton directory is present.
Likely ported settings include selected Proton version and launch options;
potential compatibility gaps include Steam's pressure-vessel/Steam Linux
Runtime environment, shader pre-caching/cache ownership, controller/overlay,
Steamworks DRM, per-game Proton override migration, compatdata/prefix mode, and
launch flags. With `--steam`, some games will still depend on the desktop
client; Aurelia's in-Wine Steam is explicitly a different environment.

Recommendation for ownership: one owner per launch. First evaluate Aurelia's
native Proton path **or** its UMU path against the current Steam GUI path; do
not stack Aurelia UMU under a second Mudos UMU wrapper. Do not switch all titles
to standalone launch until known-good game evidence covers process tree,
runtime environment, prefix location, shader behavior, Steamworks and stop.
No such launch comparison was performed in this recon.

### 6. Failure/restart semantics

- **Aurelia daemon exit:** forwarded command fails; game children may or may not
  survive independently. Sessiond must reconcile AppID processes and presentation,
  not infer game exit from lost CLI/daemon connection.
- **Session expiry / Steam unavailable:** commands return auth/network typed
  errors; daemon has refresh/reconnect and backoff, but Guard reauthentication
  requires user action. Report auth-required vs network failure distinctly.
- **Network loss during install:** CDN loop retries hosts then fails; partial
  files/incomplete manifest may remain. Reattempt may hash-reuse chunks; no
  durable recovery guarantee was live-tested.
- **Cancellation:** install stop is source-supported within the same daemon
  registry. Acquisitiond can model CANCELLING/CANCELLED, but adapter must wait
  until Aurelia has stopped writing. Launch stop depends on a running record;
  pre-spawn/preparation cancellation is not an authoritative Aurelia operation.
- **Launch failed / instant exit:** CLI eventually returns result; internal
  verification logs lifetime/exit and Mudos can observe early process exit.
  A black-box no-running timeout alone is ambiguous.
- **Lost running record:** Aurelia's `running` implementation refreshes PID from
  `/proc` AppID environment for Proton/native processes and prunes stale records.
  This is better than a bare PID, but remains same-UID `/proc` polling and
  application-process correlation, not a process-group/job-object guarantee.
- **Mudos restart during install:** Acquisitiond's durable row may survive,
  but Aurelia's daemon-memory operation registry/progress source might not. A
  restart reconciliation protocol or explicit “provider status unknown, retry
  safely” state is needed.
- **Mudos/Sessiond restart during launch:** Aurelia may still own a game; Mudos
  must query `running`, reconstruct/repair lifecycle ownership, or use an
  explicit recovery screen. Never start a duplicate AppID blindly.

These map to existing `JobManager`/Acquisitiond states and Sessiond lifecycle,
but need an adapter that preserves uncertainty rather than converting every
lost connection to failed/completed.

### 7. Capability matrix

| Question/capability | Status | Evidence / gap |
|---|---|---|
| Sole CM authentication/session owner? | **Source-supported but untested** | Full refresh-token session plus one shared daemon connection; no safe existing account session available for live test. |
| Replace SteamCMD auth/password/Guard path? | **Source-supported but untested** | Aurelia install/update uses its CM client and one persisted session; first login and Guard still need a deliberate user flow. |
| Remove Steam GUI and all parallel Steam auth? | **Unknown/blocking by title** | Store UI, overlay/Steamworks, Family-Shared and in-Wine runtime may still require official Steam client/session. |
| Persist auth across Mudos restarts? | **Source-supported but untested** | Refresh token stored; encrypted via OS keyring after login, plaintext 0600 fallback; daemon restores by mtime. Deployment/keyring behavior untested. |
| Enumerate canonical Steam library / installed titles? | **Demonstrated in isolated POC** | Safe read-only scan found registered canonical library and matching known Mudos AppIDs. Reported alias is bind-mounted view. |
| Safe install into canonical Mudos root? | **Source-supported but untested** | Config/`--library` select root; conventional ACF layout and bind mount. No write test, concurrent-writer or recovery validation. |
| Updates and byte progress? | **Source-supported but untested** | CLI/source provides update, install list and NDJSON progress; prior POC verified schema, not a live download. |
| Install cancellation? | **Source-supported but untested** | `install stop` flips shared abort signal; daemon mode is required for cross-call state. Reap-before-CANCELLED adapter behavior needed. |
| Durable resume/recovery? | **Unknown/blocking for automatic recovery** | Chunk reuse and incomplete manifest behavior exist; operation journal/restart recovery not established. |
| DLC ownership/install/enable state? | **Source-supported but untested** | DLC discovery/status and base-manifest install/enable exist; requires auth and was not queried live. |
| Mario Kart-style content set as one Mudos logical title? | **Requires implementation** | Aurelia operates per AppID; Mudos needs content-set orchestration/catalogue component mapping through Acquisitiond. |
| Resolve/install Proton and optional UMU? | **Demonstrated in isolated POC / source-supported** | Read-only runtime list showed Proton Experimental/Hotfix; installs and game selection not tested. |
| Launch existing game via Aurelia? | **Unknown/blocking for replacement** | No auth session and no launch attempted. Source has direct Proton/UMU launch and host Steam paths. |
| Coarse launch states for Sessiond? | **Requires implementation; telemetry nice-to-have** | CLI `play`, running AppID state, process observation and Mudos Gamescope observer can support truthful coarse states; daemon means CLI PID is not game owner. |
| Rich launch-stage telemetry? | **Nice-to-have / requires upstream or adapter change** | Internal pipeline events exist, no stable live event API. Not a prerequisite if coarse states are honest. |
| Cancellation/restart recovery across Sessiond? | **Requires implementation** | Mudos must correlate and stop Aurelia-owned AppID process, wait for reap, reconstruct lifecycle after service restart. |
| Stable error/progress boundary for Acquisitiond? | **Requires implementation** | Normalize command-specific JSON/NDJSON, typed errors, uncertain state and recovery without fabricating fields. |

### 8. Concrete gaps and next implementation milestone

No fundamental source-level blocker was found to Aurelia owning Steam CM
authentication and acquisition. The gaps that actually gate replacement are:

1. **Integration:** implement a non-production Aurelia executor/backend that
   runs and supervises one daemon, offers secret-free auth-health, login/Guard
   events, library/catalogue, install/update/DLC and AppID status/stop through
   stable Mudos interfaces. Reuse `CredentialBroker`, Acquisitiond and
   Sessiond; do not give raw credentials to arbitrary shells/logs.
2. **Auth policy:** decide keyring requirement/fallback, service UID/session
   bus behavior, file permissions/backup/recovery, who may request login, how
   Guard/device approval is surfaced, and how expired tokens recover.
3. **Storage:** set Aurelia's library path explicitly to the canonical Mudos
   root; validate bind mount and a disposable/backup-protected install/update
   end-to-end; coordinate Steam GUI writes and avoid duplicate-alias cleanup.
4. **Lifecycle/runtime:** approved low-risk installed-game launch comparison
   with current `steam://` baseline; capture process tree, effective command/env
   without leaking secrets, runtime and prefix paths, Gamescope presentation,
   Steamworks, clean stop, immediate exit and Sessiond restart recovery.
5. **Content model:** one Acquisitiond transaction for base/update/DLC
   components, truthful aggregate progress, cancellation barriers and replay
   after daemon restart.
6. **Fallback/rollout:** opt-in per Steam provider, preserve current path,
   no automatic migration, and test switch-back without touching install data.

Launch telemetry is not on this critical path. A future typed event stream is
an upstream quality improvement, not a prerequisite for the first controlled
backend trial.

## Recommendation

Proceed to a **bounded implementation milestone behind opt-in, not replacement**.
The best technical case is real: Aurelia can plausibly collapse SteamCMD's
separate credential/Guard/session path and Mudos' separate account ownership
lookup behind one persisted CM session and one shared daemon, while providing
install/update/DLC APIs. It discovers the canonical Mudos storage through its
Steam bind-mounted alias; the previous POC's hardlink interpretation has been
corrected. Install destination is controllable, but write safety is unproven.

The blocking evidence gap is not verbose launch telemetry; it is live proof of
auth/session persistence/re-auth UX, safe canonical-root install/update and
cancellation/recovery, and one known-good Aurelia launch using the actual
Mudos-compatible Proton/UMU/Steamworks/presentation path. Therefore Aurelia
deserves a proper, isolated adapter phase, but not yet canonical appliance
activation. The next gate should be implementation of the minimal opt-in
Acquisitiond/Sessiond adapter plus review of session-key storage, followed by a
separately approved account-authenticated content test and controlled game
launch. Do not migrate or change the production provider until those pass.

## Mudos-side adapter implementation update

The experimental integration boundary was added after this assessment in
`src/lulu/plugins/steam/aurelia.py`. It has a distinct `steam-aurelia` provider
identity, secret-free CLI client, private Aurelia config directory, read-only
health/library/running methods, an Acquisitiond `JobExecutor` with actual
NDJSON progress conversion, shared-daemon cancellation, active-job discovery
and restart adoption, plus a coarse launch controller. The current provider is
not replaced. Registration defaults off at
`providers.steam_aurelia.enabled=false`; only explicit provider-services
configuration registers the executor. Its first invocation creates a minimal
private Aurelia config pinned to Mudos' canonical library with cloud sync and
Windows-Steam discovery off; pre-existing mismatched config fails closed. See `docs/aurelia-auth-storage.md` for
session ownership, credential introduction and keyring policy.

Important boundary still outstanding: Sessiond's production launch path
continues to use its current Steam request/observe/process-owner protocol. The
new controller is testable and provides Aurelia-side launch evidence, but has
not yet been connected to Sessiond's authoritative lifecycle, presentation,
Gamescope, input, cancellation and recovery transitions. `launching` versus
`preparing` also cannot be distinguished reliably before Aurelia's running
record appears; the adapter does not invent that event. Accordingly this work
is enough to proceed to read-only auth health and controlled authenticated
acquisition adapter testing after configuration/keyring review, but not to a
controlled game launch or production backend selection.
