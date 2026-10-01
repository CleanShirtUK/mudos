import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from lulu.console_sessiond import SessionStateModel
from lulu.controllerd import ControllerRegistry
from lulu.sessiond import ConsoleSessionInterface, _wait_for_stop, serve


class SessiondTests(unittest.TestCase):
    def test_cancel_launch_delegates_to_supervisor(self) -> None:
        interface = ConsoleSessionInterface.__new__(ConsoleSessionInterface)

        class Supervisor:
            def __init__(self) -> None:
                self.cancelled = False

            async def cancel_launch(self) -> None:
                self.cancelled = True

        supervisor = Supervisor()
        interface.supervisor = supervisor

        asyncio.run(ConsoleSessionInterface.CancelLaunch.__wrapped__(interface))

        self.assertTrue(supervisor.cancelled)

    def test_guide_quit_targets_only_the_sessiond_owned_local_process_group(self) -> None:
        from types import SimpleNamespace
        from lulu.launch_identity import LaunchIdentity

        interface = ConsoleSessionInterface.__new__(ConsoleSessionInterface)
        interface._local_identity = LaunchIdentity("owned-token", 1234, 1234, "/game", ("/game",))
        interface.model = SimpleNamespace(state=SimpleNamespace(launch_token="owned-token"))
        interface.supervisor = SimpleNamespace()
        with patch("lulu.sessiond.os.killpg") as killpg:
            result = asyncio.run(ConsoleSessionInterface.QuitActiveSession.__wrapped__(interface))
        self.assertEqual(result, "quit-requested")
        killpg.assert_called_once_with(1234, __import__("signal").SIGTERM)

    def test_eden_quit_uses_owned_group_sigterm_without_unmapping_window_first(self) -> None:
        from types import SimpleNamespace
        from lulu.launch_identity import LaunchIdentity

        supervisor = SimpleNamespace(
            _presentation=None,
            _process_group_members=lambda pgid: set(),
        )
        interface = ConsoleSessionInterface.__new__(ConsoleSessionInterface)
        interface._local_identity = LaunchIdentity(
            "owned-token", 1234, 1234, "/usr/bin/bash",
            ("/opt/lulu/current/packaging/eden-flatpak", "--config", "/tmp/eden.ini"),
        )
        interface.model = SimpleNamespace(state=SimpleNamespace(launch_token="owned-token"))
        interface.supervisor = supervisor

        with patch("lulu.sessiond.os.killpg") as killpg:
            result = asyncio.run(ConsoleSessionInterface.QuitActiveSession.__wrapped__(interface))

        self.assertEqual(result, "quit-requested")
        killpg.assert_called_once_with(1234, __import__("signal").SIGTERM)

    def test_eden_quit_falls_back_to_sigkill_after_termination_timeout(self) -> None:
        from types import SimpleNamespace
        from lulu.launch_identity import LaunchIdentity

        presentation = SimpleNamespace(
            window_for_pids=lambda pids, timeout: 88,
            request_window_close=lambda window: None,
        )
        group_members = {1234, 1235}
        kill_sent = False
        reap_polls = 0

        def current_members(pgid):
            nonlocal reap_polls
            if kill_sent:
                if reap_polls < 2:
                    reap_polls += 1
                    return set(group_members)
                group_members.clear()
            return set(group_members)

        supervisor = SimpleNamespace(
            _presentation=presentation,
            _process_group_members=current_members,
        )
        interface = ConsoleSessionInterface.__new__(ConsoleSessionInterface)
        interface._local_identity = LaunchIdentity(
            "owned-token", 1234, 1234, "/usr/bin/bash",
            ("/opt/lulu/current/packaging/eden-flatpak", "--config", "/tmp/eden.ini"),
        )
        interface.model = SimpleNamespace(state=SimpleNamespace(launch_token="owned-token"))
        interface.supervisor = supervisor

        def signal_group(pgid, sig):
            nonlocal kill_sent
            if sig == __import__("signal").SIGKILL:
                kill_sent = True

        with patch("lulu.sessiond.EDEN_TERMINATE_TIMEOUT", 0), \
                patch("lulu.sessiond.os.killpg", side_effect=signal_group) as killpg:
            result = asyncio.run(ConsoleSessionInterface.QuitActiveSession.__wrapped__(interface))

        self.assertEqual(result, "quit-requested")
        signal = __import__("signal")
        self.assertEqual(killpg.call_args_list, [
            unittest.mock.call(1234, signal.SIGTERM),
            unittest.mock.call(1234, signal.SIGKILL),
        ])

    def test_local_session_return_waits_for_process_group_before_restoring_shell(self) -> None:
        from lulu.launch_identity import LaunchIdentity

        model = SessionStateModel()
        token = model.request_launch("local:switch:game")
        model.launch_starting(token)
        model.primary_started(token)
        members = iter(({456}, set()))
        observed = []

        class Presentation:
            def select_shell(self, pid):
                observed.append(("presentation", model.state.lifecycle, model.state.input_mode))

        interface = ConsoleSessionInterface.__new__(ConsoleSessionInterface)
        interface.model = model
        interface._local_identity = LaunchIdentity(token, 123, 123, "/eden", ("eden",))
        interface._local_provider_id = "eden"
        interface._applied_input_modes = {}
        interface._native_controller = False
        interface._inputplumber = SimpleNamespace(runtime_composite_statuses=lambda: {})
        interface._apply_input_mode = lambda mode: observed.append(("input", mode))
        interface._state_changed = lambda: None
        interface._state_json = lambda: "{}"
        interface.StateChanged = lambda state: None
        interface.supervisor = SimpleNamespace(
            _process_group_members=lambda pgid: next(members),
            _presentation=Presentation(),
            _shell_process=SimpleNamespace(pid=99),
        )

        async def exercise():
            task = asyncio.create_task(
                ConsoleSessionInterface.EndLocalSession.__wrapped__(interface, token, -15)
            )
            await asyncio.sleep(0)
            self.assertEqual(model.state.lifecycle.value, "game")
            await task

        asyncio.run(exercise())
        self.assertEqual(observed[0][0], "presentation")
        self.assertEqual(observed[0][1].value, "returning")
        self.assertEqual(observed[0][2].value, "gamepad")
        self.assertEqual(observed[1][0], "input")
        self.assertEqual(observed[1][1].value, "shell")
        self.assertEqual(model.state.lifecycle.value, "shell")
        self.assertEqual(model.state.input_mode.value, "shell")

    def test_guide_quit_rejects_a_stale_session_identity(self) -> None:
        from types import SimpleNamespace
        from lulu.launch_identity import LaunchIdentity
        from dbus_next import DBusError

        interface = ConsoleSessionInterface.__new__(ConsoleSessionInterface)
        interface._local_identity = LaunchIdentity("old-token", 1234, 1234, "/game", ("/game",))
        interface.model = SimpleNamespace(state=SimpleNamespace(launch_token="new-token"))
        interface.supervisor = SimpleNamespace()
        with patch("lulu.sessiond.os.killpg") as killpg:
            with self.assertRaises(DBusError):
                asyncio.run(ConsoleSessionInterface.QuitActiveSession.__wrapped__(interface))
        killpg.assert_not_called()

    def test_idle_session_waits_for_explicit_stop_signal(self) -> None:
        async def exercise() -> None:
            stop_event = asyncio.Event()
            task = asyncio.create_task(_wait_for_stop(stop_event))
            await asyncio.sleep(0)
            self.assertFalse(task.done())
            stop_event.set()
            await task
            self.assertTrue(task.done())

        asyncio.run(exercise())

    def test_session_api_becomes_ready_without_any_controller(self) -> None:
        interface = ConsoleSessionInterface.__new__(ConsoleSessionInterface)
        interface.model = SessionStateModel()
        interface._inputplumber = type("NoControllers", (), {
            "runtime_composite_statuses": lambda self: {},
        })()
        interface.controller_registry = ControllerRegistry()
        interface._native_controller = False
        interface._initialized_composites = {}
        interface._applied_input_modes = {}
        interface._inputplumber_event = None
        interface._controller_monitor_task = None
        interface._presentation_watchdog_enabled = False
        interface._presentation_watchdog_task = None
        interface._shell_selection_task = None
        interface._local_identity = None
        interface.StateChanged = lambda state: None
        interface.supervisor = type("Supervisor", (), {
            "stop": AsyncMock(),
        })()

        class FakeBus:
            def __init__(self):
                self.calls = []
                self.handlers = []

            async def connect(self):
                self.calls.append("connect")
                return self

            def export(self, path, exported):
                self.calls.append(("export", path))

            async def request_name(self, name):
                self.calls.append(("name", name))

            def _add_match_rule(self, rule):
                self.calls.append(("match", rule))

            def add_message_handler(self, handler):
                self.handlers.append(handler)

            def remove_message_handler(self, handler):
                self.handlers.remove(handler)

            def disconnect(self):
                self.calls.append("disconnect")

        buses = []
        ready_state = {}

        def new_bus(*args, **kwargs):
            bus = FakeBus()
            buses.append(bus)
            return bus

        async def exercise() -> None:
            with patch("lulu.sessiond.MessageBus", side_effect=new_bus), \
                    patch("lulu.sessiond.ConsoleSessionInterface", return_value=interface), \
                    patch("lulu.sessiond.recovery_required", return_value=False), \
                    patch("lulu.sessiond.sdl_gamepad_inventory", return_value=[]), \
                    patch("lulu.sessiond.GamescopeWindowObserver",
                          return_value=SimpleNamespace(start=lambda: None, stop=lambda: None)), \
                    patch("lulu.sessiond._notify_systemd_ready",
                          side_effect=lambda: ready_state.update({
                              "api_exported": ("export", "/org/lulu/ConsoleSession") in buses[0].calls,
                              "name_owned": ("name", "org.lulu.ConsoleSessiond") in buses[0].calls,
                              "controller_signal_subscribed": any(
                                  call[0] == "match" for call in buses[1].calls
                              ),
                          })) as notify_ready, \
                    patch("lulu.sessiond._wait_for_stop", new=AsyncMock()):
                await serve()
            notify_ready.assert_called_once()

        asyncio.run(exercise())
        self.assertGreaterEqual(len(buses), 2)
        self.assertLess(buses[0].calls.index(("export", "/org/lulu/ConsoleSession")),
                        buses[0].calls.index(("name", "org.lulu.ConsoleSessiond")))
        self.assertTrue(any(call[0] == "match" for call in buses[1].calls))
        self.assertEqual(ready_state, {
            "api_exported": True,
            "name_owned": True,
            "controller_signal_subscribed": True,
        })

    def test_reset_requests_systemd_restart_of_the_owned_vt2_session(self) -> None:
        interface = ConsoleSessionInterface.__new__(ConsoleSessionInterface)
        interface._reset_requested = False
        completed = AsyncMock()
        completed.returncode = 0
        completed.communicate.return_value = (b"", b"")

        async def exercise() -> None:
            with patch("lulu.sessiond.asyncio.create_subprocess_exec",
                       new=AsyncMock(return_value=completed)) as spawn:
                await interface._reset_mudos()
            spawn.assert_awaited_once_with(
                "systemctl", "--no-block", "restart", "lulu-session@2.service",
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.PIPE,
            )

        asyncio.run(exercise())

    def test_reset_restart_failure_is_reported_and_can_retry(self) -> None:
        interface = ConsoleSessionInterface.__new__(ConsoleSessionInterface)
        interface._reset_requested = True
        failed = AsyncMock()
        failed.returncode = 1
        failed.communicate.return_value = (b"", b"not authorized")

        async def exercise() -> None:
            with patch("lulu.sessiond.asyncio.create_subprocess_exec",
                       new=AsyncMock(return_value=failed)):
                await interface._reset_mudos()

        asyncio.run(exercise())
        self.assertFalse(interface._reset_requested)

    def test_restart_unit_has_only_narrow_systemd_authority(self) -> None:
        root = __import__("pathlib").Path(__file__).resolve().parents[1]
        rule = (root / "packaging/polkit-1/rules.d/56-lulu-session-restart.rules").read_text()
        service = (root / "packaging/lulu-session@.service").read_text()
        runtime = (root / "scripts/dev-runtime.sh").read_text()
        self.assertIn('action.lookup("unit") == "lulu-session@2.service"', rule)
        self.assertIn('action.lookup("verb") == "restart"', rule)
        self.assertNotIn('lulu-session@tty2.service', rule + runtime)
        self.assertIn("Conflicts=getty@tty%i.service", service)
        self.assertIn("lulu-session@2.service", runtime)
        self.assertIn("56-lulu-session-restart.rules", runtime)

    def test_restart_does_not_stop_prerequisites_or_kill_its_own_unit(self) -> None:
        from pathlib import Path

        source = (Path(__file__).resolve().parents[1] / "src/lulu/sessiond.py").read_text()
        reset = source.split("async def _reset_mudos(self)", 1)[1].split("@method()", 1)[0]
        self.assertIn('"systemctl", "--no-block", "restart", unit', reset)
        self.assertNotIn("supervisor.stop()", reset)
        self.assertNotIn("os.kill", reset)

    def test_first_audio_request_initializes_then_queues_that_cue(self) -> None:
        from pathlib import Path

        source = (Path(__file__).resolve().parents[1] / "native/lulu-shell.cpp").read_text()
        play = source.split("Q_INVOKABLE bool playUiSound", 1)[1].split("void setUiAudioAssetDirectory", 1)[0]
        self.assertIn("ensureUiAudioDevice(request)", play)
        self.assertIn("SDL_PutAudioStreamData(uiAudioStream_, pcm.constData(), pcm.size())", play)
        self.assertIn('"UI_AUDIO_PLAY" << request << semantic', play)
        self.assertLess(play.index("ensureUiAudioDevice(request)"),
                        play.index("SDL_PutAudioStreamData"))
        self.assertIn("if (!ensureUiAudioDevice(request))", play)
        self.assertIn("UI_AUDIO_RETRY_DEFERRED", source)
        self.assertIn("uiAudioRetryAfterMs_ =", source)


if __name__ == "__main__":
    unittest.main()
