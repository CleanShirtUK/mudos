# Active Backlog

Current engineering work is tracked here. Historical reconciliation notes are
retained in `docs/reconciliation-backlog.md` and are not the status authority.

## CLOSED MILESTONES

### OVERLAY-001 — Statistics Overlay

**Status: ACCEPTED / CLOSED** — user physical acceptance recorded separately
from automated validation in `docs/validation-log.md`; compatibility contract
and implementation evidence are in `docs/statistics-overlay-compatibility.md`.

- Accepted: persistent System Settings selection for Off, FPS Only, Minimal,
  and Detailed; application on subsequent launches; Aurelia/Proton, native
  Linux/OpenGL, compatible native emulator backends, and generic Flatpak
  integration. Acceptance explicitly includes existing and newly installed
  compatible Flatpak applications, runtime-matched extension provisioning, and
  no global Flatpak overrides or injection into unrelated processes.
- Settings-only is intentional. Live Guide-menu cycling/visibility controls
  are not required and are not an open acceptance item.
- Implementation commits: `05675dd` (native and generic Flatpak launch
  integration) and `d598c9d` (runtime compatibility documentation), building
  on `cc3da28`, `bb66e20`, `fcf77a5`, `78fd92d`, and `ffdc825`. Accepted release
  revision: `/opt/lulu/releases/d598c9d-candidate-20261009221126`.
- Standard Steam-client-managed MangoHud work is superseded: both `steam:` and
  `steam-aurelia:` Mudos identities now use Aurelia. The isolated background
  Steam runtime remains required for DRM/authentication/Steamworks, not game
  launch ownership. Nine of 28 formerly launchable legacy catalogue rows were
  stale (missing content and not installed in Aurelia); routing rejects these
  unless a matching Aurelia identity is currently launchable. See
  `docs/validation-log.md` for the complete audit. Routing implementation is in
  `934c18d` and the retained-ID lookup correction in `7adb957`; verified and
  active candidate: `/opt/lulu/releases/7adb957-candidate-20261009223803`.

## ROUTING VALIDATION

### STEAM-ROUTE-001 — Physically verify both Steam identity routes

**Status: ACCEPTED / CLOSED.** User reports successful physical testing after
the routing correction; the prior no-display observation was caused by the
display idling out and is not a defect. User-owned physical testing is recorded
separately from the automated evidence in `docs/validation-log.md`.

- When a display is connected, launch one Aurelia-installed title (for example,
  Super Meat Boy / AppID `40800`) once as `steam:40800` and once as
  `steam-aurelia:40800`; confirm launch and return to Mudos. Physical testing
  was completed by the user; no further physical test is required here.
- Stale legacy rows are handled separately by STEAM-CATALOGUE-001; they are
  not valid physical-launch test targets.

### STEAM-CATALOGUE-001 — Aurelia installed-state authority

**Status: ACCEPTED / CLOSED.** The nine confirmed stale `steam:` installed
observations were removed by Aurelia reconciliation; their 9 matching Aurelia
entitlements remain available. All 19 previously valid legacy installed rows
and all 23 Aurelia installed rows remain; visible installed Steam entries are
deduplicated. Reconciliation regression tests and a second live refresh confirm
the stale rows do not return. The verified active candidate is
`/opt/lulu/releases/e45d112-candidate-20261010073051`. See
`docs/validation-log.md` for exact IDs, backup, counts, and non-Steam comparison.

## VALIDATION

### UI-001 — Lock the default visual baseline before theming

**Status:** INITIAL VISUAL PASS — the accepted baseline and final controller-glyph
micro-fix are deployed to `/opt/lulu/dev-current`. A post-deploy Gamescope
physical capture confirms the leftmost status-strip gamepad glyph is fully
visible. `/opt/lulu/current` remains untouched. THEME-001 is now in progress as
the Modern/95 end-to-end proof-of-concept described below.

- Stabilize the accepted default UI baseline: neutral charcoal structural
  surfaces, one glass substrate per elevation root, shared expanded framing,
  fixed root-space status chrome, shared row-selection semantics, shell-owned
  controller hints, and reusable empty states. Do not build a theme engine.
- Preserve accepted Home/Recent composition, Settings navigation and panes,
  Library/Store information architecture, system transitions, Guide semantics,
  provider behavior, controller mapping, and lifecycle behavior.
- Corrective pass: status chrome now uses one root-space safe inset
  (`top=expandedShellTop`, `right=expandedShellSideMargin`) without navigation-
  dependent coordinates or a translate. Settings, Utilities, Library, and
  Installable consume shared expanded-surface X/Y/width/bottom roles. Library
  titles sit outside the glass and its substrate starts at the shared surface
  line just above the existing category rail; the list/detail layout and rail
  behavior remain intact. Settings and Utilities rows share selection fill and
  focus-border palette roles. Structural tint/internal pane darkness were
  reduced and glass transmission increased; modal overlay dimming roles remain
  separate and unchanged. Recents capture now unions live delegate bounds with
  settled layout bounds while preserving stable coordinator inputs.
- Expanded-frame convergence follow-up: `ConsoleShell.qml` now owns the common
  title, substrate and hint-band coordinates through `ExpandedSurfaceGeometry`.
  Settings, Utilities, Library and Installable receive the same surface bounds
  and 20-design-pixel inner inset. Library's duplicate 30-pixel `frameMargin`
  has been removed; its category rail remains inside the inset and list/detail
  panes now end at the shared inner bottom boundary. At 1280x720, the common
  title is `(42,28)`, substrate origin/width are `(20,94,1240)`, and the inner
  frame origin/right edge are `(40,114,1240)`; bottom coordinates follow the
  shell's live hint-band top. The full Python suite passes (1,221 tests and 85
  subtests), and the native development build passes with existing compiler
  warnings. Expanded geometry, Settings, Utilities, Library list/spatial QML
  tests pass. Installable projection retains the known provider/platform
  expectation failure (`2` observed, `3` expected). Commit `9332a86` is deployed
  to `/opt/lulu/dev-current`; Sessiond, Consoled, and Acquisitiond are active
  with that runtime configured. `/opt/lulu/current` remains unchanged. Operator
  operator acceptance of the earlier baseline was recorded; the focused final
  glyph correction is covered below.
- Final geometry correction: extend only the common substrate upward by
  `design(8)` while retaining the prior content Y/bottom bounds. The Library and
  Installable category rail now spans its actual symmetric inner frame; the
  status-strip-derived safe-width reserve is removed. Focused geometry, Library,
  Utilities QML tests pass; the focused Console UI Python tests pass. Native
  build and `git diff --check` pass. `qmllint` reports only existing warnings in
  nested delegates and StoreHome. Commit `206b7a7` is deployed to
  `/opt/lulu/dev-current`; Sessiond, Consoled, and Acquisitiond are active from
  that runtime. `/opt/lulu/current` is unchanged.
- Final glyph micro-fix: the clipped icon was the controller/gamepad glyph in
  `SystemStatusStrip.qml` via `StatusGlyph.qml`, not the controller-hint
  `ControllerGlyph.qml`. The leading controller slot clips overflow, and the
  gamepad's measured painted width exceeded its fixed glyph slot at the existing
  target height. `StatusGlyph` now width-fits only when needed and optically
  centers its tight painted bounds inside a 1.5-design-pixel safe inset. The
  focused test exercises the real clipped controller slot, confirms width-fit,
  and checks all four painted edges. Status-strip QML tests pass (9 tests),
  asset-system tests pass (5), focused Console UI Python tests pass (92), native
  build and `git diff --check` pass. The physical capture was inspected after
  deployment; UI-001 is initially passed. Commit `9de4a74` is deployed to
  `/opt/lulu/dev-current`.
- Physical validation must cover Recent end-card clipping, status-strip
  placement, Library/Installable rail clearance, Settings glass/focus,
  Utilities layout/media/hints, centered Downloads glass/empty-state/hints,
  Guide materials, and readability over bright and dark backdrop regions.
- Operator acceptance is the closure gate. Record one sweep covering those
  items and confirm that no content surface obscures the global hint band.
- Validation: Python suite passes (1,221 tests and 85 subtests); focused
  console/download UI checks and native development build pass with existing
  compiler warnings. Recent capture-envelope, SettingsSpace, and Utilities QML
  tests pass. The all-QML run reports 138 passed and 10 failures in the known
  Installable projection, native-mapping fixture, and Recent coordinator/model
  groups; no starting-revision comparison isolates those failures.
- Dev runtime refresh succeeded with DP-1 connected. Sessiond, Consoled, and
  Acquisitiond are active; Gamescope and `lulu-shell` run from
  `/opt/lulu/dev-current`. `NON_PROMOTABLE` marks the runtime non-promotable;
  `/opt/lulu/current` still resolves to
  `/opt/lulu/releases/786aba3-candidate-20261004065549` and was not changed.
- Operator recording/acceptance was recorded for the initial baseline. Sweep the Recent
  rightmost-card transition, fixed status backing, aligned Library/Installable/
  Settings/Utilities framing, wave visibility/readability, Settings focus and
  row selection, Library rail clearance, Utilities media/hints, Downloads and
  Guide overlays, and unobscured global hint band. Guide continues to use its
  separate native helper and does not sample the shell's canonical backdrop.
- Guide retains its existing separate native-helper/window architecture and now
  uses the neutral panel/selection palette. It cannot sample the shell's animated
  canonical texture from that isolated process; true backdrop-refraction there
  remains subject to physical review without changing Guide ownership/routing.
- Popup convergence initial physical acceptance: Lutris search/install and Game
  Options were accepted for initial physical use after commit `3594dc7` was
  refreshed to `/opt/lulu/dev-current`. `/opt/lulu/current` remains unchanged.
  Record visual refinements for the final UI pass; do not treat those deferred
  tweaks as a blocker for this initial acceptance.

### THEME-001 — Theme engine and external theme configuration

**Status:** VALIDATION — Modern/95 are operator-accepted; Metalheart V2 and the
Frutiger Aero implementation are deployed for development validation. Keep open
pending physical visual/controller/performance acceptance for the latest
theme-engine stress test. UI-001's accepted baseline remains Modern.
`/opt/lulu/current` is unchanged.

- A theme directory owns `theme.json`, declared font assets, optional semantic
  SVG overrides, and its wallpaper QSB. Discovery uses the immutable runtime's
  `themes/` plus user XDG data `mudos/themes/`; selection persists in
  `Mudos/lulu` QSettings at `appearance/theme`.
- ThemeManager is shared by the shell, Guide, and notification processes. It
  validates complete metadata, required semantic colors/font roles, opacity,
  radius/optics ranges, font/QSB/SVG assets, SVG XML safety, and canonical path
  containment before both discovery and selection; invalid themes are omitted
  from Settings. Missing selections fall back to `modern`. Persisted
  `mudos-default` IDs migrate to `modern` and are rewritten on load.
