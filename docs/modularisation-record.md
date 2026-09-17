# Mudos modularisation engineering record

## Baseline checkpoint — 2026-09-17

The authoritative checkout was clean before this work:

* source: `/home/josh/src/lulu`
* branch: `audit/network-file-browser-1670797`
* commit: `f81a652` (`Checkpoint controller-first OSK integration`)
* rollback tag: `mudos-modularisation-baseline-20260917`
* tests: `PYTHONPATH=src pytest -q` — 289 passed, 47 warnings
* unqualified `pytest -q` is not a valid baseline command here because this
  checkout is src-layout and does not install itself (`ModuleNotFoundError`).
* immutable release: `/opt/lulu/releases/f81a652-candidate-20260917003411`
* manifest: verified with `scripts/release.py verify`
* activation: `/opt/lulu/current` points to that release
* running services after activation: `lulu-acquisition`, `lulu-consoled`,
  `lulu-file-browser`, `lulu-osk@2`, and `lulu-session@2`

The baseline release and tag are never mutated. Deterministic rollback is:

```sh
sudo python3 /home/josh/src/lulu/scripts/release.py verify \
  --release-dir /opt/lulu/releases/f81a652-candidate-20260917003411
sudo python3 /home/josh/src/lulu/scripts/release.py activate \
  --release-dir /opt/lulu/releases/f81a652-candidate-20260917003411
```

Restart the affected `lulu-*` services after activation.

## Reconnaissance

Before this pass, platform identity, runtime executable/core paths, and
provider launch selection lived in `emulation.py` and
`emulator_runtime.py`. Native controller provisioning wrote conventional
provider locations (`~/.config/PCSX2/inis` and `~/.config/dolphin-emu`) and
RetroArch used a generated per-launch append config. RomM used
`~/.config/lulu/providers/romm.json`.

The provider executables available to this checkout use their conventional
Linux user configuration paths. No installed Dolphin, PCSX2, or RetroArch
binary/documentation in the test image demonstrated a supported explicit
config-directory switch that could be adopted safely without changing runtime
semantics. This pass therefore centralises Mudos-owned definitions and makes
provider config roots explicit, while retaining compatibility with native
locations for controller provisioning. See the strategy table below.

## Architecture and decisions

`lulu.platforms` owns content definitions and the platform registry;
`lulu.providers` owns provider definitions, capabilities, and registry;
`lulu.assets` owns logical asset resolution. `paths.py` remains the only
owner of broad filesystem roots. TOML definitions are data, not executable
provider configuration. `emulation.py` remains a compatibility facade for
existing callers while loading the new platform registry.

Provider configuration is persistent native state. Launch code must not
regenerate it as a side effect; controller provisioning only updates the
specific sections it owns and preserves unrelated native settings.

| Provider | Strategy | Actual config location | Persistence verified | Notes |
|---|---|---|---|---|
| RetroArch | DIRECT | `~/.config/lulu/providers/retroarch/config/retroarch.cfg` | unit-level | `--config` selects the Lulu-owned native file; append file is ephemeral input mapping only |
| Dolphin | DIRECT | `~/.config/lulu/providers/dolphin/config/` | unit-level | `--user` selects the Lulu-owned Dolphin user directory; native INI is preserved |
| PCSX2 | DIRECT | `~/.config/lulu/providers/pcsx2/config/PCSX2/inis` | unit-level | PCSX2 honors `XDG_CONFIG_HOME`; native INI is section-merged, not regenerated |
| Steam | N/A | Steam-owned normal paths; games at `~/Games/Executables/steam/steamapps` | existing tests | client state is intentionally not moved |
| RomM | DIRECT (Mudos metadata) | `~/.config/lulu/providers/romm/provider.toml` | unit-level | remote service has no native local config |
| Eden | DIRECT | `~/.config/lulu/providers/eden/config/` | existing tests | Mudos passes the native config file explicitly |

## Testing record

Initial validation passed as recorded above. Further changes and failures will
be appended here with commit and release evidence.

