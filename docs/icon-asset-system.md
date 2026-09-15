# Mudos icon and asset system

## Authority order

1. General shell/system chrome: bundled JetBrains Mono Nerd Font.
2. Controller hints: `ControllerProfiles.js` semantic actions, physical
   controls, and the active profile, rendered with the bundled
   controller-icons-font. The checked-in SteamDeck PNGs remain only as a
   deterministic font-load fallback.
3. Platform identity: `MudosAssetCatalog.platformArtwork()`, using the curated
   vendored RomM platform set. RomM remains the data authority for platform
   slug/label; runtime artwork never depends on the RomM API or network.
4. Bespoke navigation and metadata identity: normalized assets under
   `ui/artwork/navigation` and `ui/artwork/glyphs/metadata`.
5. Provider/game artwork: provider URLs and the existing artwork cache.

## Semantic APIs

- `MudosAssetCatalog.icon(name)` resolves system glyph names without exposing
  codepoints to screens.
- `MudosIcon` renders those names using `Typography.iconFamily`.
- `ControllerProfiles` resolves semantic actions (`confirm`, `back`,
  `navigation`, `previousCollection`, and so on) through a profile and then a
  physical control. A future Nintendo profile can replace the mapping without
  changing UI actions.
- `MudosAssetCatalog.platformArtwork(slug)` and
  `MudosAssetCatalog.systemArtwork(category)` are the canonical graphical
  lookups.

## Fonts

JetBrains Mono Nerd Font no-ligature Regular/Bold/ExtraBold files are bundled
under `ui/fonts`. `Typography.qml` loads them with `FontLoader` and uses the
runtime `FontLoader.name`, not a filename-derived family assumption. The
fallback is the system `JetBrains Mono` family if loading fails.

`Config-Glyphs.otf` is vendored from
`https://github.com/SamarthMP/controller-icons-font`. Its README describes the
font as “free and open-source”; the upstream repository does not state a
specific SPDX licence, so Mudos records that wording without inventing one.
Qt reports its runtime family as `Config` (`Config Glyphs`).

RomM platform artwork is vendored from
`https://github.com/rommapp/romm/tree/master/frontend/assets/platforms`.
The upstream repository is AGPL-3.0. Its directory `ATTRIBUTIONS` is retained
with the assets and identifies the separately licensed Libretro and PS5 files.
The curated Mudos files are mapped by RomM slug in `MudosAssetCatalog.js`.

## Adding icons and profiles

Add a system icon name and its Nerd Font codepoint only in
`MudosAssetCatalog.js`, then use `MudosIcon { name: "..." }`. Do not put raw
codepoints or font family names in screen QML. Add controller semantic actions
to `ControllerProfiles.js`; add a profile there rather than branching on
Xbox/Nintendo button names in a screen.

New graphical assets must be normalized into the appropriate artwork
directory, added to the canonical lookup, and documented with provenance.
