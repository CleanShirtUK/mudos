"""Dolphin-only lease for the configured USB Bluetooth passthrough adapter."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
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
    return PATHS.provider_config_root("dolphin") / "dolphin-emu" / "Config" / "Dolphin.ini"


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
    prior_enabled: str
    prior_wiimote_source: str
    acquired: bool = False

    @classmethod
    def create(cls) -> "DolphinBluetoothLease":
        helper = PATHS.install_root / "scripts" / "dolphin-bluetooth-lease.py"
        config = NativeConfigAdapter(dolphin_config_path())
        previous = config.get("BluetoothPassthrough", "Enabled", "False") or "False"
        wiimote_source = config.get("Core", "WiimoteSource0", "1") or "1"
        return cls(helper, config.path, uuid4().hex, previous, wiimote_source)

    def acquire(self) -> None:
        config = NativeConfigAdapter(self.config_path)
        config.set("BluetoothPassthrough", "VID", str(int(ADAPTER_VENDOR_ID, 16)))
        config.set("BluetoothPassthrough", "PID", str(int(ADAPTER_PRODUCT_ID, 16)))
        config.set("BluetoothPassthrough", "Enabled", "True")
        try:
            subprocess.run(
                ["pkexec", str(self.helper), "acquire", self.token, str(os.getpid())],
                check=True, capture_output=True, text=True, timeout=20,
            )
            self.acquired = True
            LOGGER.info("Dolphin Bluetooth passthrough lease acquired token=%s", self.token)
        except (OSError, subprocess.SubprocessError) as error:
            config.set("BluetoothPassthrough", "Enabled", self.prior_enabled)
            try:
                subprocess.run(
                    ["pkexec", str(self.helper), "release", self.token],
                    check=True, capture_output=True, text=True, timeout=20,
                )
            except (OSError, subprocess.SubprocessError):
                LOGGER.exception("Dolphin Bluetooth acquisition rollback needs recovery token=%s", self.token)
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
        error: Exception | None = None
        if self.acquired:
            try:
                subprocess.run(
                    ["pkexec", str(self.helper), "release", self.token],
                    check=True, capture_output=True, text=True, timeout=20,
                )
            except (OSError, subprocess.SubprocessError) as caught:
                error = caught
        # Config restoration is unconditional. Keep the adapter's prior host
        # service state authoritative; report a failed root restoration loudly.
        NativeConfigAdapter(self.config_path).set(
            "BluetoothPassthrough", "Enabled", self.prior_enabled,
        )
        NativeConfigAdapter(self.config_path).set(
            "Core", "WiimoteSource0", self.prior_wiimote_source,
        )
        if error is not None:
            raise RuntimeError(f"could not restore host Bluetooth ownership: {error}") from error
        self.acquired = False
        LOGGER.info("Dolphin Bluetooth passthrough lease released token=%s", self.token)

    async def release_async(self) -> None:
        await asyncio.to_thread(self.release)

    @classmethod
    async def recover_stale_async(cls) -> None:
        helper = PATHS.install_root / "scripts" / "dolphin-bluetooth-lease.py"
        await asyncio.to_thread(
            subprocess.run,
            ["pkexec", str(helper), "recover"],
            check=True, capture_output=True, text=True, timeout=20,
        )
