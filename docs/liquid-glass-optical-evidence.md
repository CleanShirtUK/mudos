# Mudos Liquid Glass Optical Evidence

## Status

**Development-host proven, not BC-250 proven.**

This record covers the accepted optical baseline physically reviewed on the
host test environment. No claim is made about BC-250 hardware validation.

## Accepted Baseline

- Shared canonical texture: `1280x720`
- Canonical mapping: `scenePosition = sceneOrigin + qt_TexCoord0 * sceneSize`,
  then `baseUv = scenePosition / canonicalSize`
- Exact rounded-card material mask and rounded-box optical footprint
- Continuous rounded-box bevel profile with `bevelWidthPx = 3`
- Rounded-box-constrained aspect-aware cosine bulge with `bulgeStrength = 100`
- Snell refraction scale: `80 px`
- Dispersion: red `IOR - 0.0175`, green `IOR`, blue `IOR + 0.0175`
- Constant diffusion radius: `5 px`
- Diffusion: current 5x5 Gaussian kernel
- Neutral transmission: `0.75`
- Geometry-derived edge light: `edgeLightStrength = 0.10`
- Reusable direction: `edgeLightDirection = (1, -1)`
- Perimeter envelope: top-right peak, smooth falloff to top-left and
  bottom-right, zero on left/bottom edges, restricted to the 3 px bevel
- Focal artwork: rounded `Image -> ShaderEffectSource (hideSource) -> ShaderEffect`
  path with a `1 px`, `0.15` neutral separation border
- Play: analytical stacked card-material sampling, no bevel, bulge `20`,
  refraction `40 px`, dispersion `IOR +/- 0.0175`, diffusion `5 px`,
  transmission `0.82`, directional lighting `0.02`, premultiplied rounded mask

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
- Rounded boundary mask, `3 px` bevel, and quintic bevel profile passed.
- Central bulge passed first at exaggerated strength and then at `100`.
- Final rounded-box-constrained cosine bulge envelope passed.
- Geometry-derived directional edge lighting passed at `0.10`.
- Rounded artwork presentation and `0.15` separation border passed.
- Analytical stacked Play material passed without changing focal-card render
  ownership.

## Rejected or Disabled Experiments

- Scene-derived displaced reflection failed because it produced recognizable
  duplicate Orbit lines.
- Broad scene-derived luminance illumination failed because the independent
  opaque artwork did not visually cohere with the brightened backdrop.
- The sparse five-tap and 13-sample diffusion kernels failed through visible
  ghost copies; the current 5x5 Gaussian replaced them.
- Slope-amplified diffusion was rejected in favor of constant 5 px diffusion.
- Uniform/inverted edge-light responses were rejected in favor of the accepted
  directional bevel envelope.
- Intermediate `cardGlassLayer`/`ShaderEffectSource` capture was rejected
  because it changed focal-card render topology.
- Play output that mixed analytical card material outside its mask was rejected;
  Play output must remain premultiplied and transparent outside its rounded mask.
- Independently visible artwork source/capture layers were rejected; only the
  rounded artwork shader may present artwork pixels.

No glow, tint, additional attenuation, or conventional Fresnel/specular lighting
is included. Developer diagnostics remain available through explicit
non-default diagnostic selectors, with production rendering at mode `0`.
