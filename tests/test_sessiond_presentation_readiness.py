from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from dbus_next import DBusError

from lulu.console_sessiond import SessionStateModel
from lulu.sessiond import ConsoleSessionInterface


def make_interface(*, ready: bool, presentation: object | None = object(),
                   shell_process: object | None = None) -> ConsoleSessionInterface:
    interface = ConsoleSessionInterface.__new__(ConsoleSessionInterface)
    interface.model = SessionStateModel()
    interface._presentation_ready = ready
    interface.supervisor = SimpleNamespace(
        _presentation=presentation,
        _shell_process=shell_process if shell_process is not None
        else SimpleNamespace(returncode=None),
        queue_steam_launch=Mock(return_value="steam-token"),
        queue_aurelia_launch=Mock(return_value="aurelia-token"),
    )
    return interface


class SessiondPresentationReadinessTests(unittest.TestCase):
    def test_ready_shell_allows_both_steam_backends(self) -> None:
        interface = make_interface(ready=True)
        aurelia_config = SimpleNamespace(provider=Mock(return_value=SimpleNamespace(enabled=True)))

        with patch("lulu.sessiond.has_connected_presentation_output", return_value=True), \
                patch("lulu.sessiond.ProviderConfigurationService.from_environment",
                      return_value=aurelia_config):
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
                              aurelia_config):
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
        interface._select_ready_shell = Mock()
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
        interface._select_ready_shell.assert_not_called()
        self.assertFalse(interface._presentation_ready)

    def test_successful_shell_window_selection_marks_presentation_ready(self) -> None:
        interface = ConsoleSessionInterface.__new__(ConsoleSessionInterface)
        interface._presentation_ready = False
        shell_process = SimpleNamespace(returncode=None)
        interface.supervisor = SimpleNamespace(
            _presentation=SimpleNamespace(select_shell=Mock()),
            _shell_process=shell_process,
        )

        async def exercise() -> None:
            async def run_in_thread(function, *args):
                return function(*args)

            with patch.object(Path, "read_text", return_value="321"), \
                    patch("lulu.sessiond.asyncio.to_thread", side_effect=run_in_thread), \
                    patch("lulu.sessiond.has_connected_presentation_output", return_value=True):
                await interface._select_ready_shell()

        asyncio.run(exercise())
        self.assertTrue(interface._presentation_ready)
        interface.supervisor._presentation.select_shell.assert_called_once_with(321)


if __name__ == "__main__":
    unittest.main()
