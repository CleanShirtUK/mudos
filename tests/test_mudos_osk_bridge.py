from pathlib import Path
import asyncio
from types import SimpleNamespace
import unittest
from importlib.machinery import SourceFileLoader


ROOT = Path(__file__).parents[1]


def load_bridge():
    return SourceFileLoader("mudos_osk_bridge", str(ROOT / "scripts/mudos-osk-bridge")).load_module()


class FakePad:
    def __init__(self):
        self.buttons = []
        self.axes = []

    def button(self, code, value):
        self.buttons.append((code, value))

    def axis(self, code, value):
        self.axes.append((code, value))

    def reset(self):
        pass


class MudosOskBridgeTests(unittest.TestCase):
    def setUp(self):
        self.bridge = load_bridge()
        # Avoid opening uinput; exercise the normalized event mapper only.
        self.mapper = object.__new__(self.bridge.Bridge)
        self.mapper.pad = FakePad()
        self.mapper.active = True
        self.mapper.dpad = {"up": False, "down": False, "left": False, "right": False}

    def event(self, name, value):
        class Message:
            body = [name, value]
        self.mapper.on_input(Message())

    def test_button_mappings_pair_down_and_up(self):
        expected = {
            "ui_accept": self.bridge.BTN_SOUTH,
            "ui_back": self.bridge.BTN_EAST,
            "ui_context": self.bridge.BTN_WEST,
            "ui_option": self.bridge.BTN_NORTH,
        }
        for name, code in expected.items():
            self.event(name, 1)
            self.event(name, 0)
        self.assertEqual(
            self.mapper.pad.buttons,
            [(code, value) for code in expected.values() for value in (1, 0)],
        )

    def test_dpad_duplicate_and_reordered_edges_do_not_release_held_direction(self):
        self.event("ui_up", 1)
        self.event("ui_up", 1)
        self.event("ui_down", 1)
        self.event("ui_up", 0)
        self.assertEqual(self.mapper.pad.axes[-1], (self.bridge.ABS_HAT0Y, 1))
        self.event("ui_down", 0)
        self.assertEqual(self.mapper.pad.axes[-1], (self.bridge.ABS_HAT0Y, 0))

    def test_trigger_mappings_are_analog(self):
        self.event("ui_l2", 0.5)
        self.event("ui_r2", 1.0)
        self.assertIn((self.bridge.ABS_Z, 128), self.mapper.pad.axes)
        self.assertIn((self.bridge.ABS_RZ, 255), self.mapper.pad.axes)

    def test_unknown_action_is_ignored(self):
        self.event("ui_menu", 1)
        self.assertEqual(self.mapper.pad.buttons, [])
        self.assertEqual(self.mapper.pad.axes, [])

    def test_lifecycle_has_fail_safe_cleanup_and_mode_restore(self):
        source = (ROOT / "scripts/mudos-osk-bridge").read_text()
        self.assertIn("finally:", source)
        self.assertIn("self.pad.reset()", source)
        self.assertIn("await set_intercept_mode(bus, self.composite_path, 1)", source)
        self.assertIn("self.process.terminate()", source)
        self.assertIn("self.process.kill()", source)
        self.assertIn("mode_restored", source)
        self.assertIn("source_present", source)
        self.assertIn("awaiting_show_until", source)
        self.assertIn("await set_intercept_mode(bus, self.composite_path, 2)", source)

    def test_osk_uses_exclusive_dbus_profile_and_restores_previous_profile(self):
        source = (ROOT / "scripts/mudos-osk-bridge").read_text()
        profile = (ROOT / "config/inputplumber/profiles/osk.yaml").read_text()
        self.assertIn("LoadProfilePath", source)
        self.assertIn("get_profile_path", source)
        self.assertIn("self.profile_path", source)
        self.assertIn("load_profile_path(bus, self.composite_path, self.profile_path)", source)
        self.assertIn("keyboard: KeyUp", profile)
        self.assertIn("keyboard: KeyEnter", profile)
        self.assertNotIn("dbus:", profile)

    def test_composite_is_discovered_from_gamepad_order_not_fixed_index(self):
        source = (ROOT / "scripts/mudos-osk-bridge").read_text()
        self.assertIn('member="Get", signature="ss"', source)
        self.assertIn('body=[INPUT_MANAGER_INTERFACE, "GamepadOrder"]', source)
        self.assertIn("self.composite_path: str | None", source)
        self.assertNotIn('COMPOSITE_PATH = "/org/shadowblip/InputPlumber/CompositeDevice0"', source)

    def test_missing_composite_keeps_bridge_alive_and_waits_for_topology(self):
        source = (ROOT / "scripts/mudos-osk-bridge").read_text()
        self.assertIn("self.composite_path = desired", source)
        self.assertIn("if desired is None:", source)
        self.assertIn("await asyncio.wait_for(self.topology_event.wait(), timeout=2.0)", source)
        self.assertNotIn("self.process.terminate()\n                    break", source)

    def test_topology_and_service_owner_signals_wake_reconciliation(self):
        source = (ROOT / "scripts/mudos-osk-bridge").read_text()
        self.assertIn('member=\'PropertiesChanged\'', source)
        self.assertIn('member=\'NameOwnerChanged\'', source)
        self.assertIn('message.body[0] == INPUT_SERVICE', source)

    def test_reconciliation_is_idle_without_a_composite_and_binds_any_path(self):
        class FakeBus:
            def __init__(self, order):
                self.order = order
                self.calls = []

            async def call(self, message):
                self.calls.append(message)
                if message.member == "Get" and message.body[1] == "GamepadOrder":
                    return SimpleNamespace(message_type=SimpleNamespace(name="METHOD_RETURN"),
                                           body=[SimpleNamespace(value=self.order)])
                if message.member == "Get" and message.body[1] == "ProfilePath":
                    return SimpleNamespace(message_type=SimpleNamespace(name="METHOD_RETURN"),
                                           body=[SimpleNamespace(value="/old/profile.yaml")])
                return SimpleNamespace(message_type=SimpleNamespace(name="METHOD_RETURN"), body=[])

        mapper = object.__new__(self.bridge.Bridge)
        mapper.pad = FakePad()
        mapper.active = False
        mapper.composite_path = None
        mapper.mode_restored = False
        mapper.source_present = True
        mapper.awaiting_show_until = 0

        empty = FakeBus([])
        asyncio.run(mapper._reconcile_composite(empty, False))
        self.assertIsNone(mapper.composite_path)
        self.assertEqual(len(empty.calls), 1)

        replacement = FakeBus(["/org/shadowblip/InputPlumber/CompositeDevice7"])
        asyncio.run(mapper._reconcile_composite(replacement, False))
        self.assertEqual(mapper.composite_path,
                         "/org/shadowblip/InputPlumber/CompositeDevice7")
        self.assertTrue(mapper.mode_restored)

    def test_private_device_is_not_the_inputplumber_xbox_identity(self):
        source = (ROOT / "scripts/mudos-osk-bridge").read_text()
        self.assertIn('b"gamepad-osk-bridge', source)
        self.assertIn("0x1D6B", source)
        self.assertNotIn("0x02A1", source)


if __name__ == "__main__":
    unittest.main()
