from __future__ import annotations

import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from lulu.console_sessiond import SessionStateModel
from lulu.contracts import InputMode
from lulu.plugins.steam.aurelia import AureliaError
from lulu.plugins.steam.provider import SteamProvider
from lulu.launch_identity import LaunchIdentity
from lulu.process_supervisor import ProcessSupervisor
from lulu.sessiond import ConsoleSessionInterface


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


class ReturnPresentation:
    def __init__(self, failures=0):
        self.failures = failures
        self.selected = None
        self.attempts = 0

    def select_pids(self, pids, timeout):
        self.selected = 800
        return 800

    def suspend_shell_window(self):
        return None

    def select_shell(self, pid):
        self.attempts += 1
        if self.attempts <= self.failures:
            raise RuntimeError("transient shell selection failure")
        self.selected = 900
        return 900

    def selected_base_window(self):
        return 900 if self.selected is not None else None

    def window_is_focusable(self, window):
        return self.selected == window


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
        self.provider.presentation_pids = lambda _app: next(candidates, [])
        with patch("lulu.process_supervisor.os.getpgid", return_value=30002), \
                patch("lulu.process_supervisor.os.path.realpath", return_value="/games/example"), \
                patch("lulu.process_supervisor.process_has_app_id", return_value=True), \
                patch("lulu.process_supervisor.process_argv", return_value=("/games/example",)):
            token = self.supervisor.queue_aurelia_launch("945360", 1000)
            await self.supervisor._aurelia_launch_task
            self.assertEqual(self.model.state.lifecycle.value, "game")
            self.assertEqual(self.model.state.provider_id, "steam-aurelia")
            self.assertEqual(aurelia.app_id, "945360")
            self.assertEqual(self.supervisor.active_identity.pid, 30002)
            self.assertNotEqual(aurelia.running_value["running"][0]["pid"], self.supervisor.active_identity.pid)
            self.assertNotEqual(cli.pid, self.supervisor.active_identity.pid)
            self.assertEqual(self.supervisor._watch_task.get_name(), f"aurelia-game-watch-{token}")
            cli.returncode = 0  # CLI completion is not evidence that the game exited.
            self.assertEqual(self.model.state.lifecycle.value, "game")
            await self.supervisor._watch_task
        self.assertEqual(self.model.state.lifecycle.value, "shell")

    async def test_request_path_remains_aurelia_and_never_selects_steamcmd(self):
        """Sessiond's accepted request stays on Aurelia; process monitoring is not a legacy launch."""
        cli = FakeCLI()
        cli.returncode = 0
        aurelia = FakeAurelia(cli=cli, running={"running": []})
        self.supervisor._aurelia_client = aurelia
        self.provider.presentation_pids = lambda _app: []
        presentation = ReturnPresentation()
        self.supervisor._presentation = presentation
        self.supervisor._shell_process = SimpleNamespace(pid=99, returncode=None)
        self.supervisor._shell_identity = LaunchIdentity("shell", 99, 99, "/shell", ("shell",))
        token = self.supervisor.queue_aurelia_launch("104200", 1000)
        with self.assertRaisesRegex(ValueError, "exited before a verified game"):
            await self.supervisor._aurelia_launch_task
        self.assertEqual(aurelia.app_id, "104200")
        self.assertIsNone(self.model.state.provider_id)
        self.assertEqual(self.model.state.lifecycle.value, "shell")
        self.assertEqual(presentation.selected, 900)
        self.assertIsNone(self.supervisor._aurelia_app_id)
        self.assertIsNone(self.supervisor._aurelia_process)
        self.assertIsNone(self.supervisor._steam_launch)
        self.assertEqual(self.model.last_result.token, token)
        self.assertFalse(hasattr(aurelia, "steamcmd"))

    async def test_aurelia_normal_exit_restores_native_controller_shell_profile(self):
        """Native-controller mode must not suppress the supervised SHELL reset."""
        sessiond = ConsoleSessionInterface.__new__(ConsoleSessionInterface)
        sessiond.model = self.model
        sessiond._native_controller = True
        sessiond._apply_input_mode = Mock()
        presentation = ReturnPresentation()
        self.supervisor = ProcessSupervisor(
            self.model, presentation=presentation,
            input_mode_changed=sessiond._apply_supervised_input_mode)
        self.supervisor._shell_process = SimpleNamespace(pid=99, returncode=None)
        self.supervisor._shell_identity = LaunchIdentity("shell", 99, 99, "/shell", ("shell",))
        provider = self.provider
        self.supervisor._steam_provider = provider
        self.supervisor._aurelia_client = FakeAurelia(
            running={"running": [{"app_id": "40800", "pid": 30003}]})
        candidates = iter(([], [30002], [30002], []))
        provider.presentation_pids = lambda _app: next(candidates, [])
        with patch("lulu.process_supervisor.os.getpgid", return_value=30002), \
                patch("lulu.process_supervisor.os.path.realpath", return_value="/games/supermeatboy"), \
                patch("lulu.process_supervisor.process_has_app_id", return_value=True), \
                patch("lulu.process_supervisor.process_argv", return_value=("/games/supermeatboy",)):
            token = self.supervisor.queue_aurelia_launch("40800", 1000)
            await self.supervisor._aurelia_launch_task
            self.assertEqual(self.model.state.lifecycle.value, "game")
            await self.supervisor._watch_task

        self.assertEqual(self.model.state.lifecycle.value, "shell")
        self.assertEqual(self.model.state.presentation.value, "shell")
        self.assertEqual(self.model.state.input_mode, InputMode.SHELL)
        self.assertEqual(self.model.last_result.token, token)
        self.assertIsNone(self.supervisor.active_identity)
        self.assertIsNone(self.supervisor._aurelia_app_id)
        self.assertIsNone(self.supervisor._aurelia_process)
        self.assertEqual(presentation.selected, 900)
        sessiond._apply_input_mode.assert_called_once_with(InputMode.SHELL)

    async def test_runner_pid_without_exact_appid_evidence_never_enters_game(self):
        cli = FakeCLI()
        aurelia = FakeAurelia(cli=cli)
        self.supervisor._aurelia_client = aurelia
        candidates = iter(([], [30002]))
        self.provider.presentation_pids = lambda _app: next(candidates, [30002])
        cli.returncode = 2
        with patch("lulu.process_supervisor.process_has_app_id", return_value=False):
            token = self.supervisor.queue_aurelia_launch("945360", 1000)
            with self.assertRaisesRegex(ValueError, "exited before a verified game"):
                await self.supervisor._aurelia_launch_task
        self.assertEqual(self.model.state.lifecycle.value, "shell")
        self.assertEqual(self.model.last_result.token, token)
        self.assertEqual(self.model.last_result.outcome, "start-failed")

    async def test_daemon_disappearance_before_game_is_failure(self):
        aurelia = FakeAurelia(running={"running": []}, daemon_states=[True, False])
        self.supervisor._aurelia_client = aurelia
        self.provider.presentation_pids = lambda _app: []
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
        self.provider.presentation_pids = lambda _app: []
        token = self.model.request_launch("steam-aurelia:945360")
        with self.assertRaisesRegex(ValueError, "bad running record"):
            await self.supervisor._launch_aurelia("945360", 1000, token)
        self.assertEqual(self.model.state.lifecycle.value, "shell")

    async def test_pre_running_cancel_terminates_only_cli_and_verifies_no_game(self):
        aurelia = FakeAurelia(running={"running": []})
        self.supervisor._aurelia_client = aurelia
        self.provider.presentation_pids = lambda _app: []
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

    def _prepare_returning(self, *, presentation=None, input_mode_changed=None):
        model = SessionStateModel()
        supervisor = ProcessSupervisor(
            model, presentation=presentation,
            input_mode_changed=input_mode_changed,
        )
        token = model.request_launch("steam-aurelia:945360")
        model.launch_starting(token)
        model.primary_observed(token)
        model.primary_started(token)
        identity = LaunchIdentity(token, 4100, 4100, "/game", ("/game",))
        supervisor.active_identity = identity
        supervisor._aurelia_app_id = "945360"
        supervisor._aurelia_process = FakeCLI()
        model.primary_exited(token)
        return model, supervisor, token

    async def test_return_retries_transient_shell_selection_and_clears_session_state(self):
        presentation = ReturnPresentation(failures=1)
        model, supervisor, token = self._prepare_returning(presentation=presentation)
        supervisor._shell_process = SimpleNamespace(pid=99, returncode=None)
        supervisor._shell_identity = LaunchIdentity("shell", 99, 99, "/shell", ("shell",))

        self.assertTrue(await supervisor._converge_supervised_return(token))
        self.assertEqual(presentation.attempts, 2)
        self.assertEqual(model.state.lifecycle.value, "shell")
        self.assertIsNone(supervisor.active_identity)
        self.assertIsNone(supervisor._aurelia_app_id)
        self.assertIsNone(supervisor._aurelia_process)
        self.assertTrue(await supervisor._converge_supervised_return(token))

    async def test_input_failure_does_not_block_verified_shell_return(self):
        presentation = ReturnPresentation()

        def fail_input(_mode):
            raise OSError("InputPlumber unavailable")

        model, supervisor, token = self._prepare_returning(
            presentation=presentation, input_mode_changed=fail_input,
        )
        supervisor._shell_process = SimpleNamespace(pid=99, returncode=None)
        supervisor._shell_identity = LaunchIdentity("shell", 99, 99, "/shell", ("shell",))

        self.assertTrue(await supervisor._converge_supervised_return(token))
        self.assertEqual(model.state.lifecycle.value, "shell")
        self.assertIn("input restoration failed", model.last_failure_reason)
        self.assertEqual(presentation.selected, 900)

    async def test_shell_failure_keeps_returning_even_when_input_restore_succeeds(self):
        presentation = ReturnPresentation(failures=99)
        input_modes = []
        model, supervisor, token = self._prepare_returning(
            presentation=presentation, input_mode_changed=input_modes.append,
        )
        supervisor._shell_process = SimpleNamespace(pid=99, returncode=None)
        supervisor._shell_identity = LaunchIdentity("shell", 99, 99, "/shell", ("shell",))

        self.assertFalse(await supervisor._converge_supervised_return(token))
        self.assertEqual(input_modes, [InputMode.SHELL])
        self.assertEqual(model.state.lifecycle.value, "returning")
        self.assertIn("shell presentation restoration failed", model.last_failure_reason)
        self.assertIsNone(supervisor.active_identity)
        self.assertIsNone(supervisor._aurelia_app_id)

        presentation.failures = 3
        self.assertTrue(await supervisor._converge_supervised_return(token))
        self.assertEqual(model.state.lifecycle.value, "shell")

    async def test_both_restore_failures_are_independent_and_diagnosed(self):
        presentation = ReturnPresentation(failures=99)

        def fail_input(_mode):
            raise OSError("profile load failed")

        model, supervisor, token = self._prepare_returning(
            presentation=presentation, input_mode_changed=fail_input,
        )
        supervisor._shell_process = SimpleNamespace(pid=99, returncode=None)
        supervisor._shell_identity = LaunchIdentity("shell", 99, 99, "/shell", ("shell",))

        self.assertFalse(await supervisor._converge_supervised_return(token))
        self.assertEqual(model.state.lifecycle.value, "returning")
        self.assertIn("input restoration failed", model.last_failure_reason)
        self.assertIn("shell presentation restoration failed", model.last_failure_reason)

    async def test_launch_failure_without_primary_uses_same_return_contract(self):
        presentation = ReturnPresentation()
        model = SessionStateModel()
        supervisor = ProcessSupervisor(model, presentation=presentation)
        token = model.request_launch("steam-aurelia:945360")
        model.launch_starting(token)
        supervisor._aurelia_app_id = "945360"
        supervisor._aurelia_process = FakeCLI()
        model.fail(token, "provider did not produce a game")
        supervisor._shell_process = SimpleNamespace(pid=99, returncode=None)
        supervisor._shell_identity = LaunchIdentity("shell", 99, 99, "/shell", ("shell",))

        self.assertTrue(await supervisor._converge_supervised_return(token))
        self.assertEqual(model.state.lifecycle.value, "shell")
        self.assertEqual(presentation.attempts, 1)
        self.assertIsNone(supervisor._aurelia_app_id)


if __name__ == "__main__":
    unittest.main()
