# Steam runtime content-ownership boundary — investigation

**Status:** read-only production baselines for one Windows/Proton and one native
Linux title are recorded below. A controlled clean-install/restart assessment
was not completed and is deferred. The namespace prototype and partial Stage 1
results are preserved as fallback evidence; mandatory production isolation
remains deferred.
Production Steam configuration,
library registration, credentials, service state, mounts, permissions, and game
content were not changed.

## Observed state

- Steam's `libraryfolders.vdf` registers two libraries: the default
  `/home/lulu/.local/share/Steam` and `/home/lulu/Games/Executables/steam`
  (`Mudos Managed`). Steam logs report 29 manifests in the default and zero in
  the latter. Aurelia's private config pins `steam_library_path` to
  `PATHS.steam_library_root`, i.e. the default library. The second registered
  folder is not currently the managed installation root.
- Rocket League's appmanifest and payload are both in the default library. The
  root, `steamapps`, manifest and game directory are owned by `lulu`; the
  relevant filesystem is the same writable Btrfs home subvolume. Resident Steam
  (`lulu-steam-runtime.service`) and Aurelia/Acquisitiond execute as `lulu`.
  File ownership or ordinary mode bits therefore cannot separate their write
  authority.
- The current manifest has `StateFlags=4`, `AutoUpdateBehavior=0`, and installed
  depot 252961 (Linux). Steam's global config has
  `AutoUpdateWindowEnabled=0`. Those settings did not prevent the observed
  update. The Steam log explicitly attributes scheduling to `Priority Auto
  Update` and says updates were disabled for zero seconds.
- Steam's retained schedule was repeatedly suspended during runtime restarts.
  On startup it resumed the scheduled AppID 252950 operation, fetched depot
  252961, and committed 5,997 changed files from
  `steamapps/downloading/252950` into `steamapps/common/rocketleague`. This is
  the evidenced immediate trigger. The logs do not establish the original event
  that first put the update into Steam's schedule. The appmanifest's prior
  `StateFlags=2` was an Update Required condition; the old stub/partial state
  likely made Steam consider the app updateable, but the precise initial
  trigger is unproven.
- **Evidence boundary:** Steam's resumption of this previously queued update
  against Rocket League's inconsistent post-experiment installation is
  confirmed. Routine interference with a healthy Aurelia-managed game, or
  replacement of explicitly selected Windows content by Linux depots, remains
  unproven. Do not generalize from the Rocket League event without the clean
  writable-library experiment.
- `AureliaClient.spawn_play()` invokes Aurelia with `--steam --no-update` and a
  Mudos graphical wrapper. Aurelia documents `--steam` as using the host Steam
  client for Steamworks integration; the established appliance requirement is
  also authenticated Steam for DRM. `--no-update` controls Aurelia's launch-time
  update check, not the resident client's independent scheduler. Aurelia still
  reads the canonical library/manifests for installed inventory, update checks,
  platform metadata and launches. Authentication, DRM and Steamworks need the
  resident client, but investigation has not yet proven which filesystem paths
  it must write during launch.

## Disposable systemd namespace prototype (2026-10-11)

`scripts/steam-ownership-prototype.py` ran a transient, uniquely named systemd
oneshot unit as the ordinary development user. It created and used only a
synthetic library under `/tmp/opencode/steam-ownership-*`; the transient unit
was collected after exit. It made no persistent unit/drop-in and never used the
production Steam paths. The successful run reported:

```text
ProtectSystem=strict
BindReadOnlyPaths=<synthetic>/home/steam/steamapps:<same path>
TemporaryFileSystem=<synthetic>/home/steam/steamapps/shadercache:rw,mode=0755,uid=<test uid>,gid=<test gid>
TemporaryFileSystem=<synthetic>/home/steam/steamapps/compatdata:rw,mode=0755,uid=<test uid>,gid=<test gid>
```

The exact invocation and deterministic fixture construction live in the script;
systemd-run applied these properties to a real transient service. The probe
read its own `/proc/self/mountinfo`, confirmed a read-only bind root and two
separate writable tmpfs child mounts, and exercised operations in that service
namespace. One representative run passed all checks and reported namespace
`mnt:[4026532759]` versus caller/host namespace `mnt:[4026531832]` (namespace
IDs vary per run).

Guard-only fixture helpers are in
`scripts/steam-ownership-guard-prototype.py`, with deterministic tests in
`tests/test_steam_ownership.py`. They deliberately live under `scripts/`, not
the packaged `src/lulu` runtime, and have no production callers.

