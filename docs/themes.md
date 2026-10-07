# Mudos themes (schema v1)

A theme is a directory containing `theme.json` plus its declared assets. Built-in
themes are installed under `$LULU_INSTALL_ROOT/themes/<id>`; user themes belong
under `${XDG_DATA_HOME:-$HOME/.local/share}/mudos/themes/<id>`. The optional
`MUDOS_THEME_ROOTS` colon-separated override is intended for development/tests.
Theme selection is persisted in the user-scoped `Mudos/lulu` QSettings key
`appearance/theme`. No theme may provide QML or JavaScript.

The built-in `themes/modern` owns the accepted baseline's JetBrains Mono
regular, bold and ExtraBold faces, Nerd Font icon face, Config-Glyphs controller
face, and the `wallpaper/wallpaper.frag.qsb` scene shader. License/provenance
notices accompany the font assets. Optional `icons/<semantic-name>.svg` assets
are monochrome white with transparent background and are tinted at runtime.
Available fallback semantic IDs include wifi/wifiOff/ethernet, bluetooth and
bluetoothOn/bluetoothOff, controller, download, clock, battery, volume,
volumeMute, storage, display, plug, settings, power, warning, error, info,
platform, provider, gameMode, genre, play, search, refresh, back, check, close,
collection, flathub, applications, empty, wrench, activity, steam and addStore.
Game metadata uses genre, clock, gameMode, wifi, info, platform, plug, developer,
publisher and release. Missing SVGs use the built-in semantic Nerd Font glyph.

The built-in set includes `Modern` (`modern`), `95`, `Metalheart`
(`metalheart`), and `Frutiger Aero` (`frutiger-aero`).
Modern's existing palette, glass profile, radii, fonts and Orbit wallpaper are
kept as the accepted UI-001 baseline. `themes/95` is an original classic desktop
interpretation: teal wallpaper; gray surfaces; navy selection; black/white text;
square radii; glass disabled; generic bevel chrome; Liberation Sans with its
redistribution license; and original monochrome semantic SVGs. Its controller
face is retained for controller-hint compatibility. No theme includes QML or
JavaScript.

Metalheart is an original near-black/gunmetal interpretation using Oxanium for
display and Share Tech Mono for interface text (both SIL OFL 1.1), with a
raymarched chrome nexus, viewport-breaking tapered spikes, orbital rings, and a
pale technical/blueprint field in its compiled wallpaper. It uses existing
glass profiles and flat generic chrome rather than adding theme-specific
rendering logic. Its controller glyph face is inherited from the existing
Mudos asset set; upstream provenance says free/open-source but does not specify
an SPDX license. See `themes/metalheart/fonts/PROVENANCE.md` and the theme-engine
constraints in `docs/theme-gap-audit-metalheart.md`.

`theme.json` v1 provides `colors` (semantic color roles), `opacity` (0..1),
`radii` (0..128 logical pixels), `radiusPolicy` (`exact` or
`componentBaseline`), `glass` (enabled and optical settings),
`fonts.faces` (role-to-relative-file declarations) and `fonts.roles`, `icons`
(semantic ID to legacy SVG shorthand or a validated SVG/PNG descriptor), and `wallpaper.shader` plus primary/secondary/
surface/error colors. Font roles are interface/display/majorHeading/icon/
controller. Colors accept Qt color strings. Glass optical values are finite and
bounded by the engine; `glass.enabled: false` leaves the ordinary QML tint and
border substrate in place and suppresses the native refraction item.

Themes may also declare `motion`, `labels.home`, `labels.views`, the
`homeTitle`/`viewTitle` text styles, and semantic text styles for `heading`,
`body`, `metadata`, `annotation`, and `status`. Each semantic role may select
one existing font role, weight 1–1000, case (`preserve`, `upper`, `lower`), and
letter spacing -4..32 design pixels. Pixel sizes remain engine-owned so theme
styles cannot change layout dimensions.
Motion uses `enabled`, finite `durationScale` in `(0,10]`, and a small set of
semantic roles (`navigation`, `focus`, `surface`, `overlay`, `fade`, `status`,
`intro`, `wallpaper`, `motionBlur`). A role may override `enabled`, `duration` (0..5000 ms), and a
safe easing name (`linear`, `inCubic`, `outCubic`, `inOutCubic`, `inQuint`,
`outQuint`, `inOutQuint`, and quadratic variants). Effective enablement is the
global switch AND the role switch. Disabled motion finalizes presentation state
synchronously; it never disables jobs, operational indicators, or lifecycle
logic. The wallpaper role may set finite `speed` in `[0,10]`; its independent
clock is not affected by UI `durationScale` or `intro` timing. Omitted motion uses
enabled, unit-scale defaults. An omitted radius policy retains the legacy
`componentBaseline` behavior; `exact` makes configured semantic radii
authoritative. Home labels map stable
domain IDs (`system`, `store`, `library`, `recent`) and `labels.views` maps
first-class view IDs (`settings`, `utilities`, `library`, `installable`,
`downloads`) to strings of at most 64 characters; absent labels use canonical
Mudos wording. Both text styles accept `case` as `preserve`, `upper`, or
`lower`; `letterSpacing` is finite design pixels (0..32) and scales with the
UI. Dynamic Library dimensions remain engine-owned text, composed with the
Library view label before applying `viewTitle`. Themes supply no executable
transformation.

