from __future__ import annotations

import unittest

from lulu.statistics_overlay import PROFILES, launch_environment, next_mode, profile
from lulu.process_supervisor import ProcessSupervisor


class StatisticsOverlayProfileTests(unittest.TestCase):
    def test_all_four_profiles_are_mangohud_configs(self) -> None:
        self.assertEqual(set(PROFILES), {"off", "fps", "minimal", "detailed"})
        self.assertEqual(launch_environment("off"), {
            "MANGOHUD": "1", "MANGOHUD_CONFIG": "no_display=1"
        })
        self.assertIn("fps_only=1", launch_environment("fps")["MANGOHUD_CONFIG"])
        self.assertIn("gpu_core_clock", launch_environment("minimal")["MANGOHUD_CONFIG"])
        self.assertIn("full", launch_environment("detailed")["MANGOHUD_CONFIG"])

    def test_invalid_or_missing_persisted_state_fails_safe_to_off(self) -> None:
        self.assertIs(profile("unknown"), PROFILES["off"])
        self.assertIs(profile(None), PROFILES["off"])

    def test_system_setting_cycles_exactly_the_four_supported_modes(self) -> None:
        current = "off"
        result = []
        for _ in range(4):
            current = next_mode(current)
            result.append(current)
        self.assertEqual(result, ["fps", "minimal", "detailed", "off"])
        self.assertEqual(next_mode("corrupt-state"), "off")

    def test_launch_environment_allowlist_preserves_only_explicit_mangohud_config(self) -> None:
        supervisor = ProcessSupervisor.__new__(ProcessSupervisor)
        supervisor.set_delegated_launch_environment({
            "DISPLAY": ":0",
            **launch_environment("minimal"),
            "LD_PRELOAD": "/untrusted/overlay.so",
        })
        self.assertEqual(supervisor.delegated_launch_environment, {
            "DISPLAY": ":0",
            "MANGOHUD": "1",
            "MANGOHUD_CONFIG": "fps,frametime,cpu_temp,gpu_temp,gpu_core_clock",
        })


if __name__ == "__main__":
    unittest.main()