**Protected synthetic tree:** the entire `steamapps` root, including game
payloads (`common`), `appmanifest_*.acf`, library metadata, `downloading`,
`temp`, depot/cache metadata and Workshop content. The only exceptions were
the synthetic `shadercache` and `compatdata` paths, mounted as fresh tmpfs
instances so they did not share writable inodes with the protected fixture
filesystem. These exceptions are prototype-only and ephemeral.

Evidence from the successful run:

- Payload append/replace, manifest rewrite, existing stage rewrite, new stage
  creation and simulated commit into the game directory were all denied.
- An in-tree symlink to protected payload and an external symlink to another
  otherwise writable fixture path were denied. Hardlink creation from protected
  content into the writable exception failed with `EXDEV` because the exception
  is a distinct tmpfs filesystem.
- A child Python process inherited the same read-only denial.
- Synthetic shader-cache and compatibility-prefix writes succeeded in their
  distinct tmpfs exceptions. This proves only filesystem write behavior; it
  does not prove Steam or a game can use those paths correctly.
- After the unit exited, the caller (simulated Aurelia/Acquisitiond) wrote
  `host-acquisition` into the **same underlying payload file** successfully.
  The host and service reported different mount-namespace IDs.
- The actual mountinfo validator confirmed the root `ro` and only the two
  allowlisted `rw` descendants. A second, deliberately unsafe transient unit
  added a writable bind at `steamapps/downloading`: a stage-file write then
  succeeded, and the guard helper rejected that actual mount table with
  `writable child mount defeats protected root`. Deterministic tests reject
  missing/read-write protected roots, duplicate writable root mounts,
  unexpected writable child mounts, missing exceptions, Steam processes
  outside the expected cgroup, unverified nested helper namespaces, and
  unknown/active Steam operation evidence.

This experiment deliberately combines `ProtectSystem=strict` with the
read-only library bind. The strict setting makes the rest of the host
filesystem read-only in the test namespace, which prevented the external
symlink from escaping. The separate tmpfs exceptions also prevented a
hardlink-based route into writable runtime state. A simple `BindReadOnlyPaths`
on `steamapps` alone would **not** prove those stronger properties: another
writable path or mount alias can defeat a narrow tree-only check. The live
design therefore needs a reviewed sandbox plus explicit, separately mounted
state exceptions, not just the one bind line.

The probe unit uses no Steam binary or actual Steam directories. It proves the
systemd mechanism for a synthetic tree, not that the proposed profile is
compatible with Steam's self-update, session persistence, or game launch.

## Disposable real-Steam Stage 1 results (2026-10-11; partial; preserved)

### Isolation and authentication

- Test host: Lulu, using dedicated temporary Unix account `steamstage1`, a
  separate HOME/Steam configuration, Xvfb `:190`, private D-Bus and XDG runtime
  state, `ProtectHome=tmpfs`, `ProtectSystem=strict`, and transient systemd
  services. Client and test library were separate Btrfs subvolumes; runtime
  exceptions were separate Btrfs subvolumes. No production library path was
  registered or mounted in the test client.
- The operator authenticated the existing account in the isolated UI. The
  signed-in UI remained available after one clean client shutdown/restart.
  Steam's client self-update completed in the isolated client subvolume.
- A later explicit sign-out returned the isolated client to its login screen.
  The transient service was stopped and the test account, client subvolume
  (including its local auth/config/log state), library subvolumes, and bridge
  artifacts were removed. Btrfs subvolume deletion removes the test state
  logically but is not a guarantee of forensic media sanitization.

### Native Linux launch and ownership

- Braid (AppID 26800, Linux x86 build, approximately 164 MB) was acquired only
  into the disposable library. Baseline Steam launch rendered and accepted
  keyboard input without advancing a saved game.
- With `steamapps` read-only and only separate persistent `compatdata` and
  `shadercache` subvolumes writable, Steam began the launch but Pressure Vessel
  exited while trying to update
  `common/SteamLinuxRuntime_soldier/.../files/.ref`. A per-file writable bind
  experiment then exposed additional per-run runtime temporary-directory writes;
  this narrow exception set was insufficient.
- The successful read-only launch profile mounted the Steam Linux Runtime
  package itself from a separate writable Btrfs subvolume at
  `steamapps/common/SteamLinuxRuntime_soldier`, alongside the `compatdata` and
  `shadercache` subvolumes. Braid then rendered under the RO game-content view.
  The runtime exception was about 673 MB and includes executable runtime files;
  it is evidence for a future separate Steam-owned runtime store, not a
  production approval to make this path writable in place.
