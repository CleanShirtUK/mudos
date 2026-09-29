"""Dolphin-only lease for the configured USB Bluetooth passthrough adapter."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import json
import logging
import os
from pathlib import Path
import subprocess
from uuid import uuid4

from .paths import PATHS
from .providers.config import NativeConfigAdapter


LOGGER = logging.getLogger("lulu.dolphin-passthrough")
ADAPTER_VENDOR_ID = "0bda"
ADAPTER_PRODUCT_ID = "8771"


def dolphin_config_path() -> Path:
    return PATHS.provider_config_root("dolphin") / "dolphin-emu" / "Dolphin.ini"


def dolphin_config_lease_path(config_path: Path | None = None) -> Path:
    config = config_path or dolphin_config_path()
    return config.with_name(".Dolphin.ini.passthrough-lease.json")


_LEASED_KEYS = (
    ("BluetoothPassthrough", "Enabled"),
    ("BluetoothPassthrough", "VID"),
    ("BluetoothPassthrough", "PID"),
)


def _capture_config(config: NativeConfigAdapter) -> dict[str, str | None]:
    return {f"{section}.{key}": config.get(section, key) for section, key in _LEASED_KEYS}


def _restore_config(config: NativeConfigAdapter, values: dict[str, object]) -> None:
    for section, key in _LEASED_KEYS:
        value = values.get(f"{section}.{key}")
        if value is None:
            config.remove(section, key)
        elif isinstance(value, str):
            config.set(section, key, value)


def _persist_config_lease(path: Path, token: str, values: dict[str, str | None]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps({"token": token, "values": values}, sort_keys=True) + "\n",
                         encoding="utf-8")
    os.chmod(temporary, 0o600)
    temporary.replace(path)


def _restore_persisted_config(config_path: Path) -> bool:
    lease_path = dolphin_config_lease_path(config_path)
    try:
        state = json.loads(lease_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return False
    if not isinstance(state, dict) or not isinstance(state.get("values"), dict):
        raise RuntimeError("Dolphin Bluetooth config lease is invalid")
    _restore_config(NativeConfigAdapter(config_path), state["values"])
    lease_path.unlink(missing_ok=True)
    return True


def adapter_present(sys_usb_root: Path = Path("/sys/bus/usb/devices")) -> bool:
    """Require exactly one matching tested adapter; never fall back to host BT."""
    matches = 0
    for device in sys_usb_root.iterdir() if sys_usb_root.is_dir() else ():
        try:
            vendor = (device / "idVendor").read_text().strip().lower()
            product = (device / "idProduct").read_text().strip().lower()
        except OSError:
            continue
        if vendor == ADAPTER_VENDOR_ID and product == ADAPTER_PRODUCT_ID:
            matches += 1
    return matches == 1


@dataclass(slots=True)
class DolphinBluetoothLease:
    """Restore Dolphin config and BlueZ service ownership after a Wii session."""

    helper: Path
    config_path: Path
    token: str
    prior_config: dict[str, str | None]
    acquired: bool = False
    attempted: bool = False

    @classmethod
    def create(cls) -> "DolphinBluetoothLease":
        helper = PATHS.install_root / "scripts" / "dolphin-bluetooth-lease.py"
        config = NativeConfigAdapter(dolphin_config_path())
        return cls(helper, config.path, uuid4().hex, _capture_config(config))

    def acquire(self) -> None:
        config = NativeConfigAdapter(self.config_path)
        lease_path = dolphin_config_lease_path(self.config_path)
        if lease_path.exists():
            raise RuntimeError("a Dolphin Bluetooth configuration lease already exists")
        _persist_config_lease(lease_path, self.token, self.prior_config)
        self.attempted = True
        try:
            config.set("BluetoothPassthrough", "VID", str(int(ADAPTER_VENDOR_ID, 16)))
            config.set("BluetoothPassthrough", "PID", str(int(ADAPTER_PRODUCT_ID, 16)))
            config.set("BluetoothPassthrough", "Enabled", "True")
            subprocess.run(
                ["pkexec", str(self.helper), "acquire", self.token, str(os.getpid())],
                check=True, capture_output=True, text=True, timeout=20,
            )
            self.acquired = True
            LOGGER.info("Dolphin Bluetooth passthrough lease acquired token=%s", self.token)
        except (OSError, subprocess.SubprocessError) as error:
            root_rollback_complete = True
            try:
                subprocess.run(
                    ["pkexec", str(self.helper), "release", self.token],
                    check=True, capture_output=True, text=True, timeout=20,
                )
            except (OSError, subprocess.SubprocessError):
                root_rollback_complete = False
                LOGGER.exception("Dolphin Bluetooth acquisition rollback needs recovery token=%s", self.token)
            if root_rollback_complete:
                try:
                    _restore_config(config, self.prior_config)
                    lease_path.unlink(missing_ok=True)
                except Exception as rollback_error:
                    LOGGER.exception("Dolphin Bluetooth config rollback needs recovery token=%s", self.token)
                    raise RuntimeError(
                        f"could not acquire Dolphin Bluetooth adapter and config rollback failed: {rollback_error}"
                    ) from error
            raise RuntimeError(f"could not acquire Dolphin Bluetooth adapter: {error}") from error

    async def acquire_async(self) -> None:
        await asyncio.to_thread(self.acquire)

    def attach(self, dolphin_pid: int) -> None:
        if not self.acquired:
            raise RuntimeError("Bluetooth passthrough adapter lease is not active")
        subprocess.run(
            ["pkexec", str(self.helper), "attach", self.token, str(dolphin_pid)],
            check=True, capture_output=True, text=True, timeout=20,
        )

    async def attach_async(self, dolphin_pid: int) -> None:
        await asyncio.to_thread(self.attach, dolphin_pid)

    def release(self) -> None:
        if not self.attempted and not self.acquired:
            return
        error: Exception | None = None
        try:
            subprocess.run(
                ["pkexec", str(self.helper), "release", self.token],
                check=True, capture_output=True, text=True, timeout=20,
            )
        except (OSError, subprocess.SubprocessError) as caught:
            error = caught
        if error is not None:
            raise RuntimeError(f"could not restore host Bluetooth ownership: {error}") from error
        if not _restore_persisted_config(self.config_path) and dolphin_config_lease_path(self.config_path).exists():
            _restore_config(NativeConfigAdapter(self.config_path), self.prior_config)
            dolphin_config_lease_path(self.config_path).unlink(missing_ok=True)
        self.acquired = False
        LOGGER.info("Dolphin Bluetooth passthrough lease released token=%s", self.token)

    async def release_async(self) -> None:
        while True:
            try:
                await asyncio.to_thread(self.release)
                return
            except (OSError, RuntimeError, subprocess.SubprocessError):
                # Keep retrying in the owning service while the root-side
                # recovery record exists. If this task is interrupted by a
                # service restart, recover_stale_async resumes after Dolphin
                # relinquishes the adapter.
                LOGGER.exception("Dolphin Bluetooth restoration pending token=%s", self.token)
                await asyncio.sleep(3)

    @classmethod
    async def recover_stale_async(cls) -> None:
        helper = PATHS.install_root / "scripts" / "dolphin-bluetooth-lease.py"
        await asyncio.to_thread(
            subprocess.run,
            ["pkexec", str(helper), "recover"],
            check=True, capture_output=True, text=True, timeout=20,
        )
        await asyncio.to_thread(_restore_persisted_config, dolphin_config_path())
