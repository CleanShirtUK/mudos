"""Pinned official Eden AppImage runtime and integrity checks."""

from __future__ import annotations

from functools import lru_cache
import hashlib
import json
import os
from pathlib import Path

from .paths import PATHS

RUNTIME_MANIFEST = PATHS.install_root / "config/providers/eden/runtime.json"
RUNTIME_ROOT = Path("/var/lib/lulu/providers/eden")


@lru_cache(maxsize=1)
def runtime_definition() -> dict[str, str]:
    value = json.loads(RUNTIME_MANIFEST.read_text(encoding="utf-8"))
    if value.get("schema") != 1:
        raise ValueError("unsupported Eden runtime manifest schema")
    for key in ("version", "source_commit", "source_commit_short", "architecture",
                "build", "filename", "url", "sha256"):
        if not isinstance(value.get(key), str) or not value[key]:
            raise ValueError(f"Eden runtime manifest has no {key}")
    if len(value["sha256"]) != 64 or any(c not in "0123456789abcdef" for c in value["sha256"]):
        raise ValueError("Eden runtime manifest has an invalid SHA-256")
    if not value["filename"].endswith(".AppImage") or not value["url"].startswith("https://"):
        raise ValueError("Eden runtime manifest must identify an HTTPS AppImage")
    return value


def runtime_path() -> Path:
    spec = runtime_definition()
    return RUNTIME_ROOT / spec["source_commit_short"] / spec["filename"]


def is_valid_runtime(path: Path | None = None) -> bool:
    target = path or runtime_path()
    try:
        info = target.stat()
        if not target.is_file() or not os.access(target, os.X_OK):
            return False
        expected = runtime_definition()["sha256"]
        digest = hashlib.sha256()
        with target.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest() == expected
    except (OSError, ValueError, json.JSONDecodeError):
        return False
