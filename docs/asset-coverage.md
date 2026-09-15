# Mudos asset coverage

| Requirement | Semantic ID | Authority | Status |
|---|---|---|---|
| Wi-Fi connected/disconnected | `wifi`, `wifiOff` | JetBrains Mono Nerd Font | bundled |
| Bluetooth | `bluetooth` | JetBrains Mono Nerd Font | bundled |
| Audio/muted | `volume`, `volumeMute` | JetBrains Mono Nerd Font | bundled |
| Controller/status/battery | `controller`, `battery` | Nerd Font; controller profile boundary | bundled/fallback |
| Download/activity | `download`, `activity` | JetBrains Mono Nerd Font | bundled |
| Storage | `storage` | JetBrains Mono Nerd Font | bundled |
| Power | `power` | JetBrains Mono Nerd Font | bundled |
| Warning/error/info | `warning`, `error`, `info` | JetBrains Mono Nerd Font | bundled |
| Settings/clock | `settings`, `clock` | JetBrains Mono Nerd Font | bundled |
| Controller confirm/back/menu/guide/view | semantic action → Xbox physical control | controller-icons-font (`Config`) | bundled |
| Controller shoulders/triggers/sticks | semantic action → Xbox physical control | controller-icons-font (`Config`) | bundled |
| Controller D-pad and directions | semantic action → Xbox physical control | controller-icons-font (`Config`) | bundled |
| Future Nintendo/PlayStation controls | profile-specific physical mappings | `ControllerProfiles.js` | profile slots ready; mappings not yet added |
| Platform identity: `nes` | `nes` | `romm/nes.svg` | bundled |
| Platform identity: `snes` | `snes` | `romm/snes.svg` | bundled |
| Platform identity: `genesis` | `genesis` | `romm/genesis.svg` | bundled |
| Platform identity: `gb` | `gb` | `romm/gb.svg` | bundled |
| Platform identity: `gbc` | `gbc` | `romm/gbc.svg` | bundled |
| Platform identity: `gba` | `gba` | `romm/gba.svg` | bundled |
| Platform identity: `nds` | `nds` | `romm/nds.svg` | bundled |
| Platform identity: `gamecube` | `ngc` alias | `romm/ngc.svg` | bundled |
| Platform identity: `wii` | `wii` | `romm/wii.svg` | bundled |
| Platform identity: `switch` | `switch` | `romm/switch.svg` | bundled |
| Platform identity: `ps1` | `psx` alias | `romm/psx.svg` | bundled |
| Platform identity: `ps2` | `ps2` | `romm/ps2.svg` | bundled |
| Platform identity: `ps3` | `ps3` | `romm/ps3.svg` | bundled |
| Platform identity: `pc`, `all`, unknown | fallback | `romm/default.ico` | bundled fallback |
| System category identity | category slug | supplied navigation PNGs | bundled |
| Metadata identity | `genres`, `last-played`, multiplayer, `protondb` | supplied SVGs | bundled; provenance needs attribution follow-up |
| Provider identity | provider slug | existing resolver/provider artwork | existing; no new provider art |

## Controller glyph coverage

The default Xbox profile resolves: `confirm→a→A`, `back→b→B`,
`menu→menu→hamburger`, `guide→guide→Xbox`, `view→view`,
`leftBumper→LB`, `rightBumper→RB`, `leftTrigger→LT`, `rightTrigger→RT`,
`leftStick→L`, `rightStick→R`, `navigation→dpad`, and `up/down/left/right`
to the four directional D-pad glyphs. `x`, `y`, `leftStickClick`, and
`rightStickClick` are also mapped centrally for future consumers.

## System icon coverage

All entries below resolve through `MudosAssetCatalog.icon()` to the bundled
JetBrains Mono Nerd Font (`JetBrainsMonoNL` family):

| Semantic ID | Nerd Font codepoint |
|---|---|
| `wifi` | U+F1EB |
| `wifiOff` | U+F6A9 |
| `bluetooth` | U+F293 |
| `volume` | U+F028 |
| `volumeMute` | U+F026 |
| `controller` | U+F11B |
| `battery` | U+F240 |
| `download` | U+F019 |
| `storage` | U+F0A0 |
| `power` | U+F011 |
| `warning` | U+F071 |
| `error` | U+F057 |
| `info` | U+F05A |
| `settings` | U+F013 |
| `clock` | U+F017 |
| `activity` | U+F1DA |
| `refresh` | U+F021 |
| `search` | U+F002 |
| `play` | U+F04B |
| `back` | U+F060 |
| `check` | U+F00C |
| `close` | U+F00D |

Aliases currently applied include `platform:nes`-style navigation scopes,
`game-cube`/`game cube`/`ngc` → `gamecube`, `nintendo-switch`/`nintendo
switch` → `switch`, and `playstation-1`/`playstation 1`/`psx` → `ps1`
(with equivalent PlayStation 2/3 aliases). Unknown platform slugs resolve to
the RomM `default.ico` fallback.

## Redundant-but-retained assets

The prior local platform portraits under `ui/artwork/platform-*.png` and
`platform-all.svg` are now superseded for platform identity by the vendored
RomM set. They are intentionally retained in this review pass and are not
deleted until visual review confirms the replacement set.
