# Archived Glass Experiment

Status: abandoned prototype optical model; not Lulu's current glass source of truth.

This archive preserves the pre-reset padded Snell experiment that was deployed for physical review. It is retained for inspection and historical recovery only and is no longer referenced by live QML.

## Contents

- `GlassSurface.qml`: deployed reusable glass component.
- `shaders/liquid-glass.frag`: source shader.
- `shaders/liquid-glass.frag.qsb`: generated Qt shader asset.
- `scripts/build-glass-shader.sh`: QSB build command.
- `scripts/validate-glass-field.py`: bounded-field validator.
- `tests/test_console_ui.py`: test snapshot containing the experiment assertions.
- Root `liquid-glass.frag.qsb`: deployed QSB copy captured before reset.
- Root `GlassSurface.qml`: deployed component copy captured before reset.

## Parameters

- `refractionStrength`: `0.65`
- `chromaticSeparation`: `1.0`
- `ior`: `1.08`
- `snellMagnitudePixels`: `6`
- `dispersionPixels`: `1.25`
- `sourcePaddingPixels`: `8`
- `diffusion`: `0.0025`
- `attenuation`: `0.72`
- `edgeHighlight`: `0.045`

## Evidence

The experiment and its investigation were documented in external evidence
records `EVID-D1-014` through `EVID-D1-017`; those artifacts are not present in
this checkout, so the references are retained as historical provenance rather
than local links. The live accepted UI/Orbit baseline remains recoverable from
Mudos commits `ffb92a1` and `46521a5`; this archive does not alter those commits
or delete any history.