The migration checkpoint at commit `f1865a0` passed `PYTHONPATH=src pytest -q`
with **293 passed**, and `git diff --check` was clean. The release builder
completed successfully at `/opt/lulu/releases/f1865a0-candidate-20260917003916`
and its payload was subsequently verified by the builder before activation.

The native provider binaries were inspected in the test image. RetroArch
explicitly supports `--config` and `--appendconfig`; the existing launch path
continues to use the user's native RetroArch config and a disposable append
file for controller indices, with its runtime `config_save_on_exit=false` safeguard. Dolphin and
PCSX2 did not provide usable non-GUI help output in this session; their
section-preserving native INI adapters remain the compatibility redirect and
do not overwrite unrelated user settings. No emulator was launched during
this pass because the active graphical session is also the test console.

## Phase 2 configuration reconnaissance and migration

The installed provider interfaces provide supported centralisation mechanisms:

* RetroArch 1.22.2 documents `--config=FILE` and `--appendconfig=FILE`.
  Production now selects `providers/retroarch/config/retroarch.cfg`; only
  the per-launch controller index append file remains ephemeral.
* Dolphin exposes `-u USER, --user=USER`. Production passes the provider
  `config/` directory as its user folder, so Dolphin's native INI files are
  physically stored there.
* PCSX2 honors `XDG_CONFIG_HOME`; production sets it to the provider config
  directory. Its native files therefore live below
  `providers/pcsx2/config/PCSX2/`.
* Eden's direct launch accepts an explicit `--config` file. Its controller
  profile and native `qt-config.ini` now live under the Eden provider config
  directory.

Existing `/home/lulu/.config` state was migrated non-destructively: the old
RetroArch config was copied to the selected central file, Dolphin and Eden
trees were copied into their provider config directories, and PCSX2's tree
was copied beneath `config/PCSX2/` to match XDG resolution. Originals were
not deleted or overwritten. `providers/migration.py` is rerunnable and copies
only missing files.

The earlier Phase 1 `REDIRECTED` labels were inaccurate: they described the
conventional locations, not the post-launch physical locations. They are now
correctly classified as `DIRECT` because the provider itself selects or
resolves the Lulu-owned native directory.

Isolated real-provider probes were attempted against the migrated locations.
RetroArch reached its native startup path but exited with the image's
nonfunctional GPU/video backend; Dolphin aborted in its headless environment;
PCSX2 entered its GUI startup and was stopped by the noninteractive timeout;
Eden's portable wrapper exited after reporting that X11 was unavailable.
These are recorded as environment limitations, not claimed launch-persistence
successes. Native file load and persistence are covered by adapter tests; a
full interactive provider launch remains a hardware-session test.

## Phase 2 runtime and asset migration

`EmulatorRuntimeAdapter` now resolves the platform definition, obtains its
declared provider, and delegates command construction to
`providers/runtime.py`. RetroArch, Dolphin, PCSX2, and Eden launch knowledge
is no longer selected by platform branches in the runtime adapter. Core still
owns lifecycle, controller assignment, and process policy; provider adapters
own executable arguments and native configuration selection. Steam and RomM
branches in catalogue/acquisition code remain legitimate provider-local
capability dispatch and are not emulator launch paths.

Local content scanning continues through the compatibility view in
`emulation.py`, but its `PLATFORMS` values are generated from the TOML
registry. Consequently extension filtering, labels, provider defaults, and
BIOS subdirectories come from platform definitions. A GameCube file now uses
the Dolphin provider relationship without a new core conditional. The
compatibility view contains only executable/core resolution needed by legacy
callers and no independent platform list.

The QML asset catalog now exposes `logicalAsset(namespace, name)` and uses it
for system artwork, supplied navigation artwork, and metadata glyphs. This
keeps the existing artwork files and output paths unchanged while preventing
individual screens from constructing those repository-relative paths.

Provider settings are deliberately narrow. No broad emulator settings UI was
invented; the native adapter supports read/write of selected INI keys while
preserving unowned sections and values, and controller provisioning writes
only its owned sections. The boundary is covered by round-trip tests.

Final deployment evidence: commit `0bb9793` passed **293 tests** and was
built as `/opt/lulu/releases/0bb9793-candidate-20260917004001`. The release
manifest verified successfully, all payload files are immutable, and
`/opt/lulu/current` was atomically activated to it. Deployed imports found six
platform definitions (including GameCube) and six provider definitions.

