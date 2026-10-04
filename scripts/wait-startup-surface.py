#!/usr/bin/env python3
"""Wait for the first rendered Mudos startup frame and release Plymouth."""

from __future__ import annotations

import logging
import os
from pathlib import Path
import select
import time


LOGGER = logging.getLogger("lulu.startup-handoff")


def wait_for_surface(marker: Path, timeout: float = 120.0) -> bool:
    """Use inotify (with a bounded select fallback) rather than a sleep delay."""
    import ctypes
    marker = Path(marker)
    if marker.is_file():
        return True
    libc = ctypes.CDLL(None, use_errno=True)
    inotify_init = libc.inotify_init1
    inotify_init.argtypes = [ctypes.c_int]
    inotify_init.restype = ctypes.c_int
    inotify_add = libc.inotify_add_watch
    inotify_add.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_uint32]
    inotify_add.restype = ctypes.c_int
    fd = inotify_init(os.O_CLOEXEC | os.O_NONBLOCK)
    if fd < 0:
        raise OSError(ctypes.get_errno(), "inotify_init1 failed")
    try:
        # IN_CREATE | IN_MOVED_TO | IN_CLOSE_WRITE
        if inotify_add(fd, os.fsencode(marker.parent), 0x100 | 0x80 | 0x8) < 0:
            raise OSError(ctypes.get_errno(), "inotify_add_watch failed")
        deadline = time.monotonic() + timeout
        while True:
            if marker.is_file():
                return True
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return False
            readable, _, _ = select.select([fd], [], [], remaining)
            if not readable:
                return marker.is_file()
            try:
                os.read(fd, 65536)
            except BlockingIOError:
                continue
            # The directory watch is only a wakeup; exact marker existence is
            # the readiness proof, including atomic file replacement.
            if marker.is_file():
                return True
    finally:
        os.close(fd)


def main() -> int:
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s %(message)s")
    marker = Path("/run/user/958/mudos-startup-surface.ready")
    started = time.monotonic_ns()
    LOGGER.info("startup_timing event=plymouth-handoff-wait monotonic_ns=%s marker=%s",
                started, marker)
    if not wait_for_surface(marker):
        LOGGER.error("startup surface was not rendered before the bounded Plymouth handoff deadline")
        return 1
    LOGGER.info("startup_timing event=plymouth-handoff-ready monotonic_ns=%s elapsed_ms=%.3f",
                time.monotonic_ns(), (time.monotonic_ns() - started) / 1_000_000)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
