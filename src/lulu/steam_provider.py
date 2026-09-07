"""Small Steam client adapter for resident-client AppID launches."""

from dataclasses import dataclass
import asyncio
import os
from pathlib import Path
import signal

from .launch_identity import LaunchIdentity


@dataclass(frozen=True, slots=True)
class SteamLaunch:
    app_id: str
    launcher: asyncio.subprocess.Process
    title: LaunchIdentity


class SteamProvider:
    """Launches an AppID through Steam and observes the native title process."""

    def __init__(self, executable: str = "steam", poll_interval: float = 0.1) -> None:
        self.executable = executable
        self.poll_interval = poll_interval

    async def launch(self, app_id: str, token: str, timeout_ms: int) -> SteamLaunch:
        if not app_id.isdecimal() or int(app_id) < 1:
            raise ValueError("Steam AppID must be a positive integer")
        process = await asyncio.create_subprocess_exec(
            self.executable,
            "-silent",
            "-applaunch",
            app_id,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
            start_new_session=True,
        )
        try:
            title = await asyncio.wait_for(
                self._find_title(app_id, token), timeout=timeout_ms / 1000
            )
        except (asyncio.TimeoutError, OSError):
            await process.wait()
            raise
        await process.wait()
        return SteamLaunch(app_id, process, title)

    async def _find_title(self, app_id: str, token: str) -> LaunchIdentity:
        while True:
            for pid in self._candidate_pids(app_id):
                try:
                    pgid = os.getpgid(pid)
                    argv = self._argv(pid)
                    executable = os.path.realpath(f"/proc/{pid}/exe")
                except (FileNotFoundError, PermissionError, ProcessLookupError):
                    continue
                return LaunchIdentity(token, pid, pgid, executable, argv)
            await asyncio.sleep(self.poll_interval)

    def _candidate_pids(self, app_id: str) -> list[int]:
        candidates: list[int] = []
        for entry in Path("/proc").iterdir():
            if not entry.name.isdecimal():
                continue
            pid = int(entry.name)
            try:
                if entry.stat().st_uid != os.getuid():
                    continue
                env = self._environment(pid)
                if env.get("SteamAppId") != app_id and env.get("SteamGameId") != app_id:
                    continue
                executable = os.path.realpath(f"/proc/{pid}/exe")
                argv = self._argv(pid)
            except (FileNotFoundError, PermissionError, OSError):
                continue
            if self._is_runtime_process(executable, argv):
                continue
            candidates.append(pid)
        return candidates

    @staticmethod
    def _environment(pid: int) -> dict[str, str]:
        return {
            item.partition(b"=")[0].decode(errors="replace"): item.partition(b"=")[2].decode(
                errors="replace"
            )
            for item in Path(f"/proc/{pid}/environ").read_bytes().split(b"\0")
            if b"=" in item
        }

    @staticmethod
    def _argv(pid: int) -> tuple[str, ...]:
        return tuple(
            item.decode(errors="replace")
            for item in Path(f"/proc/{pid}/cmdline").read_bytes().split(b"\0")
            if item
        )

    @staticmethod
    def _is_runtime_process(executable: str, argv: tuple[str, ...]) -> bool:
        text = f"{executable} {' '.join(argv)}".lower()
        basename = os.path.basename(executable).lower()
        if basename in {
            "steam",
            "steam.exe",
            "wineserver",
            "winedevice.exe",
            "xalia.exe",
        }:
            return True
        if basename.startswith("python"):
            return True
        if any(
            marker in text
            for marker in (
                "/steam/ubuntu",
                "steamwebhelper",
                "reaper",
                "pressure-vessel",
                "srt-bwrap",
                "steamlinuxruntime",
                "scout-on-soldier",
                "iscriptevaluator",
            )
        ):
            return True
        if basename.endswith("-preloader"):
            game_arguments = [argument.lower() for argument in argv if argument.lower().endswith(".exe")]
            return not any(
                "\\steamapps\\common\\" in argument
                and "proton - experimental" not in argument
                and "\\windows\\" not in argument
                for argument in game_arguments
            )
        return False

    async def wait_for_exit(self, launch: SteamLaunch) -> None:
        while Path(f"/proc/{launch.title.pid}").exists():
            await asyncio.sleep(self.poll_interval)

    async def stop(self, launch: SteamLaunch) -> None:
        try:
            os.killpg(launch.title.pgid, signal.SIGTERM)
        except ProcessLookupError:
            return
        await asyncio.sleep(0.05)
        try:
            os.killpg(launch.title.pgid, signal.SIGKILL)
        except ProcessLookupError:
            pass
