"""Bounded graphical failure history shared by Sessiond and the recovery portal."""

from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
import time
from typing import Any

from .paths import PATHS

STATE_PATH = PATHS.config_root / "recovery-state.json"
FAILURE_WINDOW_SECONDS = 300
RECOVERY_FAILURE_THRESHOLD = 3


def _load(path: Path = STATE_PATH) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text())
        if isinstance(value, dict):
            return value
    except (OSError, ValueError):
        pass
    return {"failures": [], "active": False, "last_failure": ""}


def _save(value: dict[str, Any], path: Path = STATE_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".recovery-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(value, stream, sort_keys=True)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def record_failure(reason: str, *, now: float | None = None,
                   path: Path = STATE_PATH) -> dict[str, Any]:
    timestamp = time.time() if now is None else now
    state = _load(path)
    failures = [float(item) for item in state.get("failures", [])
                if timestamp - float(item) <= FAILURE_WINDOW_SECONDS]
    failures.append(timestamp)
    state.update(failures=failures, last_failure=str(reason)[:400],
                 active=len(failures) >= RECOVERY_FAILURE_THRESHOLD,
                 updated_at=int(timestamp))
    _save(state, path)
    return state


def recovery_required(*, now: float | None = None, path: Path = STATE_PATH) -> bool:
    timestamp = time.time() if now is None else now
    state = _load(path)
    failures = [item for item in state.get("failures", [])
                if timestamp - float(item) <= FAILURE_WINDOW_SECONDS]
    return bool(state.get("active")) and len(failures) >= RECOVERY_FAILURE_THRESHOLD


def clear_failures(path: Path = STATE_PATH) -> None:
    _save({"failures": [], "active": False, "last_failure": ""}, path)


def snapshot(path: Path = STATE_PATH) -> dict[str, Any]:
    state = _load(path)
    state["failure_count"] = len(state.get("failures", []))
    return state
