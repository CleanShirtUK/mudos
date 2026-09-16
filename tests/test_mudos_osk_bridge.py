from pathlib import Path
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
        self.assertIn("await set_intercept_mode(bus, 1)", source)
        self.assertIn("self.process.terminate()", source)
        self.assertIn("self.process.kill()", source)
        self.assertIn("mode_restored", source)
        self.assertIn("source_present", source)
        self.assertIn("awaiting_show_until", source)

    def test_private_device_is_not_the_inputplumber_xbox_identity(self):
        source = (ROOT / "scripts/mudos-osk-bridge").read_text()
        self.assertIn('b"gamepad-osk-bridge', source)
        self.assertIn("0x1D6B", source)
        self.assertNotIn("0x02A1", source)


if __name__ == "__main__":
    unittest.main()