- The default bundle copies the accepted JetBrains Mono regular/bold/ExtraBold
  and Config-Glyphs faces, and the existing Orbit QSB. Palette, Typography,
  wallpaper entry points, generic/status icons, metadata identities, and the
  Settings System menu now resolve through the active theme authority. Glass
  off preserves tint/border substrates while suppressing the native glass item.
- Release and dev-runtime payload logic includes both `themes/modern` and
  `themes/95`. Modern's theme data and bundled assets are a directory/identity
  migration only. 95 provides the teal QSB wallpaper, square radii, disabled
  glass, Liberation Sans, original monochrome SVG overrides and generic bevel
  chrome. The UI now consumes theme tokens across core surfaces, Settings,
  Library, Downloads, Utilities, Guide, notifications, Game Options, Recovery,
  onboarding, network credential entry, launch actions, browser chrome and
  provider dialogs. Shell screens contain no theme-ID conditionals or direct
  JetBrains Mono normal-text declarations. Validation completed: all
  1,225 Python tests and 85 subtests pass; native shell/Guide/notification build
  and the ThemeManager Qt test pass; focused asset, Settings, status-strip,
  Downloads and onboarding QML suites pass, plus Recovery and Browser component-
  load smoke tests. The status-strip test uses the theme's bundled Modern font
  assets to retain its painted-bounds regression assertion.
- Source commit `47f7974` was built and refreshed to `/opt/lulu/dev-current` on
  2026-10-07; its `NON_PROMOTABLE` marker records this commit, clean source and
  `promotable=false`. Modern and 95 theme config, wallpaper and icon/font assets
  match the source checksums. Sessiond, Consoled and Acquisitiond are active;
  the shell reached Home, logged one SDL gamepad, and the immutable
  `/opt/lulu/current` selector remains unchanged. No physical controller input
  or visual theme acceptance is claimed.
- Still open from the earlier validation stage: complete glass
  optics binding coverage; inspection of all actual screens under both themes;
  live Settings selection and persistence across shell restart; Guide and
  notification visual checks; and controller/runtime acceptance. Keep
  THEME-001 open until that acceptance sweep is complete.
- Themeability follow-up implementation is in source: validated motion roles,
  duration scaling and safe easing resolution; synchronous Home/Recent/coordinator
  completion paths; motion-blur capture suppression; and stable Home domain IDs
  resolved through theme labels and title typography. Modern retains the current
  uppercase/tracked title treatment; 95 selects global no-motion and preserved
  case/no tracking. Custom `recent = "Last Played"` is covered without changing
  the `recent` semantic ID. Native schema tests and focused semantics/Home QML
  tests pass. Full headless QML execution still includes known fixture failures
  (native `Mudos.Poc` module unavailable, and pre-existing projection/mapping/
  Recent groups); at the time, no physical Modern/95 sweep had been performed. Commit
  `46b8b97` was refreshed to `/opt/lulu/dev-current` on 2026-10-07 with explicit
  operator authorization to restart the session while Sunshine was active. The
  runtime marker records this clean HEAD and `promotable=false`; Sessiond,
  Consoled and Acquisitiond recovered, and the shell started with one SDL
  gamepad. Startup journal review also shows existing QML warnings/errors in
  SettingsSpace/ConsoleShell and other unrelated system services; theme-motion
  runtime had not received a complete visual/input acceptance sweep. The
 immutable `/opt/lulu/current` selector remains unchanged. Do not close THEME-001.

- Corrective pass prepared on the canonical checkout: the no-motion defect was
  `libraryTransitionProgress` remaining at `0` when the transition finalizer
  published `space = "library"` or `"store"`; the shared spatial substrate
  therefore remained at Home-card bounds. Animated completion also depended on
  the animation's endpoint rather than the finalizer establishing it. Animated
  and synchronous completion now share the same endpoint finalizer, which sets
  progress to `1` before exposing the expanded destination and to `0` before
  returning to Home. A geometry-focused no-motion QML test covers Library,
  Installable, and both Back paths. `labels.views` and `textStyles.viewTitle`
  now theme first-class Settings, Utilities, Library, Installable, and Downloads
  headings; dynamic Library dimensions remain engine-owned and compose with the
  semantic Library label. Modern retains uppercase/tracking, while 95 uses
  preserved case/zero tracking. The ThemeManager native test and focused theme,
  geometry, Home-domain, and Library-projection QML tests pass. Settings and
  Utilities component tests remain blocked in the standalone runner because
  `Mudos.Poc` is not installed; full native build passes after wiring the
  already-used ThemeManager source into shell/Guide targets. This corrective
  corrective implementation commit `9bdc5f2` was refreshed to
  `/opt/lulu/dev-current` on 2026-10-07; its marker records this clean source
  HEAD and `promotable=false`. The active `lulu-session@2` and Consoled services
  were confirmed after refresh, and `/opt/lulu/current` remains unchanged. No
  physical visual/controller acceptance is claimed.

- **Operator update:** Modern/95 visual acceptance has since been granted. This
  does not close THEME-001; remaining gates include Metalheart runtime/performance
  inspection and the documented theme-engine gap review.

- **Metalheart stress-test implementation:** third built-in `metalheart` theme
  added without changing the theme schema or Modern/95 assets. It includes
  bundled Oxanium Variable (SIL OFL 1.1) display and Share Tech Mono (SIL OFL
  1.1) interface fonts, 35 original monochrome semantic SVG overrides, the
  compiled procedural fracture/chrome/energy wallpaper, near-black/gunmetal/
  chrome/electric-blue palette, dark glass profiles, small nonzero radii, fast
  motion, and `SYSTEM` / `ACQUIRE` / `LIBRARY` / `RECENT` title labels. Controller
  glyph compatibility uses the existing Config Glyphs face; its upstream says
  free/open-source but does not declare a specific SPDX license. The requested
  capability audit is `docs/theme-gap-audit-metalheart.md`; its highest-impact
  gap is declarative multi-stop structural surface material with separate edge
  highlights/shadows. A generic Guide title-tracking consumption issue was
  corrected to consume the already-existing `viewTitle` style. No screen has a
  Metalheart-specific branch, and Modern/95 theme files are unchanged.
- **Validation/deployment:** ThemeManager accepts and selects Metalheart; the
  representative QML test exercises configured font families, palette, radius,
  bevel, glass profile, icon URL, wallpaper URL, motion, and Home label. Theme
  inventory/release tests, native build/CTest, focused semantics and spatial
  QML suites, QSB rebuild/byte comparison, JSON validation, and `git diff
  --check` pass. Implementation commit `d28dfcc` is clean and its marker matches
  `/opt/lulu/dev-current` (`promotable=false`); source/config/QSB checksums agree.
  `lulu-session@2` and Consoled remain active, and `/opt/lulu/current` still
  points to the same immutable release.
- **Live switching/performance:** the watched user selection completed
  Modern → Metalheart → 95 → Metalheart → Modern with the same shell PID and no
  service restart; final persisted theme is Modern. On the BC-250, frame windows
  during this exercise were predominantly 60 fps (about 16.67 ms/frame), with
  some 54–58 fps windows and transient maxima up to 225 ms; the first startup
  window included an 801 ms outlier. RadeonTop reported 45 samples, mean GPU
  busy 17.59%, range 0–31.67%, but its capture was not aligned to a matched
  Modern baseline, so it cannot establish a Metalheart-specific performance
  delta. No shader/QSB load failure was logged. Existing shell QML startup
  warnings/errors were seen at unrelated display/settings bindings and must not
  be represented as theme regressions. The environment did not provide a usable
  display capture path; live switching and timing were verified, but individual
  screens were not visually inspected in this pass. Controller navigation and
  physical visual acceptance remain pending.

- **Metalheart V2 — declarative presentation primitives:** local accepted HEAD
  before this pass was `09ae3df` (the remote branch was behind at `80f7705` and
  was not used as the source of truth). Added validated optional `materials`
  profiles (`panel`, `card`, `navigation`, `status`, `overlay`, `row`) and
  `decorations` profiles with fixed corner SVG slots. The shared
  `MudosMaterialLayer` uses native Qt Quick gradients and bounded edge bands;
  `MudosDecorationLayer` uses validated, contained, monochrome SVG assets with
  semantic tint and engine-owned geometry. Absent profiles preserve the prior
  Modern/95 path. Metalheart declares six layered ramps and original bracket,
  registration, and segmented-chevron assets, while retaining flat chrome and
  the existing wallpaper.
- **Integration/guardrails:** canonical glass remains below the material layer;
  focus/selection and ornament layers remain above it. Material activation
  suppresses redundant flat tint over canonical glass, while glass-off fallback
  still paints the material over its semantic substrate. Shared panel/card/
  navigation/status/overlay surfaces and major Library, Settings, Utilities,
  Downloads, Guide, GameCard, and row consumers use the generic layers. No
  Metalheart-specific QML branches or layout/input changes were added. Release
  payloads recursively include `ui/` and `themes/`, including the new component
  QML and Metalheart decoration files.
- **Validation:** ThemeManager strictly rejects malformed material profiles,
  stops, colors, edges, decoration roles/slots/tints/ranges/coordinates, missing
  SVGs, traversal, symlink escapes, and unsafe SVG content. Native build and
  CTest pass (2); focused theme semantics pass (11); theme inventory/release
  tests pass (13); focused spatial/navigation QML tests pass. The broad Python
  suite reports 1,217 passed and 85 subtests passed, with 9 failures in legacy
  source-text assertions; no starting-revision comparison was run, so these are
  not classified as regressions or baseline failures. `qmllint` accepts the two
  new layers; it reports existing unqualified-access warnings in older
  `GameCard`, `GameOptions`, and notification bindings.
- **Deployment:** commit `4cba15b` is deployed to `/opt/lulu/dev-current` from
  the canonical checkout. Its marker reports `dirty=false` and
  `promotable=false`; new QML/SVG checksums match source. `/opt/lulu/current`
  remains pointed at the unchanged immutable release
  `/opt/lulu/releases/786aba3-candidate-20261004065549`.
- **Acceptance still pending:** no physical screen/controller sweep or matched
  BC-250 performance comparison was completed. The available display capture
  path does not expose Gamescope's shell output; headless validation cannot
  substitute for inspection of Home, Library, Settings, Utilities, Downloads,
  Guide, cards, and status, nor for Modern/95 visual comparison. Keep THEME-001
  open until operator visual/controller acceptance and performance review.

