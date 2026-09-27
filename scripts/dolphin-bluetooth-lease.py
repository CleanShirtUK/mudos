#!/usr/bin/env python3
"""Privileged, narrow BlueZ stop/start lease for Dolphin Bluetooth passthrough."""

from __future__ import annotations

import json
import fcntl
from contextlib import contextmanager
import os
from pathlib import Path
import stat
import re
import subprocess
import sys
import tempfile


VENDOR = "0bda"
PRODUCT = "8771"
STATE = Path("/run/lulu-dolphin-bluetooth/lease.json")
TOKEN_RE = re.compile(r"^[0-9a-f]{32}$")


def run(*command: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, check=False, capture_output=True, text=True, timeout=15)


def require_adapter(sys_usb_root: Path = Path("/sys/bus/usb/devices")) -> Path:
    matches = []
    for device in sys_usb_root.iterdir():
        try:
            vendor = (device / "idVendor").read_text().strip().lower()
            product = (device / "idProduct").read_text().strip().lower()
        except OSError:
            continue
        if (vendor, product) == (VENDOR, PRODUCT):
            matches.append(device)
    if len(matches) != 1:
        raise RuntimeError(f"expected exactly one {VENDOR}:{PRODUCT} Bluetooth adapter; found {len(matches)}")
    return matches[0]


def prepare_state_directory() -> None:
    directory = STATE.parent
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    metadata = directory.lstat()
    if stat.S_ISLNK(metadata.st_mode) or metadata.st_uid != 0:
        raise RuntimeError("Dolphin Bluetooth lease state directory is not root-owned")
    os.chmod(directory, 0o700)


def active(unit: str) -> bool:
    result = run("systemctl", "is-active", "--quiet", unit)
    if result.returncode not in (0, 3, 4):
        raise RuntimeError(result.stderr.strip() or f"could not query {unit}")
    return result.returncode == 0


def process_starttime(pid: object) -> str | None:
    if not isinstance(pid, int) or pid < 2:
        return None
    try:
        content = Path(f"/proc/{pid}/stat").read_text(encoding="ascii")
        _, _, remainder = content.rpartition(")")
        fields = remainder.split()
        return fields[19]
    except (OSError, IndexError):
        return None


@contextmanager
def state_lock():
    prepare_state_directory()
    descriptor = os.open(STATE.parent / "lock", os.O_CREAT | os.O_RDWR | os.O_CLOEXEC, 0o600)
    try:
        os.fchmod(descriptor, 0o600)
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)


def write_state(value: dict[str, object]) -> None:
    prepare_state_directory()
    fd, temporary = tempfile.mkstemp(prefix=".dolphin-bt-", dir=STATE.parent)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(value, stream, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, STATE)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def acquire(token: str, owner_pid: int) -> None:
    adapter = require_adapter()
    if STATE.exists():
        previous = json.loads(STATE.read_text(encoding="utf-8"))
        if previous.get("token") == token:
            return
        raise RuntimeError("another Dolphin Bluetooth passthrough lease is active")
    was_active = active("bluetooth.service")
    interfaces: list[str] = []
    # Publish the recovery record before changing BlueZ ownership.
    owner_start = process_starttime(owner_pid)
    if owner_start is None:
        raise RuntimeError("Dolphin passthrough owner process is not alive")
    write_state({"token": token, "owner_pid": owner_pid, "owner_starttime": owner_start,
                 "bluetooth_was_active": was_active,
                 "adapter": str(adapter), "unbound_interfaces": interfaces})
    try:
        if was_active:
            result = run("systemctl", "stop", "bluetooth.service")
            if result.returncode:
                raise RuntimeError(result.stderr.strip() or "could not stop bluetooth.service")
        if was_active and active("bluetooth.service"):
            raise RuntimeError("bluetooth.service remained active")
        for interface in sorted(adapter.glob(f"{adapter.name}:*")):
            try:
                driver = (interface / "driver").resolve(strict=True)
            except OSError:
                continue
            if driver.name != "btusb":
                continue
            interfaces.append(interface.name)
            write_state({"token": token, "owner_pid": owner_pid, "owner_starttime": owner_start,
                         "bluetooth_was_active": was_active,
                         "adapter": str(adapter), "unbound_interfaces": interfaces})
            (driver / "unbind").write_text(interface.name, encoding="ascii")
    except Exception:
        rollback_errors: list[str] = []
        try:
            bind_interfaces(interfaces)
        except Exception as error:
            rollback_errors.append(str(error))
        if was_active:
            start = run("systemctl", "start", "bluetooth.service")
            if start.returncode:
                rollback_errors.append(start.stderr.strip() or "could not restore bluetooth.service")
        if not rollback_errors:
            STATE.unlink(missing_ok=True)
        else:
            raise RuntimeError("adapter acquisition rollback incomplete: " + "; ".join(rollback_errors))
        raise


