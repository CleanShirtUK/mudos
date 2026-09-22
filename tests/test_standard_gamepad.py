import tempfile
import unittest
import importlib.util
from pathlib import Path

from lulu.controllerd import Controller, ControllerRegistry
from lulu.controller_provisioning import ensure_provider_controller_config
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
        content = module.render("event8", "usb-physical/input0")
        self.assertIn("handler: event*", content)
        self.assertIn("dev_node: /dev/event8", content)
        self.assertIn("phys_path: 'usb-physical/input0'", content)
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
        self.assertIn("dev_node: /dev/event13", content)
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
