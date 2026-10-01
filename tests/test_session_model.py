import unittest
import asyncio
import threading
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from lulu.console_sessiond import SessionStateModel
from lulu.contracts import (InputMode, LaunchDescriptor, Lifecycle, Presentation,
                            SessionClassification)
from lulu.process_supervisor import ProcessSupervisor
from lulu.sessiond import ConsoleSessionInterface


class SessionModelTests(unittest.TestCase):
    def test_presentation_call_finishes_worker_before_propagating_cancellation(self) -> None:
        async def exercise() -> None:
            session = SessionStateModel()
            supervisor = ProcessSupervisor(session)
            started = threading.Event()
            release = threading.Event()
            finished = threading.Event()

            def slow_unmap() -> None:
                started.set()
                release.wait(timeout=2)
                finished.set()

            operation = asyncio.create_task(supervisor._presentation_call(slow_unmap))
            self.assertTrue(await asyncio.to_thread(started.wait, 1))
            operation.cancel()
            await asyncio.sleep(0.02)
            self.assertFalse(finished.is_set())
            release.set()
            with self.assertRaises(asyncio.CancelledError):
                await operation
            self.assertTrue(finished.is_set())

        asyncio.run(exercise())

    def utility_descriptor(self) -> LaunchDescriptor:
        return LaunchDescriptor(
            primary_id="utility:flatpak:app.devsuite.Ptyxis",
            classification=SessionClassification.UTILITY,
            title="Ptyxis",
            presentation=Presentation.FOREIGN_UI,
            input_mode=InputMode.COMPAT,
        )

    def test_utility_descriptor_is_authoritative_and_uses_compat_mode(self) -> None:
        async def exercise() -> None:
            session = SessionStateModel()
            modes = []
            supervisor = ProcessSupervisor(session, input_mode_changed=modes.append)
            await supervisor.launch(["/bin/sh", "-c", "sleep 0.05"], 1000,
                                    descriptor=self.utility_descriptor(),
                                    presentation_controller=None)
            self.assertEqual(session.state.session_kind, "utility")
            self.assertEqual(session.state.session_title, "Ptyxis")
            self.assertEqual(session.state.delegated_surface, "utility")
            self.assertEqual(session.state.presentation, Presentation.FOREIGN_UI)
            self.assertEqual(session.state.input_mode, InputMode.COMPAT)
            await supervisor._watch_task
            self.assertEqual(modes, [InputMode.COMPAT, InputMode.SHELL])
            self.assertEqual(session.state.lifecycle, Lifecycle.SHELL)
            self.assertEqual(session.state.session_kind, "shell")
            self.assertEqual(session.state.input_mode, InputMode.SHELL)

        asyncio.run(exercise())

    def test_utility_classification_defaults_to_compat_and_game_keeps_gamepad(self) -> None:
        utility = LaunchDescriptor(
            primary_id="utility:fixture", classification=SessionClassification.UTILITY)
        game = LaunchDescriptor(primary_id="game:fixture")
        self.assertEqual(utility.input_mode, InputMode.COMPAT)
        self.assertEqual(game.input_mode, InputMode.GAME)

    def test_failed_utility_launch_rolls_compatibility_profile_back(self) -> None:
        async def exercise() -> None:
            session = SessionStateModel()
            modes = []

            def apply(mode: InputMode) -> None:
                modes.append(mode)
                if mode is InputMode.COMPAT:
                    raise RuntimeError("compat profile activation failed")

            supervisor = ProcessSupervisor(session, input_mode_changed=apply)
            with self.assertRaisesRegex(ValueError, "compat profile activation failed"):
                await supervisor.launch(["/bin/sh", "-c", "sleep 5"], 1000,
                                        descriptor=self.utility_descriptor(),
                                        presentation_controller=None)
            self.assertEqual(modes, [InputMode.COMPAT, InputMode.SHELL])
            self.assertEqual(session.state.lifecycle, Lifecycle.SHELL)
            self.assertEqual(session.state.input_mode, InputMode.SHELL)
            self.assertEqual(session.state.session_kind, "shell")
            self.assertIsNone(supervisor.active_identity)

        asyncio.run(exercise())

    def test_sessiond_utility_launch_passes_first_class_descriptor(self) -> None:
        async def exercise() -> None:
            interface = ConsoleSessionInterface.__new__(ConsoleSessionInterface)
            interface.supervisor = SimpleNamespace(launch=AsyncMock(return_value="token"))
            result = await ConsoleSessionInterface.RequestUtilityLaunch.__wrapped__(
                interface, "utility:flatpak:app.devsuite.Ptyxis", "Ptyxis",
                ["flatpak", "run", "ptyxis"], 15000)
            self.assertEqual(result, "token")
            call = interface.supervisor.launch.await_args
            descriptor = call.kwargs["descriptor"]
            self.assertEqual(descriptor.classification, SessionClassification.UTILITY)
            self.assertEqual(descriptor.title, "Ptyxis")
            self.assertEqual(descriptor.input_mode, InputMode.COMPAT)
            self.assertEqual(descriptor.presentation, Presentation.FOREIGN_UI)

        asyncio.run(exercise())

    def test_native_controller_path_still_applies_utility_compat_and_restores_default(self) -> None:
        interface = ConsoleSessionInterface.__new__(ConsoleSessionInterface)
        interface._native_controller = True
        interface.model = SessionStateModel()
        token = interface.model.request_launch(self.utility_descriptor())
        interface.model.launch_starting(token)
        interface.model.primary_started(token, presentation=Presentation.FOREIGN_UI,
                                        input_mode=InputMode.COMPAT)
        path = "/org/shadowblip/InputPlumber/CompositeDevice0"
        inputplumber = SimpleNamespace(
            runtime_composite_statuses=lambda: {path: ("controller", ("/dev/input/event0",))},
            load_mode=unittest.mock.Mock(),
            ensure_default_intercept=unittest.mock.Mock(),
        )
        interface._inputplumber = inputplumber
        interface._applied_input_modes = {}

        interface._apply_supervised_input_mode(InputMode.COMPAT)
        inputplumber.load_mode.assert_called_once_with(InputMode.COMPAT, path)

        interface._apply_supervised_input_mode(InputMode.SHELL)
        inputplumber.ensure_default_intercept.assert_called_once_with(path)

        # Native ordinary-game input is unaffected by the Utility integration.
        interface.model.state.session_kind = "game"
        inputplumber.load_mode.reset_mock()
        inputplumber.ensure_default_intercept.reset_mock()
        interface._apply_supervised_input_mode(InputMode.GAME)
        inputplumber.load_mode.assert_not_called()
        inputplumber.ensure_default_intercept.assert_not_called()

    def test_crashed_utility_returns_to_shell_mode(self) -> None:
        async def exercise() -> None:
            session = SessionStateModel()
            modes = []
            supervisor = ProcessSupervisor(session, input_mode_changed=modes.append)
            await supervisor.launch(["/bin/sh", "-c", "exit 17"], 1000,
                                    descriptor=self.utility_descriptor(),
                                    presentation_controller=None)
            await supervisor._watch_task
            self.assertEqual(session.last_result.exit_code, 17)
            self.assertEqual(session.state.lifecycle, Lifecycle.SHELL)
            self.assertEqual(session.state.input_mode, InputMode.SHELL)
            self.assertEqual(modes[-1], InputMode.SHELL)

        asyncio.run(exercise())

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

    def test_downloads_is_a_mudos_requested_surface(self) -> None:
        session = SessionStateModel()
        token = session.request_launch("steam-store")
        session.launch_starting(token)
        session.primary_started(token, presentation=Presentation.FOREIGN_UI, input_mode=InputMode.GAME)
        self.assertEqual(session.state.delegated_surface, "store")
        session.request_surface("downloads")
        self.assertEqual(session.state.requested_surface, "downloads")
        session.clear_requested_surface()
        self.assertIsNone(session.state.requested_surface)

    def test_reset_requests_owned_systemd_session_restart(self) -> None:
        async def exercise() -> None:
            interface = ConsoleSessionInterface.__new__(ConsoleSessionInterface)
            interface._reset_requested = True
            process = AsyncMock()
            process.returncode = 0
            process.communicate.return_value = (b"", b"")
            with patch("lulu.sessiond.asyncio.create_subprocess_exec",
                       new=AsyncMock(return_value=process)) as spawn:
                await interface._reset_mudos()
            spawn.assert_awaited_once_with(
                "systemctl", "--no-block", "restart", "lulu-session@2.service",
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.PIPE,
            )

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

    def test_fresh_session_after_compatibility_shutdown_starts_clean_shell(self) -> None:
        """A reboot constructs fresh authority; game/delegated state is never resumed."""
        previous_boot = SessionStateModel()
        token = previous_boot.request_launch("dolphin:game")
        previous_boot.launch_starting(token)
        previous_boot.primary_started(token, presentation=Presentation.FOREIGN_UI,
                                      input_mode=InputMode.COMPAT)
        previous_boot.state.delegated_surface = "compatibility"
        previous_boot.state.controller_mode = "compatibility"

        # SessionStateModel intentionally has no persistence layer. A new
        # Sessiond after reboot must not rehydrate the previous lifecycle/token.
        rebooted = SessionStateModel()
        self.assertEqual(rebooted.state.lifecycle, Lifecycle.SHELL)
        self.assertEqual(rebooted.state.session_kind, "shell")
        self.assertEqual(rebooted.state.presentation, Presentation.SHELL)
        self.assertEqual(rebooted.state.input_mode, InputMode.SHELL)
        self.assertIsNone(rebooted.state.primary_id)
        self.assertIsNone(rebooted.state.launch_token)
        self.assertIsNone(rebooted.state.delegated_surface)
        self.assertIsNone(rebooted.state.requested_surface)
        self.assertIsNone(rebooted.state.controller_mode)

        supervisor = ProcessSupervisor(rebooted)
        self.assertIsNone(supervisor.active_identity)
        self.assertIsNone(supervisor._shell_identity)

    def test_sessiond_recovery_initializes_connected_controller_in_shell_mode(self) -> None:
        async def exercise() -> None:
            interface = ConsoleSessionInterface.__new__(ConsoleSessionInterface)
            interface.model = SessionStateModel()
            interface._inputplumber = SimpleNamespace(
                ensure_default_intercept=unittest.mock.Mock(),
                runtime_composite_statuses=lambda: {},
                load_mode=unittest.mock.Mock(),
            )
            interface._initialized_composites = {}
            interface._applied_input_modes = {}
            await interface._initialize_composite("/controller/0", ("composite", ("/event0",)))
            interface._inputplumber.ensure_default_intercept.assert_called_once_with("/controller/0")
            interface._inputplumber.load_mode.assert_called_once_with(InputMode.SHELL)
            self.assertEqual(interface.model.state.input_mode, InputMode.SHELL)

        asyncio.run(exercise())

    def test_controller_recreation_preserves_utility_and_unfocused_game_compat(self) -> None:
        async def exercise(kind: str, expected: InputMode) -> None:
            interface = ConsoleSessionInterface.__new__(ConsoleSessionInterface)
            interface.model = SessionStateModel()
            interface.model.state.lifecycle = Lifecycle.GAME
            interface.model.state.session_kind = kind
            interface.model.state.input_mode = InputMode.COMPAT
            interface._inputplumber = SimpleNamespace(
                ensure_default_intercept=unittest.mock.Mock(),
                runtime_composite_statuses=lambda: {},
                load_mode=unittest.mock.Mock(),
            )
            interface._initialized_composites = {}
            interface._applied_input_modes = {}
            await interface._initialize_composite("/controller/0", ("composite", ("/event0",)))
            self.assertEqual(interface.model.state.input_mode, expected)
            interface._inputplumber.load_mode.assert_called_once_with(expected)

        asyncio.run(exercise("utility", InputMode.COMPAT))
        asyncio.run(exercise("game", InputMode.COMPAT))

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

    def test_delegated_launch_context_is_inherited_by_owned_child(self) -> None:
        async def exercise() -> None:
            session = SessionStateModel()
            supervisor = ProcessSupervisor(session)
            supervisor.set_delegated_launch_environment({
                "DISPLAY": ":test", "WAYLAND_DISPLAY": "gamescope-test",
                "XDG_RUNTIME_DIR": "/run/user/test", "UNRELATED_SECRET": "ignored",
            })
            await supervisor.launch([
                "/bin/sh", "-c",
                "test \"$DISPLAY\" = :test && test \"$WAYLAND_DISPLAY\" = gamescope-test && "
                "test \"$XDG_RUNTIME_DIR\" = /run/user/test && test -z \"$UNRELATED_SECRET\"",
            ], 1000, presentation_controller=None)
            await supervisor._watch_task
            self.assertEqual(session.state.lifecycle, Lifecycle.SHELL)

        asyncio.run(exercise())

    def test_presentation_timeout_releases_owned_identity(self) -> None:
        async def exercise() -> None:
            class MissingSurface:
                def select_pids(self, _pids, _timeout, _process_alive=None):
                    raise TimeoutError("surface absent")

            session = SessionStateModel()
            supervisor = ProcessSupervisor(session)
            with self.assertRaises(ValueError):
                await supervisor.launch(
                    ["/bin/sh", "-c", "sleep 10"], 1000,
                    presentation_controller=MissingSurface(),
                )
            self.assertIsNone(supervisor.active_identity)
            self.assertEqual(session.state.lifecycle, Lifecycle.SHELL)

        asyncio.run(exercise())

    def test_launch_process_exit_aborts_surface_wait_and_records_terminal_result(self) -> None:
        async def exercise() -> None:
            class MissingSurface:
                def select_pids(self, pids, _timeout, process_alive=None):
                    self.pids = pids()
                    self.process_alive = process_alive
                    if process_alive is not None and not process_alive():
                        raise RuntimeError("owned game process tree exited before a Gamescope window appeared")
                    raise AssertionError("short-lived command should be detected as exited")

            session = SessionStateModel()
            presentation = MissingSurface()
            supervisor = ProcessSupervisor(session)
            with self.assertRaisesRegex(ValueError, "process tree exited"):
                await supervisor.launch(["/bin/sh", "-c", "exit 23"], 1000,
                                        presentation_controller=presentation)
            self.assertFalse(presentation.process_alive())
            self.assertEqual(session.state.lifecycle, Lifecycle.SHELL)
            self.assertIsNone(supervisor.active_identity)
            self.assertEqual(session.last_result.outcome, "presentation-failed")
            self.assertEqual(session.last_result.exit_code, 23)

        asyncio.run(exercise())

    def test_gamescope_target_tracks_child_after_launcher_handoff(self) -> None:
        async def exercise() -> None:
            class ChildSurface:
                def __init__(self) -> None:
                    self.selected_pids = []
                    self.process_alive = None

                def select_pids(self, pids, _timeout, process_alive=None):
                    self.process_alive = process_alive
                    deadline = time.monotonic() + 2
                    while time.monotonic() < deadline:
                        self.selected_pids = pids()
                        if any(pid != supervisor._process.pid for pid in self.selected_pids):
                            return 0x123
                        if process_alive is not None and not process_alive():
                            raise RuntimeError("owned game process tree exited before a Gamescope window appeared")
                        time.sleep(0.01)
                    raise TimeoutError("launcher child was not retained in the owned process group")

            session = SessionStateModel()
            presentation = ChildSurface()
            supervisor = ProcessSupervisor(session)
            token = await supervisor.launch(
                ["/bin/bash", "-c", "sleep 1.5 & exit 0"], 1000,
                presentation_controller=presentation,
            )
            self.assertTrue(any(pid != supervisor.active_identity.pid
                                for pid in presentation.selected_pids))
            self.assertTrue(presentation.process_alive())
            self.assertEqual(session.state.launch_token, token)
            await supervisor._watch_task
            self.assertEqual(session.state.lifecycle, Lifecycle.SHELL)

        asyncio.run(exercise())


if __name__ == "__main__":
    unittest.main()
