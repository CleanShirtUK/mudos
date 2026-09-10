# USB Provisioning Plan

Status: first implementation. This document defines the production deployment
mechanism for a fresh CachyOS installation. The implementation is under
`deploy/`; it does not deploy to, or make assumptions about, the BC-250
hardware.

## Scope

The production mechanism is one repository-owned script at the USB root:

```text
sudo ./install-mudos.sh
```

The script is run locally from removable media. It may use the network for
packages, but the Mudos application and static files come from the USB payload.
The reference implementation is commit `7c96e06`, tag
`known-good-test-environment-20260910`, and
`docs/known-good-test-environment-20260910.md`.

This plan deliberately excludes package creation, image building, Ansible, and
other configuration-management systems. A shell script is sufficient provided
that it stages repo-owned files, uses `install` and package-manager operations
that are safe to repeat, and verifies each boundary.

## USB Layout

The USB should contain an immutable, self-contained payload made from the
reference commit:

```text
USB/
├── install-mudos.sh
├── CHECKPOINT
└── payload/
    ├── lib/                         # src/lulu Python package, installed as-is
    ├── bin/                         # lulu-shell, mudos-guide, lulu-vt, verifier
    ├── config/
    │   ├── inputplumber/
    │   │   ├── devices/lulu-composite.yaml
    │   │   └── profiles/{game,shell}.yaml
    │   ├── retroarch/autoconfig/udev/Microsoft X-Box 360 pad.cfg
    │   └── ...                      # Mudos UI/static/config assets
    ├── scripts/                     # runtime helper scripts
    ├── packages/
    │   ├── pcsx2/                   # reviewed, pinned PKGBUILD fallback
    │   └── rapidyaml/               # reviewed, pinned dual-package fallback
    ├── packaging/
    │   ├── lulu.target
    │   ├── lulu-session@.service
    │   ├── lulu-consoled.service
    │   ├── lulu-session.pam
    │   ├── lulu-vt
    │   ├── inputplumber-restart.conf
    │   ├── presentation.conf
    │   └── pipewire/lulu-fallback-input.conf
    └── manifest.sha256               # hashes for payload files
```

`CHECKPOINT` contains the reference tag, commit, and payload generation date.
The script validates `manifest.sha256` before changing the host. The USB does
not contain ROMs, BIOS files, Steam content, credentials, or generated emulator
state.

The payload should contain built native binaries. Requiring a C++ build on the
target would add avoidable compiler and Qt development dependencies. A
maintainer can build `lulu-shell` and `mudos-guide` before producing the USB;
the script verifies that both executables are present and runnable.

## Script Responsibilities

`install-mudos.sh` should use `#!/usr/bin/env bash`, `set -Eeuo pipefail`, a
trap that reports the failed step, and a `step()` wrapper that prints the
current numbered phase. It should resolve its own directory rather than the
current working directory, require root, acquire a lock, and tee all output to
`/var/log/mudos-install.log` without exposing secret values.

The ordered phases are:

1. **Preflight**: verify root, USB payload, checkpoint, manifest, supported
   CachyOS/Arch family, network/package-manager availability, and sufficient
   disk space. Refuse to run if the payload checksum is wrong.
2. **Package/runtime dependencies**: install the checkpoint dependency set with
   `pacman --needed`, including `inputplumber`, `gamescope-git`, `dolphin-emu`,
   `retroarch`, the required libretro cores, `steam`, `steam-devices`, `seatd`,
   PipeWire/WirePlumber, Qt6 DBus/Gui/Qml/Quick, SDL3, `python-dbus-next`,
   `python-rapidyaml`, `rapidyaml`, the required font, and other runtime Python
   dependencies. Install `pcsx2` from the configured repositories when
   available. Otherwise build the reviewed, pinned `payload/packages/pcsx2`
   PKGBUILD as an unprivileged temporary builder and install the resulting
   package. This is the only package-source fallback the script owns. Include
   `base-devel`, `cmake`, and `pkgconf` only if the payload is configured to
   build native binaries. The initial payload should not need those build
   tools.
3. **Service user and groups**: ensure the `lulu` account exists with the
   known-good UID/GID `958`, and fail rather than take over an occupied UID or
   rename an existing account. Ensure the `seat` group and required seat
   membership exist. Preserve an existing `lulu` home and all contents.
4. **Filesystem and ownership**: create `/opt/lulu`, `/etc/lulu`,
   `/etc/inputplumber/devices.d`, `/var/lib/lulu/roms/{nes,genesis,ps2,wii}`,
   `/var/lib/lulu/bios/ps2`, and the runtime/cache directories. Keep application
   files root-owned and make `/var/lib/lulu` and its user data `lulu:lulu`.