- **Frutiger Aero final theme-engine stress test:** source implementation is
  underway on the canonical checkout from `ef14dfe`. It adds the fourth
  built-in theme (`frutiger-aero`), data-only original PNG semantic overrides,
  generic semantic text treatments, and a shader-based Aero palette/material/
  glass/radius/motion configuration. PNG schema accepts legacy tintable SVG
  shorthand plus `{file, render}` descriptors (`SVG+tint`, `PNG+original`);
  one native resolver returns URL/format/render mode. Original PNGs use direct
  `Image` paths with aspect fit and no `MultiEffect`; status icons retain their
  existing safe-inset geometry. PNG payloads are content-decoded and bounded to
  4 MiB, 1024×1024, and 1,048,576 pixels. Original, theme-authored colorful
  pictograms are used (not Crystal Project/archive artwork); font and asset
  provenance is in `themes/frutiger-aero/ASSET_PROVENANCE.md`.
- Semantic text roles `heading`, `body`, `metadata`, `annotation`, and `status`
  add font-role, weight, case, and letter-spacing presentation only; pixel sizes
  remain engine-owned and the existing title roles are preserved. The Frutiger
  theme uses Noto Sans (Apache-2.0), daylight sky/aqua/grass colors, six glossy
  gradients, enabled high-transmission glass, exact 22/16/12/16/18/22 radii,
  and an original slowly animated sky/meadow/water/bubbles QSB wallpaper with
  sparse corner ornaments. No raster wallpaper primitive was needed; this
  remains a documented future gap only if a photo theme cannot be represented
  adequately by shader.
- **Automated verification:** ThemeManager native tests include PNG
  validation/resolution, invalid mode/signature/corrupt/oversized/traversal/
  symlink cases, text-role bounds, and Frutiger → Modern → Metalheart selection.
  QML tests cover PNG-direct versus SVG-tint/fallback switching in `MudosIcon`,
  `StatusGlyph`, and a metadata row; theme semantics cover all five text roles.
  Physical Frutiger visual/controller/performance acceptance is still pending.
  Source commit `1c593bf` was refreshed to `/opt/lulu/dev-current` on
  2026-10-07; its `NON_PROMOTABLE` marker records the clean source and
  `promotable=false`. Theme JSON, QSB, representative PNG, and Noto font
  checksums match source. Session, Consoled, and Acquisition services are active.
  `/opt/lulu/current` remains on the unchanged immutable release. Keep THEME-001
  open for the physical acceptance sweep.

- **Metalheart wallpaper finalisation:** starting from local clean HEAD
  `48b56ec`, replaced only `themes/metalheart/wallpaper/wallpaper.frag` and its
  QSB, plus this record, the theme description, and a reproducibility test. The
  old low-cost polar ribbon/fractal field is replaced by the operator-accepted
  Shadertoy direction: raymarched chrome nexus, six viewport-breaking tapered
  spikes, three orbital loops, 15 medium spikes, eight needles, and a pale
  technical/blueprint field with linework, rings, a moving energy sweep, and
  subtle object motion. The port uses the required Shadertoy-preserving
  `qt_TexCoord0.y` flip, `u_resolution` pixel coordinates, and `u_time`. After
  an initial post-port sample saturated the GPU, raymarching was reduced from 96
  to 20 steps, the conservative step multiplier raised from 0.76 to 0.84, AO
  samples reduced from five to two, and the six-tap normal estimate replaced
  with a four-tap tetrahedral estimate. All six large, three orbital, 15
  medium, and eight needle primitives remain. The theme's wallpaper speed
  remains enabled at 1.0. This performance tuning still needs physical visual
  validation against the accepted Shadertoy composition.
- **BC-250 baseline before replacement:** with Metalheart selected in the
  1920×1080 dev shell and the old shader active, a 30-sample/30-second idle
  `radeontop` capture reported mean GPU busy 21.83% (10.00–29.17%), VRAM
  394.60 MB, GTT 47.03 MB, and SCLK mean 3.27 GHz (2.48–3.79). This is a
  baseline sample, not a matched interaction or frame-time measurement. The
  initial 32-step version saturated GPU at 99.97% mean in 1920×1080 after the
  display reconnected. The final 20-step/tetrahedral-normal/two-sample-AO
  version measured 42.28% mean GPU busy (0–100% range) over 30 idle seconds at
  1920×1080, versus the old shader's 21.83% mean (10–29.17%) over 30 seconds.
  Utilization is materially improved from the initial port but remains above
  baseline; `radeontop` does not provide frame-time or interaction smoothness
  acceptance. Physical visual, glass, switching, and controller checks remain
   pending; do not infer them from utilization or shader compilation.

- **Metalheart wallpaper dark-field/edge/performance iteration:** source
  started at `6dde5d6`; wallpaper-only commits `2159331` and `1c33a24` darken
  the technical field and reflection environment, move the camera framing
  toward an estimated nexus position near 61% x / 31% y, and reduce scene
  primitives: major spikes 6→4, orbital loops 3→2, medium spikes 15→7,
  needles 8→0, and fused center nodes 5→3. Major silhouette directions retain
  rightward, lower-left, upper, and diagonal spikes; remaining medium spikes
  have a larger minimum radius. A conservative world-space AABB centered on
  the hub (half-extents 5.35, 4.05, 1.65) clips each ray to its scene interval.
  Final march uses 24 steps, multiplier 0.90, and one AO sample. Technical grid,
  rings, horizon, and scan lines use derivative-aware widths; raymarched surface
  hits blend over an estimated one-pixel projected footprint without
  supersampling. Source colors move from the bright blue-gray gradient to a
  near-black lower field (`0.003,0.006,0.010`) and subdued upper steel/cyan
  (`0.010,0.025,0.035`) with restrained cyan drafting marks. Chrome environment
  highlights and the faster motion remain.
- **Steady idle telemetry after this iteration:** after the device settled, a
  120-second GPU sample averaged 54.44% busy (45–67.5%); a separate 60-second
  sample averaged 44.57%. This is below the pre-iteration 99.83%, but above the
  prior shader's 21.83% baseline. Across 63 consecutive fan-curve readings over
  3m10s, PWM held exactly 128, CPU Tctl averaged 72.17°C (71–74°C), and pump
  fan RPM averaged 1714 (1666–1948). The GPU edge sensor reports 0°C throughout
  and is not a valid temperature measurement. Fan target passed for this stable
  idle window; longer-term performance and physical judgement of placement,
  darkness, silhouette AA, glass interaction, and Home overlap remain pending.
  QSB source/deployed checksum at this iteration is
  `541689b8954ff0d6c1c1da68cd8e63035ca369f18fc6ff49a4adb8265303436c`.

- **Metalheart temporal-stability follow-up:** the static object centre is moved
  farther up/right by changing the hub from `(-0.10,-0.03,0)` to `(0.04,0.02,0)`
  and camera target from `(-0.62,-0.50,0)` to `(-0.75,-0.64,0)`; the estimate is
  now about 67% x / 24% y. The construction rings move to `(0.52,0.28)`. Four
  major spikes and two loops remain; medium spikes are 5→4, the three smaller
  major spikes are thickened, loop tube radii 0.022/0.018→0.032/0.030, and all
  needles remain removed. The three center nodes and per-spike directions are now static; only
  coherent whole-object motion, background scan, and energy sweep animate. The
  AABB remains, tightened to center `(0.04,1.17,0)`
  and half-extents `(5.25,2.78,1.50)`. AO is disabled; march remains 24 steps
  with multiplier 0.92. A fixed projected-footprint estimate is used for edge
  candidacy.
- **Idle profile after temporal-stability follow-up:** 120-second GPU sample
  averaged 55.98% busy (43.33–70.83%). Over the accompanying 3-minute fan
  window, CPU Tctl averaged 67.12°C (61–75°C), PWM ranged 120–128 (never rose
  to 150), and pump fan RPM averaged 1,671 (1,604–1,726). GPU edge temperature
  remained unreadable at 0°C. The fan target of no wallpaper-related rise to
  PWM 150 passed this window, though GPU utilization remains substantially
  above the old-shader baseline. Motion shimmer and the final placement still
  require operator physical confirmation.

- **Metalheart adaptive two-sample edge test:** commit `18cf950` replaces the
  broad raymarch residual blend with a stable `EPS` hit test and adds a second
  fixed subpixel ray only for grazing hits or near-miss rays inside the scene
  bound. This is edge-conditioned 2-sample spatial AA; it does not double-sample
  the whole frame and uses no temporal jitter. QSB compiles reproducibly, the
  theme/release tests (15) and theme-semantics QML tests (12) pass. Source and
  deployed QSB checksum:
  `a6c90ec5e14bb230c930406f37ed88aa4f8b41f443e0309465b87514b6e8afb3`.
- **BC-250 after adaptive AA:** a 90-second GPU sample averaged 55.96% busy
  (43.33–72.50%). Over the settled two-minute fan window, CPU Tctl averaged
  62.58°C (60–68°C), fan PWM ranged 110–128 (never 150), and pump fan RPM
  averaged 1,624 (1,488–1,719). GPU edge sensor remained 0°C and is unusable.
  The target of no fan escalation above PWM 128 passed in this window, although
  GPU busy remains well above the old shader's approximately 21.83% baseline.
  Physical confirmation that motion shimmer is materially reduced and the
  object aligns with the requested Home reference points remains outstanding.

- **Metalheart final aliasing/reposition pass:** source started from
  `258ffea`; wallpaper-only commit `6d70dcc` keeps the simplified 4-major / 2-
  loop / 4-medium / 0-needle / 3-node scene and moves the camera target to
  `(-1.55,-1.20,0)`. With hub `(0.04,0.02,0)` this projects the static nexus
  centre to approximately 68.1% x / 27.2% y. Drafting rings move to `(0.66,0.42)`.
  Candidate-edge detection now includes near misses within 3 projected pixels
  and grazing hits with `abs(dot(normal,ray)) < 0.55`. Those pixels receive a
  fixed three-point triangular pattern spanning quarter-pixel offsets (three
  samples total only on candidate edges). No full-frame supersampling or
  temporal jitter is used. Major cone tips and loop tubes are thicker; the
  dynamic grain was removed. Ring/grid/horizon/scan retain derivative-aware AA,
  with a small feather increase; diagonal texture now has analytic footprint
  filtering. Dark field, shading, animation, 24 steps, 0.92 multiplier, AO-off,
  and the asymmetric AABB are retained.
- **BC-250 after final AA/reposition pass:** over 120 seconds GPU busy averaged
  50.10% (0–75%). In a settled three-minute fan window, CPU Tctl averaged
  64.05°C (60–71°C), GPU edge remained unreadable at 0°C, PWM ranged 120–128,
  and pump fan RPM averaged 1,660 (1,600–1,719). No PWM 150 occurred; the fan
  curve was not changed. The PWM ceiling target passed for this window; GPU busy
  remains above the old shader baseline. Physical confirmation that stair
  stepping is materially reduced and the new upper-right placement matches the
  operator's Home landmarks is still required.

