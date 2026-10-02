from __future__ import annotations

import asyncio
import json
import logging
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

from lulu.jobs import DownloadJob, JobState
from lulu.acquisition_store import AcquisitionStore
from lulu.job_manager import JobManager
from lulu.plugins.steam.aurelia import (
    AureliaAcquisitionExecutor, AureliaCapabilities, AureliaClient, AureliaInstalledGame,
    AureliaError, AureliaLaunchController, PROVIDER_ID, map_progress,
)
from lulu.paths import PATHS
from lulu.provider_config import ProviderConfigurationService


class AureliaClientTests(unittest.IsolatedAsyncioTestCase):
    async def test_auth_health_states_and_secret_free_errors(self):
        for payload, expected in [
            ({"logged_in": False}, "unauthenticated"),
            ({"logged_in": True}, "authenticated"),
            ({"authentication_required": True}, "authentication-required"),
            ({"session_expired": True}, "authentication-expired"),
        ]:
            client = AureliaClient("fake", Path(tempfile.mkdtemp()),
                                  run=lambda *a, value=payload, **kw: (0, json.dumps(value), ""))
            self.assertEqual(await client.auth_status(), expected)

        def fail(*_args, **_kwargs):
            return 1, "", "refresh_token=must-not-leak"
        client = AureliaClient("fake", Path(tempfile.mkdtemp()), run=fail)
        with self.assertRaises(AureliaError) as caught:
            await client.command("login", "--health")
        self.assertNotIn("must-not-leak", str(caught.exception))

    async def test_missing_and_malformed_output(self):
        self.assertEqual(await AureliaClient("/nonexistent/aurelia").auth_status(), "unavailable")
        client = AureliaClient("fake", Path(tempfile.mkdtemp()), run=lambda *a, **kw: (0, "{", ""))
        with self.assertRaises(AureliaError) as caught:
            await client.command("libraries")
        self.assertEqual(caught.exception.code, "malformed-output")

    async def test_installed_game_mapping(self):
        client = AureliaClient("fake", Path(tempfile.mkdtemp()),
                               run=lambda *a, **kw: (0, json.dumps([{
                                   "app_id": 40800, "name": "Super Meat Boy",
                                   "is_installed": True,
                                   "install_path": "/steamapps/common/Super Meat Boy",
                                   "platform": "linux", "update_available": False,
                               }]), ""))
        (game,) = await client.installed_games()
        self.assertEqual(game.provider, "steam-aurelia")
        self.assertEqual(game.app_id, "40800")
        self.assertTrue(game.installed)
        self.assertEqual(game.platform, "linux")

    async def test_daemon_config_directory_is_private(self):
        root = Path(tempfile.mkdtemp()) / "aurelia"
        client = AureliaClient("fake", root, run=lambda *a, **kw: (0, "{}", ""))
        await client.command("libraries")
        self.assertEqual(root.stat().st_mode & 0o777, 0o700)
        config = json.loads((root / "config.json").read_text())
        self.assertEqual(config["steam_library_path"], str(PATHS.steam_library_root))
        self.assertFalse(config["enable_cloud_sync"])
        self.assertEqual((root / "config.json").stat().st_mode & 0o777, 0o600)

    async def test_daemon_socket_is_stable_for_the_mudos_runtime(self):
        client = AureliaClient("fake", Path(tempfile.mkdtemp()),
                               run=lambda *a, **kw: (0, "{}", ""))
        with tempfile.TemporaryDirectory() as runtime:
            with patch.dict(os.environ, {"XDG_RUNTIME_DIR": runtime}):
                env = client._environment()
            self.assertEqual(env["AURELIA_DAEMON_SOCKET"],
                             f"{runtime}/aurelia-{os.geteuid()}.sock")

    async def test_existing_noncanonical_library_fails_closed(self):
        root = Path(tempfile.mkdtemp()) / "aurelia"
        root.mkdir(mode=0o700)
        (root / "config.json").write_text(json.dumps({"steam_library_path": "/not/the/mudos/library"}))
        client = AureliaClient("fake", root, run=lambda *a, **kw: (0, "{}", ""))
        with self.assertRaises(AureliaError) as caught:
            await client.command("libraries")
        self.assertEqual(caught.exception.code, "library-path-mismatch")


