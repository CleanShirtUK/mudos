from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
import tempfile
import unittest
from unittest.mock import AsyncMock

from lulu.jobs import DownloadJob, JobState
from lulu.plugins.steam.aurelia import (
    AureliaAcquisitionExecutor, AureliaCapabilities, AureliaClient,
    AureliaError, AureliaLaunchController, PROVIDER_ID, map_progress,
)
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
        self.assertEqual(await AureliaClient(None).auth_status(), "unavailable")
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
        self.assertEqual(map_progress({"state": "verifying"})["progress"], None)

    async def test_executor_maps_success_and_failure(self):
        class Client:
            async def command(self, *_args): return []
            async def install_events(self, _app_id):
                yield {"state": "downloading", "bytes_downloaded": 2, "total_bytes": 4, "percent": 50}

        class Reporter:
            def __init__(self): self.events = []
            async def state(self, state, **kw): self.events.append(("state", state, kw))
            async def progress(self, progress=None, **kw): self.events.append(("progress", progress, kw))

        reporter = Reporter()
        executor = AureliaAcquisitionExecutor(Client())
        job = DownloadJob("job", PROVIDER_ID, "Example", content_identity="steam-aurelia:123")
        await executor.run(job, reporter)
        self.assertIn(("state", JobState.COMPLETED, {"stage": "completed"}), reporter.events)
        progress = next(event for event in reporter.events if event[0] == "progress")
        self.assertEqual(progress[2]["downloaded_bytes"], 2)


class AureliaLaunchTests(unittest.IsolatedAsyncioTestCase):
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
