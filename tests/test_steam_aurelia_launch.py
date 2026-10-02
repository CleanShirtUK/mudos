from __future__ import annotations

import asyncio
import unittest
from unittest.mock import patch

from lulu.console_sessiond import SessionStateModel
from lulu.plugins.steam.aurelia import AureliaError
from lulu.plugins.steam.provider import SteamProvider
from lulu.process_supervisor import ProcessSupervisor


class FakeCLI:
    pid = 30001
    returncode = None

    def terminate(self):
        self.returncode = -15

    async def wait(self):
        return self.returncode


class FakeAurelia:
    def __init__(self, *, running=None, cli=None, daemon_states=None):
        self.process = cli or FakeCLI()
        self.running_value = running if running is not None else {
            "running": [{"app_id": "945360", "pid": 30003}]
        }
        self.stopped = []
        self.daemon_states = iter(daemon_states) if daemon_states is not None else None

    async def spawn_play(self, app_id):
        self.app_id = app_id
        return self.process

    async def running(self):
        if isinstance(self.running_value, Exception):
            raise self.running_value
        return self.running_value

    async def running_record(self, app_id):
        if isinstance(self.running_value, Exception):
            raise self.running_value
        if not isinstance(self.running_value, dict):
            raise AureliaError("malformed-running-state", "bad running record")
        rows = self.running_value.get("running")
        if rows == "bad":
            raise AureliaError("malformed-running-state", "bad running record")
        if not isinstance(rows, list):
            return None
        return next((row for row in rows if isinstance(row, dict)
                     and str(row.get("app_id")) == app_id), None)

    def daemon_alive(self):
        if self.daemon_states is not None:
            return next(self.daemon_states, False)
        return True

    async def stop(self, app_id):
        self.stopped.append(app_id)
        return {"stopped": True}


class AureliaSessionLaunchTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.model = SessionStateModel()
        self.supervisor = ProcessSupervisor(self.model)
        self.provider = SteamProvider(poll_interval=0.001)
        self.supervisor._steam_provider = self.provider

    async def test_managed_cli_pid_is_not_game_and_verified_appid_pid_enters_running(self):
        cli = FakeCLI()
        aurelia = FakeAurelia(cli=cli)
        self.supervisor._aurelia_client = aurelia
        candidates = iter(([], [30002], [30002], []))
        self.provider._candidate_pids = lambda _app: next(candidates, [])
        self.provider._argv = lambda _pid: ("/games/example",)
        with patch("lulu.process_supervisor.os.getpgid", return_value=30002), \
                patch("lulu.process_supervisor.os.path.realpath", return_value="/games/example"), \
                patch.object(self.provider, "_process_has_app_id", return_value=True):
            token = self.supervisor.queue_aurelia_launch("945360", 1000)
            await self.supervisor._aurelia_launch_task
            self.assertEqual(self.model.state.lifecycle.value, "game")
            self.assertEqual(self.model.state.provider_id, "steam-aurelia")
            self.assertEqual(self.supervisor.active_identity.pid, 30002)
            self.assertNotEqual(aurelia.running_value["running"][0]["pid"], self.supervisor.active_identity.pid)
            self.assertNotEqual(cli.pid, self.supervisor.active_identity.pid)
            self.assertEqual(self.supervisor._watch_task.get_name(), f"aurelia-game-watch-{token}")
            cli.returncode = 0  # CLI completion is not evidence that the game exited.
            self.assertEqual(self.model.state.lifecycle.value, "game")
            await self.supervisor._watch_task
        self.assertEqual(self.model.state.lifecycle.value, "shell")

    async def test_runner_pid_without_exact_appid_evidence_never_enters_game(self):
        cli = FakeCLI()
        aurelia = FakeAurelia(cli=cli)
        self.supervisor._aurelia_client = aurelia
        candidates = iter(([], [30002]))
        self.provider._candidate_pids = lambda _app: next(candidates, [30002])
        cli.returncode = 2
        with patch.object(self.provider, "_process_has_app_id", return_value=False):
            token = self.supervisor.queue_aurelia_launch("945360", 1000)
            with self.assertRaisesRegex(ValueError, "exited before a verified game"):
                await self.supervisor._aurelia_launch_task
        self.assertEqual(self.model.state.lifecycle.value, "shell")
        self.assertEqual(self.model.last_result.token, token)
        self.assertEqual(self.model.last_result.outcome, "start-failed")

    async def test_daemon_disappearance_before_game_is_failure(self):
        aurelia = FakeAurelia(running={"running": []}, daemon_states=[True, False])
        self.supervisor._aurelia_client = aurelia
        self.provider._candidate_pids = lambda _app: []
        with self.assertRaisesRegex(ValueError, "daemon disappeared"):
            await self.supervisor._launch_aurelia("945360", 10000, self.model.request_launch("steam-aurelia:945360"))
        self.assertEqual(self.model.state.lifecycle.value, "shell")

    async def test_running_game_stop_uses_aurelia_and_cancel_is_rejected(self):
        aurelia = FakeAurelia()
        self.supervisor._aurelia_client = aurelia
        self.supervisor._aurelia_app_id = "945360"
        self.model.request_launch("steam-aurelia:945360")
        self.model.launch_starting(self.model.state.launch_token)
        self.model.primary_observed(self.model.state.launch_token)
        self.model.primary_started(self.model.state.launch_token)
        watcher = asyncio.create_task(asyncio.sleep(0))
        self.supervisor._watch_task = watcher
        with self.assertRaisesRegex(ValueError, "use StopGame"):
            await self.supervisor.cancel_launch()
        await self.supervisor.stop_aurelia_game()
        self.assertEqual(aurelia.stopped, ["945360"])

    async def test_malformed_running_json_is_launch_failure(self):
        aurelia = FakeAurelia(running={"running": "bad"})
        self.supervisor._aurelia_client = aurelia
        self.provider._candidate_pids = lambda _app: []
        token = self.model.request_launch("steam-aurelia:945360")
        with self.assertRaisesRegex(ValueError, "bad running record"):
            await self.supervisor._launch_aurelia("945360", 1000, token)
        self.assertEqual(self.model.state.lifecycle.value, "shell")

    async def test_pre_running_cancel_terminates_only_cli_and_verifies_no_game(self):
        aurelia = FakeAurelia(running={"running": []})
        self.supervisor._aurelia_client = aurelia
        self.provider._candidate_pids = lambda _app: []
        token = self.supervisor.queue_aurelia_launch("945360", 10000)
        for _ in range(50):
            if self.supervisor._aurelia_process is not None:
                break
            await asyncio.sleep(0.001)
        await self.supervisor.cancel_launch()
        self.assertEqual(aurelia.process.returncode, -15)
        self.assertEqual(aurelia.stopped, [])  # `stop <AppID>` is not launch cancellation.
        self.assertEqual(self.model.state.lifecycle.value, "shell")
        self.assertEqual(self.model.last_failure_reason, "launch cancelled")


if __name__ == "__main__":
    unittest.main()