- **Metalheart edge-highlight lighting correction:** commit `fce5b41` leaves
  placement, geometry, motion, and adaptive edge sampling unchanged. Reflected
  environment bands are broadened and reduced in energy. Specular exponent is
  reduced from 110 to 48 while its multiplier drops from 2.25 to 0.95; Fresnel
  exponent changes from 5 to 4 and its environment gain from 0.58 to 0.32. The
  explicit blue rim term changes exponent 7→4 and gain 0.88→0.30, with lower
  RGB intensity. A soft `col/(1+0.22*col)` shoulder compresses highlight peaks.
  This broadens and lowers the edge response; no geometry or additional AA
  changes were made. QSB reproducibility, 15 theme/release tests, 12 theme
  semantics tests, and `git diff --check` passed.
- **BC-250 after highlight correction:** 90-second GPU busy averaged 48.27%
  (0–72.50%). Over the associated two-minute fan window, CPU Tctl averaged
  64.55°C (61–70°C), GPU sensor remained invalid at 0°C, PWM ranged 120–128,
  and pump fan RPM averaged 1,670 (1,602–1,719). PWM remained within the 128
  ceiling; the fan curve was unchanged. Physical verification of the perceived
  edge smoothness remains with the operator.

## CLOSED

### UNINSTALL-001 — Complete provider-owned uninstall coverage

**Status:** CLOSED — operator accepted the uninstall implementation and dev
validation on 2026-10-06. The earlier shell crash and Aurelia transition defect
were corrected in the dev runtime; the accepted future hide-title UX is tracked
separately below and is not a blocker for this item's closure. `/opt/lulu/current`
was not changed.

- Deployed implementation commit: `98b4667c5fd26335f0cf1517a94f62acb4b936b0`
  (`Complete provider-owned uninstall lifecycle`). The dev runtime reports this
  exact HEAD, `dirty=false`, and `promotable=false`. `/opt/lulu/current` remains
  on its existing immutable candidate release.
- Safe live checks after refresh: Sessiond, Consoled, Acquisitiond, admin, and
  InputPlumber are active; the shell is running from dev-current; Acquisitiond's
  D-Bus capability method is present. Read-only capability calls reported
  supported local, Flatpak, and Mudos-marked GOG uninstall examples, while an
  installed Steam/Aurelia example incorrectly reported unsupported. No uninstall
  request was submitted during those checks.
- **Operator acceptance report (2026-10-06):** the operator reported that
  Steam and Lutris appeared not to offer uninstall, then reported that attempting
  uninstall for an Epic title and a Wii title had the same apparent Mudos crash.
  Read-only service checks afterwards showed Acquisitiond and Sessiond active;
  `lulu-shell` had two `SIGSEGV` core dumps at 04:39:17 and 04:44:51, each with
  Qt Quick frames through `QQuickFlickable::geometryChange` / `setHeight` and
  QML binding evaluation, reached while `SystemStatusBridge` handled an
  Acquisitiond state-snapshot update. This is strong evidence of a shell UI
  crash associated with acquisition snapshot delivery, not evidence of separate
  Epic and local-ROM executor crashes. The exact QML binding/corrupt state is
  still not identified. Later job records show the Epic and Wii/local removal
  jobs reached `completed`; the operator subsequently confirmed the shell did
  not crash during the Aurelia test.
- Steam's missing action was an implementation defect, not intended policy.
  Aurelia supports per-AppID uninstall; Mudos should invoke that API and then
  reconcile Aurelia's installed list. Use the catalogue provider ID as the AppID
  (for example, `1245620` is illustrative, not a hard-coded target). Never
  substitute SteamCMD or direct Steam-library deletion. Lutris uninstall is
  available only for Mudos recipe installs and Mudos-registered
  local/manual registrations; provider-discovered entries intentionally have
  no Mudos uninstall action. Confirm which kind of Lutris entry the operator
  tested before treating that report as a provider implementation defect.
- Source now enables Aurelia uninstall jobs, validates the decimal AppID, calls
  Aurelia's `uninstall <AppID>` command, and confirms the title is absent from
  Aurelia's installed list before completing the job. Fixture coverage passes;
  this correction was deployed to `/opt/lulu/dev-current` on 2026-10-06 by the
  canonical `scripts/dev-runtime.sh refresh`. The non-promotable marker records
  HEAD `864df05d1f66e59c02e6ad437e76e4fd35dbd586`, `dirty=true`, and
  `promotable=false`. Session, Consoled, Acquisitiond, Admin, and InputPlumber
  are active; the shell is running. A read-only `CanUninstall` check for
  installed game `steam:104200` returned `supported=true` with the Aurelia
  description. No uninstall request was submitted and no real title was
  removed. `/opt/lulu/current` remains
  `/opt/lulu/releases/786aba3-candidate-20261004065549`.
- **Aurelia operator test follow-up:** two removal jobs for `Among Us`
  (`steam-aurelia:945360`) and `Baldi's Basics Classic Remastered`
  (`steam-aurelia:1712830`) ran the Aurelia uninstall command and observed both
  AppIDs absent from Aurelia's installed list, but Acquisitiond marked the jobs
  failed with `invalid job transition: starting -> completed`. This was the
  executor's terminal-state bug, not a failure of the provider command. The
  executor now transitions through `finalizing`; a real-JobManager fixture test
  covers the valid lifecycle. Do not retry these AppIDs: they are already
  absent according to the provider's post-command check.
- Do not use real titles for further physical validation unless explicitly
  approved. `/opt/lulu/current` was not changed.
- Follow-up UI observation: the operator reports Steam entries disappear
  immediately after removal, while some other providers remain visible until
  leaving and reopening the menu. The immediate refresh on job submission or
  job completion can race Acquisitiond's asynchronous provider reconciliation.
  `ConsoleShell.qml` now refreshes its Library and Installable projections when
  `CatalogueModel.generation` advances, after Consoled publishes the reconciled
  catalogue. Structural regression coverage passes. The UI follow-up was
  deployed to `/opt/lulu/dev-current` on 2026-10-06 at 04:05:02Z by
  `scripts/dev-runtime.sh refresh`; the `NON_PROMOTABLE` marker records HEAD
  `864df05d1f66e59c02e6ad437e76e4fd35dbd586`, `dirty=true`,
  `promotable=false`. The operator accepted the dev validation and authorized
  closure on 2026-10-06.

- Current game-producing provider matrix:
  - **Steam / Aurelia:** invoke Aurelia's per-title `uninstall <AppID>` operation
    for the installed catalogue row, then reconcile Aurelia's authoritative
    installed list. Validate a decimal AppID and use only Aurelia's canonical
    Mudos Steam-library configuration. Do not fall back to SteamCMD, account
    sign-out, direct library deletion, or shared-runtime cleanup.
  - **Epic / Legendary:** use Legendary's per-app uninstall command only for a
    valid app identity in Mudos' canonical Epic library; reject third-party
    managed titles and paths outside that library. Service-restart replay
    checks Legendary's authoritative installed list and is idempotent when the
    title is already gone.
  - **GOG / gogdl:** gogdl has no uninstall command. Remove only a direct-child
    per-title directory with a matching Mudos ownership marker under the
    canonical GOG library. Never delete a shared prefix or unmarked install.
  - **Flatpak:** use Flatpak/libflatpak's application uninstall operation for
    the user installation; retain Flatpak's app-data policy (no
    `--delete-data`) and reconcile the user-installed app snapshot.
  - **Lutris:** for Mudos recipe installs, remove the Lutris registration and
    then remove only the exact canonical per-game directory with a matching
    recipe ownership marker. For Mudos-registered local/manual games, remove
    the Lutris registration only and preserve all user files. Provider-discovered
    Lutris entries are not uninstallable through Mudos.
  - **Local ROM/emulation content:** use the bounded local-content executor for
    Mudos-catalogued content under its canonical platform root. ROMM is a
    remote library source; when a ROMM title is linked to a local copy, removal
    targets that local copy. ROMM itself has no local uninstall operation.
  - Torrent/Usenet acquisition, launch-only runtimes, shared services, and
    library-only entries do not create provider-owned installed-game payloads
    and are not offered as game uninstall targets.
- Acquisitiond returns a generic provider capability including support,
  reason, explicit-confirmation requirement, measurable-progress state, and
  active-operation state. The game action is backend-gated, confirms before
  submission, and suppresses a duplicate action while a removal is active.
  Removal remains a persisted Acquisitiond job; failed jobs preserve the
  catalogue state and provider reconciliation runs after every terminal result.
- Automated fixture coverage exercises successful and failed removal,
  idempotent retries, active-request deduplication, provider identity,
  reconciliation and path/ownership refusal. No real appliance games were
  uninstalled for this work.
- **Physical acceptance after dev-current deployment:** with a controller,
  open game options for one disposable title in each currently available
  provider; verify Steam/Aurelia and supported Lutris entries offer Uninstall,
  while provider-discovered Lutris entries do not; verify supported actions require
  explicit confirmation; verify Back cancels confirmation; verify an active
  removal cannot be resubmitted; verify successful removal updates Library and
  Recents after provider reconciliation; verify a failed provider removal
  reports failure and leaves the installed title represented. Use only
  disposable installs or explicitly approved test titles—never operator game
  data as an unattended fixture. Also physically test a Lutris manual
  registration and confirm its files remain after unregistering.
- The initial development refresh was explicitly authorized and completed; it
  restarted the development session as expected. Production
  `/opt/lulu/current` remains untouched.

## ACTIVE

### DISPLAY-001 — Recover the idle presentation after DRM wake/relink

**Status:** OPEN — a real display sleep/wake caused persistent no-signal even
though DRM reported a healthy connected output. Current Sessiond recovery did
not restore the display. Reproduce and complete an end-to-end automatic recovery
test before closing; do not ask the operator to disconnect/reconnect the display.

- Incident evidence (2026-10-07): DP-1 remained `connected`, `enabled`, DPMS On,
  link-status Good, and had an active 1920×1080 CRTC while the operator reported
  no video signal. The kernel logged `bc250 relink: stream down` followed by an
  AMD DC `triplebuffer_flips` warning. Existing readiness checks inspected
  Gamescope/window state and connector presence, so they incorrectly left a
  stale scanout running.
- Regression archaeology (2026-10-08): commit `1ae5388` added the surviving-
  Gamescope DRM-uEvent recovery path. It returned unless both lifecycle was
  `shell` **and** `_presentation_ready` was true. The readiness watchdog
  correctly clears that bit on output loss, so the reconnect event was discarded
  precisely in the surviving-Gamescope failure mode. The same patch stamped a
  10-second cooldown on the first event; a reconnect within that interval could
  also be swallowed after the initial attempt. The regression test first failed
  at this guard after exercising the real watchdog readiness transition.
