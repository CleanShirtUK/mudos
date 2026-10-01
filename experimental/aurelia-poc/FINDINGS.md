# Aurelia POC findings

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
`/tmp/opencode/aurelia-poc-live/config`, mode 0700 directory / 0600 config,
and these environment values: `HOME=/home/lulu`,
`AURELIA_CONFIG_DIR=/tmp/opencode/aurelia-poc-live/config`,
`AURELIA_DAEMON_SOCKET=/tmp/opencode/aurelia-poc-live/daemon.sock`,
`AURELIA_NO_DAEMON=1`, `AURELIA_NO_SPAWN=1`. No credentials were passed.

Exact safe commands (binary is the separately built `/tmp/opencode/Aurelia/target/release/aurelia`):

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
The Mudos library is registered in `libraryfolders.vdf`; Mudos/desktop manifest
paths for AppID 40800 are hardlinked (same device/inode and SHA-256), as are
the game directories. Thus this discovery did **not** establish independent
content in, or safe write behavior against, the canonical Mudos root. It did
show Aurelia sees that root through Steam's registered library list. A future
install test must explicitly target and validate
`/home/lulu/Games/Executables/steam`.

Known installed Mudos AppIDs checked against `CatalogueStore`/local Mudos
manifest enumeration included 26800, 224760, 40800, and 220780. The returned
installed state and titles matched those local records. This establishes
installed discovery and basic local metadata, **not** remote store metadata,
Steam account ownership, launchability under Aurelia, nor entitlement parity.

The adapter's exercised form was:

```sh
python3 /tmp/opencode/aurelia-poc-adapter.py \
  --binary /tmp/opencode/Aurelia/target/release/aurelia \
  --config-dir /tmp/opencode/aurelia-poc-live/config \
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
  and current Mudos has a hardlinked shared view of paths. Establish backup,
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
- **Storage:** discovery found the Mudos path registered, but actual scan
  resolved duplicate hardlinked manifests to desktop path. No import/relink or
  write test was performed. Targeted install must be separately controlled.
- **Recovery:** keep current provider available; never automatically switch a
  game or migrate library state. Provide per-provider opt-in, disable switch,
  independent backups, and tested rollback before any appliance deployment.

## Recommendation

Proceed to a **bounded engineering evaluation**, not replacement. There is
enough evidence that Aurelia can be a useful Steam protocol/install backend and
provide better structured acquisition progress. It demonstrably discovers
Mudos' registered library and several installed games. The largest original
motivation—clean authoritative launch lifecycle—is not solved by current CLI
surface: no live launch event contract, incomplete cancellation semantics for
pre-running launch, PID-based running truth, and no demonstrated Gamescope/
Sessiond integration. First request/assess upstream lifecycle API support; then
run a deliberately approved isolated launch of a low-risk known-good game and
verify process tree, Proton/UMU ownership, Steamworks, presentation, stop, and
account policy. Only after these gates should a fuller adapter phase be scoped.
