# Nintendo Switch Provider

Mudos uses the managed Flathub build of [Eden](https://eden-emu.dev/), ID
`dev.eden_emu.eden`, through the release-owned `packaging/eden-flatpak` wrapper.
Eden 0.2.1 consumes its Flatpak XDG tree at
`~/.var/app/dev.eden_emu.eden/config/eden/qt-config.ini` and
`~/.var/app/dev.eden_emu.eden/data/eden`; a separate Mudos provider config
directory is not the active runtime tree.

Before a ROM launch, Mudos preserves Eden-owned settings and replaces the
provider-owned `[Controls]` section in that active config with SDL bindings
derived from the currently assigned InputPlumber/SDL gamepads. It accepts live
GUIDs dynamically; no manufacturer, model, transport, or GUID allowlist is
used. The same launch reconciliation projects Mudos-owned keys into Eden's data
tree and installs canonical firmware in its writable NAND. Configure Provider
opens Eden through the same Flatpak wrapper without a ROM or a controller and
marks the active config's first-run state complete so the setup wizard does not
become part of normal game launch.

The Eden-owned SDL bindings for LB, RB, Back/View, and Start/Menu use the
values from the preserved historical native Eden profile (`4`, `5`, `6`, and
`7`, respectively). This corrects an Eden mapping regression without changing
InputPlumber, face buttons, sticks, triggers, or d-pad bindings.
Each connected player is emitted as an Eden-native SDL slot (`type=0`) with a
distinct SDL port; no unpopulated slot is left as a keyboard mapping.
`LULU_SWITCH_SDL_GUID` is retained only as a test/developer override. Normal
launches obtain each populated player's live SDL GUID from the Mudos controller
inventory; no controller model is the default.

Place only legally obtained user-owned files under the Mudos Switch locations:

```text
/var/lib/lulu/roms/switch/                 # .nsp or .xci games
/var/lib/lulu/bios/switch/keys/prod.keys   # user-dumped keys, if required
/var/lib/lulu/bios/switch/keys/title.keys  # user-dumped keys, if required
/var/lib/lulu/bios/switch/firmware/        # user-dumped firmware, if required
```

Mudos does not download, include, or provide firmware, keys, games, or other
copyrighted material. Eden configuration and prerequisite discovery remain
subject to hardware validation; the provider does not claim that a package is
launchable without the user's legally obtained prerequisites.

## Content lifecycle

Switch uninstall is a parent-game operation. It removes only the Mudos-owned
canonical component files recorded for that title (base, update, and DLC),
never Eden NAND, saves, controller configuration, shader caches, or staging
directories. Ambiguous, external, symlinked, or unowned paths are rejected.

The catalogue groups those components into one game identity. RomM source
records are retained as provenance and are collapsed under the parent title;
component records do not become separate Library rows. RomM content-set
acquisition uses one parent job with component-level provider identities.
Installation is not considered complete until required components transfer and
the emulator-specific activation/recognition checks succeed.
