import tempfile
import unittest
import importlib.util
from pathlib import Path

from lulu.controllerd import Controller, ControllerRegistry
from lulu.controller_provisioning import ensure_provider_controller_config
from lulu.inputplumber import normalized_controller_identity
from lulu.switch_provider import SwitchProvider


class StandardGamepadTests(unittest.TestCase):
    def test_dynamic_inputplumber_profile_uses_capability_selected_event_path(self) -> None:
        spec = importlib.util.spec_from_file_location(
            "provision_inputplumber_gamepads",
            Path(__file__).parents[1] / "scripts/provision-inputplumber-gamepads.py",
        )
        self.assertIsNotNone(spec)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)
        content = module.render("event8")
        self.assertIn("udev:\n      dev_node: /dev/input/event8", content)
        self.assertNotIn("handler: event*", content)
        self.assertNotIn("phys_path:", content)
        self.assertNotIn("vendor_id", content)
        self.assertNotIn("product_id", content)

    def test_virtual_capability_selected_profile_does_not_require_physical_path(self) -> None:
        spec = importlib.util.spec_from_file_location(
            "provision_inputplumber_gamepads_virtual",
            Path(__file__).parents[1] / "scripts/provision-inputplumber-gamepads.py",
        )
        self.assertIsNotNone(spec)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)
        content = module.render("event13")
        self.assertIn("udev:\n      dev_node: /dev/input/event13", content)
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

    def test_eden_uses_each_live_guid_but_nintendo_policy_is_shared(self) -> None:
        pads = {
            1: self._pad("sony", "DualSense", "guid-sony", 0),
            2: self._pad("generic", "Generic SDL Pad", "guid-generic", 1),
        }
        with tempfile.TemporaryDirectory() as directory:
            path = SwitchProvider(Path(directory) / "eden", Path(directory) / "config")
            content = path.ensure_controller_config(2, {1: 0, 2: 1}, pads).read_text()
        self.assertIn("port:0,guid:guid-sony", content)
        self.assertIn("port:1,guid:guid-generic", content)
        self.assertIn('player_0_button_a="engine:sdl,port:0,guid:guid-sony,button:1"', content)
        self.assertIn('player_1_button_a="engine:sdl,port:1,guid:guid-generic,button:1"', content)
        self.assertNotIn("030081b85e0400008e02000001000000", content)

    def test_same_guid_still_uses_separate_runtime_indices(self) -> None:
        pads = {
            1: self._pad("one", "Pad One", "shared-guid", 0),
            2: self._pad("two", "Pad Two", "shared-guid", 3),
        }
        with tempfile.TemporaryDirectory() as directory:
            content = SwitchProvider(Path(directory) / "eden", Path(directory) / "config").ensure_controller_config(
                2, {1: 0, 2: 3}, pads
            ).read_text()
        self.assertIn("port:0,guid:shared-guid", content)
        self.assertIn("port:3,guid:shared-guid", content)
