"""BlueZ D-Bus boundary for controller-first Bluetooth Settings.

BlueZ owns adapters, discovery and device state. This module deliberately
contains no device allowlist and never shells out to bluetoothctl.
"""

from __future__ import annotations

import asyncio
from typing import Any

from dbus_next import BusType, Variant
from dbus_next.aio import MessageBus
from dbus_next.service import ServiceInterface, method

BLUEZ = "org.bluez"
OM = "org.freedesktop.DBus.ObjectManager"
PROPERTIES = "org.freedesktop.DBus.Properties"


def _value(value: Any) -> Any:
    return value.value if isinstance(value, Variant) else value


class BluezClient:
    """Short-lived native D-Bus client; each call observes current BlueZ state."""

    def __init__(self, bus_factory=None, timeout: float = 8.0) -> None:
        self.bus_factory = bus_factory or (lambda: MessageBus(bus_type=BusType.SYSTEM))
        self.timeout = timeout
        self.agent: MudosPairingAgent | None = None
        self._discovery_bus = None
        self._discovery_interface = None

    async def _managed(self):
        bus = await asyncio.wait_for(self.bus_factory().connect(), self.timeout)
        try:
            introspection = await bus.introspect(BLUEZ, "/")
            obj = bus.get_proxy_object(BLUEZ, "/", introspection)
            manager = obj.get_interface(OM)
            return bus, await asyncio.wait_for(manager.call_get_managed_objects(), self.timeout)
        except BaseException:
            bus.disconnect()
            raise

    async def snapshot(self) -> dict[str, Any]:
        try:
            bus, objects = await self._managed()
        except Exception as error:
            return {"available": False, "error": str(error), "adapters": [], "devices": []}
        try:
            adapters: list[dict[str, Any]] = []
            devices: list[dict[str, Any]] = []
            for path, interfaces in objects.items():
                if "org.bluez.Adapter1" in interfaces:
                    raw = {key: _value(value) for key, value in interfaces["org.bluez.Adapter1"].items()}
                    adapters.append({"path": str(path), "address": raw.get("Address", ""),
                                     "name": raw.get("Alias") or raw.get("Name", "Bluetooth adapter"),
                                     "powered": bool(raw.get("Powered", False)),
                                     "discovering": bool(raw.get("Discovering", False))})
                if "org.bluez.Device1" in interfaces:
                    raw = {key: _value(value) for key, value in interfaces["org.bluez.Device1"].items()}
                    devices.append({
                        "path": str(path), "address": raw.get("Address", ""),
                        "name": raw.get("Alias") or raw.get("Name") or raw.get("Address", "Unknown device"),
                        "paired": bool(raw.get("Paired", False)), "trusted": bool(raw.get("Trusted", False)),
                        "connected": bool(raw.get("Connected", False)),
                        "class": int(raw.get("Class", 0) or 0), "icon": str(raw.get("Icon", "")),
                        "rssi": raw.get("RSSI"), "adapter": str(raw.get("Adapter", "")),
                    })
            adapters.sort(key=lambda item: item["path"])
            devices.sort(key=lambda item: (not item["paired"], item["name"].casefold(), item["path"]))
            return {"available": bool(adapters), "error": "" if adapters else "No Bluetooth adapter",
                    "adapters": adapters, "devices": devices,
                    "pairing_prompts": self.agent.prompts[:] if self.agent else []}
        finally:
            bus.disconnect()

    async def _call(self, path: str, interface: str, method: str, *args: Any) -> Any:
        bus = await asyncio.wait_for(self.bus_factory().connect(), self.timeout)
        try:
            intro = await asyncio.wait_for(bus.introspect(BLUEZ, path), self.timeout)
            proxy = bus.get_proxy_object(BLUEZ, path, intro).get_interface(interface)
            return await asyncio.wait_for(getattr(proxy, method)(*args), self.timeout)
        finally:
            bus.disconnect()

    async def mutate(self, action: str, path: str = "") -> dict[str, Any]:
        if action in {"pairing-accept", "pairing-reject"}:
            self.pairing_response(action == "pairing-accept", path)
            return await self.snapshot()
        snap = await self.snapshot()
        if not snap["available"]:
            raise RuntimeError("Bluetooth is unavailable")
        adapter = snap["adapters"][0]
        if action in {"enable", "disable", "discover", "stop-discovery"}:
            if action in {"enable", "disable"}:
                await self._call(adapter["path"], PROPERTIES, "call_set",
                                 "org.bluez.Adapter1", "Powered", Variant("b", action == "enable"))
            else:
                if action == "discover":
                    await self._start_discovery(adapter["path"])
                else:
                    await self._stop_discovery(adapter["path"])
        elif action in {"pair", "connect", "disconnect", "forget"}:
            device = next((item for item in snap["devices"] if item["path"] == path), None)
            if not device:
                raise ValueError("Bluetooth device is no longer available")
            if action == "pair":
                await self._pair(path, adapter["path"])
                await self._call(path, PROPERTIES, "call_set", "org.bluez.Device1", "Trusted", Variant("b", True))
            elif action == "connect":
                await self._call(path, "org.bluez.Device1", "call_connect")
            elif action == "disconnect":
                await self._call(path, "org.bluez.Device1", "call_disconnect")
            else:
                await self._call(adapter["path"], "org.bluez.Adapter1", "call_remove_device", path)
        else:
            raise ValueError("Unknown Bluetooth action")
        return await self.snapshot()

    async def _start_discovery(self, adapter_path: str) -> None:
        # BlueZ ties discovery to the D-Bus owner which requested it. Keep this
        # connection alive so the radio does not stop scanning after a method
        # helper disconnects.
        if self._discovery_interface is not None:
            return
        bus = await asyncio.wait_for(self.bus_factory().connect(), self.timeout)
        try:
            intro = await bus.introspect(BLUEZ, adapter_path)
            interface = bus.get_proxy_object(BLUEZ, adapter_path, intro).get_interface("org.bluez.Adapter1")
            await asyncio.wait_for(interface.call_start_discovery(), self.timeout)
            self._discovery_bus, self._discovery_interface = bus, interface
        except BaseException:
            bus.disconnect()
            raise

    async def _stop_discovery(self, adapter_path: str) -> None:
        if self._discovery_interface is not None:
            try:
                await asyncio.wait_for(self._discovery_interface.call_stop_discovery(), self.timeout)
            finally:
                self._discovery_bus.disconnect()
                self._discovery_bus = None
                self._discovery_interface = None
            return
        # Discovery can have been started outside Mudos. BlueZ only allows a
        # caller to stop its own session; in that case refresh reports state
        # accurately and the external owner remains untouched.
        raise RuntimeError("Bluetooth discovery is owned by another client")

    def pairing_response(self, accepted: bool, value: str = "") -> None:
        if self.agent is None:
            raise RuntimeError("No Bluetooth pairing is active")
        self.agent.respond(accepted, value)

    async def _pair(self, device_path: str, adapter_path: str) -> None:
        """Register Mudos' interactive BlueZ agent for this pairing attempt."""
        bus = await asyncio.wait_for(self.bus_factory().connect(), self.timeout)
        agent = MudosPairingAgent()
        self.agent = agent
        manager = None
        try:
            manager_intro = await bus.introspect(BLUEZ, "/org/bluez")
            manager_obj = bus.get_proxy_object(BLUEZ, "/org/bluez", manager_intro)
            manager = manager_obj.get_interface("org.bluez.AgentManager1")
            bus.export("/org/lulu/BluetoothAgent", agent)
            await manager.call_register_agent("/org/lulu/BluetoothAgent", "KeyboardDisplay")
            await manager.call_request_default_agent("/org/lulu/BluetoothAgent")
            device_intro = await bus.introspect(BLUEZ, device_path)
            device = bus.get_proxy_object(BLUEZ, device_path, device_intro).get_interface("org.bluez.Device1")
            await asyncio.wait_for(device.call_pair(), self.timeout * 10)
        finally:
            try:
                await manager.call_unregister_agent("/org/lulu/BluetoothAgent")
            except Exception:
                pass
            self.agent = None
            bus.disconnect()


