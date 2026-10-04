# Nintendo Switch Provider

Mudos provisions Eden from the official pinned x86_64 Clang-PGO AppImage
described by `config/providers/eden/runtime.json`. The current pin is Eden
nightly `d16735f5b6` (source commit
`d16735f5b618942136d6ab53466e3be0a382c30a`, 2026-10-02). Provisioning downloads
only that versioned official HTTPS artifact and verifies its SHA-256 before
installing it at `/var/lib/lulu/providers/eden/d16735f5b6/` as root-owned and
executable by the `lulu` group.

Mudos launches Eden with an isolated provider XDG config root. Eden appends its
own `eden` subdirectory to that root; Mudos must update that exact config file
because the AppImage does not consume `~/.config/eden/qt-config.ini` for a
Mudos-owned launch:

```text
~/.config/lulu/providers/eden/config/eden/qt-config.ini # active preferences and Controls
~/.local/share/eden/           # NAND, keys, firmware, saves, shader/cache data
~/.config/lulu/providers/eden/config/lulu-switch.ini   # Mudos controller source
```

Before the first direct launch, Mudos imports the previous Flatpak tree from
`~/.var/app/dev.eden_emu.eden/{config/eden,data/eden}`. It backs up a native
first-run config before adopting the Flatpak config and keeps conflicting
unowned files. NAND is migrated as one coherent state set: `profiles.dat`,
user/system saves, and registered content are never merged file-by-file. A
native NAND collision is preserved and left alone unless the prior migration
marker proves it skipped the legacy `profiles.dat`; that specific repair first
backs up the complete native NAND, then installs the complete Flatpak NAND as
the authoritative set. Ambiguous/custom NAND roots are left untouched. The
Flatpak source is retained. Mudos' key links and firmware projection are
reconciled against the ownership manifest after migration.

MK8 update and DLC packages can also be discovered from Eden's configured
external-content directories. They are user-owned NSP files, not NAND contents
or Mudos-projected files. Migration preserves Eden's configured external
directories; Mudos appends its ROM root without replacing other configured
locations. Do not copy or register those files into `nand/user/Contents` as a
substitute for Eden's content scan.

For each game launch Mudos updates the active Eden `[Controls]` section using
live SDL controller identities and adds its ROM directory to Eden's active
external-content path list. The original Mudos face-button order (A/B/X/Y =
SDL buttons 0/1/2/3) is retained; an Eden-authored `gp1` donor is preserved for
comparison, but its reversed ABXY order is not treated as authoritative.
Physical button acceptance remains pending. Mudos-owned keys are read-only projections
from the canonical Switch BIOS keys directory. Firmware is copied, hash
verified, and ownership-recorded in Eden's writable native NAND; the canonical
firmware source is never writable by Eden. Conflicting or unowned target paths
are preserved and are not silently replaced.

Sessiond continues to own the Eden process group, Gamescope surface selection,
controller mode, and return-to-shell lifecycle. The AppImage is launched
directly with the existing `--appimage-extract-and-run`, Mudos config,
fullscreen, and game arguments. Controller and provider-menu behavior remain
Mudos-owned.

The obsolete Mudos Flatpak wrapper/provisioner is removed. Migration revokes
only the old Mudos-added `/home/lulu/Games:ro` Eden Flatpak override; it leaves
the old Flatpak app and data in place for rollback/recovery. The generic
Flatpak provider remains available.

Place only legally obtained user-owned files under the Mudos Switch locations:

```text
/var/lib/lulu/roms/switch/                 # .nsp or .xci games
/var/lib/lulu/bios/switch/keys/prod.keys   # user-dumped keys, if required
/var/lib/lulu/bios/switch/keys/title.keys  # user-dumped keys, if required
/var/lib/lulu/bios/switch/firmware/        # user-dumped firmware, if required
```

Mudos does not download, include, or provide firmware, keys, games, or other
copyrighted material. An installed Eden runtime is distinct from game
readiness: Mudos reports missing required keys/firmware separately.

## Content lifecycle

Switch uninstall is a parent-game operation. It removes only the Mudos-owned
canonical component files recorded for that title (base, update, and DLC),
never Eden NAND, saves, controller configuration, shader caches, or staging
directories. Ambiguous, external, symlinked, or unowned paths are rejected.
