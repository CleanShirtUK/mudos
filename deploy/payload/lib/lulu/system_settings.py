"""Normalized, non-privileged System/Settings information boundary."""

from __future__ import annotations

from dataclasses import dataclass
import os
import platform
import shutil
import socket
import subprocess
from typing import Any


@dataclass(frozen=True, slots=True)
class SystemSetting:
    key: str
    label: str
    kind: str
    value: Any
    detail: str = ""
    writable: bool = False

    def as_dict(self) -> dict[str, object]:
        return {
            "key": self.key,
            "label": self.label,
            "kind": self.kind,
            "value": self.value,
            "detail": self.detail,
            "writable": self.writable,
        }


CATEGORIES = ("Display", "Audio", "Network", "Bluetooth", "Controllers", "Storage", "System", "Lulu")
FILE_BROWSER_SERVICE = "lulu-file-browser.service"
FILE_BROWSER_PORT = int(os.environ.get("LULU_FILE_BROWSER_PORT", "8080"))


def _command(*args: str) -> str:
    try:
        result = subprocess.run(args, check=False, capture_output=True, text=True, timeout=2)
    except (OSError, subprocess.SubprocessError):
        return ""
    return result.stdout.strip()


def _status(key: str, label: str, value: object, detail: str = "") -> SystemSetting:
    return SystemSetting(key, label, "status", value, detail)


class SystemSettingsProvider:
    """Read normalized host state without exposing Linux implementation details to QML."""

    categories = CATEGORIES

    def list_settings(self, category: str) -> list[dict[str, object]]:
        if category not in CATEGORIES:
            raise ValueError(f"unknown system settings category: {category}")
        return [setting.as_dict() for setting in getattr(self, f"_{category.lower()}_settings")()]

    def _display_settings(self) -> list[SystemSetting]:
        output = os.environ.get("LULU_OUTPUT_CONNECTOR", "auto")
        mode = os.environ.get("LULU_OUTPUT_MODE", "deployment")
        return [
            _status("display.output", "Presentation output", output, "Deployment configured"),
            _status("display.mode", "Active mode", mode, "Mode changes are TO PROVE"),
            _status("display.hdr", "HDR", "unknown", "Capability detection is TO PROVE"),
            _status("display.vrr", "VRR", "unknown", "Capability detection is TO PROVE"),
        ]

    def _audio_settings(self) -> list[SystemSetting]:
        default = _command("pactl", "get-default-sink") or "unknown"
        return [_status("audio.output", "Default output", default, "PipeWire/Pulse compatibility status")]

    def _network_settings(self) -> list[SystemSetting]:
        state = _command("nmcli", "-t", "-f", "STATE", "general") or "unavailable"
        wifi = _command("nmcli", "radio", "wifi") or "unavailable"
        address = _command("hostname", "-I") or "unknown"
        file_browser_state = _command("systemctl", "is-active", FILE_BROWSER_SERVICE) or "unavailable"
        file_browser_address = (
            f"http://{address.split()[0]}:{FILE_BROWSER_PORT}/"
            if address not in {"", "unknown"} and address.split()
            else "unavailable"
        )
        return [
            _status("network.state", "Connection", state),
            _status("network.wifi", "Wi-Fi", wifi, "NetworkManager radio state"),
            _status("network.address", "IP address", address),
            _status("network.scan", "Wi-Fi networks", "available", "Use Internet settings for discovery and connection"),
            _status("network.file_browser", "File browser", file_browser_state, "dufs; ROM and BIOS roots only"),
            _status("network.file_browser_address", "File browser address", file_browser_address, "Local network; authentication required"),
        ]

    def _bluetooth_settings(self) -> list[SystemSetting]:
        powered = _command("bluetoothctl", "show")
        state = "on" if "Powered: yes" in powered else "off" if powered else "unavailable"
        return [_status("bluetooth.state", "Adapter", state, "Pair/connect mutation path is TO PROVE")]

    def _controllers_settings(self) -> list[SystemSetting]:
        return [_status("controllers.state", "Controller service", "managed by InputPlumber", "Detailed controller model is TO PROVE")]

    def _storage_settings(self) -> list[SystemSetting]:
        usage = shutil.disk_usage("/")
        return [
            _status("storage.total", "System storage", f"{usage.total // (1024**3)} GiB total"),
            _status("storage.free", "Available", f"{usage.free // (1024**3)} GiB free"),
            _status("storage.library", "Game storage", "managed", "Per-provider usage is TO PROVE"),
        ]

    def _system_settings(self) -> list[SystemSetting]:
        return [
            SystemSetting("lulu.reset", "Reset Mudos", "action", "restart session", "Restarts the Lulu graphical session", True),
            _status("system.hostname", "Device name", socket.gethostname()),
            _status("system.os", "Operating system", platform.platform()),
            _status("system.kernel", "Kernel", platform.release()),
            _status("system.cpu", "CPU", platform.processor() or "unknown"),
            _status("system.memory", "Memory", "available", "Detailed memory model is TO PROVE"),
            _status("system.power", "Power controls", "available", "Controller confirmation required"),
        ]

    def _lulu_settings(self) -> list[SystemSetting]:
        return [
            _status("lulu.startup", "Startup category", "Recent", "Persistence integration is TO PROVE"),
            _status("lulu.motion", "Reduced motion", "off", "Policy integration is TO PROVE"),
            _status("lulu.hints", "Controller hints", "on"),
            _status("lulu.debug", "Developer information", "available"),
        ]
