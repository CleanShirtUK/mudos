import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from lulu.plugins.epic import EpicLauncher


class EpicLaunchTests(unittest.TestCase):
    def test_launch_requests_fresh_online_credential_each_time(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            executable = Path(directory) / "Among The Sleep.exe"
            executable.touch()
            payloads = []
            for code in ("first-code", "second-code"):
                payloads.append(json.dumps({
                    "game_directory": directory,
                    "game_executable": executable.name,
                    "egl_parameters": ["-AUTH_PASSWORD=" + code, "-AUTH_TYPE=exchangecode"],
                    "game_parameters": [], "user_parameters": [],
                }))
            results = [type("Result", (), {"stdout": value, "stderr": ""}) for value in payloads]
            with patch("lulu.plugins.epic.subprocess.run", side_effect=results) as run, \
                    patch("lulu.windows_runtime.shutil.which", return_value="/usr/bin/umu-run"):
                first = EpicLauncher().launch_command("epic:game")
                second = EpicLauncher().launch_command("epic:game")
            self.assertNotEqual(first[-2], second[-2])
            self.assertEqual(run.call_args_list[0].args[0],
                             ["legendary", "launch", "game", "--json"])
            self.assertEqual(run.call_count, 2)
            self.assertEqual(first[5], "/usr/bin/umu-run")

    def test_missing_umu_fails_before_launch_descriptor_can_be_spawned(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            executable = Path(directory) / "game.exe"
            executable.touch()
            result = type("Result", (), {"stdout": json.dumps({
                "game_directory": directory, "game_executable": executable.name,
                "egl_parameters": ["-AUTH_PASSWORD=ephemeral", "-AUTH_TYPE=exchangecode"],
                "game_parameters": [], "user_parameters": [],
            }), "stderr": ""})
            with patch("lulu.plugins.epic.subprocess.run", return_value=result), \
                    patch("lulu.windows_runtime.shutil.which", return_value=None):
                with self.assertRaisesRegex(RuntimeError, "umu-launcher package"):
                    EpicLauncher().launch_command("epic:game")

    def test_missing_launch_credential_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            executable = Path(directory) / "game.exe"
            executable.touch()
            result = type("Result", (), {"stdout": json.dumps({
                "game_directory": directory, "game_executable": executable.name,
                "egl_parameters": ["-AUTH_TYPE=exchangecode"],
                "game_parameters": [], "user_parameters": [],
            }), "stderr": ""})
            with patch("lulu.plugins.epic.subprocess.run", return_value=result):
                with self.assertRaisesRegex(RuntimeError, "fresh Epic launch credential"):
                    EpicLauncher().launch_command("epic:game")
