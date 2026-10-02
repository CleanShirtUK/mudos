from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
import socket
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from dbus_next import DBusError

from lulu.console_sessiond import SessionStateModel
from lulu.process_supervisor import ProcessSupervisor
from lulu.sessiond import ConsoleSessionInterface
from lulu.graphical_launch_context import context_is_valid


def make_interface(*, ready: bool, presentation: object | None = object(),
                   shell_process: object | None = None) -> ConsoleSessionInterface:
    interface = ConsoleSessionInterface.__new__(ConsoleSessionInterface)
    interface.model = SessionStateModel()
    interface._presentation_ready = ready
    interface._graphical_session_id = "unit-test-session"
    interface._graphical_launch_lease = None
    interface.controller_registry = SimpleNamespace(
        navigation_controller_id=None, navigation_mode="all", controllers={})
    interface._local_identity = None
    interface._local_provider_id = ""
    interface.supervisor = SimpleNamespace(
        _presentation=presentation,
        _shell_process=shell_process if shell_process is not None
        else SimpleNamespace(pid=os.getpid(), returncode=None),
        _delegated_launch_environment={
            "DISPLAY": ":test", "WAYLAND_DISPLAY": "wayland-test",
            "XDG_RUNTIME_DIR": "/tmp/test-runtime",
        },
        set_delegated_launch_environment=Mock(),
        queue_steam_launch=Mock(return_value="steam-token"),
        queue_aurelia_launch=Mock(return_value="aurelia-token"),
        state_details=Mock(return_value={}),
    )
    return interface