- Steam could read a host-created marker through the restricted view but could
  not overwrite it. Direct attempts to open a payload, appmanifest, and staging
  file for writing failed with `EROFS`; a hardlink from payload into runtime
  state failed with `EXDEV`. The host-side simulated acquisition process
  removed its marker after the check. Mountinfo from the live Steam process
  showed the protected root `ro` and only the declared Btrfs state mounts `rw`.
- Steam repeatedly logged that it could not write the read-only game
  appmanifest while tracking launch state. The Steam client remained active and
  systemd reported no restart loop. Steam Linux Runtime writes are therefore a
  real requirement; Steam's game-appmanifest write attempts are observable but
  tolerated by this title/client for a launch. Their effect on other games and
  queued-update recovery is not established.

### Compatibility not established

- Braid's process log reported its Steam API was not loaded, and Shift+Tab did
  not display the overlay. Do **not** count this as Steamworks or DRM evidence.
- No Windows/Proton title was installed or launched. No DRM-protected title or
  positively identified Steamworks-using title was accepted. No controller test,
  Aurelia `--steam --no-update` test, autonomous game update/retry test, pending
  update/restart test, or real update-stage denial/recovery test was completed.
  The real Steam child process namespace tree was not fully enumerated; only the
  Steam process mount table and process/cgroup launch evidence were captured.
- The account library remained visible in the isolated UI, but no claim is made
  that entitlements/cloud-save safety were independently verified per title.
  Steam Cloud was disabled in the isolated client before Braid testing; no
  production cloud setting was changed. Braid's API/save behavior still needs
  confirmation with the next test title.

### Diagnostic containment and hardening

During a diagnostic operation, connection-log content containing an
authentication credential appeared in a tool result. It was not written to
repository files, commits, or a retained test export, but the tool transcript
cannot be retracted; this is not represented as “no exposure.” The isolated
client was explicitly signed out, then stopped, and its dedicated Btrfs client
subvolume (including local auth files and logs) was deleted. The production
Steam runtime remained active with the same invocation, PID, and zero restarts.
No production credential/configuration/library data was read or changed by the
cleanup. The host's systemd service journal is retained normally; Steam's own
crash reporter also uploaded test-client assertion minidumps automatically, and
those dump contents were not inspected. This incident is recorded without
including credential text.

Diagnostics now use `scripts/steam_auth_status.py`, which returns only
`authenticated`, `not_authenticated`, or `unknown`; `steam-runtime-session.py`
does not decode or print connection-log lines and discards Steam child stderr.
`steam-lifecycle-probe.py` emits allowlisted launch metadata instead of raw
process arguments, titles, or window classes. `steam-auth-surface.py` filters
authentication fields and uses static error messages. Synthetic token-bearing
tests cover stdout, stderr, exceptions, lifecycle output, and a test diagnostic
export; they verify that only predefined statuses/fields are emitted.

### Prior continuation gate (closed for clean-install reassessment)

The isolated client, account, and test subvolumes were removed after Stage 1
cleanup, then recreated fresh for this continuation. The transient
`steam-compat-stage1-real.service` ran as the dedicated `steamstage1` account
with `ProtectHome=tmpfs`, `ProtectSystem=strict`, private `/tmp` and D-Bus, and
only the dedicated test HOME/library bound back into its namespace. A startup
check fails if `/home/lulu` is visible. Steam stdout/stderr are discarded.

The disposable library's `steamapps` tree was a read-only bind. Writable
`compatdata`, `shadercache`, and `SteamLinuxRuntime_soldier` are separate Btrfs
subvolumes outside that protected library subvolume and are mounted only at the
declared child paths. `SteamLinuxRuntime_soldier` remains the extra runtime
exception required by the earlier Braid experiment; it is not game-payload
storage. Before starting Steam, the service verified `steamapps` read-only,
each allowed state mount read-write, payload/staging denial (`EROFS`), runtime
state write success, hardlink denial (`EXDEV`), and rejection of a symlink from
writable state back into protected payload. Only a synthetic marker is present;
this fresh library has no downloaded or installed game.

The isolated Xvfb `:190` client had been left running after the prior task. Its
viewer used a private
Unix socket at `/run/steam-stage1-viewer/bridge.sock`, with filesystem access
limited to the operator account; it is not a TCP listener and the test account
is denied access to the viewer. It disables HTTP access logging, does not save
or log keyboard input, and passes no typed text in child process arguments.
From the operator workstation, forward that remote Unix socket to local port
18765, then open `http://127.0.0.1:18765/`. The SSH forwarding command is:

