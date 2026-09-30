import unittest
from unittest.mock import patch

from lulu.virtual_keyboard import (
    DEVICE_NAME,
    EV_KEY,
    EV_SYN,
    KEY_CAPABILITIES,
    KEY_ESC,
    ManagedVirtualKeyboard,
    UI_DEV_CREATE,
    UI_DEV_DESTROY,
    UI_SET_EVBIT,
    UI_SET_KEYBIT,
)


class ManagedVirtualKeyboardTests(unittest.TestCase):
    def test_one_persistent_escape_keyboard_emits_a_complete_tap_and_is_removed(self):
        event_path = "/dev/input/event99"
        device_matches = [[], [event_path]]
        with patch("lulu.virtual_keyboard.ManagedVirtualKeyboard._matching_event_nodes",
                   side_effect=device_matches), \
                patch("lulu.virtual_keyboard.os.open", return_value=42), \
                patch("lulu.virtual_keyboard.os.close") as close_fd, \
                patch("lulu.virtual_keyboard.os.write") as write, \
                patch("lulu.virtual_keyboard.fcntl.ioctl") as ioctl, \
                patch("lulu.virtual_keyboard.time.sleep"):
            keyboard = ManagedVirtualKeyboard()
            keyboard.send_escape(hold_seconds=0.1)
            keyboard.close()

        self.assertEqual(keyboard.event_path, event_path)
        self.assertEqual(
            [call.args[1] for call in ioctl.call_args_list],
            [UI_SET_EVBIT, *([UI_SET_KEYBIT] * len(KEY_CAPABILITIES)),
             UI_DEV_CREATE, UI_DEV_DESTROY],
        )
        events = [keyboard.INPUT_EVENT.unpack(call.args[1])
                  for call in write.call_args_list[1:]]
        self.assertEqual([(event[2], event[3], event[4]) for event in events], [
            (EV_KEY, KEY_ESC, 1), (EV_SYN, 0, 0),
            (EV_KEY, KEY_ESC, 0), (EV_SYN, 0, 0),
        ])
        close_fd.assert_called_once_with(42)
        self.assertEqual(DEVICE_NAME, "Mudos Managed Keyboard")

    def test_refuses_to_create_a_duplicate_named_keyboard(self):
        with patch("lulu.virtual_keyboard.ManagedVirtualKeyboard._matching_event_nodes",
                   return_value=["/dev/input/event99"]), \
                patch("lulu.virtual_keyboard.os.open") as open_device:
            with self.assertRaisesRegex(RuntimeError, "stale or duplicate"):
                ManagedVirtualKeyboard()
        open_device.assert_not_called()
