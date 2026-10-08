import asyncio
from pathlib import Path
from types import SimpleNamespace
import time
import unittest
from unittest.mock import AsyncMock, Mock, patch

from lulu.gamescope import (PresentationOutputUnavailable, connected_presentation_outputs,
                            has_connected_presentation_output)
from lulu.console_sessiond import SessionStateModel
from lulu.sessiond import (ConsoleSessionInterface, restart_shell_after_display_loss,
                           restart_shell_after_drm_event)


ROOT = Path(__file__).resolve().parents[1]


class ApplianceSessionRecoveryTests(unittest.TestCase):
    def test_drm_connector_absence_is_a_recoverable_environment_state(self) -> None:
        with self.subTest("disconnected connector"):
            import tempfile

            with tempfile.TemporaryDirectory() as directory:
                connector = Path(directory) / "card0-DP-1"
                connector.mkdir()
                (connector / "status").write_text("disconnected\n")
                self.assertFalse(has_connected_presentation_output(directory))
                self.assertEqual(connected_presentation_outputs(directory), ())
                with self.assertRaises(PresentationOutputUnavailable):
                    from lulu.gamescope import discover_presentation_output
                    discover_presentation_output(directory)
                (connector / "status").write_text("connected\n")
                self.assertTrue(has_connected_presentation_output(directory))
                self.assertEqual(connected_presentation_outputs(directory), ("DP-1",))

    def test_sessiond_bootstrap_waits_for_drm_then_launches_without_exiting(self) -> None:
        interface = ConsoleSessionInterface.__new__(ConsoleSessionInterface)
        interface._bootstrap_output = None
        interface.recovery_mode = False
        interface.supervisor = SimpleNamespace(
            launch_shell=AsyncMock(), set_delegated_launch_environment=Mock(),
        )

        async def exercise() -> None:
            with patch("lulu.sessiond.has_connected_presentation_output", side_effect=[False, False, True]) as has_output, \
                    patch("lulu.sessiond.connected_presentation_outputs", return_value=("DP-1",)), \
                    patch("lulu.sessiond.discover_presentation_output", return_value="DP-1"), \
                    patch("lulu.sessiond.asyncio.sleep", new=AsyncMock()), \
                    patch.dict("os.environ", {}, clear=False):
                await interface.bootstrap_shell()
            self.assertEqual(has_output.call_count, 3)
            interface.supervisor.launch_shell.assert_awaited_once()
            command = interface.supervisor.launch_shell.await_args.args[0]
            self.assertIn("--prefer-output", command)
            self.assertIn("DP-1", command)

        asyncio.run(exercise())

    def test_appliance_target_owns_maintenance_vt_and_failures_do_not_switch_to_getty(self) -> None:
        target = (ROOT / "packaging/lulu.target").read_text()
        session = (ROOT / "packaging/lulu-session@.service").read_text()
        recovery = (ROOT / "packaging/mudos-recovery-ui.service").read_text()
        self.assertIn("Conflicts=getty@tty1.service", target)
        self.assertIn("Before=getty@tty1.service", target)
        self.assertIn("Conflicts=getty@tty%i.service", session)
        self.assertNotIn("ExecStopPost=+/opt/lulu/bin/lulu-vt restore", session)
        self.assertNotIn("ExecStopPost=+/opt/lulu/current/bin/lulu-vt restore", recovery)

    def test_gamescope_exit_with_no_connector_relaunches_after_output_returns(self) -> None:
        interface = SimpleNamespace(bootstrap_shell=AsyncMock())

        async def exercise() -> None:
            stop_task = asyncio.create_task(asyncio.Event().wait())
            try:
                with patch("lulu.sessiond.has_connected_presentation_output", return_value=False), \
                        patch("lulu.sessiond.asyncio.sleep", new=AsyncMock()):
                    recovered = await restart_shell_after_display_loss(interface, stop_task)
                self.assertTrue(recovered)
                interface.bootstrap_shell.assert_awaited_once()
            finally:
                stop_task.cancel()
                await asyncio.gather(stop_task, return_exceptions=True)

        asyncio.run(exercise())

    def test_gamescope_exit_with_display_still_connected_is_not_misclassified(self) -> None:
        interface = SimpleNamespace(bootstrap_shell=AsyncMock())

        async def exercise() -> None:
            stop_task = asyncio.create_task(asyncio.Event().wait())
            try:
                with patch("lulu.sessiond.has_connected_presentation_output", return_value=True), \
                        patch("lulu.sessiond.asyncio.sleep", new=AsyncMock()):
                    recovered = await restart_shell_after_display_loss(interface, stop_task)
                self.assertFalse(recovered)
                interface.bootstrap_shell.assert_not_awaited()
            finally:
                stop_task.cancel()
                await asyncio.gather(stop_task, return_exceptions=True)

        asyncio.run(exercise())

    def test_drm_event_restarts_shell_even_when_connector_stays_connected(self) -> None:
        interface = SimpleNamespace(bootstrap_shell=AsyncMock())

        async def exercise() -> None:
            stop_task = asyncio.create_task(asyncio.Event().wait())
            try:
                recovered = await restart_shell_after_drm_event(interface, stop_task)
                self.assertTrue(recovered)
                interface.bootstrap_shell.assert_awaited_once()
            finally:
                stop_task.cancel()
                await asyncio.gather(stop_task, return_exceptions=True)

        asyncio.run(exercise())

    def test_drm_hotplug_requests_only_idle_shell_recovery(self) -> None:
        interface = ConsoleSessionInterface.__new__(ConsoleSessionInterface)
        interface.model = SimpleNamespace(
            state=SimpleNamespace(lifecycle=SimpleNamespace(value="shell"))
        )
        interface._presentation_ready = True
        interface._graphical_session_id = "unit-hotplug"
        interface._graphical_launch_lease = None
        interface.StateChanged = Mock()
        interface._state_json = Mock(return_value="{}")
        interface._display_recovery_pending = False
        interface._display_recovery_requested = False
        interface._display_recovery_required = False
        interface._display_recovery_shell_token = None
        interface._display_recovery_attempted_token = None
        # A reconnect two seconds after the prior event must not inherit the
        # old ten-second recovery cooldown.
        interface._display_recovery_last_at = time.monotonic() - 2.0
        interface.supervisor = SimpleNamespace(
            shell_status=Mock(return_value=SimpleNamespace(token="shell-1", running=True)),
            set_delegated_launch_environment=Mock(),
            restart_shell_for_display_recovery=AsyncMock(return_value=True),
        )

        async def exercise() -> None:
            with patch("lulu.sessiond.asyncio.sleep", new=AsyncMock()), \
                    patch("lulu.sessiond.write_graphical_launch_context", return_value=True), \
                    patch.object(interface, "_state_json", return_value="{}"), \
                    patch.object(interface, "StateChanged"):
                await interface._handle_drm_hotplug()
            self.assertTrue(interface._display_recovery_requested)
            self.assertFalse(interface._presentation_ready)
            interface.supervisor.restart_shell_for_display_recovery.assert_awaited_once()

        asyncio.run(exercise())

    def test_surviving_gamescope_disconnect_watchdog_loss_then_fast_reconnect_recovers(self) -> None:
        """Regression: reconnect must recover after readiness was cleared on disconnect."""
        interface = ConsoleSessionInterface.__new__(ConsoleSessionInterface)
        interface.model = SessionStateModel()
        interface._presentation_ready = True
        interface._graphical_session_id = "display-reconnect-test"
        interface._graphical_launch_lease = None
        interface._state_json = Mock(return_value="{}")
        interface.StateChanged = Mock()
        interface._display_recovery_requested = False
        interface._display_recovery_pending = False
        interface._display_recovery_required = False
        interface._display_recovery_shell_token = None
        interface._display_recovery_attempted_token = None
        shell = SimpleNamespace(token="shell-before", pid=1234, running=True,
                                presentation_available=True)
        new_shell = SimpleNamespace(token="shell-after", pid=5678, running=True,
                                    presentation_available=True)
        new_environment = {
            "DISPLAY": ":new", "WAYLAND_DISPLAY": "wayland-new",
            "XAUTHORITY": "/tmp/new-auth", "XDG_RUNTIME_DIR": "/tmp/runtime",
        }
        delegated_environment = {}
        interface.supervisor = SimpleNamespace(
            shell_status=Mock(side_effect=[shell, shell, shell, new_shell]),
            shell_is_current=Mock(return_value=True),
            set_delegated_launch_environment=lambda values: delegated_environment.update(values),
            delegated_launch_environment=delegated_environment,
            ensure_shell_presentation=Mock(return_value=321),
            shell_graphical_environment=Mock(return_value=new_environment),
            restart_shell_for_display_recovery=AsyncMock(return_value=True),
        )

        async def exercise() -> None:
            connected = {"value": False}
            with patch("lulu.sessiond.has_connected_presentation_output",
                       side_effect=lambda *_args: connected["value"]), \
                    patch("lulu.sessiond.write_graphical_launch_context", return_value=True) as write_context, \
                    patch("lulu.sessiond.context_is_valid", return_value=True), \
                    patch("lulu.sessiond.graphical_context_is_live", return_value=True), \
                    patch("lulu.sessiond.asyncio.sleep", new=AsyncMock()):
                # Disconnect: the watchdog observes loss while Gamescope stays up.
                await interface._refresh_presentation_readiness()
                self.assertTrue(shell.running)
                self.assertFalse(interface._presentation_ready)
                self.assertTrue(interface._display_recovery_required)
                # Reconnect two seconds later: not-ready is expected, not a veto.
                connected["value"] = True
                await interface._handle_drm_hotplug()
                self.assertEqual(interface._display_recovery_shell_token, "shell-before")

                # Bootstrap has created a distinct shell and fresh environment.
                await interface._refresh_presentation_readiness()
                self.assertTrue(interface._presentation_ready)
                self.assertFalse(interface._display_recovery_required)
                self.assertIsNone(interface._display_recovery_shell_token)
                self.assertEqual(delegated_environment, new_environment)
                self.assertEqual(write_context.call_args.kwargs["shell_pid"], 5678)

            self.assertTrue(interface._display_recovery_requested)
            interface.supervisor.restart_shell_for_display_recovery.assert_awaited_once()

        asyncio.run(exercise())

    def test_absent_output_does_not_restart_and_later_reconnect_is_not_cooldown_blocked(self) -> None:
        interface = ConsoleSessionInterface.__new__(ConsoleSessionInterface)
        interface.model = SimpleNamespace(state=SimpleNamespace(
            lifecycle=SimpleNamespace(value="shell")))
        interface._presentation_ready = False
        interface._graphical_launch_lease = None
        interface._graphical_session_id = "absent-then-return"
        interface._state_json = Mock(return_value="{}")
        interface.StateChanged = Mock()
        interface._display_recovery_required = False
        interface._display_recovery_pending = False
        interface._display_recovery_requested = False
        interface._display_recovery_shell_token = None
        interface._display_recovery_attempted_token = None
        interface.supervisor = SimpleNamespace(
            shell_status=Mock(return_value=SimpleNamespace(token="shell-1", running=True)),
            set_delegated_launch_environment=Mock(),
            restart_shell_for_display_recovery=AsyncMock(return_value=True),
        )

        async def exercise() -> None:
            with patch("lulu.sessiond.has_connected_presentation_output", return_value=False), \
                    patch("lulu.sessiond.asyncio.sleep", new=AsyncMock()), \
                    patch("lulu.sessiond.write_graphical_launch_context", return_value=True):
                await interface._handle_drm_hotplug()
                await interface._handle_drm_hotplug()
            interface.supervisor.restart_shell_for_display_recovery.assert_not_awaited()
            self.assertTrue(interface._display_recovery_required)
            self.assertFalse(interface._display_recovery_pending)

            # Reconnect immediately after absence; no prior event timestamp can veto it.
            with patch("lulu.sessiond.has_connected_presentation_output", return_value=True), \
                    patch("lulu.sessiond.asyncio.sleep", new=AsyncMock()), \
                    patch("lulu.sessiond.write_graphical_launch_context", return_value=True):
                await interface._handle_drm_hotplug()
                await interface._handle_drm_hotplug()
            interface.supervisor.restart_shell_for_display_recovery.assert_awaited_once()
            self.assertTrue(interface._display_recovery_pending)

        asyncio.run(exercise())

    def test_game_hotplug_defers_restart_until_shell_ownership_returns(self) -> None:
        lifecycle = SimpleNamespace(value="game")
        interface = ConsoleSessionInterface.__new__(ConsoleSessionInterface)
        interface.model = SimpleNamespace(state=SimpleNamespace(lifecycle=lifecycle))
        interface._display_recovery_required = False
        interface._display_recovery_pending = False
        interface._display_recovery_requested = False
        interface._display_recovery_shell_token = None
        interface._display_recovery_attempted_token = None
        interface._presentation_ready = True
        interface._graphical_launch_lease = None
        interface._graphical_session_id = "game-defer"
        interface._state_json = Mock(return_value="{}")
        interface.StateChanged = Mock()
        interface.supervisor = SimpleNamespace(
            shell_status=Mock(return_value=SimpleNamespace(token="shell-after-game", running=True)),
            set_delegated_launch_environment=Mock(),
            restart_shell_for_display_recovery=AsyncMock(return_value=True),
        )

        async def exercise() -> None:
            with patch("lulu.sessiond.has_connected_presentation_output", return_value=True), \
                    patch("lulu.sessiond.asyncio.sleep", new=AsyncMock()), \
                    patch("lulu.sessiond.write_graphical_launch_context", return_value=True):
                await interface._handle_drm_hotplug()
                interface.supervisor.restart_shell_for_display_recovery.assert_not_awaited()
                self.assertTrue(interface._display_recovery_required)
                lifecycle.value = "shell"
                await interface._handle_drm_hotplug()
            interface.supervisor.restart_shell_for_display_recovery.assert_awaited_once()

        asyncio.run(exercise())

    def test_failed_shell_recovery_does_not_latch_future_retry(self) -> None:
        interface = ConsoleSessionInterface.__new__(ConsoleSessionInterface)
        interface.model = SimpleNamespace(state=SimpleNamespace(
            lifecycle=SimpleNamespace(value="shell")))
        interface._presentation_ready = False
        interface._graphical_launch_lease = None
        interface._graphical_session_id = "retry-recovery"
        interface._state_json = Mock(return_value="{}")
        interface.StateChanged = Mock()
        interface._display_recovery_required = True
        interface._display_recovery_pending = False
        interface._display_recovery_requested = False
        interface._display_recovery_shell_token = None
        interface._display_recovery_attempted_token = None
        interface.supervisor = SimpleNamespace(
            shell_status=Mock(return_value=SimpleNamespace(token="shell-1", running=True)),
            set_delegated_launch_environment=Mock(),
            restart_shell_for_display_recovery=AsyncMock(side_effect=[False, True]),
        )

        async def exercise() -> None:
            with patch("lulu.sessiond.has_connected_presentation_output", return_value=True), \
                    patch("lulu.sessiond.asyncio.sleep", new=AsyncMock()), \
                    patch("lulu.sessiond.write_graphical_launch_context", return_value=True):
                await interface._handle_drm_hotplug()
                self.assertFalse(interface._display_recovery_pending)
                self.assertTrue(interface._display_recovery_required)
                await interface._handle_drm_hotplug()
            self.assertEqual(interface.supervisor.restart_shell_for_display_recovery.await_count, 2)
            self.assertTrue(interface._display_recovery_pending)

        asyncio.run(exercise())

    def test_presentation_monitor_reconciles_recovery_pending_when_shell_returns(self) -> None:
        interface = ConsoleSessionInterface.__new__(ConsoleSessionInterface)
        interface.model = SimpleNamespace(state=SimpleNamespace(
            lifecycle=SimpleNamespace(value="shell")))
        interface._display_recovery_required = True
        interface._display_recovery_pending = False
        interface._display_recovery_attempted_token = None
        interface.supervisor = SimpleNamespace(
            shell_status=Mock(return_value=SimpleNamespace(token="returned-shell", running=True)))
        interface._refresh_presentation_readiness = AsyncMock()
        interface._handle_drm_hotplug = AsyncMock()
        interface._reconcile_game_presentation = AsyncMock()

        async def stop_after_one_tick(_seconds: float) -> None:
            raise asyncio.CancelledError

        async def exercise() -> None:
            with patch("lulu.sessiond.has_connected_presentation_output", return_value=True), \
                    patch("lulu.sessiond.asyncio.sleep", side_effect=stop_after_one_tick):
                with self.assertRaises(asyncio.CancelledError):
                    await interface._monitor_presentation()
            interface._refresh_presentation_readiness.assert_awaited_once()
            interface._handle_drm_hotplug.assert_awaited_once()
            interface._reconcile_game_presentation.assert_awaited_once()

        asyncio.run(exercise())

    def test_standalone_recovery_keeps_running_when_drm_is_absent(self) -> None:
        source = (ROOT / "scripts/mudos-recovery-ui.py").read_text()
        self.assertIn("while True:", source)
        self.assertIn("if not has_connected_presentation_output()", source)
        self.assertIn("time.sleep(2.0)", source)
        self.assertIn("Recovery remains active for display return", source)
