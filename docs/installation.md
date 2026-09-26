# Production Mudos installation

## Supported base and command

The supported base is CachyOS/Arch Linux on a systemd host with `pacman`, a
working network/package mirror, and the required graphical/input hardware.
From a clean, committed canonical source checkout, run:

```sh
./install-mudos.sh
```

The command requests `sudo` when needed, installs missing shared packages with
`pacman --needed`, builds a release using `scripts/release.py`, verifies its
checksum manifest, atomically selects it at `/opt/lulu/current`, provisions
system integration, and starts the appliance target. It refuses dirty source,
unsupported operating systems, or an existing `lulu` account that conflicts
with UID/GID 958 and `/home/lulu`. The default `lulu` group/account contract is
created if absent; an existing home is preserved. No credentials are needed.
The package manifest declares `gamescope-git` as an accepted alternative to
`gamescope`, so the installer reuses that already-installed provider rather
than asking pacman to remove or replace it.

The installer leaves OOBE progress absent (which the application interprets as
`never`/required). It does not fabricate provider readiness, catalogue rows,
download history, provider accounts, or credentials. It does not reset OOBE on
reinstall. Re-running a committed-source install builds/selects a new
immutable release but preserves existing mutable user data and generated
credentials.

## Runtime and ownership boundary

`packaging/mudos-ownership.json` is the machine-readable ownership contract
consumed by install, verify, uninstall, purge, and installer tests. Immutable
code lives in `/opt/lulu/releases/<release-id>`; `/opt/lulu/current` is the
atomic selector, and `/opt/lulu/bin`, `lib`, `ui`, `config`, and `scripts` are
compatibility symlinks through that selector. Release metadata and manifest
identify the exact clean source SHA. Release artifacts contain source/runtime
files only, never user databases, credentials, logs, or game data.

Mutable Mudos state is under the explicitly listed `/home/lulu` configuration,
data, cache, game, and provider paths and `/var/lib` service paths. System
integration entries list exact owned unit/configuration files. Pacman packages
and external service packages are shared dependencies: uninstall and purge do
not remove them. Files such as `/etc/nsswitch.conf`, arbitrary files in
`/home/lulu`, and the source checkout are not owned and are never rewritten or
removed by purge. Recovery uses the selected immutable release and is
independent of `/opt/lulu/dev-current`.

The ownership contract also recognizes the exact appliance Steam-library bind
mount when systemd generated it from `/etc/fstab`. Purge stops that mount before
deleting its Mudos game tree, preserves the host's fstab entry, and installation
recreates only its Mudos-owned source and mountpoint before restarting the
generated mount. The installer never edits `/etc/fstab`.

## Verify, uninstall, purge

```sh
./install-mudos.sh --verify
./install-mudos.sh --uninstall --dry-run
./install-mudos.sh --uninstall
./install-mudos.sh --purge-user-data --dry-run
./install-mudos.sh --purge-user-data
```

Uninstall stops/disables Mudos-owned services, removes only manifest-listed
system integration and the current selector, and preserves immutable releases
and all mutable user state. Purge additionally removes the manifest-listed
Mudos-owned mutable paths, including appliance game storage and credentials,
and removes the non-promotable developer runtime. Purge does not delete the
immutable release root or rollback targets. Review the dry-run path list before
purging. Neither operation removes shared pacman packages. The source checkout
is protected in code as well as listed in the manifest.

## Rollback and development

Release construction, checksum verification, and activation remain separate
operations in `scripts/release.py`; installation does not promote V1 or delete
older releases. A previously selected immutable release can be reactivated
with the release tool after verifying it. `/opt/lulu/dev-current` and
`scripts/dev-runtime.sh` are development-only and are not production sources.
Production services use `/opt/lulu/current`; installer verification rejects a
dev-current reference in core production units.
