import asyncio
import unittest
from unittest.mock import AsyncMock

from lulu.bluetooth import BluezClient, MudosPairingAgent
from lulu.system_settings import SystemSettingsProvider


class BluetoothTests(unittest.TestCase):
    def test_settings_project_adapter_and_device_state_truthfully(self):
        class Bluez:
            async def snapshot(self):
                return {"available": True, "error": "", "pairing_prompts": [],
                        "adapters": [{"name": "Adapter", "address": "adapter-id",
                                      "powered": True, "discovering": True}],
                        "devices": [{"path": "/org/bluez/hci0/dev_a", "name": "Nearby",
                                     "paired": False, "trusted": False, "connected": False,
                                     "class": 0, "icon": "input-gaming", "rssi": -44},
                                    {"path": "/org/bluez/hci0/dev_b", "name": "Reconnected",
                                     "paired": True, "trusted": True, "connected": False,
                                     "class": 0, "icon": "audio-card", "rssi": None}]}

        rows = asyncio.run(SystemSettingsProvider(Bluez()).list_settings_async("Bluetooth"))
        by_key = {row["key"]: row for row in rows}
        self.assertEqual(by_key["bluetooth.state"]["value"], "on")
        self.assertIn("adapter-id", by_key["bluetooth.state"]["detail"])
        self.assertEqual(by_key["bluetooth:stop-discovery"]["label"], "Stop discovery")
        self.assertIn("Not trusted", by_key["bluetooth:pair:/org/bluez/hci0/dev_a"]["detail"])
        self.assertIn("Paired", by_key["bluetooth:connect:/org/bluez/hci0/dev_b"]["value"])
        self.assertIn("Trusted", by_key["bluetooth:connect:/org/bluez/hci0/dev_b"]["detail"])
        self.assertIn("RSSI -44", by_key["bluetooth:pair:/org/bluez/hci0/dev_a"]["value"])

    def test_adapter_missing_and_off_are_distinct(self):
        class Bluez:
            def __init__(self, snap): self.snap = snap
            async def snapshot(self): return self.snap

        unavailable = asyncio.run(SystemSettingsProvider(Bluez({
            "available": False, "error": "No Bluetooth adapter", "adapters": [],
            "devices": [], "pairing_prompts": []})).list_settings_async("Bluetooth"))
        off = asyncio.run(SystemSettingsProvider(Bluez({
            "available": True, "error": "", "adapters": [{"name": "a", "address": "b",
            "powered": False, "discovering": False}], "devices": [], "pairing_prompts": []
        })).list_settings_async("Bluetooth"))
        self.assertEqual(unavailable[0]["value"], "unavailable")
        self.assertEqual(off[0]["value"], "off")
        self.assertEqual(off[1]["key"], "bluetooth:enable")

    def test_action_dispatch_covers_device_mutations_and_trust_after_pair(self):
        async def exercise():
            client = BluezClient()
            client.snapshot = AsyncMock(return_value={"available": True,
                "adapters": [{"path": "/adapter"}],
                "devices": [{"path": "/device", "paired": False}]})
            client._call = AsyncMock(return_value=None)
            client._pair = AsyncMock(return_value=None)
            await client.mutate("pair", "/device")
            client._pair.assert_awaited_once_with("/device", "/adapter")
            client._call.assert_awaited_once()
            self.assertEqual(client._call.await_args.args[1], "org.freedesktop.DBus.Properties")
            client._call.reset_mock()
            for action, method in (("connect", "call_connect"), ("disconnect", "call_disconnect")):
                client._call.reset_mock()
                await client.mutate(action, "/device")
                client._call.assert_awaited_once_with("/device", "org.bluez.Device1", method)
            client._call.reset_mock()
            await client.mutate("forget", "/device")
            client._call.assert_awaited_once_with("/adapter", "org.bluez.Adapter1",
                                                  "call_remove_device", "/device")
        asyncio.run(exercise())

    def test_power_mutations_and_discovery_keep_the_same_dbus_owner(self):
        class Interface:
            def __init__(self): self.started = 0; self.stopped = 0
            async def call_start_discovery(self): self.started += 1
            async def call_stop_discovery(self): self.stopped += 1
        class Proxy:
            def __init__(self, interface): self.interface = interface
            def get_interface(self, _name): return self.interface
        class Bus:
            def __init__(self): self.interface = Interface(); self.disconnected = False
            async def connect(self): return self
            async def introspect(self, *_args): return object()
            def get_proxy_object(self, *_args): return Proxy(self.interface)
            def disconnect(self): self.disconnected = True
        async def exercise():
            bus = Bus()
            client = BluezClient(bus_factory=lambda: bus)
            client.snapshot = AsyncMock(return_value={"available": True,
                "adapters": [{"path": "/adapter"}], "devices": []})
            client._call = AsyncMock(return_value=None)
            await client.mutate("enable")
            self.assertEqual(client._call.await_args.args[2], "call_set")
            await client.mutate("discover")
            self.assertIs(client._discovery_bus, bus)
            self.assertFalse(bus.disconnected)
            await client.mutate("stop-discovery")
            self.assertEqual(bus.interface.started, 1)
            self.assertEqual(bus.interface.stopped, 1)
            self.assertTrue(bus.disconnected)
        asyncio.run(exercise())

    def test_pairing_confirmation_waits_for_explicit_user_response(self):
        async def exercise():
            agent = MudosPairingAgent()
            task = asyncio.create_task(MudosPairingAgent.RequestConfirmation.__wrapped__(
                agent, "/device", 123456))
            await asyncio.sleep(0)
            self.assertEqual(agent.prompts[0]["kind"], "confirm")
            self.assertFalse(task.done())
            agent.respond(True)
            await task
            self.assertEqual(agent.prompts, [])
        asyncio.run(exercise())

    def test_pairing_rejection_and_timeout_propagate(self):
        async def exercise():
            agent = MudosPairingAgent()
            task = asyncio.create_task(agent._ask("authorize", "/device", "Allow?"))
            await asyncio.sleep(0)
            agent.respond(False)
            with self.assertRaisesRegex(RuntimeError, "rejected"):
                await task
            with self.assertRaisesRegex(RuntimeError, "No Bluetooth pairing"):
                BluezClient().pairing_response(True)
        asyncio.run(exercise())

    def test_pairing_passkey_is_requested_through_explicit_controller_response(self):
        async def exercise():
            agent = MudosPairingAgent()
            task = asyncio.create_task(MudosPairingAgent.RequestPasskey.__wrapped__(agent, "/device"))
            await asyncio.sleep(0)
            self.assertTrue(agent.prompts[0]["needs_text"])
            agent.respond(True, "012345")
            self.assertEqual(await task, 12345)
            task = asyncio.create_task(MudosPairingAgent.RequestPinCode.__wrapped__(agent, "/device"))
            await asyncio.sleep(0)
            agent.respond(True, "1234")
            self.assertEqual(await task, "1234")
        asyncio.run(exercise())

    def test_hotplug_and_service_loss_are_graceful(self):
        class Bluez:
            def __init__(self): self.snap = {"available": False, "error": "BlueZ unavailable",
                                             "adapters": [], "devices": [], "pairing_prompts": []}
            async def snapshot(self): return self.snap
        bluez = Bluez()
        provider = SystemSettingsProvider(bluez)
        self.assertEqual(asyncio.run(provider.list_settings_async("Bluetooth"))[0]["value"], "unavailable")
        bluez.snap = {"available": True, "error": "", "adapters": [{"name": "hci0",
                    "address": "x", "powered": True, "discovering": False}],
                    "devices": [], "pairing_prompts": []}
        self.assertEqual(asyncio.run(provider.list_settings_async("Bluetooth"))[0]["value"], "on")

    def test_settings_refresh_preserves_selected_row_identity_and_status_is_live_bluez(self):
        from pathlib import Path
        root = Path(__file__).parents[1]
        qml = (root / "ui/ConsoleShell.qml").read_text()
        native = (root / "native/lulu-shell.cpp").read_text()
        self.assertIn("var selectedKey = systemSettings[systemRowIndex]", qml)
        self.assertIn('data[index].key === selectedKey', qml)
        self.assertIn('InterfacesAdded', native)
        self.assertIn('InterfacesRemoved', native)
        self.assertIn('QStringLiteral("connected")', native)
        self.assertIn('activateBluetoothSetting(systemSettings[systemRowIndex].key)', qml)
        self.assertIn('request("/keyboard/show"', qml)


if __name__ == "__main__":
    unittest.main()
