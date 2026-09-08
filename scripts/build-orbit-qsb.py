#!/usr/bin/env python3
"""Adapt Orbit's fragment shader to Qt Quick's QShader input contract."""

from pathlib import Path
import re
import sys


HEADER = """#version 440
layout(location = 0) out vec4 fragColor;
layout(std140, binding = 0) uniform buf {
    mat4 qt_Matrix;
    float qt_Opacity;
    vec2 u_resolution;
    vec2 u_origin;
    vec2 u_canvas;
    float u_time;
    float u_brightness;
    float u_visibility;
    vec3 u_primary;
    vec3 u_secondary;
    vec3 u_surface;
    vec3 u_error;
};
"""


def adapt(source: str) -> str:
    lines = source.splitlines()
    if lines and lines[0].startswith("#version"):
        lines.pop(0)
    if lines and lines[0].strip() == "precision highp float;":
        lines.pop(0)
    lines = [
        line for line in lines
        if not re.match(r"\s*uniform\s+(vec[23]|float)\s+u_(resolution|origin|canvas|time|brightness|visibility|primary|secondary|surface|error)\s*;\s*$", line)
    ]
    body = "\n".join(lines).replace("gl_FragColor", "fragColor")
    return HEADER + "\n" + body + "\n"


def main() -> int:
    if len(sys.argv) != 3:
        print(f"usage: {sys.argv[0]} ORBIT_WAVE_FRAG OUTPUT_FRAG", file=sys.stderr)
        return 2
    source_path, output_path = map(Path, sys.argv[1:])
    output_path.write_text(adapt(source_path.read_text()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