## Cold-boot failure and repair — 2026-09-17

The first post-Phase-1 cold boot produced a blinking cursor. Evidence showed
that `/opt/lulu/current` was valid, but systemd had previously been configured
by the mutable development-runtime workflow. `lulu-session@.service` and
`lulu-consoled.service` had `dev-runtime` drop-ins pointing at
`/opt/lulu/dev-current`; the development workflow had also replaced the
acquisition and OSK unit files. Running its `immutable` cleanup removed those
two units instead of restoring them. Consequently `lulu.target` retained a
dangling `lulu-osk@2` link and Acquisitiond was absent. The immutable shell
then exited with `org.lulu.Acquisitiond ... The name is not activatable`,
leaving the cursor.

Repair restored the packaged unit files and udev rule from the active release,
removed all development drop-ins, reloaded systemd, and restarted the normal
target. `dev-runtime.sh immutable` now performs that restoration itself and
restarts Acquisitiond as part of the cleanup. This is a deployment-script
repair, not a change to the immutable release contents or the Phase 1 tag.

Cold-boot validation after the repair (boot `2026-09-17 08:31`) passed:

* `/opt/lulu/current` remained the active immutable release;
* `lulu-session@2`, gamescope, and `lulu-shell` started successfully;
* Acquisitiond, Consoled, InputPlumber, seatd, and file browser were running;
* no systemd units were failed.

The OSK continues to retry when no InputPlumber DBus target device exists;
this is a controller-availability condition and does not block Mudos shell
startup. A replacement release will include the corrected cleanup script.

## Second cold-boot validation and final repair evidence

The first repaired reboot still showed the shell dependency gap because the
installed `/etc/systemd/system/lulu.target` was an older copy that omitted
`lulu-acquisition.service`, even though the repository target and release
payload included it. Installing `packaging/lulu.target` from the immutable
replacement release corrected the system-level deployment state. The next
cold boot (boot `2026-09-17 08:45`) passed with Acquisitiond started by
`lulu.target`; gamescope and the shell ran from
`/opt/lulu/releases/9bb0ab8-candidate-20260917074311`, and systemd reported no
failed units. This confirms both the source target contract and its deployed
installation are aligned.

## Known limitations at start

Provider binaries were not all runnable in a non-interactive validation
session, so native persistence requires a hardware/runtime smoke pass. Full
third-party provider plugin loading and acquisition-source pluginisation are
deliberately future work.

## Phase 2 final persistence and deployment evidence

| Provider | Final strategy | Physical config location | Mechanism | Real provider tested? | Launch persistence verified? | Service restart verified? | Cold-boot persistence relevant/verified? | Caveat |
|---|---|---|---|---|---|---|---|---|
| RetroArch | DIRECT | `~/.config/lulu/providers/retroarch/config/retroarch.cfg` | `--config FILE` | Yes; `--version` returned 0 | Native file survived invocation | Yes | Yes; file present after boot | Full content run was not safe in headless probe |
| Dolphin | DIRECT | `~/.config/lulu/providers/dolphin/config/` | `--user USER` | Attempted; aborted 134 headless | Not claimed | Yes | Yes; INIs present | Requires graphics-capable session |
| PCSX2 | DIRECT | `~/.config/lulu/providers/pcsx2/config/PCSX2/inis/` | `XDG_CONFIG_HOME` | Attempted; GUI timed out 124 | Not claimed | Yes | Yes; INIs present | Interactive GUI required |
| Eden | DIRECT | `~/.config/lulu/providers/eden/config/` and XDG `eden/` | explicit `--config` plus XDG namespace | Attempted; X11 unavailable outside session | Not claimed | Yes | Yes; native files present | Must run inside gamescope |

These results distinguish file/service/reboot persistence from successful
interactive provider launch. No unsupported live-launch claim is made for
providers that cannot safely run outside the active console.

