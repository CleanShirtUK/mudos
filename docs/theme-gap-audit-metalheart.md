# Metalheart theme-engine gap audit

This audit records only constraints encountered while rendering Metalheart
through the existing theme contracts. No engine/schema feature is added by the
Metalheart pass. The original look is interpreted for Mudos; the 2000–2003
reference is the Web Design Museum's documented combination of deformed abstract
fractals, explosion-like backgrounds and futuristic pixel typography, not a
request to reproduce any site's artwork or navigation.

## 1. Surface material has no continuous metal finish

- **Desired treatment:** a dark steel body with several restrained vertical
  graphite-to-gunmetal stops, a crisp upper chrome glint, and a darker lower
  edge, while preserving backdrop transmission.
- **Current capability:** semantic solid/tinted colors, per-profile glass optics,
  and `chrome.style = "bevel"`. `MudosChromeFrame` creates paired top/left and
  bottom/right solid strips; the native glass item supplies its optical bevel.
- **What blocks it:** there is no theme-owned gradient-stop list, per-surface
  material ramp, or independently styled edge/highlight band. Repeating narrow
  colors in QML would hard-code Metalheart into the engine, so the theme uses a
  gunmetal substrate and the existing bevel/glass profile.
- **Smallest generic primitive:** an optional declarative multi-stop surface
  material with independent top/bottom edge colors, consumed by the existing
  structural/card surface components (no arbitrary theme code).
- **Layout/navigation impact:** none; paint-only.
- **Priority / impact:** **high** — this is the single largest missing visual
  primitive for making every shell surface read as machined metal rather than
  tinted glass.

## 2. Positive theme radii do not override component metrics everywhere

- **Desired treatment:** consistent small but nonzero panel/card/row/media radii
  (approximately 4/3/1/2 px) throughout Settings, Utilities, Guide and content
  rows.
- **Current capability:** `theme.json` validates and exposes radius roles; some
  surfaces consume configured values directly. `LuluPalette.radius(role,
  fallback)` intentionally uses the configured value only when it is zero, and
  otherwise preserves each component's existing local fallback. This protects
  established Modern metrics but prevents Metalheart's small positive values
  from reaching many helper-based surfaces.
- **What blocks it:** the shared helper has no exact-positive-radius policy; using
  the configured values globally would alter the currently accepted Modern
  component radii (for example media and overlay fallbacks differ from the
  configured Modern values). Metalheart therefore gets angular chrome on direct
  consumers and the closest existing local metrics elsewhere.
- **Smallest generic primitive:** an explicit, backwards-compatible radius
  resolution policy (theme-exact versus component-baseline), selected by a
  generic schema/versioned contract rather than theme ID.
- **Layout/navigation impact:** no navigation change; corner curvature only.
- **Priority / impact:** **medium-high** — consistency is noticeably limited on
  nested panels and rows, though the information architecture remains intact.

## 3. Theme-owned ornaments have no safe placement slots

- **Desired treatment:** small corner brackets, registration marks and sparse
  technical annotations on selected panel/header chrome.
- **Current capability:** semantic SVG overrides are validated, root-contained,
  and monochrome-tinted at semantic icon consumers. They replace icons; they do
  not decorate arbitrary panel locations.
- **What blocks it:** themes cannot request extra artwork around existing
  content without executable QML or engine-owned per-screen special cases.
- **Smallest generic primitive:** optional named decorative SVG slots on existing
  surface/header primitives, with fixed engine-defined anchors and no effect on
  content ownership.
- **Layout/navigation impact:** none if slots are paint-only and excluded from
  hit testing.
- **Priority / impact:** **medium** — useful for the historic technical/HUD
  vocabulary, but less important than coherent surface materials.

## 4. Text treatment is limited to Home and first-class view titles

- **Desired treatment:** compact tracking and typography treatment on the Guide
  header and selected small technical annotations, as well as Home/view titles.
- **Current capability:** the theme controls font families/weights through
  existing semantic roles and case/tracking through `homeTitle` and `viewTitle`.
  Most body/status text uses fixed engine pixel-size and weight values; arbitrary
  per-role size/tracking is not configurable. Guide now consumes `viewTitle`
  tracking, without changing its classification/title data.
- **What blocks it:** there is no general semantic text-treatment role or
  per-role size/weight/tracking table. The current supported title styles cover
  the prominent Metalheart headings, so the remaining annotations use the
  technical font and existing sizes.
- **Smallest generic primitive:** a small validated set of semantic text roles
  (for example `annotation`, `metadata`, `body`, `heading`) for family/weight/
  tracking, preserving engine-owned pixel-size/layout decisions.
- **Layout/navigation impact:** potentially text fit only; no routing changes.
- **Priority / impact:** **low-medium** — a coherent family split already gives
  a strong technical voice, but some small data labels remain less compact.

## Deliberately not recorded as gaps

- The current font roles can select distinct existing faces for interface and
  display/major-heading use; Metalheart uses Share Tech Mono with Oxanium and
  does not require a font-engine extension.
- The wallpaper shader can derive its own fractal, metallic bands, energy burst,
  grid and slow drift from the existing time/color uniforms. No wallpaper-only
  scalar uniform is necessary for this composition.
- Glass already exposes panel/card/status/navigation profiles, transmission,
  refraction, dispersion, diffusion, bevel and edge-light values. Metalheart
  uses those rather than requesting a new material-profile schema.
- Existing status and hint placement, screen layout, and color-accurate artwork
  remain engine-owned and need no Metalheart-specific presentation layer.
