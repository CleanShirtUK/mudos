#!/usr/bin/env python3
"""Validate source padding and symmetry invariants for the Snell material."""

from math import hypot


REFRACTION_PIXELS = 6.0
DISPERSION_PIXELS = 1.25
BLUR_PIXELS = 2.5
SAFETY_PIXELS = 2.0


def padding() -> float:
    return REFRACTION_PIXELS + DISPERSION_PIXELS + BLUR_PIXELS + SAFETY_PIXELS


def normal(uv: tuple[float, float]) -> tuple[float, float]:
    x, y = uv
    dx = min(x, 1.0 - x)
    dy = min(y, 1.0 - y)
    if abs(dx - dy) < 1e-9:
        vector = (x - 0.5, y - 0.5)
        length = hypot(*vector)
        return (0.0, 0.0) if length == 0 else (vector[0] / length, vector[1] / length)
    if dx < dy:
        return (-1.0 if x < 0.5 else 1.0, 0.0)
    return (0.0, -1.0 if y < 0.5 else 1.0)


def main() -> int:
    assert padding() == 11.75
    assert padding() > REFRACTION_PIXELS + DISPERSION_PIXELS + BLUR_PIXELS
    for source_size in ((1280, 720), (1920, 1080)):
        capture_size = (source_size[0] + 2 * padding(), source_size[1] + 2 * padding())
        assert all(value > 0 for value in capture_size)
        assert REFRACTION_PIXELS + DISPERSION_PIXELS + BLUR_PIXELS < padding()
    assert normal((0.02, 0.5)) == (-1.0, 0.0)
    assert normal((0.98, 0.5)) == (1.0, 0.0)
    assert normal((0.5, 0.02)) == (0.0, -1.0)
    assert normal((0.5, 0.98)) == (0.0, 1.0)
    assert normal((0.02, 0.02))[0] < 0 and normal((0.02, 0.02))[1] < 0
    assert normal((0.98, 0.98))[0] > 0 and normal((0.98, 0.98))[1] > 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
