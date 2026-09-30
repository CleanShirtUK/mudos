import asyncio
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

from lulu.job_manager import JobManager
from lulu.jobs import JobState
from lulu.credential import CredentialInput
from lulu.steam_cmd import SteamCmdError, SteamCmdExecutor, SteamCmdParser, SteamPlatformResolver, load_platforms


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
        self.assertEqual(self.parser.parse("ERROR (Timeout)").kind, "network-error")
        self.assertEqual(self.parser.parse("Cached credentials not found.").kind, "authentication-required")
        self.assertEqual(self.parser.parse("ERROR! Failed to request app info update, not online or not logged in to Steam.").kind, "authentication-required")
        self.assertEqual(self.parser.parse("[2026-09-25] ERROR (Invalid Password)").kind,
                         "authentication-invalid-password")


class SteamCmdExecutorTests(unittest.TestCase):
    def test_steam_silent_depot_transfer_gets_long_idle_watchdog(self) -> None:
        source = (Path(__file__).parents[1] / "src/lulu/plugins/steam/cmd.py").read_text()
        self.assertIn("time() + 1800", source)
        self.assertIn('"steamcmd-timeout"', source)
        self.assertIn("idle_timeout_seconds", source)

    def test_missing_steam_account_is_retryable_after_authentication_setup(self) -> None:
        executor = SteamCmdExecutor(account="", platforms={"42": "linux"})
        with self.assertRaises(SteamCmdError) as caught:
            executor.command("42")
        self.assertEqual(caught.exception.code, "authentication-required")
        self.assertTrue(caught.exception.retryable)

    def test_executor_uses_username_from_steam_ownership_configuration(self) -> None:
        from types import SimpleNamespace

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            steam_dir = root / "steam"
            steam_dir.mkdir()
            (steam_dir / "steam.json").write_text(json.dumps({
                "steam_id": "76561198000000000",
                "steam_username": "configured-user",
                "api_key_file": "secret:steam/web-api-key",
            }))
            with patch("lulu.plugins.steam.entitlements.PATHS",
                       SimpleNamespace(plugins_root=root)), \
                    patch("lulu.plugins.steam.cmd.SecretStore") as secrets:
                secrets.return_value.get.return_value = ""
                executor = SteamCmdExecutor(account="", platforms={"42": "linux"})

        self.assertEqual(executor.account, "configured-user")
        self.assertIn("+login", executor.command("42"))

    def test_successful_steamcmd_verification_keeps_saved_password_for_future_sessions(self) -> None:
        async def exercise() -> None:
            class Process:
                pid = 42
                returncode = 0

                def __init__(self) -> None:
                    self.stdout = asyncio.StreamReader()
                    self.stderr = asyncio.StreamReader()
                    self.stdout.feed_data(b"Logged in OK\n")
                    self.stdout.feed_eof()
                    self.stderr.feed_eof()

                async def wait(self) -> int:
                    return self.returncode

            class Secrets:
                def __init__(self) -> None: self.cleared = []
                def configured(self, _namespace, _key) -> bool: return True
                def clear(self, namespace, key) -> None: self.cleared.append((namespace, key))

            executor = SteamCmdExecutor(executable="/bin/true", account="user")
            secrets = Secrets()
            executor.secrets = secrets
            with patch("asyncio.create_subprocess_exec", new=AsyncMock(return_value=Process())):
                result = await executor.authenticate()
            self.assertEqual(result, {"status": "authenticated"})
            self.assertEqual(secrets.cleared, [])

        asyncio.run(exercise())

    def test_steam_pause_is_explicitly_unsupported(self) -> None:
        executor = SteamCmdExecutor(account="user", platforms={"42": "linux"})
        self.assertFalse(executor.supports_pause)

    def test_dead_provider_withdraws_external_credential_wait(self) -> None:
        async def exercise() -> None:
            class Stdin:
                def write(self, _value: bytes) -> None:
                    raise AssertionError("dead provider must not receive credentials")

                async def drain(self) -> None:
                    raise AssertionError("dead provider must not receive credentials")

            class DeadProcess:
                pid = 24157
                stdin = Stdin()

                async def wait(self) -> int:
                    return -9

            pending = asyncio.Event()

            async def request(*_args):
                await pending.wait()
                return "never"

            executor = SteamCmdExecutor(account="user", platforms={"42": "linux"},
                                        request_credential=request)
            with self.assertRaises(SteamCmdError) as error:
                await executor._answer(
                    input_type=CredentialInput.SECRET,
                    title="SteamCMD password", prompt="Password", process=DeadProcess(),
                    owner={"provider": "steam", "job_id": "job-dead", "pid": 24157},
                )
            self.assertEqual(error.exception.code, "provider-exited")

        asyncio.run(exercise())

    def test_saved_oobe_password_bypasses_interactive_password_prompt(self) -> None:
        async def exercise() -> None:
            class Stdin:
                def __init__(self) -> None: self.values = []
                def write(self, value: bytes) -> None: self.values.append(value)
                async def drain(self) -> None: return None

            class Process:
                pid = 111
                stdin = Stdin()
                async def wait(self) -> int: return 0

            class Secrets:
                def __init__(self) -> None: self.cleared = []
                def configured(self, _namespace, _key) -> bool: return True
                def get(self, _namespace, _key) -> str: return "secret-from-oobe"
                def clear(self, namespace, key) -> None: self.cleared.append((namespace, key))

            async def unexpected_prompt(*_args):
                raise AssertionError("saved password must not prompt the shell")

            executor = SteamCmdExecutor(account="user", request_credential=unexpected_prompt)
            executor.secrets = Secrets()
            process = Process()
            await executor._answer(CredentialInput.SECRET, "SteamCMD password", "Password", process)
            self.assertEqual(process.stdin.values, [b"secret-from-oobe\n"])
            self.assertEqual(executor.secrets.cleared, [])

        asyncio.run(exercise())

    def test_guard_wait_can_fall_back_to_code_in_same_auth_transaction(self) -> None:
        async def exercise() -> None:
            class Stdin:
                def __init__(self) -> None:
                    self.values: list[bytes] = []

                def write(self, value: bytes) -> None:
                    self.values.append(value)

                async def drain(self) -> None:
                    return None

            class LiveProcess:
                pid = 77

                def __init__(self) -> None:
                    self.stdin = Stdin()
                    self.stop = asyncio.Event()

                async def wait(self) -> int:
                    await self.stop.wait()
                    return 0

            process = LiveProcess()
            requests: list[tuple[CredentialInput, dict[str, object]]] = []

            async def request(input_type, _title, _prompt, _minimum, _maximum, owner):
                requests.append((input_type, owner))
                return "enter-code" if input_type is CredentialInput.WAITING else "abcde"

            executor = SteamCmdExecutor(account="user", platforms={"42": "linux"},
                                        request_credential=request)
            result = await executor._guard_interaction(process, "job-guard", "auth-1", 77)
            self.assertEqual(result, "abcde")
            self.assertEqual([item[0] for item in requests],
                             [CredentialInput.WAITING, CredentialInput.CODE])
            self.assertEqual(requests[0][1], requests[1][1])
            self.assertEqual(process.stdin.values, [b"abcde\n"])
            process.stop.set()

        asyncio.run(exercise())

    def test_guard_wait_can_confirm_mobile_approval_without_entering_a_code(self) -> None:
        async def exercise() -> None:
            class Process:
                pid = 79
                stdin = type("Stdin", (), {"write": lambda *_: None,
                                            "drain": AsyncMock()})()
                async def wait(self) -> int:
                    await asyncio.Event().wait()
                    return 0

            requests = []

            async def request(input_type, _title, _prompt, _minimum, _maximum, _owner):
                requests.append(input_type)
                return "approved"

            executor = SteamCmdExecutor(account="user", request_credential=request)
            result = await executor._guard_interaction(Process(), "job-approved", "auth-2", 79)
            self.assertEqual(result, "approved")
            self.assertEqual(requests, [CredentialInput.WAITING])

        asyncio.run(exercise())

    def test_cancelled_external_guard_wait_withdraws_callback(self) -> None:
        async def exercise() -> None:
            class Process:
                pid = 88
                stdin = type("Stdin", (), {"write": lambda *_: None,
                                            "drain": AsyncMock()})()

                async def wait(self) -> int:
                    await asyncio.Event().wait()
                    return 0

            withdrawn = asyncio.Event()

            async def request(*_args):
                try:
                    await asyncio.Event().wait()
                finally:
                    withdrawn.set()
                return "never"

            executor = SteamCmdExecutor(account="user", platforms={"42": "linux"},
                                        request_credential=request)
            task = asyncio.create_task(executor._answer(
                CredentialInput.WAITING, "Steam Guard", "Approve", Process(),
                owner={"provider": "steam", "job_id": "job-cancel", "auth_id": "auth-cancel",
                       "pid": 88}, write_to_process=False))
            await asyncio.sleep(0)
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
            self.assertTrue(withdrawn.is_set())

        asyncio.run(exercise())

    def test_platform_policy_and_deterministic_commands(self) -> None:
        windows = SteamCmdExecutor(account="user", platforms={"263980": "windows"}, install_dir=Path("/games/Steam"))
        self.assertEqual(windows.command("263980"), [
            "/var/lib/lulu/steamcmd/steamcmd.sh", " +@sSteamCmdForcePlatformType".strip(), "windows",
            "+force_install_dir", "/games/Steam", "+login", "user", "+app_update", "263980", "validate", "+quit",
        ])
        self.assertNotIn("password", " ".join(windows.command("263980")).casefold())
        linux = SteamCmdExecutor(account="user", platforms={"42": "linux"})
        self.assertNotIn("+@sSteamCmdForcePlatformType", linux.command("42"))
        with self.assertRaisesRegex(Exception, "unknown"):
            linux.command("263980")

    def test_uninstall_is_provider_native_and_does_not_use_rm(self) -> None:
        executor = SteamCmdExecutor(account="user", platforms={"42": "linux"},
                                    install_dir=Path("/games/Steam"))
        command = executor.uninstall_command("42")
        self.assertEqual(command[-5:], ["+login", "user", "+app_uninstall", "42", "+quit"])
        self.assertNotIn("rm", " ".join(command))

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

    def test_cache_snapshot_records_metadata_without_contents(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            steam = home / ".steam"
            steam.mkdir()
            token = steam / "steam.token"
            registry = steam / "registry.vdf"
            token.write_bytes(b"secret-token")
            registry.write_text('"User" "private"\n')
            executor = SteamCmdExecutor(executable="/bin/true", account="user")
            with patch.dict("os.environ", {"HOME": str(home)}):
                snapshot = executor._cache_snapshot()
            self.assertTrue(snapshot["cache"]["steam_token"]["exists"])
            self.assertIn("inode", snapshot["cache"]["steam_token"])
            self.assertNotIn("secret-token", json.dumps(snapshot))
            self.assertNotIn("private", json.dumps(snapshot))

    def test_cache_events_detect_absent_replacement_mtime_and_registry(self) -> None:
        absent = {"exists": False}
        old_token = {"exists": True, "inode": 10, "mtime_ns": 1}
        new_token = {"exists": True, "inode": 11, "mtime_ns": 2}
        old_registry = {"exists": True, "inode": 20, "mtime_ns": 3}
        new_registry = {"exists": True, "inode": 20, "mtime_ns": 4}
        before = {"cache": {"steam_token": absent, "registry_vdf": absent}}
        after = {"cache": {"steam_token": old_token, "registry_vdf": new_registry}}
        events = SteamCmdExecutor._cache_events(before, after)
        self.assertIn("steam.token created", events)
        self.assertIn("registry.vdf created", events)
        before = {"cache": {"steam_token": old_token, "registry_vdf": old_registry}}
        after = {"cache": {"steam_token": new_token, "registry_vdf": new_registry}}
        events = SteamCmdExecutor._cache_events(before, after)
        self.assertIn("steam.token replaced inode 10 -> 11", events)
        self.assertIn("registry.vdf mtime changed", events)

    def test_lifecycle_diagnostic_is_redacted_and_exit_is_correlated(self) -> None:
        with self.assertLogs("lulu.steamcmd", level="INFO") as captured:
            SteamCmdExecutor._diagnostic({"event": "exit", "secret": "must-not-appear",
                                          "cache_events": ["steam.token mtime changed"]})
        self.assertIn("steamcmd_lifecycle", captured.output[0])
        self.assertNotIn("must-not-appear", captured.output[0])

    def test_runtime_and_provisioning_paths_do_not_touch_steam_home_state(self) -> None:
        root = Path(__file__).parents[1]
        runtime = (root / "scripts/dev-runtime.sh").read_text()
        provision = (root / "scripts/provision-steamcmd.sh").read_text()
        self.assertNotIn(".steam", runtime)
        self.assertNotIn(".steam", provision)
        self.assertNotIn("steam.token", runtime + provision)
        self.assertNotIn("registry.vdf", runtime + provision)

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
            with patch("asyncio.create_subprocess_exec", new=AsyncMock(return_value=process)), \
                    patch.object(executor, "_finalize_staged_install", return_value=Path("/games/out")):
                await manager._tasks[job.job_id]
            result = manager.jobs[job.job_id]
            self.assertEqual(result.state, JobState.COMPLETED)
            self.assertEqual(result.progress, 1.0)
            self.assertIsNone(result.downloaded_bytes)
            self.assertIsNone(result.total_bytes)
        asyncio.run(exercise())

    def test_safe_install_directory_rejects_traversal(self) -> None:
        common = Path("/games/steamapps/common")
        with self.assertRaisesRegex(Exception, "installdir"):
            SteamCmdExecutor._safe_install_directory(common, "../outside")
        with self.assertRaisesRegex(Exception, "installdir"):
            SteamCmdExecutor._safe_install_directory(common, "/absolute")

    def test_install_command_accepts_provider_owned_staging_path(self) -> None:
        executor = SteamCmdExecutor(account="user", platforms={"42": "linux"})
        command = executor.command("42", force_install_dir=Path("/games/.mudos-staging/job"))
        self.assertEqual(command[command.index("+force_install_dir") + 1],
                         "/games/.mudos-staging/job")

    def test_existing_manifest_selects_direct_update_target(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "Steam"
            manifest_dir = root / "steamapps"
            target = manifest_dir / "common" / "Example"
            target.mkdir(parents=True)
            (manifest_dir / "appmanifest_42.acf").write_text(
                '"AppState" { "appid" "42" "name" "Example" '
                '"StateFlags" "4" "installdir" "Example" }'
            )
            executor = SteamCmdExecutor(account="user", platforms={"42": "linux"}, install_dir=root)
            self.assertEqual(executor._existing_update_target("42"), target.resolve())

    def test_update_run_passes_existing_payload_to_force_install_dir(self) -> None:
        async def exercise() -> None:
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory) / "Steam"
                target = root / "steamapps/common/Example"
                target.mkdir(parents=True)
                manifest = root / "steamapps/appmanifest_42.acf"
                manifest.write_text(
                    '"AppState" { "appid" "42" "name" "Example" '
                    '"StateFlags" "4" "installdir" "Example" }'
                )
                class Process:
                    returncode = 0
                    stdout = asyncio.StreamReader()
                    stderr = asyncio.StreamReader()
                    async def wait(self): return self.returncode
                process = Process()
                process.stdout.feed_data(b"Success! App '42' fully installed.\n")
                process.stdout.feed_eof(); process.stderr.feed_eof()
                executor = SteamCmdExecutor(executable="/bin/true", account="user",
                                             platforms={"42": "linux"}, install_dir=root)
                manager = JobManager(); manager.register_executor("steam", executor)
                job = manager.submit("steam", "steam:42", "Example")
                with patch("asyncio.create_subprocess_exec", new=AsyncMock(return_value=process)), \
                        patch.object(executor, "command", wraps=executor.command) as command, \
                        patch.object(executor, "_finalize_staged_install") as finalize:
                    await manager._tasks[job.job_id]
                self.assertEqual(command.call_args.kwargs["force_install_dir"], target.resolve())
                finalize.assert_not_called()
        asyncio.run(exercise())

    def test_missing_manifest_does_not_trust_arbitrary_common_directory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "Steam"
            (root / "steamapps/common/Example").mkdir(parents=True)
            executor = SteamCmdExecutor(account="user", platforms={"42": "linux"}, install_dir=root)
            self.assertIsNone(executor._existing_update_target("42"))

    def test_fresh_promotion_renames_payload_and_manifest_atomically(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "Steam"
            staging = root / ".mudos-steam-staging/job-1/payload"
            (staging / "steamapps").mkdir(parents=True)
            (staging / "steamapps/downloading").mkdir()
            (staging / "steamapps/temp").mkdir()
            (staging / "game.bin").write_text("payload")
            (staging / "steamapps/appmanifest_42.acf").write_text(
                '"AppState" { "appid" "42" "name" "Example" '
                '"StateFlags" "4" "installdir" "Example" }'
            )
            executor = SteamCmdExecutor(account="user", platforms={"42": "linux"}, install_dir=root)
            target = executor._finalize_staged_install("42", staging)
            self.assertEqual(target, (root / "steamapps/common/Example").resolve())
            self.assertTrue((target / "game.bin").is_file())
            self.assertFalse((target / "steamapps").exists())
            self.assertTrue((root / "steamapps/appmanifest_42.acf").is_file())
            self.assertFalse((root / ".mudos-steam-staging/job-1").exists())

    def test_fresh_promotion_never_overwrites_existing_install(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "Steam"
            target = root / "steamapps/common/Example"
            target.mkdir(parents=True)
            (target / "keep.bin").write_text("keep")
            staging = root / ".mudos-steam-staging/job-2/payload"
            (staging / "steamapps").mkdir(parents=True)
            (staging / "game.bin").write_text("new")
            (staging / "steamapps/appmanifest_42.acf").write_text(
                '"AppState" { "appid" "42" "name" "Example" '
                '"StateFlags" "4" "installdir" "Example" }'
            )
            executor = SteamCmdExecutor(account="user", platforms={"42": "linux"}, install_dir=root)
            with self.assertRaisesRegex(Exception, "existing install"):
                executor._finalize_staged_install("42", staging)
            self.assertTrue((target / "keep.bin").is_file())

    def test_staging_cleanup_is_job_attributable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "Steam"
            stale = root / ".mudos-steam-staging/job-3/payload"
            stale.mkdir(parents=True)
            executor = SteamCmdExecutor(account="user", platforms={"42": "linux"}, install_dir=root)
            executor.cleanup_staging("job-3")
            self.assertFalse(stale.parent.exists())

if __name__ == "__main__":
    unittest.main()