```sh
ssh -N -L 18765:/run/steam-stage1-viewer/bridge.sock lulu
```

The operator subsequently authenticated this isolated client. The prior task
verified authentication only through the hardened status classifier, disabled
Cloud in this isolated client, confirmed the setting persisted over restart,
and verified separate writable state-subvolume canaries survived restart.
Attempts to acquire Braid and Spacewar produced no appmanifest or staged game
content; no game launch or update test occurred. This is not evidence of
healthy-install Steam behavior. The prior Stage 1 unit has since been stopped;
its six Btrfs test subvolumes, stale viewer socket, and dedicated
`steamstage1` account were retired without touching production Steam. The later
empty clean-test directory was also removed. Never attach production HOME,
credentials, libraries, or game content.

## Clean writable-library experiment (not performed; deferred)

The proposed controlled test would use a fresh dedicated HOME, Steam configuration,
Steam library, and isolated Aurelia config/state. The game library must be
normally writable (no read-only bind or mount namespace protection), and both
Steam and Aurelia must point to exactly that disposable library. No production
Steam credentials or library registrations may be present. Disable Cloud in
the isolated Steam UI before acquiring a game. Inventory registered libraries,
appmanifests, update queue/staging, and content files before installation.

Use official Aurelia to install a small, operator-owned title with both Windows
and Linux depots where practical, explicitly selecting Windows. Confirm the
installed appmanifest, depot and manifest IDs, executable, Aurelia installed
status, and Proton route before starting Steam against the same library. Do not
manually trigger a Steam update. Compare Steam's recognition/current/queue
state, manifests, depot set, and payload checksums/metadata both after discovery
and after a clean Steam shutdown/restart. Distinguish metadata rewrites from
payload modifications. A failed installation is a provider/configuration
blocker, not evidence for or against autonomous updates.

This clean-install experiment was not completed: the isolated Aurelia CLI found
no registered library, no Aurelia session existed, and no owned title was
verified. It is not in progress and is not resumed by this production-baseline
assessment. The mount-namespace prototype remains a fallback proposal rather
than a mandatory production architecture change.

### Attempted clean-environment setup (2026-10-11; Outcome C)

The previous transient `steam-compat-stage1-real.service` was stopped cleanly.
Production `lulu-steam-runtime.service` remained active with the same PID and
invocation and zero restarts. A new private test HOME/config/data/cache tree was
created at `/home/.steam-aurelia-clean-20261011`; it contained no copied Steam
or Aurelia credentials and was not used to start Steam. The `steamstage1` Unix
account and its isolated client state have since been retired.

With `HOME` and XDG paths set to the fresh tree, official Aurelia 0.1.37
`libraries --json` returned `{"libraries":[]}`. Its CLI supports explicit
`install --platform windows --library <path>`, but the fresh Steam configuration
has not registered any library. The fresh Aurelia config has no session, and no
owned-game entitlement was verified. The prior Steam UI's authenticated state
was not copied or reused. No game was selected, no installation/update was
started, and no Steam client was started in this fresh tree. The experiment
therefore ends before a healthy installation and provides no evidence about
Steam's normal update behavior (Outcome C).

No further isolated install attempt is part of this task. Any future resumption
requires a separate request and must establish Aurelia authentication without
copying session/credential material, register one disposable library in both
tools, disable isolated Cloud, and preserve the normal writable-library test
condition. Do not use production content or infer a result from the incomplete
setup.

## Production two-title baseline (2026-10-11; read-only; restart withheld)

The operator selected these already-installed titles as complementary
baselines.
No install, update, verify, repair, remove, migration, or game launch was run.
The hardened Steam authentication diagnostic classified the recorded connection
log as `authenticated` without displaying its contents. Aurelia 0.1.37
recognized both installations, and its read-only global `update` report had no
updates. Per-title catalogue state was `is_installed=true`, platform as below,
`update_available=false`, and `update_queued=false`.

