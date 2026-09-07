import asyncio
import unittest
from pathlib import Path
import tempfile
from unittest.mock import Mock
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

    async def observe_launch(self, request: SteamLaunchRequest, token: str) -> SteamLaunch:
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
            supervisor = ProcessSupervisor(
                session,
                steam_provider=provider,
                input_mode_changed=modes.append,
            )
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
            self.assertEqual(session.last_result.pid, 42)

        asyncio.run(exercise())


if __name__ == "__main__":
    unittest.main()