- The existing Gamescope-exits/output-absent path dates from `2a6a183` (2026-10-01):
  Sessiond stays alive and `bootstrap_shell()` waits for an output before starting
  Gamescope. That path is preserved. No retained journal or source acceptance
  record establishes a later physical known-good revision for the distinct
  “Gamescope survives with stale scanout” case; `1ae5388` is the first revision
  intended to cover it.
- Implementation: explicit recovery-required/pending state survives watchdog
  readiness loss; only lifecycle `shell` can trigger a restart. An absent output
  records intent and waits, while a DRM wake event can recover even if forced
  DP-1 sysfs remains `connected`. The 10-second cooldown is removed; pending
  recovery coalesces duplicate events and failed attempts remain retryable.
  Readiness and graphical launch context are invalidated before recovery and
  accepted only after a new shell/context is verified. Game/foreign sessions
  defer recovery until shell ownership returns. The new regression was first
  run against the old handler and failed at the readiness guard; it now covers
  watchdog loss/reconnect within the old cooldown window, absent-output wait,
  duplicate events, game deferral/return, failed-attempt retry, and fresh shell
  context. Related Sessiond/readiness/lease tests: 60 passed and 13 subtests.
  The full suite has 1,250 passing tests and 85 subtests; 11 unrelated pre-existing
  UI/provisioning/release checks fail. Implementation is committed as
  `bd5a821` and is ready for the canonical dev refresh; `/opt/lulu/current` must
  remain unchanged.
- Runtime evidence recorded during this pass: the previous boot's retained
  journal has no Sessiond/seatd display-recovery sequence or matching DRM
  disconnect/reconnect records. The current boot logs forced DP-1 at kernel
  startup and BC-250 AMD IRQ/infoframe warnings, but no hotplug recovery attempt.
  Live `/sys/class/drm/card1-DP-1/status` reads `connected`, `enabled`, DPMS On,
  mode 1920×1080; the kernel command line retains `video=DP-1:1920x1080@60e`.
- Physical disconnect/reconnect cycles were not performed in this pass. Keep
  DISPLAY-001 OPEN until the three requested cycles (including a short
  reconnect) pass with no manual intervention.
- Follow-up physical source-switch attempt (2026-10-08, after dev refresh):
  the operator switched the display source away and back; video did not return.
  At 22:50:49 the kernel logged `bc250 relink: stream down` and `blank was 0 ms,
  under the 3000 ms threshold`. Sessiond PID `87915` and Gamescope PID `87989`
  remained unchanged, with no Sessiond hotplug/recovery log in the interval.
  DP-1 still reported connected/enabled, DPMS On, 1920×1080. This is a failed
  physical acceptance cycle: the new recovery handler was not observed to run.
  A bounded DRM udev monitor was started for the next operator-provided source
  switch to determine whether this BC-250 event emits a DRM uevent that the
  current `HOTPLUG=1` filter can receive. No manual Sessiond/Gamescope restart
  was performed; keep DISPLAY-001 OPEN.
- Second source-switch attempt (operator report: done): the kernel again logged
  `bc250 relink: stream down` at 22:52:31 (signal=512), while Sessiond PID
  `87915` and Gamescope PID `87989` remained unchanged. The 120-second
  `udevadm monitor --kernel --property --subsystem-match=drm` capture showed
  only its startup banner and no DRM `KERNEL` event for that relink. DP-1
  continued to report connected/enabled, DPMS On. This indicates this source
  switch/relink path does not produce a DRM uevent visible to udevadm, so the
  current event-only recovery mechanism cannot cover it; investigate a
  BC-250-appropriate signal before claiming physical acceptance.
- Historical comparison and authorized idle restart test (2026-10-08):
  Sessiond's live `GetState` immediately before the test showed
  `lifecycle=shell`, `active_identity=null`, and `presentation_ready=true` while
  the operator reported no TV picture. `_refresh_presentation_readiness()`
  checks connector status, shell/Gamescope liveness and selection, and fresh
  graphical context; it does not observe a physical scanout or received image.
  With the forced connector still reported connected and the context intact,
  those logical checks can remain true indefinitely despite a blank TV.
- A matching synthetic DRM event was sent only after confirming the appliance
  was idle and under the operator's requested controlled-reinitialization test.
  The existing Sessiond path kept Sessiond PID `87915`, stopped Gamescope PID
  `87989`, and launched PID `151796`; a new shell was selected and readiness
  returned true. Gamescope 3.16.31 logged opening `/dev/dri/card1`, DP-1
  connected, and selecting 1920×1080@60. The operator confirmed the TV picture
  still did not return. Thus a Gamescope/shell reinitialization alone does not
  recover this observed failure; the remaining failure is below the shell's
  logical presentation checks (KMS/link/scanout or the effective output policy).
  No Sessiond restart, reboot, GPU reset, or package/config experiment was done.
- Leading regression hypothesis, not yet proven: tracked commit `f97109f`
  (2026-10-04) introduced `video=DP-1:1920x1080@60e`; `92a2476` removed that
  tracked boot override on 2026-10-06. However, the appliance still has a
  distinct local `/etc/limine-entry-tool.d/60-lulu-headless-evening.conf`, born
  and modified 2026-10-06 20:27, whose comment calls it a temporary Sunshine
  headless test and whose active line re-adds the same forced mode. The live
  kernel command line confirms it remains effective. It masks the output-loss
  condition used by Sessiond's earlier generic fallback: since DP-1 remains
  `connected` and Gamescope survives, the preserved `2a6a183` path (Gamescope
  exits while output is absent → Sessiond waits → output returns → bootstrap)
  is not entered. No matching DRM uevent exists to invoke the newer handler.
  Do not remove this override until its headless/Sunshine impact is understood.
- A second confounder falls in the same earliest credible regression window:
  pacman upgraded on 2026-10-06 at 20:54: Mesa 26.2.2-2→26.2.4-1.244,
  Gamescope 3.16.28.r43.gea3579ed-1→3.16.31.r6.g38293404-1, BC-250 kernel
  7.2.4-1.115→7.2.9-1.250, and AMD firmware 20260810-2→20260916-1. Current
  versions are the latter versions. Available journal history contains only
  Oct 8 boots, and repository records do not establish a dated physical
  source-switch pass immediately before these changes. Therefore the earliest
  credible regression window is Oct 6 20:27–20:54 through the Oct 7 incident;
  source history alone cannot isolate forced output policy from the package
  upgrades or identify a definitive last physically known-good revision.
- Gamescope has used the DRM backend since the initial Sep 7 session baseline;
  no historical backend switch was found. Display Settings (`8134f2c`, Sep 17)
  introduced validated `--prefer-output`/mode policy and a session restart on
  Apply. Current live launch uses `--backend drm --prefer-output DP-1`
  `--output-width 1920 --output-height 1080 --nested-refresh 60.0`; no persisted
  display-state file or explicit `/etc/lulu/presentation.conf` output override
  was found, so DP-1 selection follows the forced connector's apparent DRM
  presence. These mode arguments do not themselves supply a physical-link
  health signal. Readiness evolution (`f8f28b2` through `a25b472`) protects
  launch context freshness, but that logical invariant is not physical-output
  proof.
- No minimal software correction is justified yet: the observed transition
  supplies neither connector absence, Gamescope exit, nor a DRM uevent, and a
  controlled Gamescope restart failed to restore the image. Do not add periodic
  restarts or weaken the readiness invariant. Further automatic recovery needs
  a reliable generic signal or restoration of the previously effective link
  reacquisition behavior, while retaining the headless/Sunshine requirement.
  DISPLAY-001 remains OPEN; no code correction or dev refresh was performed
  during this archaeology pass, and `/opt/lulu/current` remains unchanged.
- Sunshine isolation test (operator authorized, 2026-10-08): the development
  `lulu-sunshine-dev.service` was stopped (not disabled and no configuration
  changed). With Sessiond reporting idle shell/no active identity, a second
  synthetic event exercised the same Sessiond-owned scoped Gamescope restart:
  Sessiond remained PID `87915`, Gamescope changed from `151796` to `168932`,
  and a fresh shell/context reached `presentation_ready=true`. Gamescope again
  opened the DRM card and selected DP-1 1920×1080@60. The operator confirmed
  there was still no TV picture. Stopping Sunshine alone had not restored it.
  This rules out Sunshine being sufficient to explain the failed reacquisition;
  it does not prove Sunshine has no interaction while active. Sunshine remains
  stopped for now; its user unit remains enabled. No GPU reset, reboot, forced-
  output edit, or package downgrade was attempted. The failure remains below
  Gamescope process/context readiness, and no code correction is warranted
  until the effective forced-output policy versus the coincident Oct 6 stack
  upgrades can be distinguished without sacrificing headless presentation.
- Retained journal coverage is limited to the current and immediately previous
  boot. It confirms the forced `video=DP-1:1920x1080@60e` configuration, the
  BC-250 `stream down`/`triplebuffer_flips` incident is retained in this backlog,
  and current boot-time DP-1 forcing plus AMD IRQ/infoframe warnings; it contains
  no retained disconnect/reconnect uevent or Sessiond recovery attempt from the
  incident boot. Current sysfs reads `DP-1 connected`, enabled, DPMS On,
  1920×1080. Sysfs therefore cannot be the sole recovery signal on this setup.
- Physical acceptance remains OPEN. Do not close until three disconnect/reconnect
  cycles (including a reconnect within ten seconds) pass without reboot or manual
  service/Gamescope intervention; confirm Sessiond PID remains stable, fresh
  shell/context and `presentation_ready` return, and controller navigation works.
- A user-authorized PCI FLR attempt left the kernel reporting the GPU “device
  lost from bus” and caused repeated amdgpu failures. Do not repeat FLR as a
  recovery step. The host later restarted for an unrelated reason; the display
  was present again after returning. Current state is display available, but
  automatic recovery remains unverified and the triggering hardware/driver
  failure is not diagnosed.
- Follow-up should correlate DRM uevents, BC-250 `cs_relink` logs, and actual
  output recovery across a controlled idle/wake test. Any future GPU reset
  mechanism needs a supported amdgpu reset path and an explicit recovery plan;
  do not treat `link-status=Good` or an active CRTC as proof that a picture is
  reaching the panel.

### RECOVERY-001 — Recovery UI reports a connected controller as absent

**Status:** OPEN — investigate controller-presence detection and recovery-screen
reporting. Do not treat recovery UI's missing-controller message as authoritative
without comparing it to the controller source.

