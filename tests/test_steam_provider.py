import asyncio
import unittest
from pathlib import Path
import tempfile
from unittest.mock import AsyncMock, Mock
from unittest.mock import patch
import signal
from unittest.mock import call

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

    async def stop_owned_client(self) -> None:
        return

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
            self.assertEqual(presentation.events, [])

            provider.started.set()
            token = await launch_task
            self.assertEqual(session.state.lifecycle.value, "game")
            self.assertEqual(presentation.events, [("game", 42)])

            provider.exited.set()
            await supervisor._watch_task
            self.assertEqual(session.state.lifecycle.value, "shell")

        asyncio.run(exercise())

    def test_request_launch_starts_steam_infrastructure_before_applaunch(self) -> None:
        async def exercise() -> None:
            provider = SteamProvider(executable="steam", poll_interval=0)
            launcher = Mock(pid=1446)
            with patch.object(provider, "_steam_client_pids", side_effect=[[], [123]]) as clients:
                with patch("lulu.steam_provider.os.getpgid", return_value=1446):
                    with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock, return_value=launcher) as create:
                        request = await provider.request_launch("220780")

            self.assertEqual(request.app_id, "220780")
            self.assertEqual(create.call_count, 2)
            self.assertEqual(create.call_args_list[0].args[:2], ("steam", "-silent"))
            self.assertEqual(create.call_args_list[1].args[:4], ("steam", "-silent", "-applaunch", "220780"))
            self.assertEqual(create.call_args_list[0].kwargs["env"]["DISPLAY"], ":0")
            self.assertEqual(create.call_args_list[1].kwargs["env"]["DISPLAY"], ":0")
            self.assertGreaterEqual(clients.call_count, 2)
            self.assertEqual(provider._owned_client_pids, {123, 1446})

        asyncio.run(exercise())

    def test_owned_group_includes_launcher_ancestor_and_members(self) -> None:
        async def exercise() -> None:
            provider = SteamProvider(poll_interval=0)
            provider._owned_client_pids = {1563}
            provider._owned_client_pgid = 1446
            provider._process_group_members = Mock(return_value={1446, 1563, 1794})
            provider._process_tree = Mock(side_effect=[{1446, 1563, 1697, 1794}, {1446, 1563, 1697, 1794}])
            with patch("lulu.steam_provider.os.kill") as kill:
                with patch("lulu.steam_provider.Path.exists", return_value=False):
                    await provider.stop_owned_client()
            self.assertIn(call(1446, signal.SIGTERM), kill.call_args_list)
            self.assertIn(call(1563, signal.SIGTERM), kill.call_args_list)
            self.assertEqual(provider._owned_client_pids, set())
            self.assertIsNone(provider._owned_client_pgid)

        asyncio.run(exercise())

    def test_stop_request_catches_appid_process_created_during_cleanup(self) -> None:
        async def exercise() -> None:
            provider = SteamProvider(poll_interval=0)
            launcher = Mock(pid=1446, returncode=0)
            request = SteamLaunchRequest("40800", launcher, ())
            now = 0

            def time() -> int:
                nonlocal now
                now += 1
                return now

            clock = Mock(time=time)
            candidates = Mock(side_effect=lambda _app_id: [] if candidates.call_count == 1 else [25878])

            with patch.object(provider, "_candidate_pids", candidates):
                with patch("lulu.steam_provider.asyncio.get_running_loop", return_value=clock):
                    with patch("lulu.steam_provider.os.getpgid", return_value=25843):
                        with patch("lulu.steam_provider.os.killpg") as killpg:
                            await provider.stop_request(request)

            self.assertGreaterEqual(candidates.call_count, 2)
            self.assertIn(call(25843, signal.SIGTERM), killpg.call_args_list)
            self.assertIn(call(25843, signal.SIGKILL), killpg.call_args_list)

        asyncio.run(exercise())

    def test_duplicate_cancel_launches_join_without_incrementing_cancellation(self) -> None:
        class Provider(FakeSteamProvider):
            def __init__(self) -> None:
                super().__init__()
                self.started.clear()
                self.observing = asyncio.Event()
                self.cleanup_started = asyncio.Event()
                self.cleanup_release = asyncio.Event()

            async def observe_launch(
                self, request: SteamLaunchRequest, token: str, orphan_watchdog: float = 300.0
            ) -> SteamLaunch:
                self.observing.set()
                await self.started.wait()
                return await super().observe_launch(request, token, orphan_watchdog)

            async def stop_request(self, request: SteamLaunchRequest) -> None:
                self.cleanup_started.set()
                await self.cleanup_release.wait()

        async def exercise() -> None:
            session = SessionStateModel()
            provider = Provider()
            supervisor = ProcessSupervisor(session, steam_provider=provider)
            supervisor.queue_steam_launch("40800", 1000)
            await provider.observing.wait()
            target = supervisor._steam_launch_task
            self.assertIsNotNone(target)

            cancellations = [asyncio.create_task(supervisor.cancel_launch())]
            await provider.cleanup_started.wait()
            cancellations.extend(asyncio.create_task(supervisor.cancel_launch()) for _ in range(2))
            await asyncio.sleep(0)
            self.assertEqual(target.cancelling(), 1)

            provider.cleanup_release.set()
            results = await asyncio.gather(*cancellations, return_exceptions=True)
            self.assertEqual(results, [None, None, None])
            self.assertEqual(target.cancelling(), 1)
            self.assertTrue(target.done())

        asyncio.run(exercise())

    def test_phase_b_cancellation_stops_owned_steam_before_pending_cleanup(self) -> None:
        class Provider(FakeSteamProvider):
            def __init__(self, owns_steam: bool) -> None:
                super().__init__()
                self.started.clear()
                self.observing = asyncio.Event()
                self.cleanup_started = asyncio.Event()
                self.cleanup_release = asyncio.Event()
                self.owns_steam = owns_steam
                self.events: list[str] = []

            async def observe_launch(
                self, request: SteamLaunchRequest, token: str, orphan_watchdog: float = 300.0
            ) -> SteamLaunch:
                self.observing.set()
                await self.started.wait()
                return await super().observe_launch(request, token, orphan_watchdog)

            async def stop_owned_client(self) -> None:
                if self.owns_steam:
                    self.events.append("owned-steam-stopped")
                    self.owns_steam = False
                else:
                    self.events.append("pre-existing-steam-preserved")

            async def stop_request(self, request: SteamLaunchRequest) -> None:
                self.events.append("pending-request-cleanup")
                self.assert_owned_steam_stopped = getattr(self, "assert_owned_steam_stopped", None)
                if self.assert_owned_steam_stopped is not None:
                    self.assert_owned_steam_stopped()
                self.cleanup_started.set()
                await self.cleanup_release.wait()

        async def exercise() -> None:
            owned = Provider(True)
            supervisor = ProcessSupervisor(SessionStateModel(), steam_provider=owned)
            supervisor.queue_steam_launch("40800", 1000)
            await owned.observing.wait()
            owned.assert_owned_steam_stopped = lambda: self.assertFalse(owned.owns_steam)
            cancel = asyncio.create_task(supervisor.cancel_launch())
            await owned.cleanup_started.wait()
            self.assertEqual(owned.events, ["owned-steam-stopped", "pending-request-cleanup"])
            owned.cleanup_release.set()
            await cancel

            pre_existing = Provider(False)
            supervisor = ProcessSupervisor(SessionStateModel(), steam_provider=pre_existing)
            supervisor.queue_steam_launch("40800", 1000)
            await pre_existing.observing.wait()
            pre_existing.assert_owned_steam_stopped = lambda: self.assertTrue(not pre_existing.owns_steam)
            cancel = asyncio.create_task(supervisor.cancel_launch())
            await pre_existing.cleanup_started.wait()
            self.assertEqual(pre_existing.events, ["pre-existing-steam-preserved", "pending-request-cleanup"])
            pre_existing.cleanup_release.set()
            await cancel

        asyncio.run(exercise())

    def test_preexisting_steam_is_not_claimed_or_stopped(self) -> None:
        async def exercise() -> None:
            provider = SteamProvider(poll_interval=0)
            with patch.object(provider, "_steam_client_pids", return_value=[1563]):
                with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock) as create:
                    await provider.ensure_client()
            create.assert_not_awaited()
            self.assertEqual(provider._owned_client_pids, set())
            with patch("lulu.steam_provider.os.kill") as kill:
                await provider.stop_owned_client()
            kill.assert_not_called()

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

    def test_store_uses_on_demand_gamepad_uri_control_without_fixed_sleep(self) -> None:
        provider = SteamProvider(executable="steam")
        with patch("lulu.steam_provider.subprocess.Popen") as popen:
            self.assertEqual(provider.open_gamepadui(), "steam://open/gamepadui")
            self.assertEqual(provider.open_store(), "steam://open/store")
        self.assertEqual([call.args[0] for call in popen.call_args_list], [
            ["steam", "steam://open/gamepadui"],
            ["steam", "steam://open/store"],
        ])
        self.assertNotIn("-gamepadui", popen.call_args_list[0].args[0])

    def test_install_dispatches_validated_steam_uri(self) -> None:
        provider = SteamProvider(executable="steam")
        with patch("lulu.steam_provider.subprocess.Popen") as popen:
            uri = provider.install("268910")
        self.assertEqual(uri, "steam://install/268910")
        popen.assert_called_once()
        self.assertEqual(popen.call_args.args[0], ["steam", uri])

    def test_install_rejects_invalid_app_id_before_dispatch(self) -> None:
        provider = SteamProvider(executable="steam")
        with patch("lulu.steam_provider.subprocess.Popen") as popen:
            for app_id in ("", "0", "-1", "268910x", "steam://install/268910"):
                with self.assertRaises(ValueError):
                    provider.install(app_id)
        popen.assert_not_called()

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
            self.assertEqual(presentation.events, [("game", 42), ("shell", 7)])
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

    def test_steam_store_transitions_gamepad_ui_to_shell_and_can_repeat(self) -> None:
        class Provider:
            def __init__(self) -> None:
                self.uris: list[str] = []
                self.pids = [99]
                self.stops = 0

            async def ensure_client(self) -> None:
                return

            async def stop_owned_client(self) -> None:
                self.stops += 1

            def open_gamepadui(self) -> str:
                self.uris.append("steam://open/gamepadui")
                return self.uris[-1]

            def open_store(self) -> str:
                self.uris.append("steam://open/store")
                return self.uris[-1]

            def gamepadui_pids(self) -> list[int]:
                return self.pids

        class StorePresentation(RecordingPresentation):
            def __init__(self) -> None:
                super().__init__()
                self.presented = True

            def select_pids(self, pids, timeout: float) -> int:
                self.events.append(("game", pids()[0]))
                return pids()[0]

            def window_is_focusable(self, window: int) -> bool:
                return self.presented

        async def exercise() -> None:
            session = SessionStateModel()
            provider = Provider()
            presentation = StorePresentation()
            supervisor = ProcessSupervisor(session, steam_provider=provider, presentation=presentation)
            supervisor._shell_process = Mock(pid=7)

            first = await supervisor.launch_steam_store(1000)
            self.assertEqual(session.state.presentation, Presentation.FOREIGN_UI)
            self.assertEqual(presentation.events, [("game", 99)])
            presentation.presented = False
            await supervisor._steam_store_watch_task
            self.assertEqual(session.state.lifecycle.value, "shell")
            self.assertEqual(presentation.events[-1], ("shell", 7))

            presentation.presented = True
            second = await supervisor.launch_steam_store(1000)
            self.assertNotEqual(first, second)
            presentation.presented = False
            await supervisor._steam_store_watch_task
            self.assertEqual(session.state.lifecycle.value, "shell")
            self.assertEqual(provider.uris, ["steam://open/gamepadui", "steam://open/store"] * 2)
            self.assertEqual(provider.stops, 2)
            self.assertEqual(presentation.events, [("game", 99), ("shell", 7), ("game", 99), ("shell", 7)])

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