| Title / AppID | Content location / actual installed platform | Appmanifest evidence | Installed depot manifest IDs | Executable evidence |
| --- | --- | --- | --- | --- |
| SILENT HILL 2 / 2124490 | `/home/lulu/.local/share/Steam/steamapps/common/SILENT HILL 2`; Windows; Aurelia reports `windows` | `StateFlags=4`, build `17080069`, `LastUpdated=1790838711` (2026-10-01 07:11:51Z), manifest mtime 2026-10-11 03:56:03Z | `2124491=4138456104249046245` | `SHProto/Binaries/Win64/SHProto-Win64-Shipping.exe`, PE, 142,126,592 bytes; SHA-256 `c21ae87cdd186ca22760ad7aa66973eaac2a4d9a4e437a3b42daaab08eb729bc` |
| Super Meat Boy / 40800 | `/home/lulu/.local/share/Steam/steamapps/common/Super Meat Boy`; native Linux; Aurelia reports `linux` | `StateFlags=4`, build `3241924`, `LastUpdated=1790777656` (2026-09-30 14:14:16Z), manifest mtime 2026-10-10 07:21:28Z | `40802=6556596646716197166` (Linux), `98011=915545047853675884` (shared) | `amd64/SuperMeatBoy`, ELF x86-64 (`e_machine=62`), 2,553,803 bytes; SHA-256 `91dfebedbdd5add0fb81535d710bb492cabb23244f733162d8984a0b154158b2` |

Read-only `aurelia manifests` showed the installed IDs match the current public
branch targets for both titles. Silent Hill's Windows platform is verified by
the installed PE executable (its installed depot itself has no OS config tag);
Super Meat Boy's native platform is verified by
the installed Linux depot and ELF executable, not inferred merely from Linux
support. Both manifests have `StateFlags=4`; no `StateUpdateRequired` flag was
set. The library held 29 appmanifests; none had that update-required flag.
Aurelia's global update report returned empty, the user session was in shell
with no launch token, `aurelia running` and install list were empty, and
Acquisitiond reported zero active downloads. No matching Acquisitiond history
jobs for these AppIDs were present (104 total jobs).
Both per-game Aurelia launch configs report `platform_preference=null` and
`runner=auto`; no per-game Proton version is forced. The installed formats and
Aurelia's detected platform establish the present content route, not a pinned
future platform preference.

### Historical content log and current file evidence

The content log was processed in memory through the existing
`steam-ownership-guard-prototype.py` classifier and a fixed-category reducer;
raw log lines were never emitted. It contains 606 AppID 2124490 records and 151
AppID 40800 records. After each manifest's `LastUpdated`, the reduced records
include respectively 95/22 queued-state transitions, 25/9 scheduler starts,
23/5 `starting commit` records, and 1/2 update-finished records. The latest
matching events were 2026-10-11 04:56:03Z and 2026-10-10 08:21:28Z. Each
appmanifest's filesystem mtime is later than its `LastUpdated` field. This is
evidence consistent with resident Steam queue/scheduler/commit work and later
manifest writes, but the log does not identify which caller initiated every
operation. Acquisitiond has no matching jobs; unrecorded direct Aurelia CLI
activity is not ruled out. Consequently no exact Aurelia install-completion
timestamp is available; appmanifest `LastUpdated` is a comparison point, not a
verified Aurelia installation timestamp.

The current tree totals were 262 regular files / 36,453,523,043 bytes for
Silent Hill 2 and 64 / 263,542,849 bytes for Super Meat Boy. Comparing file
mtimes to each manifest's `LastUpdated`, no other game-payload file was newer.
Newer Silent Hill files were `cover.jpg`, `steam_appid.txt` and vkd3d-proton
runtime caches; newer Super Meat Boy files were `cover.jpg` and
`UserData/steam_autocloud.vdf`. Current executable hashes are recorded above,
but there is no pre-event checksum baseline. Therefore actual historical payload
byte changes are **not established**, while Steam content-operation activity
and later appmanifest mtimes are observed. Both currently installed depot sets
still match Aurelia's public targets and their intended platforms.

### Restart gate and result

Before considering a restart, the full content log was reduced to activity
states, staging/temp directories and all appmanifest update flags were inspected,
and Steam process file descriptors were checked for content-path write access.
There were no entries under `steamapps/downloading`, no manifest with
`StateUpdateRequired`, and zero open Steam write descriptors. However, the
conservative historical-log helper classified overall library activity as
`active`; AppID 1332010 reduced to active and AppID 7 to unknown. Aurelia lists
1332010 (Stray) as not installed. `steamapps/temp` contained entries `1712830`,
`2225070`, and `48000`. These records may be stale or unrelated to the two
baseline games and do not prove a live operation, but they also do not establish
a safely idle queue. Following the explicit fail-safe condition, no restart was
performed. Production `lulu-steam-runtime.service` remained at PID 2071116,
invocation `972cd8168e4f4108b5928b098617716e`, `NRestarts=0`; Mudos services
stayed active.
There is no post-restart comparison and no claim that these two games were
untouched by all historical Steam activity.

### Assessment

