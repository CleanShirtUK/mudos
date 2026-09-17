"""UDisks2-backed physical storage and Mudos content-target boundary."""

from __future__ import annotations

import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Any

from dbus_next import BusType, Variant
from dbus_next.aio import MessageBus

LOGGER = logging.getLogger("lulu.storage-manager")
UDISKS = "org.freedesktop.UDisks2"
ROOT = "/org/freedesktop/UDisks2"
MANAGER_PATH = f"{ROOT}/Manager"
MANAGER = f"{UDISKS}.Manager"
BLOCK = f"{UDISKS}.Block"
DRIVE = f"{UDISKS}.Drive"
FILESYSTEM = f"{UDISKS}.Filesystem"
PROPERTIES = "org.freedesktop.DBus.Properties"


def _unwrap(value: Any) -> Any:
    if isinstance(value, Variant):
        return _unwrap(value.value)
    if isinstance(value, dict):
        return {key: _unwrap(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_unwrap(item) for item in value]
    return value


class StorageManagerAdapter:
    """UDisks2 owns device identity, filesystem state, and mount operations."""

    def __init__(self, bus: MessageBus | None = None, state_path: Path | None = None) -> None:
        self.bus = bus
        self.manager: Any = None
        self._objects: dict[str, Any] = {}
        config = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "lulu"
        self.state_path = state_path or config / "storage-targets.json"

    async def connect(self) -> None:
        self.bus = self.bus or await MessageBus(bus_type=BusType.SYSTEM).connect()
        intro = await self.bus.introspect(UDISKS, MANAGER_PATH)
        self.manager = self.bus.get_proxy_object(UDISKS, MANAGER_PATH, intro).get_interface(MANAGER)

    async def _interface(self, path: str, interface: str) -> Any:
        if self.bus is None:
            raise RuntimeError("UDisks2 is not connected")
        key = f"{path}:{interface}"
        if key not in self._objects:
            intro = await self.bus.introspect(UDISKS, path)
            self._objects[key] = self.bus.get_proxy_object(UDISKS, path, intro).get_interface(interface)
        return self._objects[key]

    async def _props(self, path: str, interface: str) -> dict[str, Any]:
        props = await self._interface(path, PROPERTIES)
        return _unwrap(await props.call_get_all(interface))

    @staticmethod
    def _mount_points(value: Any) -> list[str]:
        result = []
        for item in value or []:
            if isinstance(item, (bytes, bytearray)):
                result.append(bytes(item).rstrip(b"\0").decode(errors="replace"))
            elif isinstance(item, (list, tuple)):
                result.append(bytes(item).rstrip(b"\0").decode(errors="replace"))
        return [item for item in result if item]

    def _targets(self) -> dict[str, str]:
        try:
            value = json.loads(self.state_path.read_text())
            return {key: str(item) for key, item in value.items() if key in {"game", "emulation"} and item}
        except (OSError, ValueError, json.JSONDecodeError):
            return {}

    def _save_targets(self, targets: dict[str, str]) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(json.dumps(targets, sort_keys=True) + "\n")

    async def _devices(self) -> list[dict[str, Any]]:
        if self.manager is None:
            await self.connect()
        paths = await self.manager.call_get_block_devices({})
        root_device = os.stat("/").st_dev
        devices = []
        for path in paths:
            try:
                block = await self._props(path, BLOCK)
                if not block.get("IdUsage") or block.get("HintIgnore"):
                    continue
                device_number = int(block.get("DeviceNumber", -1))
                filesystem = await self._props(path, FILESYSTEM)
                mount_points = self._mount_points(filesystem.get("MountPoints"))
                protected = device_number == root_device or bool(block.get("HintSystem"))
                drive_path = str(block.get("Drive", "/"))
                drive = await self._props(drive_path, DRIVE) if drive_path != "/" else {}
                uuid = str(block.get("IdUUID", ""))
                if not uuid:
                    continue
                size = int(block.get("Size", 0))
                free = None
                if mount_points:
                    try:
                        usage = os.statvfs(mount_points[0])
                        free = usage.f_bavail * usage.f_frsize
                    except OSError:
                        pass
                removable = bool(drive.get("Removable", False) or block.get("HintRemovable", False))
                devices.append({
                    "id": uuid, "name": str(block.get("IdLabel") or drive.get("Id", "") or uuid),
                    "label": str(block.get("IdLabel", "")), "filesystem": str(block.get("IdType", "")),
                    "capacity": size, "free": free, "mounted": bool(mount_points),
                    "mount_point": mount_points[0] if mount_points else "", "removable": removable,
                    "system": protected, "read_only": bool(block.get("ReadOnly", False)),
                    "available": True, "bus": str(drive.get("ConnectionBus", "")),
                    "object_path": path,
                })
            except Exception:
                LOGGER.debug("ignoring unreadable UDisks block device %s", path, exc_info=True)
        return devices

    async def snapshot(self) -> dict[str, Any]:
        base = {"available": False, "devices": [], "targets": {"game": None, "emulation": None},
                "error": "UDisks2 unavailable"}
        try:
            devices = await self._devices()
            targets = self._targets()
            by_id = {item["id"]: item for item in devices}
            target_state = {}
            for kind in ("game", "emulation"):
                selected = by_id.get(targets.get(kind, ""))
                target_state[kind] = selected | {"configured": True, "available": bool(selected.get("mounted"))} if selected else (
                    {"id": targets[kind], "available": False, "configured": True} if kind in targets else None)
                if selected and selected.get("mount_point"):
                    targets[f"{kind}_path"] = selected["mount_point"]
            if targets != self._targets():
                self._save_targets(targets)
            for device in devices:
                device["game_target"] = device["id"] == targets.get("game")
                device["emulation_target"] = device["id"] == targets.get("emulation")
            return {"available": True, "devices": devices, "targets": target_state, "error": ""}
        except Exception as error:
            LOGGER.warning("UDisks2 snapshot failed: %s", error)
            return base | {"error": str(error)}

    async def _find(self, device_id: str) -> tuple[str, dict[str, Any]]:
        for item in await self._devices():
            if item["id"] == device_id:
                return item["object_path"], item
        raise ValueError("storage device is unavailable")

    async def mount(self, device_id: str) -> dict[str, Any]:
        path, item = await self._find(device_id)
        if item["system"] or item["read_only"]:
            return (await self.snapshot()) | {"error": "protected or read-only storage"}
        await (await self._interface(path, FILESYSTEM)).call_mount({})
        return await self.snapshot()

    async def unmount(self, device_id: str) -> dict[str, Any]:
        path, item = await self._find(device_id)
        if item["system"]:
            return (await self.snapshot()) | {"error": "system storage cannot be unmounted"}
        await (await self._interface(path, FILESYSTEM)).call_unmount({})
        return await self.snapshot()

    async def eject(self, device_id: str) -> dict[str, Any]:
        path, item = await self._find(device_id)
        if item["system"] or not item["removable"]:
            return (await self.snapshot()) | {"error": "only removable storage can be ejected"}
        drive_path = (await self._props(path, BLOCK)).get("Drive", "/")
        if drive_path == "/":
            raise ValueError("storage drive is unavailable")
        await (await self._interface(drive_path, DRIVE)).call_power_off({})
        return await self.snapshot()

    async def select_target(self, kind: str, device_id: str) -> dict[str, Any]:
        if kind not in {"game", "emulation"}:
            raise ValueError("unknown storage target")
        if not device_id:
            targets = self._targets()
            targets.pop(kind, None)
            try:
                state = json.loads(self.state_path.read_text())
                state.pop(f"{kind}_path", None)
                state.pop(kind, None)
                self.state_path.write_text(json.dumps(state, sort_keys=True) + "\n")
            except (OSError, ValueError, json.JSONDecodeError):
                pass
            return await self.snapshot()
        _, item = await self._find(device_id)
        if item["system"] or item["read_only"] or not item["mounted"]:
            return (await self.snapshot()) | {"error": "target must be mounted and writable"}
        root = Path(item["mount_point"]) / "Mudos"
        for directory in ((root / "Executables/steam"), (root / "Executables/lutris"),
                          (root / "Executables/native"), root / "ROMs", root / "BIOS"):
            directory.mkdir(parents=True, exist_ok=True)
        targets = self._targets()
        targets[kind] = device_id
        targets[f"{kind}_path"] = str(item["mount_point"])
        self._save_targets(targets)
        return await self.snapshot()
