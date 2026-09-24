import asyncio
import unittest
from unittest.mock import AsyncMock, patch

from lulu.sessiond import ConsoleSessionInterface, _wait_for_stop


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
