import asyncio
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from lulu.gamescope import (PresentationOutputUnavailable, connected_presentation_outputs,
                            has_connected_presentation_output)
from lulu.sessiond import ConsoleSessionInterface, restart_shell_after_display_loss


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
        interface._select_ready_shell = AsyncMock()
        interface.supervisor = SimpleNamespace(launch_shell=AsyncMock())

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

    def test_standalone_recovery_keeps_running_when_drm_is_absent(self) -> None:
        source = (ROOT / "scripts/mudos-recovery-ui.py").read_text()
        self.assertIn("while True:", source)
        self.assertIn("if not has_connected_presentation_output()", source)
        self.assertIn("time.sleep(2.0)", source)
        self.assertIn("Recovery remains active for display return", source)
