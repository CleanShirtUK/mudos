"""Evidence-backed observation of a process by environment metadata."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Callable, Iterable


PROC_ROOT = Path("/proc")
APP_ID_ENVIRONMENT_KEYS = ("SteamAppId", "SteamGameId", "STEAM_COMPAT_APP_ID")


def process_environment(pid: int, *, proc_root: Path = PROC_ROOT) -> dict[str, str]:
    """Read the kernel-exposed environment for a live process."""
    raw = (proc_root / str(pid) / "environ").read_bytes()
    return {
        item.partition(b"=")[0].decode(errors="replace"): item.partition(b"=")[2].decode(
            errors="replace"
        )
        for item in raw.split(b"\0")
        if b"=" in item
    }


def process_argv(pid: int, *, proc_root: Path = PROC_ROOT) -> tuple[str, ...]:
    """Read a process argument vector from procfs."""
    return tuple(
        item.decode(errors="replace")
        for item in (proc_root / str(pid) / "cmdline").read_bytes().split(b"\0")
        if item
    )


def process_has_app_id(pid: int, app_id: str, *,
                       environment_keys: Iterable[str] = APP_ID_ENVIRONMENT_KEYS,
                       proc_root: Path = PROC_ROOT) -> bool:
    """Require an exact AppID match in kernel process environment evidence."""
    try:
        environment = process_environment(pid, proc_root=proc_root)
    except (FileNotFoundError, PermissionError, ProcessLookupError, OSError):
        return False
    return any(environment.get(key) == app_id for key in environment_keys)


def processes_with_app_id(
    app_id: str,
    *,
    exclude: Callable[[str, tuple[str, ...]], bool],
    environment_keys: Iterable[str] = APP_ID_ENVIRONMENT_KEYS,
    proc_root: Path = PROC_ROOT,
    uid: int | None = None,
) -> list[int]:
    """Find same-user AppID processes, excluding provider-specific runtimes.

    The observer owns only procfs/AppID evidence. Callers supply the runtime
    exclusion policy so Steam-specific helper filtering remains with Steam.
    """
    owner = os.getuid() if uid is None else uid
    keys = tuple(environment_keys)
    result: list[int] = []
    for entry in proc_root.iterdir():
        if not entry.name.isdecimal():
            continue
        try:
            if entry.stat().st_uid != owner:
                continue
            environment = process_environment(int(entry.name), proc_root=proc_root)
            if not any(environment.get(key) == app_id for key in keys):
                continue
            executable = os.path.realpath(str(entry / "exe"))
            argv = process_argv(int(entry.name), proc_root=proc_root)
        except (FileNotFoundError, PermissionError, ProcessLookupError, OSError):
            continue
        if not exclude(executable, argv):
            result.append(int(entry.name))
    return result