- Operator report (2026-10-06): Mudos Recovery claimed the controller was not
  present while the controller was connected.
- During recovery triage, `/v1/status` reported the controllers component
  healthy with `connected_count: 1` from `InputPlumber GamepadOrder`, while the
  normal graphical session was stopped. Reconcile the recovery UI's displayed
  controller state with this health snapshot and live input source; add a
  regression test for the mismatch.

### SET-001 — Consolidate System Settings navigation

**Status:** VALIDATION — implementation, automated tests, and dev-current
deployment are complete; physical/presentation acceptance remains.

- **Back-to-Home acceptance: PASS.** Operator confirmed that Back from Settings
  must return directly to normal Home; the standalone two-card System landing
  was removed. The remaining checklist below is still open.

- System exposes only **Settings** and **Utilities**. Settings categories are
  derived from the existing provider-backed pages: Network, Bluetooth, Display,
  Audio, Controllers, Storage, and System.
- Settings uses a two-panel category/content shell without a horizontal category
  rail. Existing category components retain their models, refresh behavior,
  subviews, and mutation/service boundaries.
- Physical/presentation acceptance checklist:
  1. Open System and confirm only **Settings** and **Utilities** are present.
  2. Open Settings; confirm title directly precedes the two panels, with no
     horizontal category rail or reserved gap. Check list density/glyphs,
     panel-level glass, plain setting rows, couch readability, and active border
     contrast while focus moves between panels.
  3. With a controller, move up/down through categories; move right into content;
     navigate controls; use left (or Back where a control consumes left) to
     return to categories. Back from Settings must go straight to normal Home,
     with no intermediate System card landing.
  4. Visit Network, Bluetooth, Display, Audio, Controllers, Storage, and System;
     confirm their live models populate/update and category changes do not reset
     discovered state. Check nested details/subviews and unwind each with Back.
  5. Confirm Utilities still opens and works. Do not apply display modes, eject
     storage, pair/connect devices, or change network settings during this pass.
- `/opt/lulu/current` must remain unchanged.

**Implementation status:** latest commit `9524cc2` removes the standalone
System landing and returns Back directly to Home. Earlier commits implement the
unified Settings shell, category hosts, and corrected dev refresh wiring.
Settings hosts are exclusive by category: System and Bluetooth use SystemSpace,
while Network, Display, Audio, Controllers, and Storage use their existing
dedicated components. Full Python suite: 1,205 passed and 85 subtests; focused
settings QML suite: 5 passed; QML lint and shell syntax checks passed. The final
`/opt/lulu/dev-current` deployment and running ConsoleShell are verified below.
Three failed starts during initial validation entered the existing recovery
latch; after correcting the duplicate QML properties, only that failure history
was cleared and the normal ConsoleShell was restarted. `/opt/lulu/current`
remains on its original immutable release.

### LIBRARY-001 — Open the selected Library dimension

**Status:** OPEN — operator-reported navigation defect; not investigated or
fixed.

- On the Library home, selecting a Provider or Platform card and opening it
  always enters the Provider view, regardless of which card was selected.
- Once the Library view has opened, switching categories within the view works
  normally. Preserve that working behavior while tracing the initial
  card-selection/open transition.
- Acceptance: opening each Provider/Platform card enters its corresponding
  dimension and selected category; in-view category switching continues to
  work in both dimensions.

### UNINSTALL-UX-001 — Hide titles while uninstall runs

**Status:** ACCEPTED — requirements captured; implementation deferred.

- Uninstall must invoke provider removal; catalogue refresh is post-removal
  reconciliation, not the mechanism used to make the title disappear from the
  current Library view.
- Add a **Hide** action under Game Options and a **Show hidden titles in
  library** setting. The setting is deliberately session-only/in-memory, is not
  persisted, and resets to its default after any Mudos session reload. Decide
  the persistence/lifetime policy for individual hidden-title membership
  separately from this setting.
- After the user confirms Uninstall, add that game ID to the same hidden-title
  mechanism before submitting provider removal. It should leave the Library
  view immediately while asynchronous removal runs; do not treat temporary
  hiding as provider success or mutate installed catalogue state early.
- After successful uninstall, refresh/reconcile Library from provider state;
  only after that refresh completes, remove the game ID from the temporary
  hidden set. The title then remains absent because provider reconciliation
  removed it, not because it remains hidden.
- Define and test failure/cancellation behavior so an installed game cannot
  remain invisibly hidden indefinitely. Likely refresh the still-installed
  catalogue and restore visibility after a failed or cancelled removal.
- Turning **Show hidden titles in library** on reveals hidden entries without
  changing their hidden membership; turning it off hides them again. Verify the
  setting resets on session reload while membership follows its separately
  chosen persistence policy.

### RECENTS-001 — Steam Recents and legacy launch behavior after Aurelia migration

**Status:** FIXED — direct Steam-family launch recents and legacy Aurelia identity
projection corrected; full regression suite passed.

- Root causes were separate: direct Steam/Aurelia launches through the UI bridge
  bypassed Consoled's `mark_played` path, while legacy `steam:<AppID>` recents
  remained in the recent query after Library had switched to the Aurelia row.
  The latter recent identity was not launchable through the current Library
  projection when its Aurelia counterpart existed.
- After a Sessiond-accepted Steam or Aurelia launch, the bridge now records the
  launch through Consoled. Legacy play timestamps are projected onto the
  matching installed `steam-aurelia:<AppID>` row; stale entries whose Aurelia
  counterpart is not installed are not exposed as launchable recents.
- Regression coverage verifies both direct-launch recents updates and migration
  of legacy Steam history to the Aurelia identity. Production was not changed.

### LIBRARY-LAUNCH-001 — Preserve launch return choreography from Library

**Status:** FIXED IN SOURCE — dev physical confirmation pending.

- Keep the home content faded out while the Library surface moves offscreen.
  Once Library is hidden, run the wallpaper's `beginContentExit()` animation;
  only after that completes should the launch overlay appear and the game launch.
  The previous handoff faded home content in alongside the Library exit, which
  violated the intended presentation order.
- The UI now chains the wallpaper exit after Library has left and reuses the
  existing hidden-home launch handoff (including its return watcher). Regression
  assertions cover the ordering. Failure-path trace review found that the Library
  fade-out remained at zero through return; the home layer is now restored before
  the coordinator's entrance animation. Focus moves to Recents immediately before
  the launch overlay appears; the existing deferred reconcile/presentation
  animation then runs on return, avoiding per-row Library return animations.
- For the launch-only Library exit, hold the glass backing at expanded dimensions
  and appearance while translating it vertically offscreen with the Library
  surface. Ordinary Back navigation retains the existing scale-to-card transition.
  Regression coverage checks the launch-only geometry; physically verify the
  launch/return choreography in dev-current. Production remains unchanged.

### NOTIFICATIONS-001 — Route transient status messages to Notifications

**Status:** IMPLEMENTATION COMPLETE — automated validation recorded below;
physical visual/passive-input acceptance pending.

- Consoled owns the one FIFO presenter queue; Acquisitiond detects normalized
  JobManager transitions and forwards through Consoled D-Bus, while the shell
  uses bridge `POST /notification`. Severity lifetimes are info/success 4s,
  warning 6s, error 8s; automatic passive dismissal only.
- Inventory/disposition is documented in `docs/notification-system.md`.
  Confirmation prompts remain in `interactionPrompt`; launch lifecycle and
  contextual panel feedback stay local; acquisition submission/handoff strings
  do not duplicate broker events. Generic bottom-right `root.message` rendering
  is removed. Library refresh now produces completion feedback.
- Validation: notification contract/convergence tests 16 passed; bridge tests
  31 passed; acquisition suites 13 passed; Consoled startup tests 14 passed;
  selected QML regressions 3 passed; focused console UI tests 13 passed. The
  full Python discovery suite ran 1,169 tests and retained 9 unrelated existing
  source-text failures (eight Home/Library/Store/Settings assertions and one
  native easing-literal assertion); notification changes did not touch those
  contracts. `compileall` and `git diff --check` passed. Notification native
  binary compiled successfully (existing Qt deprecation warning only).
- Sessiond inspection could not be performed (`org.lulu.ConsoleSessiond` was
  not activatable on the current user bus), so development-runtime refresh is
  deferred as ambiguous. No production runtime was touched. Physical
  notification appearance and passive-input acceptance remain outstanding.

### LUTRIS-002 — Sonic 3 A.I.R. launch leaves Mudos unresponsive

**Status:** INVESTIGATING — evidence collected; preserve the current session.

- After the Sonic 3 A.I.R. installation completed, launching it left Mudos
  apparently unresponsive. The game process is still alive behind a modal
  `zenity` error dialog; Sessiond remains in `game` lifecycle and has not
  recorded a launch result.
- Game logs show engine startup succeeded, then ROM discovery failed. It searched
  Steam's Sega Classics paths for `Sonic_Knuckles_wSonic3.bin`. The selected
  user-provided file is present in the install tree as
  `Sonic and Knuckles & Sonic 3.bin`, so the recipe's copy location/name and the
  game's lookup behavior need investigation.
- Lutris's recipe metadata does not state that target filename: it declares
  `bin: "N/A:Please select the .bin file from Steam"`. Its installer then copies
  `bin` into the app directory without a destination filename. Lutris therefore
  supplied no expected-name hint for Mudos to use; verify a supported target
  location/name before adding any recipe-specific copy/rename behavior.
- Launch diagnostics show Gamescope selected the game's X11 window and unmapped
  the shell. The waiting Zenity process inherited the Gamescope Wayland display,
  but has no visible X11 window. This is consistent with its error dialog being
  outside the selected game surface; confirm the Wayland/Gamescope surface
  behavior before treating that as proven.
- Do not infer that the game binary itself crashed. Preserve the current state
  and logs while tracing launch supervision, dialog visibility/input routing,
  and how the recipe-provided ROM is expected to be located. Do not restart or
  terminate the current game/session without operator authorization.

### DOWNLOADS-001 — Downloads list rendering and clear-action stability

**Status:** OPEN — operator findings recorded; investigation and fixes deferred.

- In the Downloads list, a row's bottom edge can be clipped when its error text
  wraps across too many lines.
- Clearing a download often leads to a crash. The crash trigger and affected
  component have not yet been established.
- These are observations from ongoing physical testing, not confirmed root
  causes. Do not change behavior as part of this finding until it is separately
  taken up for investigation.

### DOWNLOADS-002 — Show useful installation progress in Downloads

**Status:** OPEN — operator finding recorded; implementation deferred.

- During a Lutris installation, the Downloads view displays only “Downloading,”
  including while Lutris is extracting and compiling the recipe payload. Show a
  useful current stage and progress there so the operator can tell what the job
  is doing and whether it is advancing.
