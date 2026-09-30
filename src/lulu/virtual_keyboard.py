"""Session-lifetime virtual keyboard for managed application hotkeys."""

from __future__ import annotations

import fcntl
import glob
import logging
import os
from pathlib import Path
import struct
import time


LOGGER = logging.getLogger("lulu.virtual_keyboard")
DEVICE_NAME = "Mudos Managed Keyboard"
KEY_ESC = 1
EV_SYN = 0
EV_KEY = 1
SYN_REPORT = 0
UI_SET_EVBIT = 0x40045564
UI_SET_KEYBIT = 0x40045565
UI_DEV_CREATE = 0x5501
UI_DEV_DESTROY = 0x5502
UI_USER_DEV = struct.Struct("=80sHHHHI" + ("i" * 64 * 4))
INPUT_EVENT = struct.Struct("@llHHi")


class ManagedVirtualKeyboard:
    """One minimal Escape-capable keyboard held for the Mudos session lifetime."""

    def __init__(self) -> None:
        existing = self._matching_event_nodes()
        if existing:
            raise RuntimeError(
                f"stale or duplicate {DEVICE_NAME!r} devices already exist: {existing}"
            )

        self.fd = os.open("/dev/uinput", os.O_WRONLY | os.O_NONBLOCK | os.O_CLOEXEC)
        self.closed = False
        self.escape_down = False
        try:
            fcntl.ioctl(self.fd, UI_SET_EVBIT, EV_KEY)
            fcntl.ioctl(self.fd, UI_SET_KEYBIT, KEY_ESC)
            payload = UI_USER_DEV.pack(
                DEVICE_NAME.encode().ljust(80, b"\0"),
                0x03, 0x1209, 0x4C55, 1, 0,
                *([0] * (64 * 4)),
            )
            os.write(self.fd, payload)
            fcntl.ioctl(self.fd, UI_DEV_CREATE)
            self.event_path = self._wait_for_event_node()
        except Exception:
            os.close(self.fd)
            self.closed = True
            raise
        LOGGER.info("persistent virtual keyboard ready name=%r event=%s", DEVICE_NAME,
                    self.event_path)

    @staticmethod
    def _matching_event_nodes() -> list[str]:
        matches = []
        for path in glob.glob("/dev/input/event*"):
            try:
                name = Path(f"/sys/class/input/{Path(path).name}/device/name").read_text().strip()
            except OSError:
                continue
            if name == DEVICE_NAME:
                matches.append(path)
        return matches

    def _wait_for_event_node(self) -> str:
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            matches = self._matching_event_nodes()
            if len(matches) == 1:
                return matches[0]
            if len(matches) > 1:
                raise RuntimeError(f"duplicate {DEVICE_NAME!r} devices appeared: {matches}")
            time.sleep(0.05)
        raise RuntimeError(f"uinput device {DEVICE_NAME!r} did not appear")

    def _event(self, event_type: int, code: int, value: int) -> None:
        now = time.time()
        seconds = int(now)
        microseconds = int((now - seconds) * 1_000_000)
        os.write(self.fd, INPUT_EVENT.pack(seconds, microseconds, event_type, code, value))

    INPUT_EVENT = INPUT_EVENT

    def send_escape(self, hold_seconds: float = 0.1) -> None:
        if self.closed:
            raise RuntimeError("persistent virtual keyboard is closed")
        self._event(EV_KEY, KEY_ESC, 1)
        self._event(EV_SYN, SYN_REPORT, 0)
        self.escape_down = True
        try:
            time.sleep(hold_seconds)
        finally:
            self._event(EV_KEY, KEY_ESC, 0)
            self._event(EV_SYN, SYN_REPORT, 0)
            self.escape_down = False
        LOGGER.info("persistent virtual keyboard Escape tap sent event=%s hold_ms=%d",
                    self.event_path, round(hold_seconds * 1000))

    def close(self) -> None:
        if self.closed:
            return
        try:
            if self.escape_down:
                self._event(EV_KEY, KEY_ESC, 0)
                self._event(EV_SYN, SYN_REPORT, 0)
                self.escape_down = False
            fcntl.ioctl(self.fd, UI_DEV_DESTROY)
        finally:
            os.close(self.fd)
            self.closed = True
        LOGGER.info("persistent virtual keyboard removed name=%r", DEVICE_NAME)
