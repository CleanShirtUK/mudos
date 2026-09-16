import asyncio
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

from lulu.job_manager import JobManager
from lulu.jobs import JobState
from lulu.steam_cmd import SteamCmdExecutor, SteamCmdParser, SteamPlatformResolver, load_platforms


class SteamCmdParserTests(unittest.TestCase):
    def setUp(self) -> None:
        self.parser = SteamCmdParser()

    def test_observed_lifecycle_and_stage_aware_progress(self) -> None:
        self.assertEqual(self.parser.parse("Update state (0x3) reconfiguring, progress: 0.00 (0 / 0)").kind, "starting")
        progress = self.parser.parse("\x1b[0m Update state (0x61) downloading, progress: 42.10 (137846818 / 327444829)\r")
        self.assertEqual((progress.kind, progress.staged_bytes, progress.total_staged_bytes),
                         ("transferring", 137846818, 327444829))
        self.assertAlmostEqual(progress.progress, .421)
        self.assertEqual(self.parser.parse("Update state (0x101) committing, progress: 15.86 (51924940 / 327444829)").kind, "finalizing")
        self.assertEqual(self.parser.parse("Success! App '263980' fully installed.").kind, "success")

    def test_noop_errors_and_authentication(self) -> None:
        self.assertEqual(self.parser.parse("Success! App '263980' already up to date.").kind, "success")
        self.assertEqual(self.parser.parse("ERROR! Failed to install app '263980' (Invalid platform)").kind, "invalid-platform")
        self.assertEqual(self.parser.parse("Cached credentials not found.").kind, "authentication-required")
        self.assertEqual(self.parser.parse("ERROR! Failed to request app info update, not online or not logged in to Steam.").kind, "authentication-required")


class SteamCmdExecutorTests(unittest.TestCase):
    def test_platform_policy_and_deterministic_commands(self) -> None:
        windows = SteamCmdExecutor(account="user", platforms={"263980": "windows"}, install_dir=Path("/games/Steam"))
        self.assertEqual(windows.command("263980"), [
            "/var/lib/lulu/steamcmd/steamcmd.sh", "+@NoPromptForPassword", "1", " +@sSteamCmdForcePlatformType".strip(), "windows",
            "+force_install_dir", "/games/Steam", "+login", "user", "+app_update", "263980", "validate", "+quit",
        ])
        linux = SteamCmdExecutor(account="user", platforms={"42": "linux"})
        self.assertNotIn("+@sSteamCmdForcePlatformType", linux.command("42"))
        with self.assertRaisesRegex(Exception, "unknown"):
            linux.command("263980")

    def test_executable_resolution_override_and_canonical(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            executable = Path(directory) / "steamcmd.sh"
            executable.write_text("#!/bin/sh\nexit 0\n")
            executable.chmod(0o755)
            override = SteamCmdExecutor(executable=str(executable), account="user",
                                         platforms={"42": "linux"})
            self.assertEqual(override._require_executable(), str(executable))
            with patch.dict("os.environ", {"LULU_STEAMCMD": str(executable)}):
                self.assertEqual(SteamCmdExecutor(account="user", platforms={"42": "linux"}).executable,
                                 str(executable))

    def test_missing_executable_is_normalized(self) -> None:
        executor = SteamCmdExecutor(executable="/does/not/exist/steamcmd", account="user",
                                    platforms={"42": "linux"})
        with self.assertRaisesRegex(Exception, "SteamCMD is not provisioned") as error:
            executor._require_executable()
        self.assertEqual(error.exception.code, "steamcmd-unavailable")

    def test_provisioner_is_rerunnable_and_checksum_aware(self) -> None:
        script = Path(__file__).parents[1] / "scripts/provision-steamcmd.sh"
        source = script.read_text()
        self.assertIn("if [ -x \"$root/steamcmd.sh\" ]", source)
        self.assertIn("LULU_STEAMCMD_SHA256", source)
        self.assertIn("mv \"$temporary\" \"$root\"", source)

    def test_platform_metadata_is_explicit(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "platforms.json"
            path.write_text(json.dumps({"263980": "windows", "42": "linux", "bad": "console"}))
            self.assertEqual(load_platforms(path), {"263980": "windows", "42": "linux"})

    def test_platform_resolver_prefers_linux_then_windows_and_fails_closed(self) -> None:
        responses = {
            "42": b'{"42":{"success":true,"data":{"platforms":{"linux":true,"windows":true}}}}',
            "263980": b'{"263980":{"success":true,"data":{"platforms":{"linux":false,"windows":true}}}}',
            "99": b'{"99":{"success":true,"data":{"platforms":{"linux":false,"windows":false,"mac":true}}}}',
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "platforms.json"
            resolver = SteamPlatformResolver(path, lambda url, _timeout: responses[url.split("appids=")[1].split("&")[0]])
            self.assertEqual(resolver.resolve("42"), "linux")
            self.assertEqual(resolver.resolve("263980"), "windows")
            self.assertIsNone(resolver.resolve("99"))
            self.assertEqual(load_platforms(path), {"263980": "windows", "42": "linux"})

    def test_unknown_platform_and_missing_account_fail_before_spawn(self) -> None:
        executor = SteamCmdExecutor(account="", platforms={"263980": "windows"})
        with self.assertRaisesRegex(Exception, "authentication"):
            executor.command("263980")

    def test_live_output_normalizes_lifecycle_and_clears_commit_bytes(self) -> None:
        async def exercise() -> None:
            class Process:
                returncode = 0
                stdout = asyncio.StreamReader()
                stderr = asyncio.StreamReader()

                async def wait(self) -> int:
                    return self.returncode

            process = Process()
            for line in (
                "Update state (0x61) downloading, progress: 99.68 (326396253 / 327444829)\n",
                "Update state (0x101) committing, progress: 15.86 (51924940 / 327444829)\n",
                "Success! App '263980' fully installed.\n",
            ):
                process.stdout.feed_data(line.encode())
            process.stdout.feed_eof()
            process.stderr.feed_eof()
            manager = JobManager()
            executor = SteamCmdExecutor(executable="/bin/true", account="user", platforms={"263980": "windows"}, install_dir=Path(tempfile.gettempdir()) / "lulu-steam-test")
            manager.register_executor("steam", executor)
            job = manager.submit("steam", "steam:263980", "Out There Somewhere")
            with patch("asyncio.create_subprocess_exec", new=AsyncMock(return_value=process)):
                await manager._tasks[job.job_id]
            result = manager.jobs[job.job_id]
            self.assertEqual(result.state, JobState.COMPLETED)
            self.assertEqual(result.progress, 1.0)
            self.assertIsNone(result.downloaded_bytes)
            self.assertIsNone(result.total_bytes)

        asyncio.run(exercise())


if __name__ == "__main__":
    unittest.main()