class SessiondPresentationReadinessTests(unittest.TestCase):
    def test_ready_shell_allows_both_steam_backends(self) -> None:
        interface = make_interface(ready=True)
        aurelia_config = SimpleNamespace(provider=Mock(return_value=SimpleNamespace(enabled=True)))

        with patch("lulu.sessiond.has_connected_presentation_output", return_value=True), \
                patch("lulu.sessiond.ProviderConfigurationService.from_environment",
                      return_value=aurelia_config), \
                patch("lulu.sessiond.graphical_context_is_live", return_value=True), \
                patch("lulu.sessiond.write_graphical_launch_context", return_value=True), \
                patch("lulu.sessiond.context_is_valid", return_value=True), \
                patch.object(interface, "StateChanged", lambda *_args: None):
            steam_token = ConsoleSessionInterface.RequestSteamLaunch.__wrapped__(
                interface, "104200", 15000)
            aurelia_token = ConsoleSessionInterface.RequestAureliaLaunch.__wrapped__(
                interface, "104200", 15000)

        self.assertEqual(steam_token, "steam-token")
        self.assertEqual(aurelia_token, "aurelia-token")
        interface.supervisor.queue_steam_launch.assert_called_once_with("104200", 15000)
        interface.supervisor.queue_aurelia_launch.assert_called_once_with("104200", 15000)

    def test_missing_drm_output_rejects_both_backends_before_provider(self) -> None:
        for method_name in ("RequestSteamLaunch", "RequestAureliaLaunch"):
            with self.subTest(method=method_name):
                interface = make_interface(ready=True)
                aurelia_config = Mock()
                with patch("lulu.sessiond.has_connected_presentation_output", return_value=False), \
                        patch("lulu.sessiond.ProviderConfigurationService.from_environment",
                              aurelia_config):
                    with self.assertRaisesRegex(
                            DBusError, "no connected DRM presentation output"):
                        getattr(ConsoleSessionInterface, method_name).__wrapped__(
                            interface, "104200", 15000)

                interface.supervisor.queue_steam_launch.assert_not_called()
                interface.supervisor.queue_aurelia_launch.assert_not_called()
                aurelia_config.assert_not_called()
                self.assertEqual(interface.model.state.lifecycle.value, "shell")

    def test_missing_gamescope_presentation_rejects_both_backends(self) -> None:
        for method_name in ("RequestSteamLaunch", "RequestAureliaLaunch"):
            with self.subTest(method=method_name):
                # A shell lifecycle and even a connected output do not establish
                # that Gamescope bootstrapped and selected the shell window.
                interface = make_interface(ready=True, presentation=None)
                aurelia_config = Mock()
                with patch("lulu.sessiond.has_connected_presentation_output", return_value=True), \
                        patch("lulu.sessiond.ProviderConfigurationService.from_environment",
                              aurelia_config), \
                        patch("lulu.sessiond.context_is_valid", return_value=False), \
                        patch.object(interface, "StateChanged", lambda *_args: None):
                    with self.assertRaisesRegex(
                            DBusError, "Gamescope presentation is not ready"):
                        getattr(ConsoleSessionInterface, method_name).__wrapped__(
                            interface, "104200", 15000)

                interface.supervisor.queue_steam_launch.assert_not_called()
                interface.supervisor.queue_aurelia_launch.assert_not_called()
                aurelia_config.assert_not_called()
                self.assertEqual(interface.model.state.lifecycle.value, "shell")

    def test_no_display_boot_keeps_waiting_without_starting_shell_or_recovery(self) -> None:
        interface = ConsoleSessionInterface.__new__(ConsoleSessionInterface)
        interface._bootstrap_output = None
        interface._presentation_ready = False
        interface.recovery_mode = False
        interface.supervisor = SimpleNamespace(launch_shell=Mock())
        sleep_calls = 0

        async def stop_waiting(_seconds: float) -> None:
            nonlocal sleep_calls
            sleep_calls += 1
            if sleep_calls == 3:
                raise asyncio.CancelledError

        async def exercise() -> None:
            with patch("lulu.sessiond.has_connected_presentation_output", return_value=False), \
                    patch("lulu.sessiond.asyncio.sleep", side_effect=stop_waiting), \
                    patch.dict("os.environ", {}, clear=False):
                with self.assertRaises(asyncio.CancelledError):
                    await interface.bootstrap_shell()

        asyncio.run(exercise())
        self.assertEqual(sleep_calls, 3)
        interface.supervisor.launch_shell.assert_not_called()
        self.assertFalse(interface._presentation_ready)

    def test_watchdog_selection_sets_readiness_and_launch_remains_allowed(self) -> None:
        interface = ConsoleSessionInterface.__new__(ConsoleSessionInterface)
        interface.model = SessionStateModel()
        interface.controller_registry = SimpleNamespace(
            navigation_controller_id=None, navigation_mode="all", controllers={})
        interface._local_identity = None
        interface._local_provider_id = ""
        interface._presentation_ready = False
        interface._graphical_session_id = "test-session"
        interface._graphical_launch_lease = None
        shell_process = SimpleNamespace(pid=os.getpid(), returncode=None)
        interface.supervisor = SimpleNamespace(
            _presentation=object(),
            _shell_process=shell_process,
            _delegated_launch_environment={
                "DISPLAY": ":test", "WAYLAND_DISPLAY": "wayland-test",
                "XDG_RUNTIME_DIR": "/tmp/test-runtime",
            },
            ensure_shell_presentation=Mock(return_value=321),
            queue_aurelia_launch=Mock(return_value="aurelia-token"),
            state_details=Mock(return_value={}),
        )
        interface.supervisor.set_delegated_launch_environment = lambda values: setattr(
            interface.supervisor, "_delegated_launch_environment", dict(values))
        aurelia_config = SimpleNamespace(provider=Mock(return_value=SimpleNamespace(enabled=True)))

        async def exercise() -> None:
            async def run_in_thread(function, *args):
                return function(*args)

            with patch("lulu.sessiond.asyncio.to_thread", side_effect=run_in_thread), \
                    patch("lulu.sessiond.has_connected_presentation_output", return_value=True), \
                    patch("lulu.sessiond.ProviderConfigurationService.from_environment",
                          return_value=aurelia_config), \
                    patch("lulu.sessiond.graphical_context_is_live", return_value=True), \
                    patch("lulu.sessiond.write_graphical_launch_context", return_value=True), \
                    patch("lulu.sessiond.context_is_valid", return_value=True), \
                    patch.object(interface, "StateChanged", Mock()) as state_changed:
                await interface._refresh_presentation_readiness()
                self.assertTrue(interface._presentation_ready)
                self.assertTrue(json.loads(state_changed.call_args.args[0])["presentation_ready"])
                token = ConsoleSessionInterface.RequestAureliaLaunch.__wrapped__(
                    interface, "104200", 15000)

            self.assertEqual(token, "aurelia-token")
            interface.supervisor.queue_aurelia_launch.assert_called_once_with("104200", 15000)

        asyncio.run(exercise())
        self.assertTrue(interface._presentation_ready)
        interface.supervisor.ensure_shell_presentation.assert_called_once_with()

    def test_watchdog_clears_readiness_when_output_disappears_and_restores_it(self) -> None:
        interface = ConsoleSessionInterface.__new__(ConsoleSessionInterface)
        interface.model = SessionStateModel()
        interface.controller_registry = SimpleNamespace(
            navigation_controller_id=None, navigation_mode="all", controllers={})
        interface._local_identity = None
        interface._local_provider_id = ""
        interface._presentation_ready = True
        interface._graphical_session_id = "test-session"
        interface._graphical_launch_lease = None
        shell_process = SimpleNamespace(pid=os.getpid(), returncode=None)
        interface.supervisor = SimpleNamespace(
            _presentation=object(),
            _shell_process=shell_process,
            _delegated_launch_environment={
                "DISPLAY": ":test", "WAYLAND_DISPLAY": "wayland-test",
                "XDG_RUNTIME_DIR": "/tmp/test-runtime",
            },
            ensure_shell_presentation=Mock(return_value=321),
            queue_aurelia_launch=Mock(return_value="aurelia-token"),
            state_details=Mock(return_value={}),
        )
        interface.supervisor.set_delegated_launch_environment = lambda values: setattr(
            interface.supervisor, "_delegated_launch_environment", dict(values))
        aurelia_config = SimpleNamespace(provider=Mock(return_value=SimpleNamespace(enabled=True)))
        output = False

        async def exercise() -> None:
            async def run_in_thread(function, *args):
                return function(*args)

            nonlocal output
            with patch("lulu.sessiond.asyncio.to_thread", side_effect=run_in_thread), \
                    patch("lulu.sessiond.has_connected_presentation_output",
                          side_effect=lambda: output), \
                    patch("lulu.sessiond.ProviderConfigurationService.from_environment",
                          return_value=aurelia_config), \
                    patch("lulu.sessiond.graphical_context_is_live", return_value=True), \
                    patch("lulu.sessiond.write_graphical_launch_context", return_value=True), \
                    patch("lulu.sessiond.context_is_valid", return_value=True), \
                    patch.object(interface, "StateChanged", Mock()):
                await interface._refresh_presentation_readiness()
                self.assertFalse(interface._presentation_ready)
                with self.assertRaisesRegex(DBusError, "no connected DRM presentation output"):
                    ConsoleSessionInterface.RequestAureliaLaunch.__wrapped__(
                        interface, "104200", 15000)
                interface.supervisor.queue_aurelia_launch.assert_not_called()

                output = True
                await interface._refresh_presentation_readiness()
                self.assertTrue(interface._presentation_ready)
                ConsoleSessionInterface.SetDelegatedLaunchContext.__wrapped__(
                    interface, json.dumps({
                        "DISPLAY": ":test", "WAYLAND_DISPLAY": "wayland-test",
                        "XDG_RUNTIME_DIR": "/tmp/test-runtime",
                    }))
                token = ConsoleSessionInterface.RequestAureliaLaunch.__wrapped__(
                    interface, "104200", 15000)
                self.assertEqual(token, "aurelia-token")

        asyncio.run(exercise())
        self.assertEqual(interface.supervisor.ensure_shell_presentation.call_count, 1)


class GraphicalReadinessInvariantTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.runtime = root / "runtime"
        self.runtime.mkdir()
        x11_dir = root / "x11"
        x11_dir.mkdir()
        self.wayland = self.runtime / "wayland-test"
        self.x11 = x11_dir / "X9"
        self.servers = []
        for path in (self.wayland, self.x11):
            server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            server.bind(str(path))
            server.listen(128)
            self.servers.append(server)
        self.context_path = root / "context.json"
        self.environment = {
            "DISPLAY": f"unix:{self.x11}",
            "WAYLAND_DISPLAY": "wayland-test",
            "XDG_RUNTIME_DIR": str(self.runtime),
        }

    def tearDown(self):
        for server in self.servers:
            server.close()
        self.temp.cleanup()

    def make_ready_interface(self):
        interface = ConsoleSessionInterface.__new__(ConsoleSessionInterface)
        interface.model = SessionStateModel()
        interface.controller_registry = SimpleNamespace(
            navigation_controller_id=None, navigation_mode="all", controllers={})
        interface._local_identity = None
        interface._local_provider_id = ""
        interface._presentation_ready = False
        interface._graphical_session_id = "readiness-test-session"
        interface._graphical_launch_lease = None
        interface._presentation_wait_log_at = 0.0
        interface.StateChanged = lambda *_args: None
        shell = SimpleNamespace(pid=os.getpid(), returncode=None)
        interface.supervisor = SimpleNamespace(
            _shell_process=shell,
            _presentation=object(),
            _delegated_launch_environment={},
            ensure_shell_presentation=Mock(return_value=321),
            shell_graphical_environment=Mock(return_value=self.environment),
            set_delegated_launch_environment=lambda values: setattr(
                interface.supervisor, "_delegated_launch_environment", dict(values)),
            state_details=Mock(return_value={}),
        )
        return interface

    async def tick(self, interface):
        async def inline(function, *args):
            return function(*args)

        with patch("lulu.sessiond.asyncio.to_thread", side_effect=inline), \
                patch("lulu.sessiond.has_connected_presentation_output", return_value=True):
            await interface._refresh_presentation_readiness()

    async def test_readiness_is_published_only_after_valid_context_exists(self):
        interface = self.make_ready_interface()
        with patch("lulu.graphical_launch_context.CONTEXT_PATH", self.context_path):
            await self.tick(interface)
            self.assertTrue(self.context_path.exists())
            self.assertTrue(interface._presentation_ready)
            self.assertTrue(context_is_valid(
                self.context_path, session_id=interface._graphical_session_id,
                shell_pid=os.getpid()))

    async def test_snapshot_publication_failure_keeps_readiness_false(self):
        interface = self.make_ready_interface()
        with patch("lulu.graphical_launch_context.CONTEXT_PATH", self.context_path), \
                patch("lulu.sessiond.write_graphical_launch_context", return_value=False):
            await self.tick(interface)
            self.assertFalse(interface._presentation_ready)
            self.assertFalse(self.context_path.exists())

    async def test_missing_or_invalid_snapshot_lowers_readiness_then_recovers(self):
        interface = self.make_ready_interface()
        with patch("lulu.graphical_launch_context.CONTEXT_PATH", self.context_path):
            await self.tick(interface)
            self.assertTrue(interface._presentation_ready)

            self.context_path.unlink()
            await self.tick(interface)
            self.assertFalse(interface._presentation_ready)
            self.assertFalse(self.context_path.exists())

            await self.tick(interface)
            self.assertTrue(interface._presentation_ready)
            self.assertTrue(self.context_path.exists())

            self.context_path.write_text("{}")
            await self.tick(interface)
            self.assertFalse(interface._presentation_ready)
            self.assertFalse(self.context_path.exists())

            await self.tick(interface)
            self.assertTrue(interface._presentation_ready)
            self.assertTrue(self.context_path.exists())

    def test_supervisor_only_reports_shell_ready_after_gamescope_selection_verifies(self) -> None:
        class Presentation:
            def __init__(self, selected: int | None) -> None:
                self.selected = selected

            def ensure_shell(self, _pid: int) -> int:
                return 321

            def selected_base_window(self) -> int | None:
                return self.selected

            def window_is_focusable(self, window: int) -> bool:
                return window == 321

        for selected, expected in ((321, 321), (999, None), (None, None)):
            with self.subTest(selected=selected):
                supervisor = ProcessSupervisor(
                    SessionStateModel(), presentation=Presentation(selected))
                supervisor._shell_process = SimpleNamespace(pid=123, returncode=None)
                self.assertEqual(supervisor.ensure_shell_presentation(), expected)


if __name__ == "__main__":
    unittest.main()
