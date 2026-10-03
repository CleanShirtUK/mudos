from __future__ import annotations

import asyncio
import os
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from lulu.console_sessiond import SessionStateModel
from lulu.contracts import Lifecycle
from lulu.launch_identity import LaunchIdentity
from lulu.sessiond import ConsoleSessionInterface


class PresentationFake:
    def __init__(self, selected=(10, os.getpid())):
        self.selected = selected
        self.read_error = None
        self.select_result = None
        self.selections = 0

    def selected_base_surface(self):
        if self.read_error:
            raise self.read_error
        return self.selected


class GamePresentationReconciliationTests(unittest.IsolatedAsyncioTestCase):
    def make_interface(self, *, lifecycle=Lifecycle.GAME, pids=None, selected=(10, os.getpid())):
        interface = ConsoleSessionInterface.__new__(ConsoleSessionInterface)
        interface.model = SessionStateModel()
        if lifecycle is Lifecycle.GAME:
            token = interface.model.request_launch("game:test")
            interface.model.launch_starting(token)
            interface.model.primary_started(token)
        interface._local_identity = None
        interface._game_surface_missing_since = None
        interface.StateChanged = Mock()
        interface._state_json = Mock(return_value="{}")
        identity = LaunchIdentity(interface.model.state.launch_token or "", os.getpid(), os.getpgid(0), "game", ())
        presentation = PresentationFake(selected)
        owned = set(pids if pids is not None else {os.getpid()})

        def select(identity_arg, timeout):
            presentation.selections += 1
            if presentation.select_result is not None:
                presentation.selected = presentation.select_result
            return 10

        interface.supervisor = SimpleNamespace(
            active_identity=identity,
            _presentation=presentation,
            session_process_ids=Mock(return_value=owned),
            session_surface_is_owned=lambda pid, _identity: pid in owned,
            reconcile_session_surface=Mock(side_effect=select),
            quit_active_session=AsyncMock(),
        )
        interface._owned_game_pids = lambda: set(owned)
        return interface, identity, presentation

    async def test_correct_running_surface_is_accepted_without_reselection(self):
        interface, _identity, presentation = self.make_interface()
        await interface._reconcile_game_presentation()
        self.assertEqual(interface.model.state.lifecycle, Lifecycle.GAME)
        self.assertEqual(presentation.selections, 0)

    async def test_temporarily_unavailable_surface_is_reselected_without_lifecycle_change(self):
        interface, _identity, presentation = self.make_interface(selected=(None, None))
        presentation.select_result = (11, os.getpid())
        await interface._reconcile_game_presentation()
        self.assertEqual(interface.model.state.lifecycle, Lifecycle.GAME)
        self.assertEqual(presentation.selections, 1)

    async def test_disappeared_surface_is_reselected_while_process_lives(self):
        interface, _identity, presentation = self.make_interface(selected=(None, None))
        presentation.select_result = (11, os.getpid())
        await interface._reconcile_game_presentation()
        self.assertEqual(interface.model.state.lifecycle, Lifecycle.GAME)
        self.assertEqual(presentation.selected, (11, os.getpid()))

    async def test_wrong_pid_triggers_reselection_using_owned_process_evidence(self):
        interface, identity, presentation = self.make_interface(selected=(12, 999999))
        presentation.select_result = (13, os.getpid())
        await interface._reconcile_game_presentation()
        interface.supervisor.reconcile_session_surface.assert_called_once_with(identity, 0)
        self.assertEqual(interface.model.state.lifecycle, Lifecycle.GAME)

    async def test_correct_surface_reappearance_clears_loss_timer(self):
        interface, _identity, presentation = self.make_interface(selected=(None, None))
        interface._game_surface_missing_since = 4.0
        presentation.selected = (14, os.getpid())
        await interface._reconcile_game_presentation()
        self.assertIsNone(interface._game_surface_missing_since)

    async def test_process_exit_evidence_does_not_infer_presentation_failure(self):
        interface, _identity, _presentation = self.make_interface(pids=set(), selected=(None, None))
        await interface._reconcile_game_presentation()
        self.assertEqual(interface.model.state.lifecycle, Lifecycle.GAME)
        interface.supervisor.reconcile_session_surface.assert_not_called()

    async def test_shell_lifecycle_is_unaffected(self):
        interface, _identity, _presentation = self.make_interface(lifecycle=Lifecycle.SHELL)
        await interface._reconcile_game_presentation()
        self.assertEqual(interface.model.state.lifecycle, Lifecycle.SHELL)
        interface.supervisor.reconcile_session_surface.assert_not_called()

    async def test_transient_gamescope_read_failure_does_not_end_game(self):
        interface, _identity, presentation = self.make_interface()
        presentation.read_error = OSError("temporary X connection failure")
        await interface._reconcile_game_presentation()
        self.assertEqual(interface.model.state.lifecycle, Lifecycle.GAME)
        interface.supervisor.reconcile_session_surface.assert_not_called()

    async def test_persistent_wrong_surface_fails_through_return_and_stops_owned_game(self):
        interface, identity, presentation = self.make_interface(selected=(12, 999999))
        interface._game_surface_missing_since = asyncio.get_running_loop().time() - 6
        await interface._reconcile_game_presentation()
        # The fake selector cannot repair it; recovery takes the established
        # return path and asks the supervisor to stop only this owned launch.
        self.assertEqual(interface.model.state.lifecycle, Lifecycle.RETURNING)
        self.assertEqual(interface.model.last_failure_reason,
                         "Gamescope game presentation could not be recovered")
        interface.supervisor.quit_active_session.assert_awaited_once()
        self.assertEqual(interface.model.state.launch_token, identity.token)


if __name__ == "__main__":
    unittest.main()
