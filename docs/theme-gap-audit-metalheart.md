# Metalheart theme-engine gap audit

This audit tracks presentation constraints encountered while rendering
Metalheart through Mudos' declarative theme contracts. The V2 additions remain
data-only: themes cannot supply executable QML or shaders, choose layout
coordinates, or change navigation/routing. The 2000–2003 reference remains the
Web Design Museum's account of abstract fractals, explosion-like backgrounds,
and futuristic pixel typography—not a request to copy artwork or navigation.

## Surface material — addressed in V2

- **Original finding:** surfaces could use semantic solid/tinted color, native
  glass, and generic flat/95 bevel chrome, but had no continuous metallic ramp
  or independently styled edge bands. The first Metalheart bevel approximation
  read as Windows-95 framing during physical review and was removed in the
  corrective pass.
- **V2 capability:** validated semantic `materials` profiles (`panel`, `card`,
  `navigation`, `status`, `overlay`, `row`) support flat fallback or bounded
  vertical/horizontal Qt Quick linear gradients, 2–8 ordered stops, four outer
  edges, and four optional inner edges. Band widths are 0–8 design pixels.
  `MudosMaterialLayer` is shared by the structural surfaces and selected/common
  row consumers; no theme shader or offscreen material pass was added.
- **Layering:** semantic base color → canonical glass/refraction → translucent
  material ramp and edge bands → semantic selection/focus overlay → optional
  fixed-slot ornament. When the material is active over canonical glass, the
  old flat tint contribution is suppressed; glass-off themes retain their
  ordinary substrate below the material. Absent profiles leave the legacy
  surface path in place.
- **Metalheart use:** all six generic profiles are declared. Panel, card,
  navigation, status, and overlay use vertical graphite/steel ramps; the row
  profile is horizontal and restrained. Metalheart stays `chrome.style =
  "flat"`; 95 keeps its classic bevel.
- **Validation:** schema validation rejects unknown profiles/fields, bad styles
  or orientation, stop counts outside 2–8, invalid/non-finite/out-of-range or
  descending stop positions, invalid colors, and invalid edge colors/widths.
- **Status:** engine gap addressed; visual tuning still requires the pending
  physical Metalheart surface sweep.

## Radius authority — addressed by the corrective pass

- **Original defect:** configured zero radii were honored, but positive theme
  radii often fell through to component-local values.
- **Correction:** validated `radiusPolicy` supports `exact` and
  `componentBaseline`. Exact radii are authoritative; Modern explicitly keeps
  the compatibility behavior, and 95/Metalheart use exact values. Metalheart
  currently requests zero for all six semantic roles.
- **Status:** resolved generically and covered by positive/zero radius tests.

## Fixed decorative SVG slots — addressed in V2

- **Original finding:** semantic SVG overrides could replace icons but there
  were no safe theme-owned locations for small technical marks without
  screen-specific QML or arbitrary coordinates.
- **V2 capability:** `MudosDecorationLayer` supports `panel`, `card`, `status`,
  and `overlay` profiles with fixed four-corner slots. The engine owns slot
  size/inset/orientation; themes control only SVG asset, semantic tint, opacity,
  and bounded scale. Layers are disabled for input and have zero implicit size.
- **Security:** assets use the existing canonical root-containment and SVG XML
  safety path, including symlink-escape rejection. Unknown roles/slots and
  arbitrary coordinates are rejected.
- **Metalheart assets:** original monochrome corner bracket, registration mark,
  and segmented-chevron SVGs. Panel and major overlay slots are used sparingly;
  the compact status strip intentionally has no ornament configured because its
  content already occupies its safe inset.
- **Status:** generic capability addressed; pending physical check that selected
  surfaces keep all ornaments clear of content at appliance scale.

## Remaining presentation gap: semantic text treatment

- **Current capability:** theme font-family/weight roles and Home/view title
  case/tracking controls. Engine-owned pixel sizes and layouts remain fixed.
- **Limitation:** there is no bounded set of generic body/metadata/annotation
  tracking or weight roles. Some small labels therefore cannot receive the same
  deliberate compact technical treatment as headings without changing engine
  typography contracts.
- **Smallest future primitive:** validated semantic text roles for family,
  weight, and tracking only; keep pixel size and layout engine-owned.
- **Priority:** highest remaining schema-level presentation gap after V2; not
  required for the material/ornament system to function.

## Implementation coverage and acceptance boundary

- Common panel/card/navigation/status/overlay surfaces and major Library,
  Settings, Utilities, Downloads, Guide, GameCard, and shared row boundaries
  consume the generic layers. Some inline provider/modal rows remain on the
  semantic flat path; moving every inline row is implementation debt, not a
  theme-specific workaround or a material-schema blocker.
- No Metalheart-specific production QML branch was added. Modern and 95 omit
  both optional sections and are covered by regression tests for empty resolved
  material/decoration maps.
- The local headless/capture path does not expose the Gamescope shell output.
  Therefore this code pass cannot claim physical inspection, controller
  acceptance, or a BC-250 before/after performance comparison. Those remain
  operator acceptance gates; no performance delta is inferred from off-device
  tests.

## Deliberately not recorded as V2 gaps

- Existing glass profiles, canonical wallpaper texture, wallpaper clock, and
  surface geometry remain unchanged.
- Material noise/grain, material masks, arbitrary gradients/angles, custom
  shaders, multi-color icon architecture, free-form ornament placement, and
  theme-controlled text sizes are outside this pass.
- Wallpaper artwork was not redesigned; the existing Metalheart shader remains
  the source of the animated abstract environment.