class MudosPairingAgent(ServiceInterface):
    """Pairing callbacks require explicit console confirmation for comparisons."""

    def __init__(self) -> None:
        super().__init__("org.bluez.Agent1")
        self.prompts: list[dict[str, Any]] = []
        self._response: asyncio.Future | None = None

    async def _ask(self, kind: str, device: str, message: str, *, number: int | None = None,
                   needs_text: bool = False) -> Any:
        loop = asyncio.get_running_loop()
        self._response = loop.create_future()
        self.prompts[:] = [{"kind": kind, "device": device, "message": message,
                            "number": number, "needs_text": needs_text}]
        try:
            return await asyncio.wait_for(self._response, 90)
        finally:
            self.prompts.clear()
            self._response = None

    def respond(self, accepted: bool, value: str = "") -> None:
        if self._response is None or self._response.done():
            raise RuntimeError("No Bluetooth pairing prompt is pending")
        if not accepted:
            self._response.set_exception(RuntimeError("Pairing rejected by user"))
        else:
            self._response.set_result(value)

    @method()
    def Release(self) -> "":
        return

    @method()
    def Cancel(self) -> "":
        if self._response is not None and not self._response.done():
            self._response.set_exception(RuntimeError("Remote cancelled pairing"))

    @method()
    async def RequestConfirmation(self, device: "o", passkey: "u") -> "":
        await self._ask("confirm", device, f"Confirm the displayed code {passkey}", number=passkey)

    @method()
    async def RequestAuthorization(self, device: "o") -> "":
        await self._ask("authorize", device, "Allow this device to pair?")

    @method()
    async def AuthorizeService(self, device: "o", uuid: "s") -> "":
        await self._ask("service", device, f"Allow Bluetooth service {uuid}?")

    @method()
    async def DisplayPasskey(self, device: "o", passkey: "u", entered: "q") -> "":
        self.prompts[:] = [{"kind": "display", "device": device,
                            "message": f"Enter this code on the other device: {passkey}",
                            "number": passkey, "needs_text": False}]

    @method()
    async def DisplayPinCode(self, device: "o", pincode: "s") -> "":
        self.prompts[:] = [{"kind": "display", "device": device,
                            "message": f"Enter this PIN on the other device: {pincode}",
                            "number": None, "needs_text": False}]

    @method()
    async def RequestPinCode(self, device: "o") -> "s":
        value = str(await self._ask("pin", device, "Enter the requested PIN code", needs_text=True))
        if not value or len(value) > 16:
            raise RuntimeError("Invalid Bluetooth PIN")
        return value

    @method()
    async def RequestPasskey(self, device: "o") -> "u":
        value = await self._ask("passkey", device, "Enter the requested numeric passkey", needs_text=True)
        if not str(value).isdigit() or len(str(value)) > 6:
            raise RuntimeError("Invalid Bluetooth passkey")
        return int(value)