Semantic icon values retain the legacy string shorthand for tintable SVG, for
example `"wifi": "icons/wifi.svg"`. Descriptor form is
`{"file":"icons/settings.svg","render":"tint"}` or
`{"file":"icons/settings.png","render":"original"}`. Only SVG+tint and
PNG+original are accepted. ThemeManager resolves each semantic ID to a
validated `{url, renderMode, format}` descriptor; UI components do not infer
semantics from extensions. Original-mode PNGs display directly without
colorization, preserving RGB and alpha. PNGs must decode as actual PNG, be no
larger than 4 MiB, 1024×1024, or 1,048,576 pixels. Theme-root containment and
SVG validation apply as before.

Optional `materials` profiles are restricted to `panel`, `card`, `navigation`,
`status`, `overlay`, and `row`. An omitted profile (or section) preserves the
existing surface rendering. `style: "flat"` selects that legacy semantic-color
path; `linearGradient` supports vertical/horizontal orientation and 2–8
monotonic, finite stops with valid Qt colors. `edges` and `innerEdges` may name
only top/bottom/left/right bands, each with a color and width from 0 to 8 design
pixels. Mudos renders the validated data with a normal Qt Quick rounded
rectangle gradient and boundary-aligned strips; themes cannot provide shader
code or coordinates. Material layers follow canonical glass and precede
selection/focus treatment. Glass-off themes still paint the ramp over their
ordinary semantic substrate.

Optional `decorations` profiles are restricted to `panel`, `card`, `status`,
and `overlay`, with only `topLeft`, `topRight`, `bottomLeft`, and `bottomRight`
slots. Each slot references a root-contained, validated SVG and may select one
of the semantic `accent`, `secondaryText`, `border`, or `focusIndicator` tints,
opacity 0–1, and scale 0.5–2.0. Slot anchors, 12-design-pixel base size, and
insets are engine-owned; coordinates and arbitrary theme QML are rejected.
Decoration items are input-disabled and have zero implicit size. SVG path,
symlink, and XML checks reuse the semantic icon validator.

Wallpaper shaders are Qt Quick QSB packages. Their fixed uniform contract is
`u_resolution`, `u_origin`, `u_canvas`, `u_time`, `u_brightness`, `u_visibility`,
`u_primary`, `u_secondary`, `u_surface` and `u_error`; unused uniforms may be
omitted. Mudos owns animation/presentation lifecycle. The shader generates the
canonical scene, which remains the source for the visible backdrop and glass.
For authoring, compile a GLSL fragment with Qt's `qsb --qt6 --batchable -o
wallpaper.frag.qsb wallpaper.frag`; production does not compile themes at boot.

Discovery fully validates theme metadata, all required font roles, all declared
assets, semantic icon descriptors/SVG/PNG payloads, wallpaper QSB, colors, opacity, radii, glass values,
and chrome before exposing a theme in Settings. Selection consumes the same
validated manifest; invalid themes are never listed. `chrome.style` may be
`flat` or `bevel`; bevel themes declare highlight/light/shadow/darkShadow and a
1..8 pixel edge width. Shared shell surfaces consume that semantic treatment.

All declared assets must be relative paths under the theme directory. Absolute,
network and traversal paths, including symlinks escaping the theme root, are
rejected. Invalid selected themes fall back to `modern`; a persisted legacy ID
`mudos-default` is loaded as `modern` and rewritten to `modern`. Missing or
invalid themes are logged, and missing wallpaper must be handled by the engine's
backdrop color. The built-in theme is mandatory for a valid runtime.

Illustrative shape only (incomplete themes are rejected by discovery):

```json
{
  "schema_version": 1,
  "id": "modern",
  "name": "Modern",
  "version": "1",
  "author": "Mudos",
  "colors": { "primaryText": "#eadcff", "backdrop": "#060607" },
  "opacity": { "surface": 0.42 },
  "radii": { "panel": 18 },
  "glass": { "enabled": true },
  "fonts": { "faces": { "regular": { "file": "fonts/regular.ttf" } }, "roles": { "interface": "regular" } },
  "wallpaper": { "shader": "wallpaper/wallpaper.frag.qsb" },
  "icons": {
    "wifi": "icons/wifi.svg",
    "settings": { "file": "icons/settings.png", "render": "original" }
  }
}
```

Frutiger Aero's palette/materials, original procedural wallpaper, Noto Sans
font licensing, and icon/decoration provenance are documented in
`themes/frutiger-aero/theme.json` and `themes/frutiger-aero/ASSET_PROVENANCE.md`.