The baseline confirms the intended Windows/Proton and native Linux
installations are currently Aurelia-recognized, fully installed, and manifest-current under
the normal shared writable library. Historical Steam queue/scheduler/commit
events mean this is **not** evidence that resident Steam never manages their
content; however, current depot/platform state is coherent and no historical
payload byte change is proven. This two-title observation alone does not justify
deploying filesystem isolation. Keep the namespace implementation deferred and
the issue open; do not restart through active/ambiguous content evidence. The
isolated Stage 1 unit, six Btrfs test subvolumes, stale viewer socket, dedicated
Unix account, and empty second test tree were retired. Btrfs subvolume removal
is logical cleanup, not a claim of forensic media sanitization. Production
Steam and Mudos state were not modified.

## Operational conflict signals (assessment only)

Acquisitiond's idle snapshot is not evidence that the resident Steam client has
no content operation. Steam's content log, `downloading`/`temp` and manifest
state, active Steam processes, and open writers to content paths can corroborate
activity. No supported authoritative idle API has been established, and log
silence or a one-time filesystem/process scan cannot prove inactivity or close
a race. Do not introduce log parsing or deployment-policy changes as part of
this evidence-gathering task. A later lightweight conflict check should avoid
known overlap and defer on ambiguous evidence, but must not treat that as proof
that a kernel namespace is required.

The OOBE readiness-test failure present at commit `9dafec0` was a stale fixture
expectation: it injected only the legacy `steam` entitlement source, while
current reconciliation intentionally handles `steam-aurelia`; no readiness
record should be invented for the unused legacy source. The test now asserts
that the legacy source refresh and interactive auth verifier remain unused.
The focused OOBE and Steam regression tests pass.

## Required writable-state inventory (not verified by live experiments)

Read-only inventory found these state locations:

- Steam authentication/client state: `config/` (including `loginusers.vdf`),
  `userdata/<account>/`, `appcache/`, and Steam's client installation/runtime
  directories (`ubuntu12_*`, `steamrt*`, `package/`). Authentication and client
  logs (`connection_log.txt`, `content_log.txt`, etc.) are under `logs/`.
  Steamworks metadata/cache includes `appcache/appinfo.vdf` and per-user state.
  These are outside `steamapps` except the app's manifests. Which exact files
  Steam must mutate during normal authenticated startup has not been
  experimentally established here.
- Steam logs under `logs/` and content operation logs are expected to be
  writable for normal diagnostics; the prototype did not attempt a Steam
  startup.
- `steamapps/shadercache` is a plausible cache write location.
- `steamapps/compatdata` contains Proton prefixes and is expected to need writes
  for a Windows/Proton launch.
- `steamapps/common`, `downloading`, `temp`, `appmanifest_*.acf`,
  `libraryfolders.vdf`, `depotcache`, and `workshop/content` can hold payload,
  install state, or staging data and must not be writable exceptions.

These are classifications, not claims that authentication, DRM, Steamworks,
native launch or Proton launch work under the tested restrictions. The current
Steam client and authentication state are inside the home Steam tree; a live
profile cannot simply make all of that tree read-only without testing the
client's persistence needs. Writable persistent state exceptions must be
separate filesystem/subvolume views, or otherwise proven unable to alias
protected content via hardlinks or mounts. Do not use synthetic tmpfs cache
exceptions as a production configuration.

## Options considered

| Option | Stops writes? | Preserves client functions? | Assessment |
| --- | --- | --- | --- |
| Disable automatic updates / set per-game update policy | No hard guarantee; queued work and client policy can still resume or change | Likely preserves normal client use | Reversible but insufficient as an ownership boundary; observed global window setting did not stop the queue. |
| Stop/restart Steam around installs or deployments | Only while stopped; creates authentication and launch outages, and queued work resumes later | No, unavailable during stop | Not a durable fix and restarts already have operational/start-limit risk. |
| Change Unix ownership/modes or ACLs | No useful separation: both actors use UID `lulu`; changing them would also affect Aurelia and existing content | Uncertain / likely breaks writes needed by Aurelia | Reject. Do not chmod, chown or ACL the live tree. |
| Separate Steam client library and Mudos-managed library | Strong if the client cannot write the managed root, but Steam's launch/DRM integration may expect its installed manifest and library registration | Could preserve the client if a read-only launch view works | Larger migration; the currently registered `Mudos Managed` folder is empty and must not be repurposed without a tested migration plan. |
| Read-only managed-library view in Steam's service mount namespace | Kernel-enforced against every Steam process in that namespace while host Aurelia remains writable | Authentication/client state stays writable outside the managed tree; read-only launch compatibility must be demonstrated | Preferred first prototype: narrow and reversible at the unit boundary. Not proven for live use. |

