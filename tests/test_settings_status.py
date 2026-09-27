import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from lulu.settings import SettingsStore
from lulu.status import (
    BluetoothState,
    Readiness,
    RuntimeStatus,
    SystemStatus,
    network_manager_state_is_connected,
    normalize_bluetooth_state,
)
from lulu.system_settings import SystemSettingsProvider


class SettingsStatusTests(unittest.TestCase):
    def test_network_manager_states_normalize_to_usable_connection(self) -> None:
        self.assertTrue(network_manager_state_is_connected(50))
        self.assertTrue(network_manager_state_is_connected(60))
        self.assertTrue(network_manager_state_is_connected(70))
        self.assertFalse(network_manager_state_is_connected(20))
        self.assertFalse(network_manager_state_is_connected(None))

    def test_bluetooth_state_normalizes_power_off_and_absence(self) -> None:
        self.assertEqual(normalize_bluetooth_state(True, (True,)), BluetoothState.POWERED)
        self.assertEqual(normalize_bluetooth_state(True, (False,)), BluetoothState.OFF)
        self.assertEqual(normalize_bluetooth_state(True, (False, False)), BluetoothState.OFF)
        self.assertEqual(normalize_bluetooth_state(True, ()), BluetoothState.UNAVAILABLE)
        self.assertEqual(normalize_bluetooth_state(False, (True,)), BluetoothState.UNAVAILABLE)

    def test_settings_are_typed_persisted_and_owned(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.sqlite3"
            settings = SettingsStore(path)
            self.assertEqual(settings.get("display.output"), "auto")
            self.assertTrue(settings.get("launch_overlay_enabled"))
            self.assertTrue(settings.get("controllers.nintendo_button_layout"))
            settings.set("display.output", "auto")
            self.assertEqual(SettingsStore(path).get("display.output"), "auto")
            settings.set("controllers.nintendo_button_layout", False)
            self.assertFalse(SettingsStore(path).get("controllers.nintendo_button_layout"))

        with self.assertRaises(TypeError):
            settings.set("network.enabled", "yes")

    def test_readiness_and_status_are_normalized_and_read_only(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            settings = SettingsStore(Path(directory) / "settings.sqlite3")
            with self.assertRaisesRegex(ValueError, "read-only"):
                settings.set("runtime.dolphin_ready", True)

        status = SystemStatus(
            controller_connected=True,
            navigation_owner="pad-a",
            input_mode="shell",
            storage_free_bytes=1024,
            network_connected=None,
            display_output="HDMI-A-1",
            display_mode="1280x720",
            runtimes=(RuntimeStatus("RetroArch", Readiness.READY),),
        )
        self.assertEqual(status.runtimes[0].readiness, Readiness.READY)
        self.assertIsNone(status.network_connected)

    def test_network_settings_expose_file_browser_status_and_address(self) -> None:
        def command(*args: str) -> str:
            if args[:2] == ("hostname", "-I"):
                return "192.168.1.42"
            if args[:2] == ("systemctl", "is-active"):
                return "active"
            return ""

        with patch("lulu.system_settings._command", side_effect=command):
            settings = SystemSettingsProvider().list_settings("Network")

        values = {item["key"]: item["value"] for item in settings}
        self.assertEqual(values["network.file_browser"], "active")
        self.assertEqual(values["network.file_browser_address"], "http://192.168.1.42:8080/")


if __name__ == "__main__":
    unittest.main()
