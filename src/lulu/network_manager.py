"""Small normalized NetworkManager D-Bus adapter for the Mudos settings UI."""

from __future__ import annotations

import logging
from typing import Any

from dbus_next import BusType, Variant
from dbus_next.aio import MessageBus


LOGGER = logging.getLogger("lulu.network-manager")
NM = "org.freedesktop.NetworkManager"
NM_PATH = "/org/freedesktop/NetworkManager"
DEVICE = "org.freedesktop.NetworkManager.Device"
WIFI = "org.freedesktop.NetworkManager.Device.Wireless"
AP = "org.freedesktop.NetworkManager.AccessPoint"
PROPERTIES = "org.freedesktop.DBus.Properties"


def _unwrap(value: Any) -> Any:
    if isinstance(value, Variant):
        return _unwrap(value.value)
    if isinstance(value, dict):
        return {key: _unwrap(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_unwrap(item) for item in value]
    return value


def _ssid(value: Any) -> str:
    raw = bytes(value or [])
    return raw.decode("utf-8", errors="replace").strip("\x00")


class NetworkManagerAdapter:
    """NetworkManager owns all network state, profiles, and secrets."""

    def __init__(self) -> None:
        self.bus: MessageBus | None = None
        self.nm: Any = None
        self.settings: Any = None
        self._objects: dict[str, Any] = {}

    async def connect(self) -> None:
        self.bus = await MessageBus(bus_type=BusType.SYSTEM).connect()
        nm_intro = await self.bus.introspect(NM, NM_PATH)
        nm_obj = self.bus.get_proxy_object(NM, NM_PATH, nm_intro)
        self.nm = nm_obj.get_interface(NM)
        settings_path = "/org/freedesktop/NetworkManager/Settings"
        settings_intro = await self.bus.introspect(NM, settings_path)
        settings_obj = self.bus.get_proxy_object(NM, settings_path, settings_intro)
        self.settings = settings_obj.get_interface(f"{NM}.Settings")

    async def _interface(self, path: str, interface: str) -> Any:
        if self.bus is None:
            raise RuntimeError("NetworkManager is not connected")
        key = f"{path}:{interface}"
        if key not in self._objects:
            intro = await self.bus.introspect(NM, path)
            obj = self.bus.get_proxy_object(NM, path, intro)
            self._objects[key] = obj.get_interface(interface)
        return self._objects[key]

    async def _props(self, path: str, interface: str) -> dict[str, Any]:
        props = await self._interface(path, PROPERTIES)
        return _unwrap(await props.call_get_all(interface))

    async def _property(self, path: str, interface: str, name: str) -> Any:
        props = await self._interface(path, PROPERTIES)
        return _unwrap(await props.call_get(interface, name))

    async def _wifi_device(self) -> tuple[str, Any] | None:
        for path in await self.nm.call_get_devices():
            if int(await self._property(path, DEVICE, "DeviceType")) != 2:
                continue
            return path, await self._interface(path, WIFI)
        return None

    async def _profiles(self) -> list[dict[str, Any]]:
        result = []
        for path in await self.settings.call_list_connections():
            try:
                connection = await self._interface(path, f"{NM}.Settings.Connection")
                settings = _unwrap(await connection.call_get_settings())
                wireless = settings.get("802-11-wireless", {})
                if settings.get("connection", {}).get("type") != "802-11-wireless":
                    continue
                result.append({
                    "path": path,
                    "ssid": _ssid(wireless.get("ssid", [])),
                    "id": settings.get("connection", {}).get("id", ""),
                })
            except Exception:
                LOGGER.debug("ignoring unreadable NetworkManager profile %s", path, exc_info=True)
        return result

    async def snapshot(self) -> dict[str, Any]:
        base = {"available": False, "wifi_available": False, "online": False,
                "wifi_enabled": False, "state": "unavailable",
                "current": None, "networks": [], "error": "NetworkManager unavailable"}
        try:
            if self.nm is None:
                await self.connect()
            enabled = bool(await self._property(NM_PATH, NM, "WirelessEnabled"))
            state_code = int(await self._property(NM_PATH, NM, "State"))
            try:
                connectivity = int(await self._property(NM_PATH, NM, "Connectivity"))
            except Exception:
                connectivity = 4 if state_code == 70 else 1
            wifi = await self._wifi_device()
            profiles = await self._profiles()
            known = {item["ssid"] for item in profiles if item["ssid"]}
            current = None
            networks = []
            if wifi and enabled:
                device_path, wifi_iface = wifi
                device_props = await self._props(device_path, DEVICE)
                active_path = device_props.get("ActiveConnection", "/")
                if active_path != "/":
                    active = await self._props(active_path, f"{NM}.Connection.Active")
                    current = {"ssid": active.get("Id", ""), "state": "connected",
                               "interface": device_props.get("Interface", "")}
                for ap_path in await wifi_iface.call_get_all_access_points():
                    props = await self._props(ap_path, AP)
                    ssid = _ssid(props.get("Ssid", []))
                    if not ssid:
                        continue
                    security = int(props.get("WpaFlags", 0)) or int(props.get("RsnFlags", 0))
                    networks.append({"ssid": ssid, "strength": int(props.get("Strength", 0)),
                                     "secured": bool(security), "security": "secured" if security else "open",
                                     "connected": bool(current and current["ssid"] == ssid),
                                     "known": ssid in known})
            networks.sort(key=lambda item: (-item["strength"], item["ssid"]))
            state = "connected" if current else "disconnected" if enabled else "disabled"
            return {"available": True, "wifi_available": bool(wifi),
                    "online": connectivity == 4, "wifi_enabled": enabled, "state": state,
                    "current": current, "networks": networks, "known": sorted(known),
                    "error": ""}
        except Exception as error:
            LOGGER.warning("NetworkManager snapshot failed: %s", error)
            return base | {"wifi_available": False, "online": False, "error": str(error)}

    async def scan(self) -> dict[str, Any]:
        """Request an access-point scan through NetworkManager."""
        try:
            if self.nm is None:
                await self.connect()
            wifi = await self._wifi_device()
            if wifi is not None:
                await wifi[1].call_request_scan({})
            return await self.snapshot()
        except Exception as error:
            return {"ok": False, "error": str(error)}

    async def set_enabled(self, enabled: bool) -> dict[str, Any]:
        try:
            if self.nm is None:
                await self.connect()
            await (await self._interface(NM_PATH, PROPERTIES)).call_set(
                NM, "WirelessEnabled", Variant("b", enabled))
            return await self.snapshot()
        except Exception as error:
            return {"ok": False, "error": str(error)}

    async def disconnect(self) -> dict[str, Any]:
        try:
            if self.nm is None:
                await self.connect()
            wifi = await self._wifi_device()
            if not wifi:
                return {"ok": False, "error": "No Wi-Fi adapter"}
            await (await self._interface(wifi[0], DEVICE)).call_disconnect()
            return await self.snapshot()
        except Exception as error:
            return {"ok": False, "error": str(error)}

    async def forget(self, ssid: str) -> dict[str, Any]:
        try:
            if self.nm is None:
                await self.connect()
            for profile in await self._profiles():
                if profile["ssid"] == ssid:
                    await (await self._interface(profile["path"], f"{NM}.Settings.Connection")).call_delete()
                    return await self.snapshot()
            return {"ok": False, "error": "Network is not saved"}
        except Exception as error:
            return {"ok": False, "error": str(error)}

    async def connect_network(self, ssid: str, password: str = "") -> dict[str, Any]:
        try:
            if self.nm is None:
                await self.connect()
            wifi = await self._wifi_device()
            if not wifi:
                return {"ok": False, "error": "No Wi-Fi adapter"}
            device_path = wifi[0]
            profile = next((item for item in await self._profiles() if item["ssid"] == ssid), None)
            if profile and not password:
                active = await self.nm.call_activate_connection(profile["path"], device_path, "/")
            else:
                settings: dict[str, dict[str, Variant]] = {
                    "connection": {"id": Variant("s", ssid), "type": Variant("s", "802-11-wireless")},
                    "802-11-wireless": {"ssid": Variant("ay", ssid.encode())},
                }
                if password:
                    settings["802-11-wireless-security"] = {
                        "key-mgmt": Variant("s", "wpa-psk"), "psk": Variant("s", password)}
                active = await self.nm.call_add_and_activate_connection(settings, device_path, "/")
            LOGGER.info("NetworkManager connection requested ssid=%s active=%s", ssid, active)
            return (await self.snapshot()) | {"connecting": True}
        except Exception as error:
            LOGGER.warning("NetworkManager connection failed ssid=%s: %s", ssid, error)
            return {"ok": False, "error": str(error)}