## Recommended prototype and compatibility boundary

The tested synthetic profile was `ProtectSystem=strict`, a read-only bind of
the complete `steamapps` tree, and two distinct tmpfs exceptions for
`shadercache` and `compatdata`. It is stronger than a single read-only bind:
the strict namespace prevented writes through external symlinks and all other
host paths. For a live profile, keep the same system-wide read-only principle,
but do **not** use ephemeral tmpfs for persistent state. Provide narrowly
scoped, persistent mutable Steam client/session/log/runtime state and the two
game runtime paths through separately mounted, dedicated state filesystems or
Btrfs subvolumes that cannot share inodes with protected game content. Exact
paths and persistence mechanics remain to be designed and reviewed. Do not use
`ReadWritePaths` to reopen arbitrary paths on the same managed-content
filesystem without a hardlink/alias proof. Do not let exceptions include
`steamapps/common`, `steamapps/downloading`, appmanifests, `temp`, depot
staging, or Workshop content. If Steam requires write access there for
DRM/Steamworks launch, stop: do not weaken the restriction without a revised
design and operator review.

The design's intended preserved functions are Steam login/session, license/DRM
checks, Steamworks client integration, and launching already-installed content.
It intentionally prevents Steam-client installs/updates/removals from being
the content-management path. Aurelia/Acquisitiond retain full host-side access,
including the explicit Windows/Linux selection and platform-aware installation
submission from STEAM-PLATFORM-001. Steam UI may report update-required or
write errors; do not hide those signals. Running an application whose depot is
out of date may still fail, and there must be no implicit fallback update.

## Guarded deployment additions

The existing `guarded-deploy.py` checks Acquisitiond states but cannot see an
operation initiated by Steam. The guard should fail closed unless it can:

1. Enumerate the resident Steam service cgroup and scan `/proc` for Steam
   executables outside it. Read mount namespace IDs for every cgroup member;
   helpers such as pressure-vessel may create nested namespaces, so do not
   require all PIDs to have the exact same namespace ID.
2. For **each** distinct service/child namespace, inspect its own mount table
   and prove the protected roots are actually read-only (not merely a `ro`
   parent masked by a writable child mount). Accept only declared, separately
   mounted runtime-state exceptions. Unknown processes, namespaces or mount
   records fail closed.
3. Check for Steam content work using independent evidence: active update state
   from the client/log, staged/download activity and open write descriptors to
   Steam content paths. Missing, stale, malformed or contradictory evidence is
   unknown and blocks deployment. The prototype classifier requires an
   explicit fresh-evidence assertion; the guard must establish freshness from
   timestamps/collection success rather than trusting the log contents alone.
   Logs alone are not authoritative.
4. Repeat the check directly before activation and during post-restart
   readiness. Keep rejecting known queued/in-progress Steam work rather than
   restarting through it. Acquisitiond's explicit job-state checks remain
   required.

The mount boundary prevents a Steam write racing between the final check and
activation; the activity check provides operator safety and detects attempts.
Until both are implemented and fixture-tested, Steam readiness/authentication
must not be treated as evidence of content idleness. The current guard is not
yet sufficient for an online deployment where Steam content ownership matters.

## Rollback and required validation

The synthetic mount mechanism is validated, but a real Steam-client sandbox
prototype with a disposable test account and synthetic libraries remains a
separate phase. Never attach the Rocket League library or credentials.

### Proposed live rollout sequence (not authorized)

1. **Complete design and disposable-client phase.** Decide exact persistent
   client/auth/log/runtime state locations and filesystem/subvolume boundaries.
   Test the real Steam client with a throwaway account and only synthetic
   libraries under the exact candidate systemd profile. Prove client
   self-update, authentication persistence, native and Proton launch, DRM and
   Steamworks; do not treat a failed function as grounds for a broad writable
   exception. Complete integration of the guard evidence checks, but leave
   them gated/off until the service boundary is deployed.
2. **Obtain live maintenance approval.** Approval must name the precise unit
   drop-in, mount targets and persistent-state layout; explicitly permit one
   planned Steam runtime restart and acceptance launches using named non-Rocket
   League test titles; accept possible Steam reauthentication. If moving or
   creating storage subvolumes is required, obtain a separate storage/content
   migration approval. No install/update/remove of Rocket League is included.
