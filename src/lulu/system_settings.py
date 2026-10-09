"""Normalized, non-privileged System/Settings information boundary."""

from __future__ import annotations

from dataclasses import dataclass
import os
import platform
import shutil
import socket
import subprocess
import asyncio
from typing import Any

from .bluetooth import BluezClient
from .paths import PATHS
from .settings import SettingsStore


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


CATEGORIES = ("Display", "Audio", "Network", "Bluetooth", "Controllers", "Storage", "Performance", "System")
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

    def __init__(self, bluetooth: BluezClient | None = None) -> None:
        self.bluetooth = bluetooth or BluezClient()

    def list_settings(self, category: str) -> list[dict[str, object]]:
        if category not in CATEGORIES:
            raise ValueError(f"unknown system settings category: {category}")
        return [setting.as_dict() for setting in getattr(self, f"_{category.lower()}_settings")()]

    async def list_settings_async(self, category: str) -> list[dict[str, object]]:
        if category != "Bluetooth":
            return self.list_settings(category)
        snap = await self.bluetooth.snapshot()
        adapters = snap["adapters"]
        rows: list[dict[str, object]] = []
        powered = any(adapter["powered"] for adapter in adapters)
        discovery = any(adapter["discovering"] for adapter in adapters)
        rows.append(SystemSetting("bluetooth.state", "Bluetooth", "status",
                                  "unavailable" if not snap["available"] else "on" if powered else "off",
                                  snap["error"] or (adapters[0]["name"] + " · " + adapters[0]["address"]
                                                     if adapters else "No adapter present")).as_dict())
        if snap["available"] and powered:
            rows.extend([
                SystemSetting("bluetooth:stop-discovery" if discovery else "bluetooth:discover",
                              "Stop discovery" if discovery else "Start discovery",
                              "action", "Scanning" if discovery else "Ready", "", True).as_dict(),
                SystemSetting("bluetooth:disable", "Turn Bluetooth off", "action", "", "", True).as_dict(),
            ])
        elif snap["available"]:
            rows.append(SystemSetting("bluetooth:enable", "Turn Bluetooth on", "action", "", "", True).as_dict())
        for prompt in snap.get("pairing_prompts", []):
            if prompt.get("kind") == "display":
                rows.append(SystemSetting("bluetooth:pairing-info", "Pairing · " + prompt["message"],
                                          "status", "", "Follow the instruction on the other device.").as_dict())
                continue
            if prompt.get("needs_text"):
                rows.append(SystemSetting("bluetooth:pairing-accept", "Enter PIN/passkey · " + prompt["message"],
                                          "input", "", "Use the controller keyboard to enter the requested value.", True).as_dict())
            else:
                rows.append(SystemSetting("bluetooth:pairing-accept", "Confirm · " + prompt["message"],
                                          "action", "", "A confirmation is required to continue pairing.", True).as_dict())
            rows.append(SystemSetting("bluetooth:pairing-reject", "Reject pairing request", "action", "", "", True).as_dict())
        for device in snap["devices"]:
            kind = device["icon"] or (f"Class {device['class']:06X}" if device["class"] else "Bluetooth device")
            strength = f" · RSSI {device['rssi']} dBm" if device["rssi"] is not None else ""
            state = "Connected" if device["connected"] else "Paired" if device["paired"] else "Nearby"
            detail = (f"{state} · {'Trusted' if device['trusted'] else 'Not trusted'} · {kind}{strength}; "
                      "paired, trusted and connected are independent BlueZ states")
            actions = (["disconnect"] if device["connected"] else
                       ["connect", "forget"] if device["paired"] else ["pair"])
            for action in actions:
                label = {"pair": "Pair", "connect": "Connect", "disconnect": "Disconnect",
                         "forget": "Forget"}[action]
                rows.append(SystemSetting(
                    f"bluetooth:{action}:{device['path']}", f"{label} · {device['name']}",
                    "action", f"{state} · {kind}{strength}", detail, True).as_dict())
        return rows

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
        return [_status("bluetooth.state", "Adapter", "use async BlueZ snapshot")]

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

    def _performance_settings(self) -> list[SystemSetting]:
        mode = SettingsStore(PATHS.config_root / "settings.sqlite3").get(
            "statistics_overlay_mode"
        )
        labels = {"off": "Off", "fps": "FPS Only", "minimal": "Minimal", "detailed": "Detailed"}
        selected = labels.get(mode, "Off")
        return [SystemSetting(
            "statistics-overlay:mode", "Statistics Overlay", "action", selected,
            "Press A to cycle. Applies to subsequent Mudos-launched games with MangoHud support.", True,
        )]
