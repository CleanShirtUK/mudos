# Mudos Asset Contract

Assets are shipped in the release payload and are resolved relative to the
installed `/opt/lulu/ui` directory. Replacing an asset in one of these
locations does not require a QML or service change. The checked-in files are
safe placeholders or manifests where the final supplied binary is absent.

## UI glyphs

Canonical directory: `ui/assets/ui-glyphs/`

Files use descriptive, lowercase names and the `.svg` extension. The
`MANIFEST` lists the reserved names. SVGs are loaded by UI components with
`Qt.resolvedUrl()` so they also work when the UI is run directly from the
worktree.

## Controller hint glyphs

Canonical directory: `ui/controllerglyphs/`

The exact Steam Deck PNG names are retained as the public contract:
`SteamDeck_A.png`, `SteamDeck_B.png`, `SteamDeck_L1.png`,
`SteamDeck_R1.png`, `SteamDeck_Dpad.png`, and the four directional
`SteamDeck_Dpad_*.png` files. `ControllerGlyph.qml` resolves these relative to
itself, so replacements are picked up automatically.

## Portrait non-game artwork

Canonical directory: `ui/assets/portrait-artwork/`

The exact fallback is `portrait-placeholder.svg`. `GameCard.qml` uses it when
catalogue artwork is absent or suppressed. Supplied portrait artwork may
replace this file without changing the component.

## UI sounds

Canonical directory: `ui/assets/ui-sounds/`

Reserved exact filenames are `focus.wav`, `activate.wav`, `back.wav`, and
`error.wav`, as listed in `MANIFEST`. They are kept separate from game audio;
future sound playback must resolve these paths from the UI asset root.

## Steam intro

Canonical file: `ui/assets/steam/steamdeck-startup.webm`.

This is the Mudos-owned input for the Steam startup movie contract. Mudos does
not overwrite Steam's installation or its generated user data; the Steam
bootstrap/provider integration is responsible for presenting this file when
that integration is enabled.

## Plymouth

Canonical source directory: `packaging/plymouth/lulu/`. The theme descriptor is
`lulu.plymouth`, the script is `lulu.script`, and the replaceable logo is
`lulu-logo.png`, as listed in `MANIFEST`. The installer/release payload keeps
these files together so a Plymouth package integration can install the theme
under `/usr/share/plymouth/themes/lulu/` without changing source code.
