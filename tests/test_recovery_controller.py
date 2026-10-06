from pathlib import Path
import unittest

from lulu.contracts import InputMode
from lulu.recovery_controller import apply_recovery_gamepad_mode


ROOT = Path(__file__).resolve().parents[1]


class RecoveryControllerTests(unittest.TestCase):
    def test_standalone_recovery_selects_gamepad_profile_for_connected_composites(self) -> None:
        class Client:
            def __init__(self):
                self.loads = []

            def runtime_composite_statuses(self):
                return {
                    "/controller/0": ("xbox", ("/dev/input/event0",)),
                    "/controller/1": ("waiting", ()),
                }

            def load_mode(self, mode, object_path=None):
                self.loads.append((mode, object_path))
                return []

        client = Client()
        self.assertEqual(apply_recovery_gamepad_mode(client), ("/controller/0",))
        self.assertEqual(client.loads, [(InputMode.GAME, "/controller/0")])

    def test_recovery_applies_inputplumber_profile_and_reconnect_reuses_hotplug_path(self) -> None:
        recovery = (ROOT / "scripts/mudos-recovery-ui.py").read_text()
        hotplug = (ROOT / "scripts/provision-inputplumber-gamepads.py").read_text()
        self.assertIn("apply_recovery_gamepad_mode(inputplumber)", recovery)
        self.assertIn('"mudos-recovery-ui.service"', hotplug)
        self.assertIn("apply_recovery_gamepad_mode(client)", hotplug)
        self.assertNotIn('["systemctl", "restart", "inputplumber.service"]', hotplug)

    def test_recovery_qml_has_deterministic_focus_and_controller_action_paths(self) -> None:
        qml = (ROOT / "ui/Recovery.qml").read_text()
        native = (ROOT / "native/lulu-shell.cpp").read_text()
        self.assertIn("property int selected: 0", qml)
        self.assertIn("recoveryRoot.forceActiveFocus()", qml)
        self.assertIn("focus: root.selected === index", qml)
        self.assertIn("border.color: root.selected === index ? luluPalette.focusIndicator", qml)
        self.assertIn("LuluPalette { id: luluPalette }", qml)
        self.assertIn("Typography { id: typography }", qml)
        self.assertNotIn('color: "#10131a"', qml)
        self.assertIn("function controllerUp()", qml)
        self.assertIn("function activate()", qml)
        self.assertIn("SDL_GAMEPAD_BUTTON_DPAD_UP, \"up\"", native)
        self.assertIn("SDL_GAMEPAD_BUTTON_SOUTH, \"confirm\"", native)
        self.assertIn("SDL_GAMEPAD_BUTTON_EAST, \"back\"", native)
        self.assertIn("if (qEnvironmentVariableIntValue(\"LULU_RECOVERY_STANDALONE\") != 0)", native)
        self.assertIn("QMetaObject::invokeMethod(window_, function)", native)
