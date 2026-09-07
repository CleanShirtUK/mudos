import unittest
import asyncio
from unittest.mock import patch

from lulu.console_sessiond import SessionStateModel
from lulu.contracts import Lifecycle
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
        self.assertEqual(session.state.lifecycle, Lifecycle.LAUNCHING)
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

    def test_invalid_started_and_exit_transitions_are_rejected(self) -> None:
        session = SessionStateModel()
        with self.assertRaises(ValueError):
            session.primary_started("missing")
        token = session.request_launch("game")
        with self.assertRaises(ValueError):
            session.primary_exited(token)

    def test_empty_primary_id_is_rejected_and_new_launch_clears_failure(self) -> None:
        session = SessionStateModel()
        with self.assertRaises(ValueError):
            session.request_launch("")
        token = session.request_launch("first")
        session.fail(token, "failed")
        session.return_complete(token)
        session.request_launch("second")
        self.assertIsNone(session.last_failure_reason)

    def test_start_timeout_returns_to_shell_without_an_active_process(self) -> None:
        async def delayed_spawn(*_args, **_kwargs):
            await asyncio.sleep(0.05)

        async def exercise() -> None:
            session = SessionStateModel()
            supervisor = ProcessSupervisor(session)
            with patch("asyncio.create_subprocess_exec", new=delayed_spawn):
                with self.assertRaises(ValueError):
                    await supervisor.launch(["slow-start"], 1)
            self.assertEqual(session.state.lifecycle, Lifecycle.SHELL)
            self.assertIsNone(supervisor.active_identity)
            self.assertEqual(session.last_result.outcome, "timeout")

        asyncio.run(exercise())


if __name__ == "__main__":
    unittest.main()
