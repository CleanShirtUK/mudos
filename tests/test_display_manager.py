import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from lulu.display_manager import DisplayManagerAdapter, DisplayMode, display_environment


class DisplayManagerTests(unittest.TestCase):
    def test_automatic_detection_does_not_turn_discovered_output_into_override(self):
        state = {"displays": [{"id": "DP-1", "connector": "DP-1", "connected": True,
                               "preferred": {"width": 1920, "height": 1080, "refresh": 60.0}}],
                 "requested": {}, "known_good": {}, "selected": {"id": "DP-1"}}
        with patch("lulu.display_manager.DisplayManagerAdapter") as adapter:
            adapter.return_value.snapshot.return_value = state
            self.assertEqual(display_environment(), {})

    def test_drm_output_and_modes_are_normalized(self):
        with TemporaryDirectory() as directory:
            connector = Path(directory) / "card0-DP-1"
            connector.mkdir()
            (connector / "status").write_text("connected\n")
            (connector / "modes").write_text("1920x1080\n1280x720\n1920x1080\n")
            with patch("lulu.display_manager._modetest_modes", return_value={
                "DP-1": [DisplayMode(1920, 1080, 59.94, True), DisplayMode(1920, 1080, 120.0)]
            }):
                display = DisplayManagerAdapter(state_path=Path(directory) / "state.json", drm_path=directory).snapshot()["displays"][0]
            self.assertEqual(display["id"], "DP-1")
            self.assertEqual(display["preferred"]["refresh"], 59.94)
            self.assertEqual([mode["refresh"] for mode in display["modes"]], [59.94, 120.0])

    def test_apply_rejects_invalid_mode_and_persists_known_good(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            connector = root / "card0-HDMI-A-1"
            connector.mkdir()
            (connector / "status").write_text("connected\n")
            (connector / "modes").write_text("1920x1080\n")
            with patch("lulu.display_manager._modetest_modes", return_value={
                "HDMI-A-1": [DisplayMode(1920, 1080, 60.0, True)]
            }):
                adapter = DisplayManagerAdapter(state_path=root / "state.json", drm_path=directory)
                with self.assertRaisesRegex(ValueError, "unavailable"):
                    adapter.apply("HDMI-A-1", 1280, 720, 60.0)
                state = adapter.apply("HDMI-A-1", 1920, 1080, 60.0)
            self.assertEqual(state["known_good"]["refresh"], 60.0)
            self.assertEqual(json.loads((root / "state.json").read_text())["requested"]["output"], "HDMI-A-1")


if __name__ == "__main__":
    unittest.main()