5. **Mudos deployment**: stage the payload into a temporary directory on the
   same filesystem, verify it, then atomically replace the `/opt/lulu/current`
   symlink. Retain the prior release for rollback. Install no files from the
   USB by symlink. The stable runtime paths are `/opt/lulu/current/lib`,
   `/opt/lulu/current/bin`, `/opt/lulu/current/config`, and
   `/opt/lulu/current/scripts`.
6. **Systemd units and target**: install the repo-owned unit templates and
   PAM file to `/etc/systemd/system` and `/etc/pam.d`, with paths adjusted to
   `/opt/lulu/current`. Install the InputPlumber restart drop-in. Run
   `systemctl daemon-reload` after file changes.
7. **InputPlumber**: copy the device definition to
   `/etc/inputplumber/devices.d/lulu-composite.yaml`, preserving the validated
   one-source-per-composite topology. Do not persist runtime composite names,
   SDL indices, event numbers, or player identity. Restart InputPlumber only if
   its package/configuration changed.
8. **udev and permissions**: install or verify only the package-provided
   `steam-devices`/seat permissions and the `xpad` driver. The checkpoint found
   no custom Xbox-specific udev rule. Reload udev rules if a package install
   changed them. Do not invent a rule that bypasses seat/device ownership.
9. **Gamescope/session configuration**: install the baseline
   `/etc/lulu/presentation.conf`, with `DISPLAY=:0`, `WAYLAND_DISPLAY=gamescope-0`,
   and the checkpoint session variables. Treat `HDMI-A-1` as a configurable
   default, not a proven BC-250 connector. Do not overwrite a locally supplied
   hardware-specific presentation file on rerun.
10. **Emulator installation**: verify `dolphin-emu`, `pcsx2`, and `retroarch`
    executables resolve, and verify the required RetroArch cores. Do not copy
    emulator profiles from the checkpoint's generated home state.
11. **Provider prerequisites**: install the RetroArch autoconfig and static
    provider assets from the payload. Create provider-owned parent directories;
    let Mudos regenerate Dolphin, PCSX2, and per-launch RetroArch configuration
    from live InputPlumber discovery. Never use saved `gamepadN`, `dbusN`, or
    SDL indices as physical identity.
12. **ROM/BIOS directories**: create and chown the directories only. If they
    already contain files, leave them untouched. Print the required locations
    and explicitly report that content and BIOS licensing are the operator's
    responsibility.
13. **Enable services**: enable `seatd.service` and `inputplumber.service`.
    Install the `lulu.target` wants-link under `multi-user.target`, because the
    current checkpoint target has no `[Install]` section and therefore cannot
    safely be treated as a normally enableable unit. Enable the target's
    catalogue/session wants only after installing the units. Start or restart
    only services whose unit, package, or relevant configuration changed. A
    first install may start the target; a rerun must not launch a second
    session.
14. **Verification**: run the checks below and exit nonzero on a failed
    required check. Write a concise summary to the terminal and the log.

## Reproduced Host State

| State | Source of truth | Destination/action | Rerun rule |
| --- | --- | --- | --- |
| Runtime packages | checkpoint package list | `pacman --needed`; AUR `pcsx2` build/install if unavailable in configured repos | package manager decides; never remove packages |
| `lulu` account | checkpoint UID/GID 958 | create or verify account and `seat` membership | preserve account/home; fail on collision |
| Application release | USB payload at reference commit | atomic release under `/opt/lulu`, update `current` | replace only repo-owned release |
| Python/native/static files | payload manifest | install root-owned files into release | deterministic replacement |
| Systemd target/units | `payload/packaging` | `/etc/systemd/system` | overwrite only these named files |
| PAM session file | `payload/packaging/lulu-session.pam` | `/etc/pam.d/lulu-session` | deterministic replacement |
| InputPlumber device | payload YAML | `/etc/inputplumber/devices.d` | deterministic replacement; no runtime IDs |
| InputPlumber restart drop-in | payload config | `/etc/systemd/system/inputplumber.service.d` | deterministic replacement |
| Seat/udev access | installed `seatd` and `steam-devices` packages | enable seatd; reload package rules | do not remove unrelated rules |
| Presentation defaults | payload `presentation.conf` | `/etc/lulu/presentation.conf` | create if absent; preserve hardware override |
| PipeWire fallback input | payload `pipewire/lulu-fallback-input.conf` | `/var/lib/lulu/.config/pipewire/pipewire-pulse.conf.d` | deterministic replacement |
| Emulator profiles | Mudos runtime ownership | generated below `/var/lib/lulu` | regenerate only through Mudos |
| ROMs and BIOS | operator | `/var/lib/lulu/roms`, `/var/lib/lulu/bios` | create/chown directories; never delete/copy |
| Steam data | operator | `/var/lib/lulu/.local/share/Steam` | preserve; do not attempt to provision content |
| SteamGridDB secret | operator | `/etc/lulu/steamgriddb.env` | create only from supplied secret; never log or overwrite |