class AureliaAcquisitionTests(unittest.IsolatedAsyncioTestCase):
    async def test_progress_mapping_preserves_unknown_fields(self):
        mapped = map_progress({"event": "progress", "state": "downloading",
                               "bytes_downloaded": 64, "total_bytes": 128, "percent": 50,
                               "speed_bps": 1024, "eta_seconds": 20})
        self.assertEqual(mapped["downloaded_bytes"], 64)
        self.assertEqual(mapped["total_bytes"], 128)
        self.assertEqual(mapped["progress"], 0.5)
        self.assertEqual(mapped["download_rate"], 1024)
        self.assertEqual(mapped["eta_seconds"], 20)
        listed = map_progress({"app_id": 123, "downloaded_bytes": 80,
                               "total_bytes": 100, "percent": 80,
                               "status": "Downloading"})
        self.assertEqual(listed["downloaded_bytes"], 80)
        self.assertEqual(listed["stage"], "Downloading")
        self.assertEqual(map_progress({"state": "verifying"})["progress"], None)

    async def test_executor_maps_success_and_failure(self):
        class Client:
            async def command(self, *_args): return []
            async def install_events(self, _app_id):
                yield {"event": "progress", "state": "downloading",
                       "bytes_downloaded": 2, "total_bytes": 4, "percent": 50,
                       "speed_bps": 12, "eta_seconds": 1}
            async def installed_games(self):
                from lulu.plugins.steam.aurelia import AureliaInstalledGame
                return (AureliaInstalledGame(PROVIDER_ID, "123", "Example", True,
                                             "/steam/common/Example", "windows", False),)

        class Reporter:
            def __init__(self): self.events = []
            async def state(self, state, **kw): self.events.append(("state", state, kw))
            async def progress(self, progress=None, **kw): self.events.append(("progress", progress, kw))
            async def metadata(self, **kw): self.events.append(("metadata", kw))

        reporter = Reporter()
        executor = AureliaAcquisitionExecutor(Client())
        job = DownloadJob("job", PROVIDER_ID, "Example", content_identity="steam-aurelia:123")
        await executor.run(job, reporter)
        self.assertIn(("state", JobState.COMPLETED, {"stage": "completed"}), reporter.events)
        progress = next(event for event in reporter.events if event[0] == "progress")
        self.assertEqual(progress[2]["downloaded_bytes"], 2)
        final_progress = [event for event in reporter.events if event[0] == "progress"][-1]
        self.assertEqual(final_progress[1], 1.0)
        self.assertEqual(final_progress[2]["downloaded_bytes"], 2)
        self.assertEqual(final_progress[2]["total_bytes"], 4)
        metadata = [event[1] for event in reporter.events if event[0] == "metadata"]
        self.assertTrue(any(item.get("destination") == "/steam/common/Example" for item in metadata))
        self.assertTrue(any(item.get("provider_job_id") == "123" for item in metadata))

    async def test_successful_job_persists_aurelia_telemetry_and_destination(self):
        class Client:
            async def command(self, *_args):
                return []
            async def install_events(self, _app_id):
                yield {"event": "progress", "state": "downloading",
                       "bytes_downloaded": 90, "total_bytes": 100,
                       "percent": 90.0, "speed_bps": 40, "eta_seconds": 1,
                       "depot_id": 42, "depot_bytes_downloaded": 45,
                       "depot_total_bytes": 50, "depot_percent": 90.0,
                       "file": "depot_chunk_01"}
            async def installed_games(self):
                return (AureliaInstalledGame(PROVIDER_ID, "123", "Example", True,
                                             "/steamapps/common/Example", "windows", False),)

        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "jobs.sqlite3"
            store = AcquisitionStore(database)
            manager = JobManager(store=store)
            manager.register_executor(PROVIDER_ID, AureliaAcquisitionExecutor(Client()))
            job = manager.submit(PROVIDER_ID, "steam-aurelia:123", "Example",
                                 provider_job_id="123", cancellation_supported=True)
            task = manager._tasks[job.job_id]
            await task
            restored_store = AcquisitionStore(database)
            (restored,) = [item for item in restored_store.load() if item.job_id == job.job_id]
            self.assertEqual(restored.state, JobState.COMPLETED)
            self.assertEqual(restored.provider_job_id, "123")
            self.assertEqual(restored.backend, "aurelia")
            self.assertEqual(restored.provider_state, "installed")
            self.assertEqual(restored.downloaded_bytes, 90)
            self.assertEqual(restored.total_bytes, 100)
            self.assertEqual(restored.destination, "/steamapps/common/Example")
            self.assertEqual(restored.completion_path, "/steamapps/common/Example")
            self.assertEqual(restored.origin_metadata["aurelia_progress"]["depot_id"], 42)
            self.assertEqual(restored.origin_metadata["aurelia_progress"]["file"], "depot_chunk_01")
            restored_store.close()
            store.close()

    async def test_cancel_waits_for_aurelia_active_registry_to_clear(self):
        calls = []
        def run(argv, **_kwargs):
            args = tuple(argv[2:])
            calls.append(args)
            if args[:2] == ("install", "stop"):
                value = {"event": "stopping", "app_id": 123}
            elif len(calls) == 2:
                value = [{"app_id": 123, "is_downloading": True}]
            else:
                value = []
            return 0, json.dumps(value), ""

        client = AureliaClient("fake", Path(tempfile.mkdtemp()), run=run)
        await client.cancel_install("123", timeout=1)
        self.assertEqual(calls[0], ("install", "stop", "123"))
        self.assertEqual(calls[1], ("install", "list"))
        self.assertEqual(calls[-1], ("install", "list"))