- Recorded during physical testing; no UI or progress-reporting changes are
  included in this finding.

### DOWNLOADS-003 — Mudos crash after Lutris install completion

**Status:** OPEN — operator observation recorded; no investigation requested.

- The operator reports that Mudos appeared to crash when the Sonic 3 A.I.R.
  Lutris installation finished downloading. This is recorded as an observation
  only; do not investigate it as part of the current launch-hang diagnosis.

### QUIVER-001 — Quiver acquisition and library provider

**Status:** ABANDONED — Lutris is the selected PC installation foundation.

- Repository and upstream investigation is recorded in
  `docs/quiver-provider-contract.md`. This checkout has no Quiver integration.
- The public project matching the name, Quiver Launcher, has a name-based CLI
  (`--list`, `--download`, `--update`, `--run`, `--uninstall`) and its own
  library/app folders, but no structured acquisition-job API. Questarr is a
  separate, retired integration and must not be restored.
- Before implementation, confirm whether this is the intended Quiver and
  whether Mudos should consume a future/other Quiver API or own a separate
  GitHub/GitLab release acquisition backend. These choices change acquisition,
  catalogue, installation, and launch authority; do not guess or treat the
  upstream GUI's local files as an API.

### CTRL-001 — Prevent controller navigation loss after runtime target churn

**Status:** ACTIVE — physical navigation recovered; startup/runtime cause still
needs a durable fix and regression coverage.

- **Observed symptom:** The shell/Home screen displayed normally, but D-pad
  navigation stopped responding. Guide still worked through its independent
  InputPlumber D-Bus/OSK route; that did not prove the native SDL navigation
  route was healthy. The controller was a Microsoft Xbox 360 wireless receiver.
- In the earlier occurrence, the receiver and physical event node existed and
  InputPlumber showed one composite, but SDL exposed two InputPlumber-marked
  virtual gamepads for that one composite. Sessiond's identity-agnostic target
  association correctly refused to guess and left the SDL index unset. This
  mismatch is a confirmed failure signature, but it was not present in every
  later snapshot of the recurrence.
- **Known-good recovery (operator confirmed twice, most recently 2026-10-06):**
  after stale InputPlumber event-node/composite churn has settled, restart
  `inputplumber.service`. Its `PartOf` relationship also restarts
  `lulu-session@2.service`; allow the session and Home startup to finish before
  testing. On the successful recovery, the canonical native path was restored:
  `LULU_NATIVE_CONTROLLER=1`, InputPlumber `Default` profile, intercept mode 1,
  OSK hidden, one physical receiver source, one composite, exactly one SDL
  InputPlumber target, and Sessiond `sdl_index=0`. The operator then confirmed
  Home navigation worked. Restarting InputPlumber too early can first attach a
  stale event node; if that happens, let udev/hotplug reconciliation settle and
  repeat the restart rather than treating the transient post-restart state as
  recovered.
- **Detailed 2026-10-06 timeline:** The boot following removal of the forced
  headless-display kernel argument started InputPlumber at 04:10:12 and the
  graphical session at 04:10:13. Early InputPlumber discovery raced transient
  event nodes (including stale Sunshine virtual-pad nodes); logs showed
  `No such device`, failed target attachment/channel-closed errors, and
  composite teardown/recreation. At 04:21:04, restarting InputPlumber initially
  recreated a composite from stale `event17`; that composite failed at 04:21:27.
  The hotplug reconciliation service ran at 04:21:30 and discovered the real
  Xbox receiver at `/dev/input/event9`; Sessiond then corrected the profile and
  obtained SDL association index 0. A later restart at 04:35 attached directly
  to `event9` and remained stable.
- **Important recovery detail:** An attempted runtime-only override
  `LULU_NATIVE_CONTROLLER=0` plus the `Lulu SHELL` keyboard-emulation profile
  did not restore Home navigation. It was removed. The final successful
  recovery used the packaged/canonical `LULU_NATIVE_CONTROLLER=1` native-SDL
  architecture and its `Default` InputPlumber profile. Do not leave the runtime
  override in place or interpret Guide/OSK operation as proof of D-pad routing.
- A separate probe found the OSK hidden while InputPlumber was temporarily in
  intercept mode 2; restoring mode 1 and reloading `Lulu SHELL` alone did not
  restore Home navigation. On final recovery, OSK was hidden and intercept mode
  1. Record this as a potentially relevant stale-state observation, not as the
  proven root cause. Direct `evtest` captures and broad D-Bus monitoring during
  this incident did not provide a decisive physical D-pad event trace; the
  source event was grabbed by InputPlumber, so absence of events in those
  captures is not evidence that the controller itself was defective.
- **Current evidence / open cause:** On recovery, checks showed one SDL gamepad
  (`Xbox 360 Controller`, udev-marked InputPlumber target), one composite
  sourced from `/dev/input/event9`, one target gamepad, one Sessiond SDL slot at
  index 0, profile `Default`, intercept mode 1, and OSK `hidden`. Before the
  final recovery those same counts/mappings could appear healthy while the
  operator still reported no Home navigation. Therefore target count and SDL
  association are necessary diagnostics but are not sufficient acceptance;
  the root trigger and the reason a stable-looking intermediate state failed
  remain unproven.
- **Runbook for recurrence:** First record `date`, `systemctl status
  inputplumber.service lulu-session@2.service lulu-osk@2.service`, and the
  relevant boot journal before restarting anything. Check
  `sudo inputplumber devices list`, `sudo inputplumber targets list`, and
  `sudo inputplumber sources list`; inspect
  `journalctl -b -u inputplumber.service -u lulu-session@2.service` for
  `No such device`, `Gamepad order: []`, stale event numbers, composite
  teardown/recreation, and target attach failures. Read Sessiond's `GetState`
  and verify one connected controller with a non-null `sdl_index`; count SDL
  gamepads as user `lulu` (not the desktop operator, whose device permissions
  can produce a false empty inventory). Check the composite `ProfileName`,
  `InterceptMode`, its `TargetDevices`, and the OSK bridge socket `status`
  together. A hidden OSK with intercept mode 2 is suspicious; mode 1 is the
  expected shell state. Preserve the controller setup's canonical
  `LULU_NATIVE_CONTROLLER=1`; do not use the unsuccessful mode-0 runtime
  workaround. If logs show stale-node churn, let the hotplug reconciliation
  finish, restart InputPlumber once, wait for Home startup to complete, then
  check the state again and ask the operator to verify D-pad navigation. Record
  both the resulting diagnostics and physical confirmation; a healthy-looking
  inventory alone does not close this issue.
- Sunshine's `controller = disabled` setting is intentional and must remain
  unchanged. No Sunshine input, controller allowlist, or synthetic/virtual
  controller path is an acceptable workaround. No Lutris implementation change
  has been identified as the cause. No source change was made for this recovery;
  `/opt/lulu/current` was not changed.
- Diagnose and fix the smallest lifecycle/reconciliation issue that permits
  stale/duplicate InputPlumber targets to outlive their composite. Keep the
  physical Xbox/InputPlumber/composite/Sessiond/native-SDL architecture,
  identity-agnostic standard gamepad support, and single controller path.
  Do not add a controller allowlist, virtual path, or Sunshine input.
- Validate after a cold boot and shell startup: one normalized controller,
  non-null Sessiond SDL association, Guide plus continued D-pad/A/B/Start
  navigation, no duplicate/phantom controller, and Sunshine still disabled.
  Add automated coverage for the discovered runtime mismatch/recovery. Do not
  resume LUTRIS-001 physical acceptance until controller navigation remains
  reliable through the required Home → Installable → Lutris flow.
- **Power-cut recurrence (2026-10-06):** after reboot, Sessiond showed one
  connected Xbox 360 receiver controller sourced from `/dev/input/event17`, but
  `sdl_index` was null. InputPlumber had one `Default`/intercept-mode-1 composite,
  while SDL exposed two InputPlumber-marked virtual Xbox targets (`event16` and
  `event19`). This reproduced the known duplicate-target mismatch. Following
  the runbook, the pre-restart state was recorded and InputPlumber was restarted
  once after the receiver node was present. It recreated one composite; SDL then
  exposed one marked target (`event10`) and Sessiond mapped it to `sdl_index=0`.
  InputPlumber and Sessiond are active, and intercept mode remains 1. Physical
  D-pad/A/B/Start confirmation is still required; do not count the state readback
  alone as operator acceptance.
- **Headless-display test reboot recurrence (2026-10-06):** booting with the
  temporary `video=DP-1:1920x1080@60e` override again raced stale input nodes;
  InputPlumber logged an absent Sunshine virtual-pad event node, briefly created
  and tore down a second composite, and SDL ended up with two marked pads for
  the one receiver composite. After recording the state and allowing discovery
  to settle, one InputPlumber restart restored one composite/one SDL target and
  Sessiond `sdl_index=0`. Profile `Default`, intercept mode 1, OSK bridge, and
  native SDL remain intact. Restarting stopped the live Gamescope/Sunshine stream
  session; Sunshine remains running and the client may need to reconnect.
  Physical navigation confirmation is still pending. This is operational
  recovery, not a durable fix for the boot-time stale-target race.

### LUTRIS-001 — Mudos-native PC game install and add-game flows

**Status:** PASS WITH FOLLOW-UP — operator confirmed the Lutris discovery,
required-file selection, installation, and launch-attempt flow end to end. The
flow mostly works; listed follow-ups remain open, so this item is not closed and
successful gameplay is not claimed.

- Lutris 0.5.22's installer interpreter, game model/config save, database
  inventory, launch-script exporter, and uninstall model are integrated behind
  the existing Acquisitiond/catalogue/Sessiond boundaries. An isolated real
  Lutris test covers native local registration, discovery, launch export, and
  unregistering. The suite also covers recipe requirement parsing, catalogue
  identity, and the shared acquisition lifecycle.
- Installable's controller-X/BTN_WEST action launches controller text entry for
  Lutris search through Mudos' shared contextual options action. The flow
  discovers upstream games/recipes, shows required user-file steps, uses the
  generic Mudos file picker, then calls CreateLutrisInstallSource,
  RegisterPcSource, and SubmitPcInstall. The existing Acquisitiond job and
  LutrisInstallExecutor remain the only installation path.
- Confirmed upstream recipe `sonic-3-air-stable`: Linux runner, download
  `sonic3air_game.tar.gz`, and required user file
  `Sonic_Knuckles_wSonic3.bin`. The real live API search/recipe routes and
  requirement-source validation were exercised; no ROM/game data was copied
  or installed.
- Refreshed non-promotable `/opt/lulu/dev-current`; session, Consoled,
  Acquisitiond, and admin services were active for physical acceptance. The
  operator later supplied a file and explicitly approved its use for the test.
