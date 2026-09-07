import tempfile
import unittest
from pathlib import Path

from lulu.settings import SettingsStore
from lulu.status import Readiness, RuntimeStatus, SystemStatus


class SettingsStatusTests(unittest.TestCase):
    def test_settings_are_typed_persisted_and_owned(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.sqlite3"
            settings = SettingsStore(path)
            self.assertEqual(settings.get("display.output"), "auto")
            settings.set("display.output", "auto")
            self.assertEqual(SettingsStore(path).get("display.output"), "auto")

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


if __name__ == "__main__":
    unittest.main()