class AureliaLaunchTests(unittest.IsolatedAsyncioTestCase):
    async def test_running_record_reads_aurelia_runner_pid_without_cli_query(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory)
            running = config / "running"
            running.mkdir()
            (running / "104200.json").write_text(
                json.dumps({"app_id": 104200, "name": "BEEP", "pid": 4321})
            )
            client = AureliaClient(executable="aurelia", config_dir=config, run=lambda *_a, **_k: None)
            self.assertEqual(await client.running_record("104200"),
                             {"app_id": 104200, "name": "BEEP", "pid": 4321})
            self.assertIsNone(await client.running_record("945360"))

    async def test_malformed_running_record_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory)
            running = config / "running"
            running.mkdir()
            (running / "104200.json").write_text('{"app_id":104200,"pid":"not-a-pid"}')
            client = AureliaClient(executable="aurelia", config_dir=config, run=lambda *_a, **_k: None)
            with self.assertRaisesRegex(AureliaError, "invalid AppID/PID"):
                await client.running_record("104200")

    async def test_running_pid_requires_exact_kernel_appid_evidence(self):
        class Client:
            available = True
            async def launch(self, _app_id): await asyncio.Event().wait()
            async def running(self): return {"running": [{"app_id": "40800", "pid": 999}]}

        controller = AureliaLaunchController(Client())
        await controller.request("40800")
        with patch("lulu.plugins.steam.aurelia._process_has_app_id", return_value=False):
            self.assertEqual(await controller.observe(), "preparing")
        self.assertIsNone(controller.runner_pid)
        await controller.cancel_preparing()
        self.assertEqual(controller.state, "cancelled")

    async def test_malformed_running_state_does_not_claim_game_running(self):
        class Client:
            available = True
            async def launch(self, _app_id): await asyncio.Event().wait()
            async def running(self): return {"running": "not-a-list"}

        controller = AureliaLaunchController(Client())
        await controller.request("40800")
        self.assertEqual(await controller.observe(), "preparing")
        self.assertEqual(controller.error, "malformed-running-state")
        await controller.cancel_preparing()

    async def test_coarse_state_and_cancel_remain_provider_operation_only(self):
        class Client:
            available = True
            def __init__(self): self.started = asyncio.Event()
            async def launch(self, _app_id):
                self.started.set()
                await asyncio.Event().wait()
            async def running(self): return {"running": [{"app_id": 40800, "pid": 999}]}
            async def stop(self, _app_id): return {}

        client = Client()
        controller = AureliaLaunchController(client)
        self.assertTrue(controller.can_launch("40800"))
        await controller.request("40800")
        await client.started.wait()
        with patch("lulu.plugins.steam.aurelia._process_has_app_id", return_value=True):
            self.assertEqual(await controller.observe(), "running")
        state = await controller.stop()
        self.assertEqual(state, "cancelled")
        snapshot = controller.snapshot()
        self.assertEqual(snapshot["provider"], PROVIDER_ID)
        self.assertFalse(snapshot["detailed_launch_progress"])


class AureliaOptInTests(unittest.TestCase):
    def test_backend_disabled_by_default(self):
        config = ProviderConfigurationService(system_path=Path("/nonexistent"),
                                              user_path=Path("/nonexistent"))
        self.assertFalse(config.provider("providers.steam_aurelia").enabled)
        self.assertEqual(PROVIDER_ID, "steam-aurelia")
        self.assertEqual(AureliaCapabilities().detailed_launch_progress, False)


if __name__ == "__main__":
    unittest.main()
