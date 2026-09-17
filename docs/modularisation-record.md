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
| RetroArch | REDIRECTED | `~/.config/retroarch` plus Lulu append files | unit-level | RetroArch has no proven direct user-dir flag in image; append file is ephemeral input mapping only |
| Dolphin | REDIRECTED | `~/.config/dolphin-emu` | unit-level | native INI is preserved; Lulu provider root is the declared future migration target |
| PCSX2 | REDIRECTED | `~/.config/PCSX2/inis` | unit-level | native INI is section-merged, not regenerated |
| Steam | N/A | Steam-owned normal paths; games at `~/Games/Executables/steam/steamapps` | existing tests | client state is intentionally not moved |
| RomM | DIRECT (Mudos metadata) | `~/.config/lulu/providers/romm/provider.toml` | unit-level | remote service has no native local config |
| Eden | REDIRECTED | `~/.config/eden` | existing tests | retained compatibility path |

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
file for controller indices, with `config_save_on_exit=false`. Dolphin and
PCSX2 did not provide usable non-GUI help output in this session; their
section-preserving native INI adapters remain the compatibility redirect and
do not overwrite unrelated user settings. No emulator was launched during
this pass because the active graphical session is also the test console.

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
