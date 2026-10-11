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

## Options considered

| Option | Stops writes? | Preserves client functions? | Assessment |
| --- | --- | --- | --- |
| Disable automatic updates / set per-game update policy | No hard guarantee; queued work and client policy can still resume or change | Likely preserves normal client use | Reversible but insufficient as an ownership boundary; observed global window setting did not stop the queue. |
| Stop/restart Steam around installs or deployments | Only while stopped; creates authentication and launch outages, and queued work resumes later | No, unavailable during stop | Not a durable fix and restarts already have operational/start-limit risk. |
| Change Unix ownership/modes or ACLs | No useful separation: both actors use UID `lulu`; changing them would also affect Aurelia and existing content | Uncertain / likely breaks writes needed by Aurelia | Reject. Do not chmod, chown or ACL the live tree. |
| Separate Steam client library and Mudos-managed library | Strong if the client cannot write the managed root, but Steam's launch/DRM integration may expect its installed manifest and library registration | Could preserve the client if a read-only launch view works | Larger migration; the currently registered `Mudos Managed` folder is empty and must not be repurposed without a tested migration plan. |
| Read-only managed-library view in Steam's service mount namespace | Kernel-enforced against every Steam process in that namespace while host Aurelia remains writable | Authentication/client state stays writable outside the managed tree; read-only launch compatibility must be demonstrated | Preferred first prototype: narrow and reversible at the unit boundary. Not proven for live use. |

## Recommended prototype and compatibility boundary

Prototype a systemd mount namespace only for `lulu-steam-runtime.service`,
which contains the resident Steam process tree. Present the canonical managed
`steamapps` tree read-only to that service while leaving the host namespace
writable for Aurelia and Acquisitiond. Inventory candidate writable Steam
state (e.g. shader cache and compatibility data) using synthetic fixtures;
allow only narrowly scoped paths if a read-only launch test proves they are
required and they are not game payload or install metadata. Do not let broad
write exceptions include `steamapps/common`, `steamapps/downloading`, install
manifests, or depot staging. If Steam requires write access to those paths for
DRM/Steamworks launch, stop: do not relax the protection without a revised
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

1. Enumerate the resident Steam service cgroup and prove its processes are in
   the expected mount namespace.
2. Verify from that namespace's mount table that the managed tree is actually
   read-only (not merely a `ro` source mount masked by a writable child mount).
3. Check for Steam content work using independent evidence: active update state
   from the client/log, staged/download activity and open write descriptors to
   Steam content paths. Missing, stale, malformed or contradictory evidence is
   unknown and blocks deployment. Logs alone are not authoritative.
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

Prototype off the appliance with a synthetic library and a throwaway Steam
configuration/account; do not attach the Rocket League library or credentials.
Capture the exact systemd drop-in/mount definition and expected mount table.
Rollback is removal of that isolated drop-in/prototype namespace and a normal
service restart; no host library path, manifest, credential or permission is
rewritten. On the appliance, rollback would require explicit approval, restoring
the previous unit definition and restarting the Steam runtime, with the normal
authentication/start-limit readiness checks. That live rollback is not
authorized by this design task.

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
  refuses missing or writable mount proof; detects a second Steam process or
  unexpected namespace; and rechecks before activation and after restart.
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
