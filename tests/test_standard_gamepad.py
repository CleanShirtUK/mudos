import tempfile
import unittest
import importlib.util
import sqlite3
from pathlib import Path

from lulu.controllerd import Controller, ControllerRegistry
from lulu.controller_provisioning import (
    ensure_provider_controller_config,
    ensure_retroarch_autoconfig,
)
from lulu.inputplumber import associate_sdl_targets, normalized_controller_identity
from lulu.switch_provider import SwitchProvider


class StandardGamepadTests(unittest.TestCase):
    def test_native_face_button_profiles_preserve_identity(self) -> None:
        from lulu.controller_provisioning import _pcsx2_values, _dolphin_values
        pcsx2 = _pcsx2_values(0)
        self.assertEqual(pcsx2["Cross"], "SDL-0/FaceSouth")
        self.assertEqual(pcsx2["Circle"], "SDL-0/FaceEast")
        self.assertEqual(pcsx2["Square"], "SDL-0/FaceWest")
        self.assertEqual(pcsx2["Triangle"], "SDL-0/FaceNorth")
        dolphin = _dolphin_values("SDL Gamepad", 0)
        self.assertEqual(dolphin["Buttons/A"], "`Button A`")
        self.assertEqual(dolphin["Buttons/B"], "`Button B`")
        self.assertEqual(dolphin["Buttons/X"], "`Button X`")
        self.assertEqual(dolphin["Buttons/Y"], "`Button Y`")

    def test_legacy_true_layout_setting_cannot_change_generated_profiles(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            legacy_db = sqlite3.connect(root / "settings.sqlite3")
            legacy_db.execute(
                "CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)",
            )
            legacy_db.execute(
                "INSERT INTO settings VALUES (?, ?)",
                ("controllers.nintendo_button_layout", "true"),
            )
            legacy_db.commit()
            legacy_db.close()

            pcsx2 = ensure_provider_controller_config("pcsx2", root, 1, {1: 0}).read_text()
            dolphin = ensure_provider_controller_config("dolphin", root, 1, {1: 0}).read_text()
            retroarch_dir = ensure_retroarch_autoconfig(root)
            retroarch = next(retroarch_dir.glob("*.cfg")).read_text()

        self.assertIn("Cross = SDL-0/FaceSouth", pcsx2)
        self.assertIn("Buttons/A = `Button A`", dolphin)
        self.assertIn('input_a_btn = "1"', retroarch)
        self.assertIn('input_b_btn = "0"', retroarch)
        self.assertIn('input_x_btn = "3"', retroarch)
        self.assertIn('input_y_btn = "2"', retroarch)

    def test_inputplumber_profile_preseeds_live_devices_and_supports_hotplug(self) -> None:
        spec = importlib.util.spec_from_file_location(
            "provision_inputplumber_gamepads",
            Path(__file__).parents[1] / "scripts/provision-inputplumber-gamepads.py",
        )
        self.assertIsNotNone(spec)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)
        content = module.render()
        self.assertNotIn("dev_node: /dev/input/event", content)
        self.assertIn("name: MUDOS_STANDARD_GAMEPAD", content)
        self.assertNotIn("handler: event*", content)
        self.assertNotIn("phys_path:", content)
        self.assertNotIn("vendor_id", content)
        self.assertNotIn("product_id", content)

    def test_virtual_gamepad_hotplug_profile_does_not_require_event_number(self) -> None:
        spec = importlib.util.spec_from_file_location(
            "provision_inputplumber_gamepads_virtual",
            Path(__file__).parents[1] / "scripts/provision-inputplumber-gamepads.py",
        )
        self.assertIsNotNone(spec)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)
        content = module.render()
        self.assertNotIn("dev_node: /dev/input/event", content)
        self.assertIn("MUDOS_STANDARD_GAMEPAD", content)
        self.assertNotIn("phys_path:", content)
        self.assertNotIn("vendor_id", content)
        self.assertNotIn("product_id", content)

    def test_virtual_source_is_distinguished_from_composite_output(self) -> None:
        spec = importlib.util.spec_from_file_location(
            "provision_inputplumber_gamepads_source",
            Path(__file__).parents[1] / "scripts/provision-inputplumber-gamepads.py",
        )
        self.assertIsNotNone(spec)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)
        source = {"ID_INPUT_JOYSTICK=1", "DEVPATH=/devices/virtual/input/input44/event13"}
        output = {"ID_INPUT_JOYSTICK=1", "ID_INPUT_WIDTH_MM=65535"}
        self.assertTrue(module._is_virtual_source(source))
        self.assertFalse(module._is_virtual_source(output))

    def test_sysfs_identity_deduplicates_interfaces_but_keeps_receiver_slots_distinct(self) -> None:
        spec = importlib.util.spec_from_file_location(
            "provision_inputplumber_gamepads_identity",
            Path(__file__).parents[1] / "scripts/provision-inputplumber-gamepads.py",
        )
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        interface_a = "/sys/devices/pci/usb6/6-1/6-1:1.0/input/input1676"
        interface_a_second_event = "/sys/devices/pci/usb6/6-1/6-1:1.0/input/input1676"
        interface_b = "/sys/devices/pci/usb6/6-1/6-1:1.2/input/input1680"
        self.assertEqual(module.logical_device_key(interface_a),
                         module.logical_device_key(interface_a_second_event))
        self.assertNotEqual(module.logical_device_key(interface_a),
                            module.logical_device_key(interface_b))

    def test_sdl_association_filters_unmanaged_physical_pad_between_targets(self) -> None:
        devices = [
            {"sdl_index": 0, "sdl_path": "/dev/input/event10", "inputplumber_target": True},
            {"sdl_index": 1, "sdl_path": "/dev/input/event13", "inputplumber_target": False},
            {"sdl_index": 2, "sdl_path": "/dev/input/event16", "inputplumber_target": True},
        ]
        targets = [
            ("CompositeDevice0", "/devices/target/gamepad0"),
            ("CompositeDevice1", "/devices/target/gamepad1"),
        ]
        self.assertEqual(associate_sdl_targets(targets, devices), {
            "CompositeDevice0": 0,
            "CompositeDevice1": 2,
        })

    def test_sdl_association_refuses_incomplete_target_output_sets(self) -> None:
        self.assertEqual(associate_sdl_targets(
            [("CompositeDevice0", "/devices/target/gamepad0"),
             ("CompositeDevice1", "/devices/target/gamepad1")],
            [{"sdl_index": 0, "inputplumber_target": True}],
        ), {})

    def test_three_pad_inventory_reconciles_duplicate_models_and_renumbered_reconnect(self) -> None:
        targets = [
            ("CompositeDevice0", "/devices/target/gamepad0"),
            ("CompositeDevice1", "/devices/target/gamepad1"),
            ("CompositeDevice2", "/devices/target/gamepad2"),
        ]
        sdl = [
            {"sdl_index": 0, "sdl_instance_id": 40, "sdl_guid": "same-guid",
             "sdl_name": "Xbox 360 Wireless Controller", "sdl_path": "/dev/input/event40",
             "inputplumber_target": True},
            {"sdl_index": 1, "sdl_instance_id": 41, "sdl_guid": "series-guid",
             "sdl_name": "Xbox Series Controller", "sdl_path": "/dev/input/event41",
             "inputplumber_target": True},
            {"sdl_index": 2, "sdl_instance_id": 42, "sdl_guid": "same-guid",
             "sdl_name": "Xbox 360 Wireless Controller", "sdl_path": "/dev/input/event42",
             "inputplumber_target": True},
        ]
        slot_indices = associate_sdl_targets(targets, sdl)
        self.assertEqual(slot_indices, {
            "CompositeDevice0": 0, "CompositeDevice1": 1, "CompositeDevice2": 2,
        })

        registry = ControllerRegistry()
        registry.observe_runtime_composites({
            "CompositeDevice0": ("receiver-slot-a", ("/dev/input/event12",)),
            "CompositeDevice1": ("series-usb", ("/dev/input/event8",)),
            "CompositeDevice2": ("receiver-slot-b", ("/dev/input/event13",)),
        }, slot_indices, {int(pad["sdl_index"]): pad for pad in sdl})
        connected = [pad for pad in registry.controllers.values() if pad.connected]
        self.assertEqual(len(connected), 3)
        self.assertEqual(len({pad.physical_identity for pad in connected}), 3)
        self.assertEqual(registry.navigation_mode, "all")
        self.assertIsNone(registry.navigation_controller_id)

        # One receiver slot drops out: it is no longer counted, while the
        # other identical slot and USB pad retain their own identities.
        registry.observe_runtime_composites({
            "CompositeDevice0": ("receiver-slot-a", ("/dev/input/event12",)),
            "CompositeDevice1": ("series-usb", ("/dev/input/event8",)),
        }, {"CompositeDevice0": 0, "CompositeDevice1": 1},
            {int(pad["sdl_index"]): pad for pad in sdl[:2]})
        self.assertEqual(sum(pad.connected for pad in registry.controllers.values()), 2)

        # The same normalized receiver identity returns on a different event
        # node and runtime handle. No second connected record is created for it.
        registry.observe_runtime_composites({
            "CompositeDevice0": ("receiver-slot-a", ("/dev/input/event28",)),
            "CompositeDevice1": ("series-usb", ("/dev/input/event8",)),
            "CompositeDevice3": ("receiver-slot-b", ("/dev/input/event29",)),
        }, {"CompositeDevice0": 1, "CompositeDevice1": 0, "CompositeDevice3": 2},
            {int(pad["sdl_index"]): pad for pad in sdl})
        connected = [pad for pad in registry.controllers.values() if pad.connected]
        self.assertEqual(len(connected), 3)
        self.assertEqual(len({pad.physical_identity for pad in connected}), 3)
        self.assertEqual(registry.navigation_mode, "all")
        self.assertIsNone(registry.navigation_controller_id)

    def test_hotplug_waits_for_auto_managed_source_without_duplicate_creation(self) -> None:
        spec = importlib.util.spec_from_file_location(
            "provision_inputplumber_gamepads_retry",
            Path(__file__).parents[1] / "scripts/provision-inputplumber-gamepads.py",
        )
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        clock = [0.0]
        active = set()
        def sleep(interval):
            clock[0] += interval

        attempts = [0]

        def probe():
            attempts[0] += 1
            if attempts[0] == 3:
                active.add("/dev/input/event19")
            return set(active)

        connected = module.wait_for_source_composite(
            "/dev/input/event19", probe,
            timeout=2.0, poll_interval=0.1,
            clock=lambda: clock[0], sleep=sleep,
        )
        self.assertTrue(connected)
        self.assertEqual(attempts[0], 3)

    def test_hotplug_activation_does_not_duplicate_inputplumber_auto_manage(self) -> None:
        source = (Path(__file__).parents[1] / "scripts/provision-inputplumber-gamepads.py").read_text()
        activate = source.split("def _activate(", 1)[1].split("\n\ndef main(", 1)[0]
        self.assertIn("wait_for_source_composite(source, active_sources)", activate)
        self.assertNotIn("CreateCompositeDevice", activate)
        self.assertIn("auto_manage: true", source)

    def test_serial_less_receiver_slots_get_stable_distinct_controller_identities(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            first_interface = root / "6-1:1.0"
            second_interface = root / "6-1:1.2"
            first_interface.mkdir()
            second_interface.mkdir()
            (first_interface / "bInterfaceNumber").write_text("00\n")
            (second_interface / "bInterfaceNumber").write_text("02\n")
            first_path = str(first_interface / "input/input100")
            second_path = str(second_interface / "input/input101")
            first = normalized_controller_identity("045e_0291", first_path, False)
            first_again = normalized_controller_identity("045e_0291", first_path, False)
            second = normalized_controller_identity("045e_0291", second_path, False)
        self.assertEqual(first, first_again)
        self.assertNotEqual(first, second)
        # Device-level input uniq values distinguish identical pads behind
        # one receiver even when event nodes are renumbered.
        self.assertEqual(
            normalized_controller_identity("045e_0291", first_path, False, "slot-a"),
            normalized_controller_identity("045e_0291", "/sys/devices/reconnected/input/input9", False,
                                           "slot-a"),
        )
        self.assertNotEqual(
            normalized_controller_identity("045e_0291", first_path, False, "slot-a"),
            normalized_controller_identity("045e_0291", first_path, False, "slot-b"),
        )
        self.assertEqual(
            normalized_controller_identity("serial-bearing-id", first_path, True),
            "serial-bearing-id",
        )
        # BlueZ supplies a persistent peer address even though its UHID sysfs
        # path changes across reconnects; keep that identity stable.
        self.assertEqual(
            normalized_controller_identity(
                "f4:6a:d7:d1:10:f2", "/devices/virtual/uhid/input/input51", False
            ),
            "f4:6a:d7:d1:10:f2",
        )

    def _pad(self, ident: str, name: str, guid: str, index: int) -> Controller:
        return Controller(
            ident, physical_identity=ident, player=index + 1,
            sdl_index=index, sdl_guid=guid, sdl_name=name,
            button_count=17, axis_count=6, connection_type="usb",
        )

    def test_unknown_standard_gamepad_is_eligible_without_identity_allowlist(self) -> None:
        pad = self._pad("new-device", "Unbranded USB Gamepad", "guid-new", 0)
        self.assertTrue(pad.gameplay_eligible)
        registry = ControllerRegistry()
        registry.connect(pad)
        self.assertEqual(registry.controllers["new-device"].player, 1)

    def test_live_inventory_keeps_connection_and_physical_identity_separate(self) -> None:
        registry = ControllerRegistry()
        registry.observe_runtime_composites({
            "CompositeDevice4": ("same-model/slot-a", ("/dev/input/event11",)),
            "CompositeDevice7": ("same-model/slot-b", ("/dev/input/event12",)),
        }, {"CompositeDevice4": 0, "CompositeDevice7": 1})
        first = registry.controllers["CompositeDevice4"]
        second = registry.controllers["CompositeDevice7"]
        self.assertTrue(first.connected and second.connected)
        self.assertNotEqual(first.physical_identity, second.physical_identity)
        self.assertNotEqual(first.connection_identity, second.connection_identity)
        self.assertEqual({first.sdl_index, second.sdl_index}, {0, 1})

        # Node renumbering updates the current connection record without
        # creating another controller or changing physical assignments.
        registry.observe_runtime_composites({
            "CompositeDevice4": ("same-model/slot-a", ("/dev/input/event30",)),
            "CompositeDevice7": ("same-model/slot-b", ("/dev/input/event31",)),
        }, {"CompositeDevice4": 1, "CompositeDevice7": 0})
        self.assertEqual(len([c for c in registry.controllers.values() if c.connected]), 2)
        self.assertEqual(first.physical_identity, "same-model/slot-a")
        self.assertEqual(first.sdl_index, 1)
        self.assertEqual(first.connection_identity, "/dev/input/event30")

        registry.observe_runtime_composites({
            "CompositeDevice7": ("same-model/slot-b", ("/dev/input/event31",)),
        }, {"CompositeDevice7": 0})
        self.assertFalse(first.connected)
        self.assertTrue(second.connected)
        self.assertEqual(len([c for c in registry.controllers.values() if c.connected]), 1)

    def test_heterogeneous_players_keep_independent_live_identities(self) -> None:
        pads = {
            1: self._pad("xbox", "Xbox Series", "guid-xbox", 2),
            2: self._pad("sony", "DualSense", "guid-sony", 0),
            3: self._pad("generic", "Generic SDL Pad", "guid-generic", 1),
        }
        with tempfile.TemporaryDirectory() as directory:
            path = ensure_provider_controller_config(
                "dolphin", Path(directory), 3,
                {player: pad.sdl_index for player, pad in pads.items()},
                controller_identities=pads,
            )
            content = path.read_text()
        self.assertIn("SDL/2/Xbox Series", content)
        self.assertIn("SDL/0/DualSense", content)
        self.assertIn("SDL/1/Generic SDL Pad", content)

    def test_eden_uses_each_live_guid_with_native_face_buttons(self) -> None:
        pads = {
            1: self._pad("sony", "DualSense", "030081b85e0400008e02000001000000", 0),
            2: self._pad("generic", "Generic SDL Pad", "03001234050400008e02000001000000", 1),
        }
        with tempfile.TemporaryDirectory() as directory:
            path = SwitchProvider(Path(directory) / "eden", Path(directory) / "config")
            content = path.ensure_controller_config(2, {1: 0, 2: 1}, pads).read_text()
        self.assertIn("port:0,guid:030000005e0400008e02000001000000", content)
        self.assertIn("port:0,guid:03000000050400008e02000001000000", content)
        for player, guid in ((0, "030000005e0400008e02000001000000"),
                             (1, "03000000050400008e02000001000000")):
            for action, button in (("a", 0), ("b", 1), ("x", 2), ("y", 3)):
                self.assertIn(
                    f'player_{player}_button_{action}="engine:sdl,port:0,guid:{guid},button:{button}"',
                    content,
                )
        self.assertNotIn("030081b85e0400008e02000001000000", content)

    def test_same_guid_still_uses_separate_runtime_indices(self) -> None:
        pads = {
            1: self._pad("one", "Pad One", "030081b85e0400008e02000001000000", 0),
            2: self._pad("two", "Pad Two", "030081b85e0400008e02000001000000", 3),
        }
        with tempfile.TemporaryDirectory() as directory:
            content = SwitchProvider(Path(directory) / "eden", Path(directory) / "config").ensure_controller_config(
                2, {1: 0, 2: 3}, pads
            ).read_text()
        self.assertIn("port:0,guid:030000005e0400008e02000001000000", content)
        self.assertIn("port:1,guid:030000005e0400008e02000001000000", content)