- Physical acceptance exposed that BTN_WEST dispatched to the generic
  `openSelectedGameOptions()` handler while Lutris search was reachable only
  from the Qt `Key_X` path. The shared action now dispatches Installable's
  search flow. The operator confirmed the search window opens and the OSK is
  controllable; the later install attempt confirms the results/recipe flow is
  receiving the controller action.
  Do not install copyrighted game files as part of this action-path check.
- Follow-up OSK testing found Sessiond's profile-drift reconciler overwrote the
  OSK bridge's temporary exclusive InputPlumber profile/intercept mode while
  the keyboard was visible. Sessiond now yields reconciliation only while the
  managed OSK reports visible, allowing its bridge to restore shell input on
  hide. The operator confirmed physical OSK control now works.
- The first physical game search remained on its loading message because the
  new Lutris QML components sent relative XHR paths, which Qt interpreted as
  local-file URLs rather than requests to the shell API. Route search, recipe,
  file-picker, and local-registration XHRs through the configured `apiUrl`, and
  show a useful error if a request fails. Lutris also returns no exact match
  for the dotted `A.I.R.` spelling, so retry dotted abbreviations compacted.
  Regression coverage passes and the fix is refreshed to dev-current; physically
  verify search results and recipe selection.
- Physical retest found native controller actions bypass the Qt key handler's
  Lutris-modal checks: A invoked the root Installable activation and started
  `A Difficult Game About Climbing`. That acquisition completed before it was
  observed. Root controller handlers now delegate A/B to the visible Lutris
  modal and suppress other actions that could affect the covered surface;
  regression coverage passes and the fix is deployed to dev-current. Physically
  retest confirmed A selected the Lutris item rather than the covered Installable
  game.
- The next Lutris install failed because `/home/lulu/Games/Executables/lutris`
  was owned by root, preventing Acquisitiond (user `lulu`) from creating the
  game directory. Corrected ownership on that parent directory only; preserved
  its mode and all existing game files. The failed Sonic job created no partial
  destination. The operator later explicitly authorized use of their provided
  Sonic file and requested another test.
- The retry exposed Lutris's scalar file declaration format (`{"bin":
  "N/A:Please select the .bin file from Steam"}`), which the requirement parser
  had skipped. It is now surfaced as a required local-file selection and mapped
  under the recipe's `bin` ID; focused regression tests pass and the correction
  is refreshed to dev-current. The operator selected their file in the UI.
- Physical testing found the install action was not visible beneath the required
  file row. It is now a dedicated visible row immediately after the file list,
  with controller navigation and activation coverage. The operator confirmed
  the row is now visible and requested another install test. The first retried
  job was cancelled during compilation; its logged missing-source error
  coincided with transaction cleanup removing the build directory, so it is
  inconclusive. The operator reports the current test was started from the UI;
  the install completed and the operator attempted launch. The build succeeded,
  but ROM discovery failed and the game left a Zenity error dialog waiting while
  the shell appeared unresponsive; see LUTRIS-002. This confirms the install and
  launch-attempt path, not successful gameplay.
- Full Python suite and QML checks pass. The checkout still has unrelated
  pre-existing modifications; dev runtime records `dirty=true` and must never
  be promoted.

### EDEN-001 — Eden AppImage migration acceptance

**Status:** ACTIVE. Do not close or promote until both regressions are fixed and
the operator completes physical acceptance.

- **EDEN-001A — MK8 update/DLC discovery:** The v0.8.1 runtime loads its config
  below `XDG_CONFIG_HOME/eden`, which for Mudos is
  `~/.config/lulu/providers/eden/config/eden/qt-config.ini`. The prior adapter
  edited `~/.config/eden/qt-config.ini`; the runtime config had
  `Paths\\external_content_dirs\\size=0`. v0.8.1 scans configured NSP/XCI
  directories into an in-memory `ExternalContentProvider`; there is no
  persistent external-content database/index. Point the adapter at the active
  provider config and ensure the ROM directory is registered there. Do not
  move, reinstall, register, or delete update/DLC NSP files during diagnosis.
- **EDEN-001B — controller input:** Use the generic live SDL/InputPlumber
  identity and Eden's native serialization contract; do not add controller
  allowlists or pin event device numbers. The original Mudos face-button map
  (A/B/X/Y = SDL buttons 0/1/2/3) is the correct baseline and must be retained.
  Eden's v0.8.1-authored `gp1` donor was preserved at
  `/home/lulu/.config/lulu/providers/eden/config/eden/input/gp1.ini.eden-v0.8.1-donor`;
  the updated `gp1.ini` now contains the original Mudos-generated mapping.
  Donor profile checksum: `6d9a889c66df2ac7561dbb9681e6e73ca9110dab2ed75d5ced3e91db274b4537`.
  Updated profile checksum: `8447a50eade12c04794a930cdb9364d312ff8eda77caaef2d53f46e9cdbc551b`.
  Physical ABXY correctness remains an operator-confirmed fact, not something
  inferred from Eden's saved mapping.
- Keep the existing pinned AppImage, coherent NAND/profile state, keys and
  firmware, Gamescope ownership, Mudos controller assignment policy, and
  prompt Eden-to-Mudos lifecycle return.
- Preserve the old Flatpak tree as read-only donor evidence. Leave
  `/opt/lulu/current` untouched; development deployment is restricted to
  `/opt/lulu/dev-current` and remains separate from promotion.
- Required operator acceptance: MK8 v4.0.0 with existing DLC active, controller
  input, clean lifecycle return, rendering, and remaining requested checks.

**Implementation status:** The adapter now targets the provider XDG config Eden
actually reads, registers the Switch ROM directory there, and retains the
original Mudos button map. Runtime-path regression coverage is implemented; the
full test suite passes (1,169 tests and 85 subtests). Commit `fe840db` was
deployed to `/opt/lulu/dev-current` on 2026-10-04. The dev tree is explicitly
`promotable=false` and records `dirty=true` because pre-existing, uncommitted
session/lifecycle work was included in the dev refresh. `/opt/lulu/current`
still points to the immutable candidate release. Physical acceptance has not
occurred.

**Next:** Obtain operator acceptance on dev-current for MK8 v4.0.0 plus DLC,
controller input, clean lifecycle return, rendering, and remaining requested
checks. Keep EDEN-001 ACTIVE until those checks pass. Do not promote this dirty
dev runtime.

## DESKTOP-001 — Mudos Desktop Mode

- Corrective pass: the deployed wrapper did resolve installed tint2 17.0.2 and jgmenu 4.6.0 at `/usr/bin/tint2` and `/usr/bin/jgmenu`; package installation was not the original gap. Sessiond's child log showed tint2 rejecting unsupported keys (`font`, `font_color`, `clock_format`, `clock_font`, `button_text_color`, etc.). A hand-built minimal replacement also proved incomplete and crashed tint2 during initialization, so the final generator starts from the installed tint2 default configuration, then applies supported theme settings and Mudos buttons. The wrapper captures logs, gates startup on Xephyr/Openbox readiness, retries once, and isolates panel failure.
- Added `mudos-desktop-wallpaper`, an X11 Qt Quick host sharing `OrbitRenderSource.qml` and the native ThemeManager context. It selects the currently active validated `appearance/theme` QSB and palette; no theme IDs or raw-fragment conversion are used. The desktop window carries EWMH desktop/skip-taskbar/skip-pager/below semantics and does not accept focus. An isolated Xephyr/Openbox smoke run verified the actual window properties and logged the selected `modern` QSB path. Root surface color is painted first and remains fallback on shader failure. Wallpaper and tint2 failures do not terminate the nested desktop.
- Startup is now Xephyr → `xdpyinfo` connection readiness → nested DISPLAY/XAUTHORITY → Openbox → EWMH WM readiness → semantic root fallback → wallpaper → tint2. Panel menu/taskbar/tray/clock/Wi-Fi/Bluetooth/power controls remain; power actions are still only Restart, Shutdown, and Exit Desktop Mode through Sessiond.
- Ownership/release/install verification now includes wallpaper executable, QML files, and required X11 binaries/packages. Focused desktop tests: 9 passed. Native build including the wallpaper executable, shell syntax, ownership JSON, and diff checks pass; source-build warnings remain existing warnings.
- Physical corrective acceptance completed on 2026-10-08 in `/opt/lulu/dev-current`. The first trial exposed inherited Wayland selection (`BadWindow` on XCB); forcing `QT_QPA_PLATFORM=xcb` fixed it. On subsequent real Sessiond entries the Modern QSB wallpaper rendered visibly, tint2 remained live with no invalid-option/fault log, and the wallpaper window reported `_NET_WM_WINDOW_TYPE_DESKTOP`, skip-taskbar, skip-pager, below, and non-focusable hints. Captures showed the wallpaper and bottom panel together.
- Opened jgmenu's normal XDG application menu and confirmed Mudos Wi-Fi/Bluetooth entries and the desktop launchers were enumerated. Launched Mudos Network Settings; its taskbar entry appeared and its read-only network view loaded. The panel showed Wi-Fi, Bluetooth, clock, and power controls. The Power menu displayed exactly Restart, Shutdown, Exit Desktop Mode; no power action was invoked.
- Reversibly switched `appearance/theme` from Modern to 95 for a separate entry. The wallpaper log selected `themes/95/wallpaper/wallpaper.frag.qsb`; the capture showed the 95 teal wallpaper and the panel config used its gray/blue colors and exact zero radius. Restored the original Modern setting afterward.
- Repeated entry/exit returned Sessiond to `lifecycle=shell`, `session_kind=shell`, `input_mode=shell`, `presentation_ready=true`; no Xephyr/Openbox/tint2/wallpaper process remained. Consoled, Acquisitiond, and the resident Steam runtime were active. No restart or shutdown validation was performed.
- The unrelated `tests/test_console_ui.py` source-assertion failures and earlier 134-test baseline remain as previously recorded; the current corrective focused suite is 9 passed.
- Deployed to the existing non-promotable `/opt/lulu/dev-current` from committed implementation HEAD `db81b9f601e5def6a6efc8288ca3b009522b1193` using `scripts/dev-runtime.sh settings-refresh`; required Xephyr/tint2/jgmenu/X11 utility packages were installed. The acceptance runtime is marked non-promotable.
- Runtime lifecycle exercise was observed: Sessiond recorded the Desktop Mode wrapper exit successfully, restored `lifecycle=shell` and `input_mode=shell`, and no nested Xephyr/Openbox/tint2 processes remained in the follow-up process check. Core services and the resident Steam runtime were active afterward.
- Production `/opt/lulu/current` remains `/opt/lulu/releases/786aba3-candidate-20261004065549` and was not modified. Physical visual/input acceptance and operator confirmation remain pending.
