import asyncio
import unittest
from pathlib import Path
import tempfile
from unittest.mock import AsyncMock, Mock
from unittest.mock import patch

from lulu.console_sessiond import SessionStateModel
from lulu.contracts import InputMode, Presentation
from lulu.launch_identity import LaunchIdentity
from lulu.process_supervisor import ProcessSupervisor
from lulu.steam_provider import InstalledSteamGame, SteamLaunch, SteamLaunchRequest, SteamProvider


class FakeSteamProvider:
    def __init__(self) -> None:
        self.exited = asyncio.Event()
        self.started = asyncio.Event()
        self.started.set()

    async def request_launch(self, app_id: str) -> SteamLaunchRequest:
        return SteamLaunchRequest(app_id, Mock())

    async def observe_launch(
        self, request: SteamLaunchRequest, token: str, orphan_watchdog: float = 300.0
    ) -> SteamLaunch:
        await self.started.wait()
        identity = LaunchIdentity(token, 42, 42, "/games/SuperMeatBoy", ("SuperMeatBoy",))
        return SteamLaunch(request.app_id, request.launcher, identity)

    async def wait_for_exit(self, launch: SteamLaunch) -> None:
        await self.exited.wait()

    async def stop(self, launch: SteamLaunch) -> None:
        self.exited.set()


class RecordingPresentation:
    def __init__(self) -> None:
        self.events: list[tuple[str, int | None]] = []

    def clear_selection(self) -> None:
        self.events.append(("clear", None))

    def select_pid(self, pid: int) -> int:
        self.events.append(("game", pid))
        return pid

    def select_shell(self, pid: int) -> int:
        self.events.append(("shell", pid))
        return pid


class DelayedPresentation:
    def __init__(self) -> None:
        self.process_sets: list[list[int]] = []

    def clear_selection(self) -> None:
        return

    def select_pids(self, pids, timeout: float) -> int:
        self.process_sets.append(pids())
        return 99

    def select_shell(self, pid: int) -> int:
        return pid


