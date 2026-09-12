# Non-game portrait artwork

Landing cards load the following replaceable 600x900 portrait assets from this
directory. Keep the filenames unchanged when supplying artwork.

- `platform-all.svg`
- `platform-pc.png`
- `platform-nes.png`
- `platform-snes.png`
- `platform-genesis.png`
- `platform-gb.png`
- `platform-gbc.png`
- `platform-gba.png`
- `platform-nds.png`
- `platform-gamecube.png`
- `platform-wii.png`
- `platform-switch.png`
- `platform-ps1.png`
- `platform-ps2.png`
- `platform-ps3.png`
- `store.png`
- `system-display.svg`
- `system-audio.svg`
- `system-network.svg`
- `system-bluetooth.svg`
- `system-controllers.svg`
- `system-storage.svg`
- `system-system.svg`
- `system-lulu.svg`

The checked-in SVGs are harmless placeholders. They can be replaced directly
with artwork in the same filenames and do not require a source-code change.

Tintable monochrome SVG assets must use white foregrounds on a transparent
background. Runtime icon color is supplied by `LuluPalette` through the shared
`MultiEffect` path.