The current checkpoint's generated catalogue, artwork, emulator INIs, saves,
caches, logs, D-Bus objects, event numbers, and process IDs are not deployment
inputs. They are regenerated or created at runtime.

## Verification Mode

The script should support `sudo ./install-mudos.sh --verify` and invoke the same
verification phase without changing packages or files. Required checks are:

- every required package is installed and each executable resolves with
  `command -v`;
- `/opt/lulu/current/lib`, `bin`, `config`, `ui`, and `scripts` exist, native
  binaries are executable, and the payload manifest matches;
- `lulu`, `seatd`, and `inputplumber` prerequisites are present;
- `seatd.service` and `inputplumber.service` are enabled, and the
  `multi-user.target.wants/lulu.target` boot link exists;
- `inputplumber.service` is active;
- the InputPlumber manager exposes at least one composite and each discovered
  composite has one D-Bus target and `InterceptMode=1`;
- all ROM/BIOS directories exist and are writable by `lulu` without checking
  for proprietary content;
- `dolphin-emu`, `pcsx2`, `retroarch`, and required RetroArch cores resolve;
- `lulu-consoled.service` and `lulu-session@2.service` are active after the
  target starts;
- a Mudos session can reach its shell/catalogue startup path and reports a
  usable session bus, PipeWire runtime, and Gamescope display.

The final session check must have a bounded timeout and must clean up only the
probe it started. It must not kill unrelated emulator or Steam processes.

## Manual Intervention

- Install and connect the BC-250 display, receiver, and three controllers.
- Confirm the physical display connector and adjust
  `/etc/lulu/presentation.conf` if `HDMI-A-1` is wrong.
- Supply legally obtained ROMs and PS2 BIOS files; independently record and
  verify their expected hashes if this becomes a production requirement.
- Supply Steam installation/game data if Steam providers are required.
- Supply `/etc/lulu/steamgriddb.env` separately if artwork lookup is required.
- Resolve any `lulu` UID 958 collision rather than allowing the script to alter
  another account.
- Complete BC-250-specific GPU, Gamescope, firmware, thermal, seat/device,
  receiver, and reconnect validation. The script cannot infer these safely.

## First-Boot Acceptance

1. Boot the fresh CachyOS system with the USB removed and confirm the system
   reaches `lulu.target` and the Mudos session appears on the intended VT.
2. Rerun the USB script with `sudo ./install-mudos.sh --verify`.
3. With controllers connected, run `sudo /opt/lulu/current/bin/verify-mudos.sh --hardware` and confirm the composite and `InterceptMode=1` checks pass.
4. Confirm `systemctl --failed` is empty for the Mudos-related services and
   inspect `journalctl -b -u inputplumber -u lulu-consoled -u lulu-session@2`.
5. Open Guide from P1, P2, and P3 and confirm each controller navigates only
   its own logical player.
6. Launch the known-good three-player Dolphin/Mario Kart Wii scenario and
   confirm independent input, no duplicate input, and no dead slots.
7. Verify the NES/Genesis and PCSX2 providers only after supplying their
   required content; record those results separately because they were not
   fully validated at the checkpoint.
8. Test one controlled service restart and one rerun of the installer. Confirm
   user data, ROMs, BIOS files, secrets, and generated state remain intact and
   that no duplicate session is created.
9. Record BC-250 display, controller reconnect, Steam visibility, and thermal
   results as hardware acceptance evidence, not as assumptions in the generic
   payload.

## External References

- InputPlumber installation: https://shadowblip.github.io/InputPlumber/install/
- InputPlumber usage and D-Bus model: https://shadowblip.github.io/InputPlumber/usage/
- InputPlumber composite D-Bus interface: https://shadowblip.github.io/InputPlumber/dbus-interface/composite_device/
- Arch package/AUR guidance: https://wiki.archlinux.org/title/Arch_User_Repository
- systemd units and overrides: https://wiki.archlinux.org/title/Systemd
- Gamescope: https://wiki.archlinux.org/title/Gamescope
- Steam and Steam devices: https://wiki.archlinux.org/title/Steam
- Dolphin package: https://archlinux.org/packages/extra/x86_64/dolphin-emu/
- PCSX2 AUR package: https://aur.archlinux.org/packages/pcsx2
