# Mudos themes (schema v1)

A theme is a directory containing `theme.json` plus its declared assets. Built-in
themes are installed under `$LULU_INSTALL_ROOT/themes/<id>`; user themes belong
under `${XDG_DATA_HOME:-$HOME/.local/share}/mudos/themes/<id>`. The optional
`MUDOS_THEME_ROOTS` colon-separated override is intended for development/tests.
Theme selection is persisted in the user-scoped `Mudos/lulu` QSettings key
`appearance/theme`. No theme may provide QML or JavaScript.

The built-in `themes/mudos-default` owns the accepted baseline's JetBrains Mono
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

`theme.json` v1 provides `colors` (semantic color roles), `opacity` (0..1),
`radii` (0..128 logical pixels), `glass` (enabled and optical settings),
`fonts.faces` (role-to-relative-file declarations) and `fonts.roles`, `icons`
(semantic ID to relative SVG), and `wallpaper.shader` plus primary/secondary/
surface/error colors. Font roles are interface/display/majorHeading/icon/
controller. Colors accept Qt color strings. Glass optical values are finite and
bounded by the engine; `glass.enabled: false` leaves the ordinary QML tint and
border substrate in place and suppresses the native refraction item.

Wallpaper shaders are Qt Quick QSB packages. Their fixed uniform contract is
`u_resolution`, `u_origin`, `u_canvas`, `u_time`, `u_brightness`, `u_visibility`,
`u_primary`, `u_secondary`, `u_surface` and `u_error`; unused uniforms may be
omitted. Mudos owns animation/presentation lifecycle. The shader generates the
canonical scene, which remains the source for the visible backdrop and glass.
For authoring, compile a GLSL fragment with Qt's `qsb --qt6 --batchable -o
wallpaper.frag.qsb wallpaper.frag`; production does not compile themes at boot.

All declared assets must be relative paths under the theme directory. Absolute,
network and traversal paths, including symlinks escaping the theme root, are
rejected. Invalid selected themes fall back to `mudos-default`; missing or
invalid themes are logged, and missing wallpaper must be handled by the engine's
backdrop color. The built-in theme is mandatory for a valid runtime.

Minimal shape (the production default contains the full required role set):

```json
{
  "schema_version": 1,
  "id": "mudos-default",
  "name": "Mudos Default",
  "version": "1",
  "author": "Mudos",
  "colors": { "primaryText": "#eadcff", "backdrop": "#060607" },
  "opacity": { "surface": 0.42 },
  "radii": { "panel": 18 },
  "glass": { "enabled": true },
  "fonts": { "faces": { "regular": { "file": "fonts/regular.ttf" } }, "roles": { "interface": "regular" } },
  "wallpaper": { "shader": "wallpaper/wallpaper.frag.qsb" },
  "icons": { "wifi": "icons/wifi.svg" }
}
```
