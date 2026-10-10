"""Validated session-scoped geometry handoff for the external notification overlay."""

from __future__ import annotations

import json
import math
import os
from pathlib import Path
import tempfile
import time
from typing import Mapping


GEOMETRY_FILENAME = "mudos-status-geometry.json"


def geometry_path(runtime_dir: str | Path | None = None) -> Path:
    root = Path(runtime_dir or os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}"))
    return root / GEOMETRY_FILENAME


def validate_geometry(value: object) -> dict[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError("geometry must be an object")
    required = ("session_id", "coordinate_space", "x", "y", "width", "height",
                "viewport_width", "viewport_height", "display_width", "display_height",
                "device_pixel_ratio", "ui_scale")
    if any(key not in value for key in required):
        raise ValueError("geometry is incomplete")
    session_id = value["session_id"]
    if not isinstance(session_id, str) or not session_id or len(session_id) > 128:
        raise ValueError("invalid geometry session")
    if value["coordinate_space"] != "shell-logical-top-left":
        raise ValueError("unsupported geometry coordinate space")
    result: dict[str, object] = {"session_id": session_id,
                                 "coordinate_space": "shell-logical-top-left",
                                 "updated_at": time.time()}
    bounds = {}
    for key in required[2:]:
        try:
            number = float(value[key])
        except (TypeError, ValueError) as error:
            raise ValueError(f"invalid geometry value: {key}") from error
        if not math.isfinite(number) or number <= 0 and key not in {"x", "y"}:
            raise ValueError(f"invalid geometry value: {key}")
        bounds[key] = number
    if bounds["x"] < 0 or bounds["y"] < 0:
        raise ValueError("geometry origin must be within the viewport")
    if (bounds["x"] + bounds["width"] > bounds["viewport_width"] + 1
            or bounds["y"] + bounds["height"] > bounds["viewport_height"] + 1):
        raise ValueError("status strip geometry exceeds viewport")
    if bounds["viewport_width"] > bounds["display_width"] + 1 \
            or bounds["viewport_height"] > bounds["display_height"] + 1:
        raise ValueError("shell viewport exceeds display bounds")
    result.update(bounds)
    return result


def write_geometry(value: object, runtime_dir: str | Path | None = None) -> dict[str, object]:
    record = validate_geometry(value)
    path = geometry_path(runtime_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(record, stream, separators=(",", ":"), sort_keys=True)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise
    return record
