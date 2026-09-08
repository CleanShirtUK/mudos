# Lulu Liquid Glass Optical Evidence

## Status

**HOST PROVEN, not BC-250 proven.**

This record covers the accepted optical baseline physically reviewed on the
host test environment. No claim is made about BC-250 hardware validation.

## Accepted Baseline

- Shared canonical texture: `1280x720`
- Canonical mapping: `scenePosition = sceneOrigin + qt_TexCoord0 * sceneSize`,
  then `baseUv = scenePosition / canonicalSize`
- Exact rounded-card material mask and rounded-box optical footprint
- Continuous rounded-box bevel profile with `bevelWidthPx = 10`
- Rounded-box-constrained aspect-aware cosine bulge with `bulgeStrength = 100`
- Snell refraction scale: `80 px`
- Dispersion: red `IOR - 0.0175`, green `IOR`, blue `IOR + 0.0175`
- Constant diffusion radius: `5 px`
- Diffusion: current 5x5 Gaussian kernel
- Neutral transmission: `0.75`

## Physical Results

- Canonical identity passed against animated Orbit lines.
- Forced `+20 px` source displacement passed visibly.
- Exaggerated continuous refraction passed with smooth direction changes and no
  medial-axis seams.
- Rounded-rectangle field and exact card footprint passed.
- Dispersion passed at the accepted IOR offsets.
- Dense Gaussian diffusion passed after replacing the sparse kernel.
- Constant diffusion passed at `5 px`.
- Transmission passed at `0.75`.
- Rounded boundary mask, `10 px` bevel, and quintic bevel profile passed.
- Central bulge passed first at exaggerated strength and then at `100`.
- Final rounded-box-constrained cosine bulge envelope passed.

## Deliberately Deferred

No edge/specular lighting, glow, tint, additional attenuation, or Play glass is
included. Developer diagnostics remain available through an explicit
non-default `diagnosticMode`, with production rendering at mode `0`.