3. **Capture baseline and quiesce.** Record unit/drop-in hashes, selector,
   Steam readiness/authentication, start-limit counters, service cgroup,
   mountinfo, library registrations, manifests and available Btrfs snapshots.
   Confirm shell idle, no game/session, no active Acquisitiond job, no active or
   queued Steam content operation and no staging writer. Do not clear queues or
   modify the library to achieve quiet. Abort if any evidence is unknown.
4. **Apply the reviewed unit delta only.** Preserve the prior unit file and
   drop-ins for rollback. Install the approved namespace configuration and
   reload systemd; do not alter Steam's library registration or game files.
   Restart Steam once during the approved window. Inspect `/proc/<pid>/cgroup`,
   mount namespace IDs and `/proc/<pid>/mountinfo` for the complete process
   tree, including every nested helper namespace; verify protected roots and
   only declared persistent state exceptions. Verify Steam returns to
   authenticated READY and no start-limit/restart churn occurs.
5. **Validate without content mutation.** Prove denied writes against synthetic
   bind-mounted marker files only. Using operator-approved, already-installed
   non-Rocket League titles, test native and Proton launch, DRM/Steamworks, and
   Return-to-Home. Confirm no install/update/remove begins in Steam and confirm
   Aurelia/Acquisitiond retain host-side authority on synthetic fixtures. Then
   enable the deployment-guard checks only in a separately reviewed release;
   test refusal on unknown/active Steam work, unexpected Steam process,
   namespace escape, writable child mount and stale status. Do not deploy while
   Steam work is active.
6. **Accept or rollback.** Keep the change only after all required readiness,
   controller/presentation, authentication, native/Proton, lifecycle and guard
   checks pass. If any check fails, stop further launches and content actions;
   do not retry Steam restarts repeatedly. Restore the exact previous unit and
   drop-in, reload systemd, and make at most one approved runtime restart.
   Recheck start-limit allowance before that restart; if exhausted or uncertain,
   stop and request operator intervention rather than `reset-failed`/restart
   loops. Verify prior authenticated readiness if possible, and confirm Steam
   library registration, Rocket League manifest/content, credentials and
   Acquisitiond history are unchanged. Remove only newly created, empty
   prototype state mounts after proving no process uses them; retain evidence
   and report any incomplete rollback.

This rollout and rollback plan is a proposal only. No live unit/drop-in,
filesystem mount, production service lifecycle, Steam configuration or installed
game test was changed or authorized by this prototype task.

**Exact authorization requested before proceeding:** first, approve a separate
disposable Steam-client compatibility phase using a throwaway account and
synthetic libraries only. After its results are reviewed, separately approve a
written appliance change plan naming the exact unit/drop-in and persistent
state mount paths, one planned Steam runtime restart, the named non-Rocket
League acceptance titles/actions, the maintenance window, and the rollback
owner/procedure. Approval of storage/subvolume creation or migration must be
explicit and separate. Any game install/update/remove—including Rocket
League—requires its own explicit content-operation authorization. No approval
is implied by this prototype request.

Required regression cases before live review:

- Synthetic install/update/remove requests from Steam cannot alter payload,
  appmanifest, download/staging directories or depot state in the managed tree.
- Host-side Acquisitiond can still install and update fixture titles, including
  selected Windows and Linux depots; selected platform persists through update
  checks and job recovery.
- Steam authentication succeeds; Steamworks/DRM launch and an already-installed
  native game and Proton game work with the intended read-only content view.
  Exercise normal per-user config and shader writes only in approved isolated
  locations. Any failed launch is a compatibility failure, not permission to
  add broad write access.
- Guard refuses active, queued, unobservable and malformed Steam operations;
  refuses missing or writable mount proof in every nested namespace; detects
  a second Steam process or unexpected namespace; and rechecks before
  activation and after restart.
- Guard's existing Acquisitiond, controller, Sessiond, rollback, and restart
  tests continue to pass. Unit stop/start remains bounded and authenticated;
  the deployment must not trigger repeated Steam restarts.
- Inspect rollback with synthetic data and confirm the host library, credentials,
  service state, and manifests remain unchanged.

## Approval gate

This investigation authorizes documentation and a disposable, synthetic
prototype only. It does **not** authorize a live unit/mount change, Steam
restart, library re-registration, or testing against installed games. Before
any live implementation, the operator must explicitly approve the reviewed
prototype, the exact unit and mount delta, expected authentication/launch
compatibility, the maintenance window, and the rollback/restart plan. Keep
Rocket League's current Linux installation as evidence; do not reinstall,
update, uninstall or migrate it for this work.