def attach(token: str, dolphin_pid: int) -> None:
    state = json.loads(STATE.read_text(encoding="utf-8"))
    if state.get("token") != token:
        raise RuntimeError("Dolphin Bluetooth lease token does not match")
    start = process_starttime(dolphin_pid)
    if start is None:
        raise RuntimeError("Dolphin process is not alive")
    state["dolphin_pid"] = dolphin_pid
    state["dolphin_starttime"] = start
    write_state(state)


def restore(state: dict[str, object]) -> None:
    errors: list[str] = []
    try:
        bind_interfaces(state.get("unbound_interfaces", []))
    except Exception as error:
        errors.append(str(error))
    if state.get("bluetooth_was_active") and not active("bluetooth.service"):
        result = run("systemctl", "start", "bluetooth.service")
        if result.returncode:
            errors.append(result.stderr.strip() or "could not restore bluetooth.service")
    if errors:
        raise RuntimeError("adapter restoration incomplete: " + "; ".join(errors))


def release(token: str) -> None:
    try:
        state = json.loads(STATE.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return
    if state.get("token") != token:
        raise RuntimeError("Dolphin Bluetooth lease token does not match")
    restore(state)
    STATE.unlink(missing_ok=True)


def recover() -> None:
    try:
        state = json.loads(STATE.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return
    owner_starttime = state.get("owner_starttime")
    if (owner_starttime is not None
            and process_starttime(state.get("owner_pid")) == owner_starttime):
        raise RuntimeError("Dolphin passthrough owner is still active")
    dolphin_starttime = state.get("dolphin_starttime")
    if (dolphin_starttime is not None
            and process_starttime(state.get("dolphin_pid")) == dolphin_starttime):
        raise RuntimeError("Dolphin still owns the Bluetooth passthrough adapter")
    restore(state)
    STATE.unlink(missing_ok=True)


def bind_interfaces(interfaces: object) -> None:
    if not isinstance(interfaces, list):
        raise RuntimeError("Dolphin Bluetooth lease has invalid interface state")
    bind = Path("/sys/bus/usb/drivers/btusb/bind")
    for interface in interfaces:
        if not isinstance(interface, str) or not re.fullmatch(r"[0-9-]+:[0-9.]+", interface):
            raise RuntimeError("Dolphin Bluetooth lease contains an invalid USB interface")
        path = Path("/sys/bus/usb/devices") / interface
        if path.is_dir() and bind.exists():
            try:
                if (path / "driver").resolve(strict=True).name == "btusb":
                    continue
            except OSError:
                pass
            bind.write_text(interface, encoding="ascii")


def main(argv: list[str]) -> int:
    valid = (len(argv) == 4 and argv[1] == "acquire" and TOKEN_RE.fullmatch(argv[2])
             and argv[3].isdigit() and int(argv[3]) > 1) or (
                 len(argv) == 4 and argv[1] == "attach" and TOKEN_RE.fullmatch(argv[2])
                 and argv[3].isdigit() and int(argv[3]) > 1) or (
                     len(argv) == 3 and argv[1] == "release" and TOKEN_RE.fullmatch(argv[2])) or (
                         len(argv) == 2 and argv[1] == "recover")
    if os.geteuid() != 0 or not valid:
        print("usage: dolphin-bluetooth-lease.py acquire TOKEN OWNER_PID | attach TOKEN DOLPHIN_PID | release TOKEN | recover",
              file=sys.stderr)
        return 2
    try:
        with state_lock():
            if argv[1] == "acquire":
                acquire(argv[2], int(argv[3]))
            elif argv[1] == "attach":
                attach(argv[2], int(argv[3]))
            elif argv[1] == "release":
                release(argv[2])
            else:
                recover()
    except (OSError, RuntimeError, ValueError, json.JSONDecodeError) as error:
        print(str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
