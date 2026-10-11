# Steam runtime content-ownership boundary — investigation

**Status:** design proposal only. No Steam configuration, library registration,
credentials, service state, mounts, permissions, or game content was changed.

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
