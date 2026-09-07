import unittest
from pathlib import Path
import tempfile
from unittest.mock import patch

from lulu.applicationd import ApplicationCatalog
from lulu.console_sessiond import SessionStateModel
from lulu.console_ui import ConsoleUi
from lulu.consoled import ConsoleCatalog
from lulu.controllerd import Controller, ControllerRegistry
from lulu.controllerd import default_inputplumber_client
from lulu.contracts import InputMode, Lifecycle, Overlay, Role, ServiceName
from lulu.gamescope import GamescopeInvocation, discover_presentation_output
from lulu.sessiond import ConsoleSessionInterface


class RecordingInputPlumber:
    def __init__(self, composites: dict[str, tuple[str, tuple[str, ...]]]) -> None:
        self.composites = composites
        self.loads: list[tuple[InputMode, str | None]] = []

    def runtime_composite_statuses(self) -> dict[str, tuple[str, tuple[str, ...]]]:
        return self.composites

    def load_mode(
        self, mode: InputMode, object_path: str | None = None, *, execute: bool = True
    ) -> list[str]:
        self.loads.append((mode, object_path))
        return []


def input_mode_interface(
    client: RecordingInputPlumber,
) -> ConsoleSessionInterface:
    interface = ConsoleSessionInterface.__new__(ConsoleSessionInterface)
    interface._inputplumber = client
    interface._applied_input_modes = {}
    return interface


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
        self.assertEqual(session.state.lifecycle, Lifecycle.LAUNCH_REQUESTED)
        session.launch_starting(token)
        self.assertEqual(session.state.lifecycle, Lifecycle.STARTING)
        session.primary_started(token)
        self.assertEqual(session.state.lifecycle, Lifecycle.GAME)
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

    def test_controller_loss_releases_navigation_and_same_identity_reconnects(self) -> None:
        registry = ControllerRegistry()
        registry.observe_persistent_composite("", ())
        self.assertEqual(registry.controllers, {})
        self.assertIsNone(registry.navigation_controller_id)
        registry.observe_persistent_composite("045e_0291", ("/dev/input/event18",))
        self.assertEqual(registry.navigation_controller_id, "045e_0291")
        registry.observe_persistent_composite("", ())
        self.assertIsNone(registry.navigation_controller_id)
        self.assertFalse(registry.controllers["045e_0291"].connected)
        registry.observe_persistent_composite("045e_0291", ("/dev/input/event20",))
        self.assertEqual(registry.navigation_controller_id, "045e_0291")
        self.assertTrue(registry.controllers["045e_0291"].connected)
        self.assertEqual(registry.controllers["045e_0291"].player, 1)

    def test_runtime_controller_loss_transfers_navigation_to_other_slot(self) -> None:
        registry = ControllerRegistry()
        registry.observe_runtime_composites(
            {
                "CompositeDevice0": ("045e_0291", ("/dev/input/event18",)),
                "CompositeDevice1": ("045e_0291", ("/dev/input/event22",)),
            }
        )
        self.assertEqual(registry.navigation_controller_id, "CompositeDevice0")
        self.assertEqual(registry.controllers["CompositeDevice0"].player, 1)
        self.assertIsNone(registry.controllers["CompositeDevice1"].player)

        registry.observe_runtime_composites(
            {"CompositeDevice1": ("045e_0291", ("/dev/input/event22",))}
        )
        self.assertFalse(registry.controllers["CompositeDevice0"].connected)
        self.assertTrue(registry.controllers["CompositeDevice1"].connected)
        self.assertEqual(registry.controllers["CompositeDevice0"].player, 1)
        self.assertEqual(registry.navigation_controller_id, "CompositeDevice1")
        self.assertIsNone(registry.controllers["CompositeDevice1"].player)

    def test_intercept_mode_is_bounded_to_inputplumber_api_values(self) -> None:
        client = default_inputplumber_client(Path("config/inputplumber"))
        self.assertEqual(client.set_intercept_mode(2, execute=False)[-1], "2")
        with self.assertRaises(ValueError):
            client.set_intercept_mode(4, execute=False)

    def test_shell_profile_load_is_optional_when_no_controller_exists(self) -> None:
        client = default_inputplumber_client(Path("config/inputplumber"))
        with patch("subprocess.run") as run:
            run.return_value.stdout = ""
            command = client.load_mode(InputMode.SHELL)
        self.assertEqual(command[-1], "config/inputplumber/profiles/shell.yaml")
        self.assertEqual(run.call_count, 1)

    def test_present_composite_converges_once_when_shell_mode_is_applied(self) -> None:
        path = "/org/shadowblip/InputPlumber/CompositeDevice0"
        client = RecordingInputPlumber({path: ("045e_0291", ("/dev/input/event13",))})
        interface = input_mode_interface(client)

        interface._apply_input_mode(InputMode.SHELL)
        interface._reconcile_input_mode(client.composites, InputMode.SHELL)

        self.assertEqual(client.loads, [(InputMode.SHELL, path)])

    def test_late_composite_converges_to_active_shell_mode(self) -> None:
        path = "/org/shadowblip/InputPlumber/CompositeDevice0"
        client = RecordingInputPlumber({})
        interface = input_mode_interface(client)

        interface._apply_input_mode(InputMode.SHELL)
        client.composites = {path: ("045e_0291", ("/dev/input/event13",))}
        interface._reconcile_input_mode(client.composites, InputMode.SHELL)

        self.assertEqual(client.loads, [(InputMode.SHELL, None), (InputMode.SHELL, path)])

    def test_recreated_composite_is_reapplied_while_shell_remains_active(self) -> None:
        path = "/org/shadowblip/InputPlumber/CompositeDevice0"
        client = RecordingInputPlumber({path: ("045e_0291", ("/dev/input/event13",))})
        interface = input_mode_interface(client)

        interface._reconcile_input_mode(client.composites, InputMode.SHELL)
        interface._reconcile_input_mode({}, InputMode.SHELL)
        interface._reconcile_input_mode(client.composites, InputMode.SHELL)

        self.assertEqual(
            client.loads,
            [(InputMode.SHELL, path), (InputMode.SHELL, path)],
        )

    def test_converged_composite_is_not_reapplied(self) -> None:
        path = "/org/shadowblip/InputPlumber/CompositeDevice0"
        client = RecordingInputPlumber({path: ("045e_0291", ("/dev/input/event13",))})
        interface = input_mode_interface(client)

        interface._reconcile_input_mode(client.composites, InputMode.SHELL)
        interface._reconcile_input_mode(client.composites, InputMode.SHELL)

        self.assertEqual(client.loads, [(InputMode.SHELL, path)])

    def test_reconciliation_preserves_registry_ownership_and_player_assignment(self) -> None:
        path = "/org/shadowblip/InputPlumber/CompositeDevice0"
        client = RecordingInputPlumber({path: ("045e_0291", ("/dev/input/event13",))})
        interface = input_mode_interface(client)

        interface.controller_registry = ControllerRegistry()
        interface.controller_registry.observe_runtime_composites(client.composites)
        interface._reconcile_input_mode(client.composites, InputMode.SHELL)

        controller = interface.controller_registry.controllers[path]
        self.assertTrue(controller.connected)
        self.assertEqual(controller.player, 1)
        self.assertEqual(interface.controller_registry.navigation_controller_id, path)

    def test_gamescope_invocation_accepts_deployment_output(self) -> None:
        command = GamescopeInvocation().argv(["/usr/bin/true"])
        self.assertNotIn("--prefer-output", command)
        configured = GamescopeInvocation(output="HDMI-A-1").argv(["/usr/bin/true"])
        self.assertEqual(configured[3:5], ["--prefer-output", "HDMI-A-1"])

    def test_gamescope_discovers_connected_connector(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            drm = Path(directory) / "card0-HDMI-A-1"
            drm.mkdir(parents=True)
            (drm / "status").write_text("connected\n")
            self.assertEqual(discover_presentation_output(directory), "HDMI-A-1")


if __name__ == "__main__":
    unittest.main()
