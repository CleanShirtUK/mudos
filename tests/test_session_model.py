import unittest
import asyncio
from unittest.mock import patch

from lulu.console_sessiond import SessionStateModel
from lulu.contracts import InputMode, Lifecycle, Presentation
from lulu.process_supervisor import ProcessSupervisor


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


if __name__ == "__main__":
    unittest.main()
