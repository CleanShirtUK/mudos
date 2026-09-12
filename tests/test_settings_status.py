import tempfile
import unittest
from pathlib import Path

from lulu.settings import SettingSpec, SettingsStore
from lulu.system_settings import SystemSettingsProvider
from lulu.status import Readiness, RuntimeStatus, SystemStatus


class SettingsStatusTests(unittest.TestCase):
    def test_settings_are_typed_persisted_and_owned(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.sqlite3"
            settings = SettingsStore(path)
            self.assertEqual(settings.get("display.output"), "auto")
            settings.set("display.output", "auto")
            settings.set("network.enabled", False)
            self.assertEqual(SettingsStore(path).get("display.output"), "auto")
            self.assertFalse(SettingsStore(path).get("network.enabled"))

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

    def test_registered_settings_validate_options_and_render_as_controls(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = SettingsStore(Path(directory) / "settings.sqlite3", specs=())
            store.register(SettingSpec("ui.theme", "Display", str, "dark", label="Theme",
                                       kind="select", options=("dark", "light")))
            provider = SystemSettingsProvider(store)
            row = provider.list_settings("Display")[0]
            self.assertEqual((row["kind"], row["value"], row["options"], row["writable"]),
                             ("select", "dark", ["dark", "light"], True))
            with self.assertRaises(ValueError):
                store.set("ui.theme", "neon")
            store.set("ui.theme", "light")
            self.assertEqual(SettingsStore(Path(directory) / "settings.sqlite3", specs=(
                SettingSpec("ui.theme", "Display", str, "dark", kind="select", options=("dark", "light")),
            )).get("ui.theme"), "light")

if __name__ == "__main__":
    unittest.main()
