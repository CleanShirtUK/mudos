# Nintendo Switch Provider

Mudos provisions Eden from the official pinned x86_64 Clang-PGO AppImage
described by `config/providers/eden/runtime.json`. The current pin is Eden
nightly `d16735f5b6` (source commit
`d16735f5b618942136d6ab53466e3be0a382c30a`, 2026-10-02). Provisioning downloads
only that versioned official HTTPS artifact and verifies its SHA-256 before
installing it at `/var/lib/lulu/providers/eden/d16735f5b6/` as root-owned and
executable by the `lulu` group.

Native Eden uses the standard XDG locations:

```text
~/.config/eden/qt-config.ini   # Eden preferences and Mudos-owned Controls
~/.local/share/eden/           # NAND, keys, firmware, saves, shader/cache data
~/.config/lulu/providers/eden/config/lulu-switch.ini  # Mudos controller source
```

Before the first direct launch, Mudos imports the previous Flatpak tree from
`~/.var/app/dev.eden_emu.eden/{config/eden,data/eden}`. It copies only into
missing native paths, keeps conflicting native files, backs up a native
first-run config before replacing it with the working Flatpak config, and
records a one-time migration marker. It does not delete the Flatpak tree or
NAND state. The managed key links and firmware projection are reconciled again
against Mudos' ownership manifest after migration.

For each game launch Mudos updates only the Eden `[Controls]` section using
live SDL controller identities. Mudos-owned keys are read-only projections
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