class SteamProviderTests(unittest.TestCase):
    def test_starting_retains_ownership_until_game_process_is_discovered(self) -> None:
        async def exercise() -> None:
            session = SessionStateModel()
            provider = FakeSteamProvider()
            presentation = RecordingPresentation()
            supervisor = ProcessSupervisor(
                session,
                steam_provider=provider,
                presentation=presentation,
            )
            provider.started.clear()
            launch_task = asyncio.create_task(supervisor.launch_steam("40800", 1))
            await asyncio.sleep(0)
            self.assertEqual(session.state.lifecycle.value, "starting")
            self.assertEqual(presentation.events, [("clear", None)])

            provider.started.set()
            token = await launch_task
            self.assertEqual(session.state.lifecycle.value, "game")
            self.assertEqual(presentation.events, [("clear", None), ("game", 42)])

            provider.exited.set()
            await supervisor._watch_task
            self.assertEqual(session.state.lifecycle.value, "shell")

        asyncio.run(exercise())

    def test_request_launch_starts_steam_infrastructure_before_applaunch(self) -> None:
        async def exercise() -> None:
            provider = SteamProvider(executable="steam", poll_interval=0)
            launcher = Mock()
            with patch.object(provider, "_steam_client_pids", side_effect=[[], [123]]) as clients:
                with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock, return_value=launcher) as create:
                    request = await provider.request_launch("220780")

            self.assertEqual(request.app_id, "220780")
            self.assertEqual(create.call_count, 2)
            self.assertEqual(create.call_args_list[0].args[:2], ("steam", "-silent"))
            self.assertEqual(create.call_args_list[1].args[:4], ("steam", "-silent", "-applaunch", "220780"))
            self.assertEqual(create.call_args_list[0].kwargs["env"]["DISPLAY"], ":0")
            self.assertEqual(create.call_args_list[1].kwargs["env"]["DISPLAY"], ":0")
            self.assertGreaterEqual(clients.call_count, 2)

        asyncio.run(exercise())

    def test_open_game_details_detaches_uri_without_waiting(self) -> None:
        provider = SteamProvider(executable="steam")
        with patch("lulu.steam_provider.subprocess.Popen") as popen:
            uri = provider.open_game_details("268910")

        self.assertEqual(uri, "steam://nav/games/details/268910")
        popen.assert_called_once()
        self.assertEqual(popen.call_args.args[0], ["steam", uri])
        self.assertTrue(popen.call_args.kwargs["start_new_session"])
        self.assertNotIn("-applaunch", popen.call_args.args)

    def test_launch_gamepad_title_detaches_rungame_uri_without_waiting(self) -> None:
        provider = SteamProvider(executable="steam")
        with patch("lulu.steam_provider.subprocess.Popen") as popen:
            uri = provider.launch_gamepad_title("268910")

        self.assertEqual(uri, "steam://rungameid/268910")
        popen.assert_called_once()
        self.assertEqual(popen.call_args.args[0], ["steam", uri])
        self.assertTrue(popen.call_args.kwargs["start_new_session"])

    def test_request_launch_rejects_existing_target_before_duplicate_submission(self) -> None:
        async def exercise() -> None:
            provider = SteamProvider(executable="steam")
            with patch.object(provider, "_candidate_pids", return_value=[1234]):
                with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock) as create:
                    with self.assertRaisesRegex(ValueError, "already running"):
                        await provider.request_launch("15700")
            create.assert_not_awaited()

        asyncio.run(exercise())

    def test_queued_launch_failure_returns_to_shell_asynchronously(self) -> None:
        class FailingProvider(FakeSteamProvider):
            async def request_launch(self, app_id: str) -> SteamLaunchRequest:
                raise TimeoutError("Steam client did not become ready")

        async def exercise() -> None:
            session = SessionStateModel()
            supervisor = ProcessSupervisor(session, steam_provider=FailingProvider())

            token = supervisor.queue_steam_launch("220780", 1000)
            self.assertEqual(session.state.lifecycle.value, "launch_requested")
            with self.assertRaisesRegex(ValueError, "Steam launch failed"):
                await supervisor._steam_launch_task

            self.assertEqual(session.state.lifecycle.value, "shell")
            self.assertEqual(session.last_result.token, token)
            self.assertIn("Steam launch failed", session.last_failure_reason)

        asyncio.run(exercise())

    def test_queued_launch_returns_before_title_discovery(self) -> None:
        async def exercise() -> None:
            session = SessionStateModel()
            provider = FakeSteamProvider()
            provider.started.clear()
            supervisor = ProcessSupervisor(session, steam_provider=provider)

            token = supervisor.queue_steam_launch("40800", 1000)
            self.assertEqual(session.state.lifecycle.value, "launch_requested")
            await asyncio.sleep(0)
            self.assertEqual(session.state.lifecycle.value, "starting")

            provider.started.set()
            for _ in range(10):
                await asyncio.sleep(0)
                if supervisor._watch_task is not None:
                    break
            self.assertEqual(session.state.lifecycle.value, "game")
            provider.exited.set()
            await supervisor._watch_task
            self.assertEqual(session.state.lifecycle.value, "shell")

        asyncio.run(exercise())

    def test_list_installed_parses_manifests_and_filters_runtimes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "Steam"
            apps = root / "steamapps"
            apps.mkdir(parents=True)
            (apps / "libraryfolders.vdf").write_text(
                f'"libraryfolders" {{ "0" {{ "path" "{root}" }} }}'
            )
            (apps / "appmanifest_40800.acf").write_text(
                '"AppState" { "appid" "40800" "name" "Super Meat Boy" '
                '"StateFlags" "4" "installdir" "Super Meat Boy" '
                '"SizeOnDisk" "123" "LastPlayed" "9" }'
            )
            (apps / "appmanifest_1070560.acf").write_text(
                '"AppState" { "appid" "1070560" "name" "Steam Linux Runtime 1.0" '
                '"StateFlags" "4" "installdir" "SteamLinuxRuntime" }'
            )

            games = SteamProvider().list_installed((root,))

        self.assertEqual(games, [InstalledSteamGame(
            "40800", "Super Meat Boy", str(root / "steamapps/common/Super Meat Boy"),
            str(root), 123, 9,
        )])
    def test_environment_markers_are_decoded(self) -> None:
        with patch.object(Path, "read_bytes", return_value=b"SteamAppId=40800\0DISPLAY=:0\0"):
            self.assertEqual(SteamProvider._environment(1), {"SteamAppId": "40800", "DISPLAY": ":0"})

    def test_runtime_processes_are_not_title_candidates(self) -> None:
        self.assertTrue(
            SteamProvider._is_runtime_process(
                "/usr/bin/reaper", ("reaper", "SteamLaunch", "AppId=40800")
            )
        )
        self.assertTrue(
            SteamProvider._is_runtime_process(
                "/usr/lib/pressure-vessel/srt-bwrap", ("srt-bwrap",)
            )
        )
        self.assertFalse(
            SteamProvider._is_runtime_process(
                "/games/SuperMeatBoy", ("./amd64/SuperMeatBoy",)
            )
        )
        self.assertTrue(
            SteamProvider._is_runtime_process(
                "/opt/proton/files/bin/python3", ("proton", "waitforexitandrun", "Cuphead.exe")
            )
        )
        self.assertTrue(
            SteamProvider._is_runtime_process(
                "/opt/proton/files/bin/wine-preloader", ("c:\\windows\\system32\\steam.exe",)
            )
        )
        self.assertFalse(
            SteamProvider._is_runtime_process(
                "/opt/proton/files/bin/wine-preloader",
                ("S:\\steamapps\\common\\Cuphead\\Cuphead.exe",),
            )
        )
        self.assertTrue(
            SteamProvider._is_runtime_process(
                "/opt/proton/files/bin/wine-preloader",
                ("C:\\windows\\system32\\services.exe",),
            )
        )

    def test_native_title_controls_return_without_steam_exit(self) -> None:
        async def exercise() -> None:
            session = SessionStateModel()
            provider = FakeSteamProvider()
            modes: list[InputMode] = []
            presentation = RecordingPresentation()
            supervisor = ProcessSupervisor(
                session,
                steam_provider=provider,
                presentation=presentation,
                input_mode_changed=modes.append,
            )
            supervisor._shell_process = Mock(pid=7)
            token = await supervisor.launch_steam("40800", 1000)
            self.assertEqual(session.state.lifecycle.value, "game")
            self.assertEqual(session.state.presentation, Presentation.GAME)
            self.assertEqual(session.state.input_mode, InputMode.GAME)
            self.assertEqual(modes, [InputMode.GAME])
            self.assertEqual(supervisor.active_identity.executable, "/games/SuperMeatBoy")
            provider.exited.set()
            await supervisor._watch_task
            self.assertEqual(session.state.lifecycle.value, "shell")
            self.assertEqual(session.state.presentation, Presentation.SHELL)
            self.assertEqual(session.state.input_mode, InputMode.SHELL)
            self.assertEqual(modes, [InputMode.GAME, InputMode.SHELL])
            self.assertIsNone(supervisor.active_identity)
            self.assertEqual(session.last_result.token, token)
            self.assertEqual(presentation.events, [("clear", None), ("game", 42), ("shell", 7)])
            self.assertEqual(session.last_result.pid, 42)

        asyncio.run(exercise())

    def test_target_exit_restores_shell_while_provider_remains_alive(self) -> None:
        async def exercise() -> None:
            session = SessionStateModel()
            provider = FakeSteamProvider()
            presentation = RecordingPresentation()
            supervisor = ProcessSupervisor(session, steam_provider=provider, presentation=presentation)
            supervisor._shell_process = Mock(pid=7)
            token = await supervisor.launch_steam("15700", 1000)
            provider.exited.set()
            await supervisor._watch_task
            self.assertEqual(session.state.lifecycle.value, "shell")
            self.assertEqual(session.state.input_mode.value, "shell")
            self.assertEqual(presentation.events[-1], ("shell", 7))
            self.assertIsNone(supervisor.active_identity)
            self.assertEqual(session.last_result.token, token)

        asyncio.run(exercise())

    def test_delayed_indirect_window_owner_enters_pending_before_running(self) -> None:
        class Provider(FakeSteamProvider):
            def presentation_pids(self, app_id: str) -> list[int]:
                return [99]

        async def exercise() -> None:
            session = SessionStateModel()
            states: list[str] = []
            presentation = DelayedPresentation()
            supervisor = ProcessSupervisor(
                session,
                state_changed=lambda: states.append(session.state.lifecycle.value),
                steam_provider=Provider(),
                presentation=presentation,
            )
            supervisor._shell_process = Mock(pid=7)
            token = await supervisor.launch_steam("15700", 1000)
            self.assertEqual(session.state.lifecycle.value, "game")
            self.assertIn("presentation_pending", states)
            self.assertEqual(presentation.process_sets, [[99]])
            self.assertEqual(session.state.launch_token, token)

        asyncio.run(exercise())


if __name__ == "__main__":
    unittest.main()
