import unittest
from pathlib import Path

from lulu.applicationd import ApplicationCatalog
from lulu.console_sessiond import SessionStateModel
from lulu.console_ui import ConsoleUi
from lulu.consoled import ConsoleCatalog
from lulu.controllerd import Controller, ControllerRegistry
from lulu.controllerd import default_inputplumber_client
from lulu.contracts import InputMode, Lifecycle, Overlay, Role, ServiceName


class BoundaryTests(unittest.TestCase):
    def test_all_first_step_boundaries_are_explicit(self) -> None:
        self.assertEqual(
            {
                ControllerRegistry.descriptor.name,
                SessionStateModel.descriptor.name,
                ConsoleCatalog.descriptor.name,
                ApplicationCatalog.descriptor.name,
                ConsoleUi.descriptor.name,
            },
            set(ServiceName),
        )

    def test_controller_navigation_is_separate_from_player_assignment(self) -> None:
        registry = ControllerRegistry()
        controller = Controller("pad-a", role=Role.PLAYER)
        registry.connect(controller)
        registry.assign_player("pad-a", 1)
        registry.set_navigation_controller("pad-a")
        self.assertEqual(registry.controllers["pad-a"].player, 1)
        self.assertEqual(registry.navigation_controller_id, "pad-a")

    def test_disconnect_releases_navigation_ownership_only(self) -> None:
        registry = ControllerRegistry()
        registry.connect(Controller("pad-a"))
        registry.assign_player("pad-a", 1)
        registry.set_navigation_controller("pad-a")
        registry.disconnect("pad-a")
        self.assertIsNone(registry.navigation_controller_id)
        self.assertEqual(registry.controllers["pad-a"].player, 1)

    def test_session_lifecycle_and_orthogonal_state(self) -> None:
        session = SessionStateModel()
        token = session.request_launch("game-1")
        self.assertEqual(session.state.lifecycle, Lifecycle.LAUNCHING)
        session.primary_started(token)
        self.assertEqual(session.state.input_mode, InputMode.GAME)
        session.set_overlay(Overlay.OPEN)
        session.primary_exited(token)
        self.assertEqual(session.state.lifecycle, Lifecycle.RETURNING)
        session.return_complete(token)
        self.assertEqual(session.state.lifecycle, Lifecycle.SHELL)
        self.assertEqual(session.state.overlay, Overlay.CLOSED)

    def test_controllerd_loads_mode_profiles_without_target_replacement(self) -> None:
        client = default_inputplumber_client(Path("config/inputplumber"))
        command = client.load_mode(InputMode.COMPAT, execute=False)
        self.assertEqual(command[-1], "config/inputplumber/profiles/compat.yaml")
        self.assertNotIn("SetTargetDevices", command)

    def test_intercept_mode_is_bounded_to_inputplumber_api_values(self) -> None:
        client = default_inputplumber_client(Path("config/inputplumber"))
        self.assertEqual(client.set_intercept_mode(2, execute=False)[-1], "2")
        with self.assertRaises(ValueError):
            client.set_intercept_mode(4, execute=False)


if __name__ == "__main__":
    unittest.main()
