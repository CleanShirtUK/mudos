# Emulation Library Convention

Status: initial implementation, 2026-09-10.

## Storage

The Lulu appliance's persistent emulation roots are:

```text
/var/lib/lulu/roms/<platform-id>/
/var/lib/lulu/bios/<platform-id>/
```

The service account owns these directories. `LULU_ROM_ROOT` and
`LULU_BIOS_ROOT` may override them for a deliberate development or test
installation. Platform IDs are lowercase, stable directory names such as
`nes`, `genesis`, `ps2`, `wii`, and `switch`. ROMs go directly in their
platform directory. BIOS files go in the matching BIOS directory; emulator
specific subdirectories can be declared by the platform definition (PS2 uses
`bios/ps2`). Lulu never downloads or copies BIOS files.

The Mudos `lulu.consoled` service calls `ensure_storage()` at startup. It creates the common
roots and the known platform directories, but does not create firmware files.

## Discovery

`src/lulu/emulation.py` is the platform registry. Each definition contains the
user-facing name, accepted extensions, runtime name, executable, optional
RetroArch core, and BIOS subdirectory. `LocalContentProvider` scans only the
configured ROM root and only the extensions in that registry. A file is given a
stable `local:<platform>:<hash>` identity based on its relative path.

Adding another ROM to a supported system requires only placing it in the
correct directory. The next catalogue refresh discovers it; no UI change is
needed. CUE files are retained only when their referenced image is present.

## Catalogue and Categories

ROM records and Steam records share `CatalogueGame` and the SQLite catalogue.
ROM metadata includes source (`local`), platform ID and label, ROM path,
runtime name, install state, launchability, and stable identity. Artwork is
currently empty for local records; the existing SteamGridDB path remains Steam
only.

`All Games` queries every installed record. `Steam` filters provider `steam`.
Platform categories are generated from installed local records, so empty
platforms do not appear. Their scopes are `platform:<platform-id>` and their
labels come from the registry. The HTTP bridge exposes these categories at
`/platforms`; the existing Library landing and collection selector use the
same NavigationCard and controller-first focus behavior as before.

## Runtime Mapping

The registry maps the current fixtures as follows:

| Platform | Runtime | Invocation shape |
| --- | --- | --- |
| NES | RetroArch + Nestopia | `retroarch -L <core> <rom>` |
| Genesis | RetroArch + Genesis Plus GX | `retroarch -L <core> <rom>` |
| PS2 | PCSX2 | `pcsx2-qt <disc>` |
| Wii | Dolphin | `dolphin-emu -e <disc>` |
| Switch | Yuzu | `yuzu <package>` |

Paths are configurable with `LULU_RETROARCH`, `LULU_NES_CORE`,
`LULU_GENESIS_CORE`, `LULU_PCSX2`, `LULU_DOLPHIN`, and `LULU_YUZU`. Missing
runtime, core, or BIOS prerequisites leave a discovered game visible but not
launchable. The runtime adapter builds an intent and does not start a process;
session ownership remains with the existing ConsoleSessiond boundary.

## Adding a New Console

1. Add a platform definition with a stable ID, label, extensions, runtime
   executable, core or emulator arguments, and BIOS subdirectory if needed.
2. Add the corresponding runtime argument branch to
   `EmulatorRuntimeAdapter` when the emulator's invocation shape is new.
3. Place ROMs under `roms/<platform-id>` and firmware under
   `bios/<platform-id>` (or the declared subdirectory).
4. Add provider/runtime unit tests and refresh the catalogue. No QML category
   code should be added for the platform.

Runtime paths must be executable/readable by the Lulu `lulu` service account, and
ROM/BIOS directories must be readable by that account. Static validation can
check directory discovery, metadata, scopes, command intents, SQL records, and
QML bindings without starting gameplay. Actual emulator, Gamescope, and
lifecycle validation is intentionally pending while the parallel lifecycle
debug session is active.
