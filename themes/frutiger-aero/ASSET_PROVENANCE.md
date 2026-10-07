# Frutiger Aero asset provenance

All icon and decoration artwork in this theme is original Mudos artwork created
for this theme. The semantic PNGs were procedurally drawn at 4× resolution with
Pillow and downsampled with Lanczos; their gloss, colour, and symbol geometry
were authored locally. No Crystal Project, Frutiger Aero Archive, Vista, or
other third-party artwork is included.

| Local files | Original project / author | Source | License | Modification |
|---|---|---|---|---|
| `icons/*.png` | Mudos; original theme assets | Authored in this repository | Mudos project copyright/license | Original pictograms, gradients, transparent antialiased PNG rendering |
| `decorations/*.svg` | Mudos; original theme assets | Authored in this repository | Mudos project copyright/license | Original small bubble/leaf marks |
| `wallpaper/wallpaper.frag` and `.qsb` | Mudos; original shader | Authored in this repository | Mudos project copyright/license | Procedural shader and Qt Shader Baker output |
| `fonts/NotoSans-*.ttf` | Noto Project / Google and contributors | System package `noto-fonts`, `/usr/share/fonts/noto` | Apache License 2.0; full text at `fonts/NOTO-SANS-APACHE-2.0.txt` | Unmodified copies |
| `fonts/JetBrainsMonoNLNerdFont-Regular.ttf` | Nerd Fonts / JetBrains | Existing Mudos Modern theme asset | SIL Open Font License; see `fonts/NERD-FONTS-LICENSE.txt` | Unmodified compatibility icon face |
| `fonts/Config-Glyphs.otf` | Upstream Config-Glyphs contributors | Existing Mudos Modern theme asset | Upstream provenance does not specify an SPDX license; see accompanying provenance notice | Unmodified controller-hint compatibility face |

Noto Sans was selected for the humanist interface/display roles. The inherited
Nerd Font and Config-Glyphs faces are limited to existing semantic/controller
fallback compatibility; colourful theme PNGs are the primary visual icon path.
