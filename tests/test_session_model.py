import unittest
import asyncio
from unittest.mock import AsyncMock, patch

from lulu.console_sessiond import SessionStateModel
from lulu.contracts import InputMode, Lifecycle, Presentation
from lulu.process_supervisor import ProcessSupervisor
from lulu.sessiond import ConsoleSessionInterface


class SessionModelTests(unittest.TestCase):
    def test_conflicting_launch_is_rejected(self) -> None:
        session = SessionStateModel()
        session.request_launch("first")
        with self.assertRaises(ValueError):
            session.request_launch("second")

    def test_wrong_token_cannot_complete_or_change_session(self) -> None:
        session = SessionStateModel()
        token = session.request_launch("game")
        with self.assertRaises(ValueError):
            session.primary_started("wrong")
        self.assertEqual(session.state.lifecycle, Lifecycle.LAUNCH_REQUESTED)
        session.launch_starting(token)
        with self.assertRaises(ValueError):
            session.return_complete("wrong")

    def test_failed_launch_returns_through_returning(self) -> None:
        session = SessionStateModel()
        token = session.request_launch("game")
        session.fail(token, "deterministic fixture failed")
        self.assertEqual(session.state.lifecycle, Lifecycle.RETURNING)
        self.assertEqual(session.last_failure_reason, "deterministic fixture failed")
        session.return_complete(token)
        self.assertEqual(session.state.lifecycle, Lifecycle.SHELL)

    def test_return_failure_keeps_returning_ownership(self) -> None:
        session = SessionStateModel()
        token = session.request_launch("game")
        session.fail(token, "launch failed")
        session.return_failed(token, "Presentation recovery failed: shell missing")
        self.assertEqual(session.state.lifecycle, Lifecycle.RETURNING)
        self.assertEqual(session.last_failure_reason, "Presentation recovery failed: shell missing")

    def test_invalid_started_and_exit_transitions_are_rejected(self) -> None:
        session = SessionStateModel()
        with self.assertRaises(ValueError):
            session.primary_started("missing")
        token = session.request_launch("game")
        session.launch_starting(token)
        with self.assertRaises(ValueError):
            session.primary_exited(token)

    def test_failed_generation_cannot_reenter_starting(self) -> None:
        session = SessionStateModel()
        token = session.request_launch("game")
        session.fail(token, "failed")
        with self.assertRaises(ValueError):
            session.launch_starting(token)

    def test_process_observed_enters_presentation_pending_before_running(self) -> None:
        session = SessionStateModel()
        token = session.request_launch("game")
        session.launch_starting(token)
        session.primary_observed(token)
        self.assertEqual(session.state.lifecycle, Lifecycle.PRESENTATION_PENDING)
        session.primary_started(token)
        self.assertEqual(session.state.lifecycle, Lifecycle.GAME)

    def test_steam_store_downloads_is_one_delegated_application(self) -> None:
        session = SessionStateModel()
        token = session.request_launch("steam-store")
        session.launch_starting(token)
        session.primary_started(token, presentation=Presentation.FOREIGN_UI, input_mode=InputMode.GAME)
        self.assertEqual(session.state.delegated_surface, "store")
        session.set_delegated_surface("downloads")
        self.assertEqual(session.state.primary_id, "steam-store")
        self.assertEqual(session.state.delegated_surface, "downloads")
        session.set_delegated_surface("store")
        self.assertEqual(session.state.delegated_surface, "store")

    def test_reset_tears_down_session_and_requests_service_restart(self) -> None:
        async def exercise() -> None:
            interface = ConsoleSessionInterface.__new__(ConsoleSessionInterface)
            interface.stop_controller_monitor = AsyncMock()
            interface.supervisor = type("Supervisor", (), {"stop": AsyncMock()})()
            with patch("lulu.sessiond.os.kill") as kill:
                await interface._reset_mudos()
            interface.stop_controller_monitor.assert_awaited_once()
            interface.supervisor.stop.assert_awaited_once()
            kill.assert_called_once()

        asyncio.run(exercise())
    def test_empty_primary_id_is_rejected_and_new_launch_clears_failure(self) -> None:
        session = SessionStateModel()
        with self.assertRaises(ValueError):
            session.request_launch("")
        token = session.request_launch("first")
        session.fail(token, "failed")
        session.return_complete(token)
        session.request_launch("second")
        self.assertIsNone(session.last_failure_reason)

    def test_shell_launch_keeps_shell_presentation_and_input_mode(self) -> None:
        async def exercise() -> None:
            session = SessionStateModel()
            supervisor = ProcessSupervisor(session)
            token = await supervisor.launch_shell(["/usr/bin/true"], 1000)
            await supervisor._watch_task
            self.assertEqual(session.state.lifecycle, Lifecycle.SHELL)
            self.assertEqual(session.state.presentation, Presentation.SHELL)
            self.assertEqual(session.state.input_mode, InputMode.SHELL)
            self.assertEqual(session.last_result.token, token)

        asyncio.run(exercise())

    def test_application_exit_restores_shell_input_mode(self) -> None:
        async def exercise() -> None:
            session = SessionStateModel()
            modes = []
            supervisor = ProcessSupervisor(session, input_mode_changed=modes.append)
            await supervisor.launch(["/bin/sh", "-c", "sleep 0.05"], 1000)
            session.set_input_mode(InputMode.COMPAT)
            await supervisor._watch_task
            self.assertEqual(modes[-1], InputMode.SHELL)
            self.assertEqual(session.state.input_mode, InputMode.SHELL)

        asyncio.run(exercise())


if __name__ == "__main__":
    unittest.main()
