# Native glass POC reconnaissance

This is a development-only experiment. It is not a `GlassSurface` or
`PlayGlassSurface` migration.

## Qt 6.11.2 route

The ordinary `QQuickItem::updatePaintNode()` route is sufficient for the
primitive: a `QSGGeometryNode` supplies a local rectangle, a `QSGMaterial`
owns the material state, and `QSGMaterialShader::updateUniformData()` receives
the effective scene render matrix through `RenderState::combinedMatrix()`.
The shader can also bind a texture in `updateSampledImage()`.

The effective matrix is only the item's local-to-scene render transform. It
does **not** identify the canonical Orbit texture coordinates. In particular,
`qt_Matrix` cannot infer capture padding, an external `ShaderEffectSource`, or
which scene texture is canonical.

The POC therefore makes the missing contract explicit:

```text
canonicalRect = (origin in Orbit pixels, size in Orbit pixels)
canonicalUV = (canonicalRect.xy + localUV * canonicalRect.zw) / canonicalSize
```

The native item has no `mapToItem()`, timer, scene root, live origin, or
presentation-hierarchy knowledge. The owner supplies `backdrop`,
`canonicalSize`, and `canonicalRect`. The backdrop crosses the scene-graph
boundary through the `ShaderEffectSource` `QSGTextureProvider`; provider
lookup is performed during scene-graph node synchronization, and the texture
is consumed by `updateSampledImage()` on the render thread.

## Material

`mudos-glass.frag` is the accepted canonical Snell/refraction shader copied
without optical redesign. It retains the rounded mask, refraction,
dispersion, diffusion, tint/edge-related uniforms, and existing tuning. The
native vertex shader only supplies the local rectangle and texture coordinate.

## Current POC boundary

The temporary `ui/DevGlassPoc.qml` compares the old and native primitives over
one live `orbitTexture`, with identical dimensions and explicit canonical
mapping. Its 13 selectable states cover stationary, translation, animated
translation, resize, resize-plus-motion, translated/nested/scaled/clipped
ancestors, 64-pixel capture padding, composed-pane capture, outer directional
blur, and focal-like interpolation. `D` requests a one-shot native mapping
dump; no per-frame diagnostic polling is used. Capture and blur states are
development composition probes only; they do not alter `canonicalRect`.

## Dependencies removed / introduced

The native primitive removes the old surface's coordinate polling Timer,
`sceneCoordinateRoot`, `liveSceneOrigin`, initialization state, origin/size
overrides, mapped origin, and layout dependency tricks from its public API.
It introduces native C++/scene-graph code, a QSB shader pair, an explicit
canonical-rectangle owner contract, and a texture-provider lifetime/threading
boundary. The latter is the principal risk to resolve before migration.

An initial BC-250 observation with both sides visible recorded 120 frames at
approximately 0.199 ms average render-thread frame time and 0.307 ms maximum
in the existing `RENDER_TIMELINE` diagnostic. This is not an OLD-versus-NEW
benchmark: texture/pass/reallocation counters have not yet been isolated.