Final Phase 2 source commit is `8de4eee`; immutable release
`/opt/lulu/releases/8de4eee-candidate-20260917080027` was manifest-verified
and activated. Cold boot `2026-09-17 09:01` verified that release, target
dependency closure, centralized files, running shell, and zero failed units.

## Recent-card launch regression repair — 2026-09-17

`RecentHome.qml` had a binding on `selectedGameId` but imperatively assigned
that property during index changes and reconciliation, destroying the binding.
`ConsoleShell.qml` also kept a second mutable `recentSelectedGameId`. After
the visible card moved, this could launch the stale index-0 game and leave
`homeLaunchGated` set by a mismatched feedback completion.

The repair makes both live identities readonly and derived from the
authoritative selected index/model. Selection anchors and frozen IDs remain
only for reorder/presentation reconciliation. The selection-change signal now
only synchronizes options state.

The deployed candidate was exercised through the real launch boundary. The
catalogue's index-1 game, `local:nes:00946aa2b54b27d0` (Super Mario Bros),
returned a launch token, and Consoled logged and started:

```text
/usr/bin/retroarch --appendconfig <ephemeral-controller-config>
  --config /home/lulu/.config/lulu/providers/retroarch/config/retroarch.cfg
  -L /usr/lib/libretro/nestopia_libretro.so
  /home/lulu/Games/ROMs/nes/Super Mario Bros (E).nes
```

RetroArch was then cancelled through `/cancel`; Mudos returned to its shell
with no failed units. Repair commit: `9b97b66`; Python suite: 297 passed. The
QML runner's unrelated failures require the unavailable `Mudos.Poc` import and
legacy harness assumptions; production shell startup was successful.

## Provider Guide regression repair — 2026-09-17

History identified the regression at `64aeb5c` (`Add Mudos-owned Downloads
surface`). Before that change, `lulu-shell.cpp` returned `Provider Menu` for
normal game contexts and selected contextual labels only for delegated Steam
surfaces. That commit changed the fallback command and label to
`MUDOS_DOWNLOADS` / `Open Downloads`, causing Downloads to replace Provider
globally. The change was not intentional for emulator games.

The fallback is now empty again, while Steam Store retains `Open Downloads`.
RetroArch game processes advertise `Provider` and the Guide keeps Downloads
contextual. Provider settings metadata is resolved by Consoled through the
platform and provider registries. The restored Guide surface currently exposes
one deliberately narrow native setting: RetroArch `fps_show`,
read/written by `NativeConfigAdapter` in the centralized
`~/.config/lulu/providers/retroarch/config/retroarch.cfg` file. The setting
screen toggles the value and supports controller Back without leaking input to
the game. Unsupported providers do not receive a fabricated settings screen.

The live persistence exercise used `fps_show`, which is not overridden by the
ephemeral controller config. Its baseline was `"false"`; the deployed provider boundary changed the native file to `true`,
and `GetProviderGuide` immediately reported `false`. Super Mario Bros was
relaunched successfully with RetroArch using the centralized file. After
restarting Acquisitiond, Consoled, and the graphical session, the setting
still reported `true` and the native line remained present. Cold-boot
validation follows the final release deployment.

## Guide controller mutation trace

The initial functional trace showed Guide input arriving, but Provider metadata
was unavailable because `mudos-guide` queried `GetProviderGuide` on the
`ConsoleSession` interface instead of Consoled. The corrected trace on the
deployed candidate was:

```text
Guide provider metadata ... available:true provider_id:retroarch setting_key:fps_show
Guide input ui_down
Guide input ui_accept
Guide input ui_accept
provider setting mutation requested provider=retroarch key=fps_show value=true
provider setting mutation applied provider=retroarch key=fps_show value=true
Guide provider setting call "true" ReplyMessage
Guide input ui_back
```

This was performed through the real `mudos-guide` QML window and its
controller command stream while Super Mario Bros was running; no direct
provider-setting API call was used in that functional mutation. The native
file changed from `fps_show = "false"` to `fps_show = "true"`, and the Guide
model refreshed its displayed value. A subsequent normal relaunch started
RetroArch with that file, and the value survived service/session restart and
cold boot. `config_save_on_exit` remains forced false in the ephemeral
controller config and is not used as the validation setting.
