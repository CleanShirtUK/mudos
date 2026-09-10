# Mudos Liquid Glass Optical Architecture

## Reference Pipeline

`kwin-effects-glass` is a compositor effect, not a reusable Qt component. Its
material is a pipeline: capture an expanded background texture, blur it with
pixel-sized taps, evaluate a rounded-box SDF, derive a finite-difference
gradient, construct a shallow 3D glass normal, and use `refract()` to obtain a
local texture direction. Edge/concavity and bevel parameters control how much
of that ray is applied. Wavelength samples vary the refractive displacement for
red, green and blue. Tint, attenuation, glow/reflection and the rounded SDF
mask are applied after sampling.

The important separation is between the effect texture extent and the visible
rounded geometry. KWin's blur buffer has neighboring pixels outside the glass
shape, so the refracted samples do not use the pane mask as their source
boundary. Its `uvScale` and `halfpixel` values convert physical pixel offsets
to the effect texture coordinate system.

## Canonical Texture Contract

The accepted identity pipeline is now a shared presentation-sized texture:

`OrbitRenderSource -> orbitTexture -> OrbitBackdropView + GlassSurface`

`orbitTexture` is exactly `1280x720`. The visible backdrop and the Recent focal
card consume this same texture. The card's immutable base coordinate is:

`scenePosition = sceneOrigin + qt_TexCoord0 * sceneSize`

`baseUv = scenePosition / canonicalSize`

There is no local `ShaderEffectSource`, per-card `sourceRect`, padding, or
coordinate correction in this contract. This identity mapping was physically
accepted with animated Orbit lines crossing the card boundary.

## Accepted HOST Optical Baseline

The current Recent focal material is the accepted HOST PROVEN baseline. These
values were physically reviewed on the host test environment only; they are
not BC-250 proven:

- `bevelWidthPx`: `3`
- `bulgeStrength`: `100`
- refraction scale: `80 px`
- wavelength IOR offsets: red `ior - 0.0175`, green `ior`, blue `ior + 0.0175`
- diffusion radius: constant `5 px`
- diffusion kernel: current 5x5 Gaussian, with 1D weights
  `[0.0625, 0.25, 0.375, 0.25, 0.0625]`
- neutral transmission: `0.75`
- geometry-derived edge lighting: `edgeLightStrength = 0.10`
- reusable edge direction: `edgeLightDirection = (1, -1)` for the accepted
  top-right peak, with smooth perimeter falloff

The optical height is the sum of an exact rounded-box boundary bevel and a
rounded-box-constrained, aspect-aware cosine bulge. Both use the same
finite-difference gradient and Snell pipeline. The material boundary is an
antialiased rounded-box mask composited over the untouched canonical backdrop.

Lighting is limited to the accepted geometry-derived directional bevel response:
it is restricted to the existing 3 px bevel, peaks at the top-right, falls to
zero at the top-left and bottom-right, and contributes nothing on the left or
bottom edges. Play glass is intentionally not part of this baseline.

The accepted focal artwork path is `Image -> ShaderEffectSource` with
`hideSource: true` and `visible: false` on the source texture item, followed by
the sole visible rounded `ShaderEffect`. Its radius comes from the focal
artwork geometry, with derivative antialiasing and a subtle neutral `1 px`
border at `0.15` alpha.

The accepted Play control is a separate analytical stacked-material consumer.
It does not capture or reroute the focal card. It evaluates the card material at
displaced scene coordinates, then applies its own rounded premultiplied mask.
Play uses no optical bevel, bulge strength `20`, refraction `40 px`, dispersion
`IOR +/- 0.0175`, constant diffusion `5 px`, transmission `0.82`, and
directional lighting `0.02`.

## Qt Quick Optical Layer

The optical prototype samples only the canonical texture. Any displacement is
applied to the accepted `baseUv`; it must not replace or alter that mapping.

The Qt fragment shader uses the required `qt_Matrix`/`qt_Opacity` uniform block
prefix and binding-1 sampler, then follows this sequence:

1. Convert local fragment coordinates into the canonical `baseUv`.
2. Evaluate a rounded-box SDF in surface pixels.
3. Use finite differences to obtain a normalized XY gradient.
4. Construct `normalize(vec3(normalXY * depth, 1.0))`.
5. Call `refract(viewRay, glassNormal, 1.0 / wavelengthIor)` for each channel.
6. Apply only the bounded local Snell displacement for the current prototype.

Dispersion, diffusion, neutral transmission, the accepted surface profile, and
directional bevel lighting are enabled in the HOST baseline above. Tint,
additional attenuation, glow, conventional Fresnel/specular lighting, and
Play-layer glass is enabled only through the accepted analytical Play path
described above.

The scene-derived lighting experiment is retained but disabled
(`sceneLightStrength = 0`); it was rejected because even broad scene energy
made the independent opaque artwork read as a reflected/brightened backdrop
rather than cohesive glass illumination.

Developer diagnostics are retained but cannot affect normal rendering unless a
caller explicitly sets `GlassSurface.diagnosticMode`: mode `7` shows total
height, `8` gradient magnitude, `9` final displacement magnitude, `10` is the
known-good forced +20 source-pixel offset, and `11..13` show bulge height,
bulge gradient, and bulge-only displacement. Production instances use mode `0`.

## Licensing Boundary

The upstream project is GPLv3. Lulu has no declared repository license. This
implementation is independent shader code based on generic optical principles
and does not copy upstream source. The upstream repository is not installed,
linked, or required at runtime.
