#!/usr/bin/env python3
"""Validate the bounded, mirrored optical field used by liquid-glass.frag."""

from math import hypot


def normal(uv: tuple[float, float]) -> tuple[float, float]:
    x, y = uv
    dx = min(x, 1.0 - x)
    dy = min(y, 1.0 - y)
    vector = (x - 0.5, y - 0.5)
    length = hypot(*vector)
    if length == 0:
        return (0.0, 0.0)
    if abs(dx - dy) < 1e-9:
        return (vector[0] / length, vector[1] / length)
    if dx < dy:
        return (-1.0 if x < 0.5 else 1.0, 0.0)
    if dy < dx:
        return (0.0, -1.0 if y < 0.5 else 1.0)
    return (0.0, 0.0)


def lens(uv: tuple[float, float]) -> float:
    inside_distance = min(uv[0], 1.0 - uv[0], uv[1], 1.0 - uv[1]) * 720.0
    interior = max(0.0, min(1.0, inside_distance / 96.0))
    interior = interior * interior * (3.0 - 2.0 * interior)
    edge = max(0.0, min(1.0, inside_distance / 6.0))
    edge = edge * edge * (3.0 - 2.0 * edge)
    edge_outer = max(0.0, min(1.0, (inside_distance - 6.0) / 90.0))
    edge_outer = edge_outer * edge_outer * (3.0 - 2.0 * edge_outer)
    return 0.08 * interior + 0.92 * edge * (1.0 - edge_outer)


def displacement(uv: tuple[float, float], maximum: float = 6.0, strength: float = 0.65) -> tuple[float, float]:
    factor = maximum * strength * lens(uv) ** 2
    direction = normal(uv)
    return direction[0] * factor, direction[1] * factor


def main() -> int:
    centre = displacement((0.5, 0.5))
    samples = {
        "left": displacement((0.02, 0.5)),
        "right": displacement((0.98, 0.5)),
        "top": displacement((0.5, 0.02)),
        "bottom": displacement((0.5, 0.98)),
        "top-left": displacement((0.02, 0.02)),
        "top-right": displacement((0.98, 0.02)),
        "bottom-left": displacement((0.02, 0.98)),
        "bottom-right": displacement((0.98, 0.98)),
    }
    assert hypot(*centre) < 1.0
    assert lens((0.0, 0.5)) == 0.0
    assert lens((0.005, 0.5)) > lens((0.0, 0.5))
    assert lens((0.5, 0.5)) < lens((0.02, 0.5))
    assert all(hypot(*value) <= 6.0 * 0.65 + 1e-6 for value in samples.values())
    assert samples["left"][0] < 0 < samples["right"][0]
    assert samples["top"][1] < 0 < samples["bottom"][1]
    assert samples["top-left"][0] < 0 and samples["top-left"][1] < 0
    assert samples["top-right"][0] > 0 and samples["top-right"][1] < 0
    assert samples["bottom-left"][0] < 0 and samples["bottom-left"][1] > 0
    assert samples["bottom-right"][0] > 0 and samples["bottom-right"][1] > 0
    assert abs(hypot(*samples["left"]) - hypot(*samples["right"])) < 1e-6
    assert abs(hypot(*samples["top"]) - hypot(*samples["bottom"])) < 1e-6
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
