from __future__ import annotations

import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch

from lulu.statistics_overlay import (
    PROFILES, adapt_native_launch, launch_environment, next_mode, profile,
)
from lulu.process_supervisor import ProcessSupervisor


class StatisticsOverlayProfileTests(unittest.TestCase):
    def test_all_four_profiles_are_mangohud_configs(self) -> None:
        self.assertEqual(set(PROFILES), {"off", "fps", "minimal", "detailed"})
        self.assertEqual(launch_environment("off"), {"MANGOHUD": "0"})
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

    def test_native_elf_launch_uses_official_wrapper_and_forwards_argv(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            executable = Path(directory) / "native-game"
            executable.write_bytes(b"\x7fELF" + b"fixture")
            command, environment = adapt_native_launch(
                [str(executable), "arg with spaces"], launch_environment("minimal"),
                wrapper="/usr/bin/mangohud",
            )
        self.assertEqual(command, ["/usr/bin/mangohud", "--dlsym", str(executable), "arg with spaces"])
        self.assertEqual(environment, launch_environment("minimal"))

    def test_off_does_not_wrap_and_missing_wrapper_is_graceful(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            executable = Path(directory) / "native-game"
            executable.write_bytes(b"\x7fELF" + b"fixture")
            off_command, off_environment = adapt_native_launch([str(executable)], launch_environment("off"))
            with patch("lulu.statistics_overlay.shutil.which", return_value=None):
                command, environment = adapt_native_launch([str(executable)], launch_environment("fps"))
        self.assertEqual(off_command, [str(executable)])
        self.assertEqual(off_environment, {"MANGOHUD": "0"})
        self.assertEqual(command, [str(executable)])
        self.assertEqual(environment, launch_environment("fps"))

    def test_native_entry_script_is_wrapped_but_proton_launcher_script_is_not(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            native = root / "SuperMeatBoy"
            native.write_text('#!/bin/sh\ncd "$(dirname "$0")"\nexec ./amd64/SuperMeatBoy "$@"\n')
            proton = root / "proton-game"
            proton.write_text('#!/bin/sh\nexec wine64-preloader game.exe "$@"\n')
            wrapped, _ = adapt_native_launch([str(native), "arg"], launch_environment("fps"),
                                             wrapper="/usr/bin/mangohud")
            unchanged, _ = adapt_native_launch([str(proton)], launch_environment("fps"),
                                               wrapper="/usr/bin/mangohud")
        self.assertEqual(wrapped, ["/usr/bin/mangohud", "--dlsym", str(native), "arg"])
        self.assertEqual(unchanged, [str(proton)])


if __name__ == "__main__":
    unittest.main()
