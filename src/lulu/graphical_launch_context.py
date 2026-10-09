"""Current graphical launch context shared with the Aurelia script boundary."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
import re
import socket
import time
from typing import Mapping

from .paths import PATHS

GRAPHICAL_ENV = ("DISPLAY", "WAYLAND_DISPLAY", "XDG_RUNTIME_DIR")
OPTIONAL_GAME_ENV = ("MANGOHUD", "MANGOHUD_CONFIG")
APPROVED_CONTEXT_ENV = GRAPHICAL_ENV + OPTIONAL_GAME_ENV
CONTEXT_PATH = PATHS.runtime_root / "aurelia-graphical-launch-context.json"
# Sessiond refreshes this snapshot on its 0.5-second presentation watchdog.
# A narrow expiry prevents a recently disconnected display from riding out a
# long-lived snapshot while the daemon retains an older environment.
CONTEXT_MAX_AGE_SECONDS = 0.75
LOGGER = logging.getLogger("lulu.graphical-launch-context")
_LAUNCH_TOKEN = re.compile(r"^[0-9a-f]{32}$")


def _process_start_time(pid: int) -> str | None:
    try:
        stat = Path(f"/proc/{pid}/stat").read_text(encoding="ascii")
        fields_after_comm = stat[stat.rfind(")") + 2:].split()
        return fields_after_comm[19]  # Linux stat field 22 (starttime).
    except (OSError, IndexError, ValueError):
        return None


def write_context(
    values: Mapping[str, str], session_id: str, *, ready: bool,
    shell_pid: int | None = None, launch_token: str | None = None,
    path: Path | None = None,
) -> bool:
    """Atomically publish a small, private session snapshot for the wrapper."""
    path = path or CONTEXT_PATH
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        if not ready:
            clear_context(path)
            return True
        environment = {key: values[key] for key in APPROVED_CONTEXT_ENV if values.get(key)}
        shell_start_time = _process_start_time(shell_pid) if shell_pid is not None else None
        if (not set(GRAPHICAL_ENV).issubset(environment) or shell_start_time is None
                or (launch_token is not None and not _LAUNCH_TOKEN.fullmatch(launch_token))):
            clear_context(path)
            return False
        temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
        with temporary.open("w", encoding="utf-8") as stream:
            os.chmod(temporary, 0o600)
            json.dump({"environment": environment, "session_id": session_id,
                       "shell_pid": shell_pid, "shell_start_time": shell_start_time,
                       "launch_token": launch_token, "updated_at": time.time(),
                       "presentation_ready": True}, stream)
            stream.write("\n")
        os.replace(temporary, path)
        temporary.unlink(missing_ok=True)
        return True
    except OSError:
        LOGGER.exception("could not publish the current graphical launch context")
        return False


def consumed_marker(path: Path, launch_token: str) -> Path:
    if not _LAUNCH_TOKEN.fullmatch(launch_token):
        raise ValueError("invalid graphical launch token")
    return path.with_name(f"{path.name}.consumed.{launch_token}")


def context_was_consumed(path: Path, launch_token: str) -> bool:
    return consumed_marker(path, launch_token).exists()


def clear_context(path: Path | None = None, *, launch_token: str | None = None) -> None:
    """Remove a snapshot and its acknowledgement without touching another lease."""
    path = path or CONTEXT_PATH
    try:
        current_token = None
        try:
            current = json.loads(path.read_text(encoding="utf-8"))
            current_token = current.get("launch_token")
        except (OSError, ValueError, AttributeError):
            pass
        if launch_token is None or current_token in (None, launch_token):
            path.unlink(missing_ok=True)
        if launch_token is not None:
            consumed_marker(path, launch_token).unlink(missing_ok=True)
        elif current_token:
            consumed_marker(path, str(current_token)).unlink(missing_ok=True)
    except OSError:
        LOGGER.exception("could not clear the graphical launch context")


def _socket_is_live(path: Path) -> bool:
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.settimeout(0.15)
            client.connect(str(path))
        return True
    except OSError:
        return False


def graphical_context_is_live(environment: Mapping[str, str]) -> bool:
    """Check runtime ownership and both sockets independently of shell lifecycle."""
    try:
        if any(not isinstance(environment.get(key), str) or not environment[key]
               for key in GRAPHICAL_ENV):
            return False
        runtime = Path(environment["XDG_RUNTIME_DIR"])
        if not runtime.is_dir() or runtime.stat().st_uid != os.geteuid():
            return False
        wayland = Path(environment["WAYLAND_DISPLAY"])
        wayland_socket = wayland if wayland.is_absolute() else runtime / wayland
        x11_socket = _display_socket(environment["DISPLAY"])
        return bool(x11_socket and _socket_is_live(wayland_socket)
                    and _socket_is_live(x11_socket))
    except (OSError, TypeError, ValueError):
        return False


def context_is_valid(
    path: Path | None = None,
    *,
    session_id: str,
    shell_pid: int,
    now: float | None = None,
    launch_token: str | None = None,
) -> bool:
    """Validate a published snapshot without consuming its launch lease."""
    path = path or CONTEXT_PATH
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
        environment = record["environment"]
        updated_at = float(record["updated_at"])
        if (
            record.get("presentation_ready") is not True
            or record.get("session_id") != session_id
            or record.get("shell_pid") != shell_pid
            or (launch_token is None and record.get("launch_token") is not None)
            or (launch_token is not None and record.get("launch_token") != launch_token)
        ):
            return False
        current_start = _process_start_time(shell_pid)
        if current_start is None or current_start != record.get("shell_start_time"):
            return False
        current_time = time.time() if now is None else now
        if current_time < updated_at or current_time - updated_at > CONTEXT_MAX_AGE_SECONDS:
            return False
        return isinstance(environment, dict) and graphical_context_is_live(environment)
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        return False


def _display_socket(display: str) -> Path | None:
    # Support local X11 display names (e.g. :0, :0.0, unix/:0).
    if display.startswith("unix:/"):
        return Path(display[5:])
    value = display.removeprefix("unix/")
    if value.startswith(":"):
        number = value[1:].split(".", 1)[0]
    elif value.startswith("unix:"):
        number = value[5:].split(".", 1)[0]
    else:
        return None
    if not number.isdecimal():
        return None
    return Path("/tmp/.X11-unix") / f"X{number}"


def read_current_context(path: Path | None = None, *, now: float | None = None) -> dict[str, str]:
    """Return approved, live session values or raise ValueError when stale."""
    path = path or CONTEXT_PATH
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
        environment = record["environment"]
        timestamp = float(record["updated_at"])
        if not record.get("presentation_ready") or not record.get("session_id"):
            raise ValueError("presentation is no longer ready")
        shell_pid = record.get("shell_pid")
        if (not isinstance(shell_pid, int) or shell_pid <= 1
                or _process_start_time(shell_pid) != record.get("shell_start_time")):
            raise ValueError("graphical context belongs to an obsolete Mudos session")
        current_time = time.time() if now is None else now
        if current_time < timestamp or current_time - timestamp > CONTEXT_MAX_AGE_SECONDS:
            raise ValueError("graphical session context is stale")
        if not isinstance(environment, dict) or not record.get("launch_token"):
            raise ValueError("graphical session context is incomplete")
        if not graphical_context_is_live(environment):
            raise ValueError("graphical runtime or display/compositor socket is unavailable")
        launch_token = str(record["launch_token"])
        marker = consumed_marker(path, launch_token)
        descriptor = os.open(marker, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        os.close(descriptor)
        path.unlink(missing_ok=True)
        return {key: environment[key] for key in APPROVED_CONTEXT_ENV if key in environment}
    except (OSError, KeyError, TypeError, json.JSONDecodeError) as error:
        raise ValueError("no current graphical launch context") from error
