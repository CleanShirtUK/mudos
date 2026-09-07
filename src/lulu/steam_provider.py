"""Small Steam client adapter for resident-client AppID launches."""

from dataclasses import dataclass
import asyncio
import os
from pathlib import Path
import re
import signal

from .launch_identity import LaunchIdentity


@dataclass(frozen=True, slots=True)
class SteamLaunchRequest:
    app_id: str
    launcher: asyncio.subprocess.Process


@dataclass(frozen=True, slots=True)
class SteamLaunch:
    app_id: str
    launcher: asyncio.subprocess.Process
    title: LaunchIdentity


@dataclass(frozen=True, slots=True)
class InstalledSteamGame:
    app_id: str
    title: str
    install_dir: str
    library_root: str
    size_on_disk: int
    last_played: int

    @property
    def artwork_url(self) -> str:
        return f"https://cdn.cloudflare.steamstatic.com/steam/apps/{self.app_id}/library_600x900_2x.jpg"


class SteamProvider:
    """Launches an AppID through Steam and observes the native title process."""

    def __init__(self, executable: str = "steam", poll_interval: float = 0.1) -> None:
        self.executable = executable
        self.poll_interval = poll_interval

    def list_installed(self, roots: tuple[Path, ...] | None = None) -> list[InstalledSteamGame]:
        roots = roots or self._library_roots()
        games: list[InstalledSteamGame] = []
        for root in roots:
            folders = root / "steamapps" / "libraryfolders.vdf"
            if not folders.exists():
                continue
            libraries = self._parse_vdf(folders.read_text(errors="replace")).get("libraryfolders", {})
            for folder in libraries.values():
                library_root = Path(folder.get("path", ""))
                if not library_root:
                    continue
                for manifest in sorted((library_root / "steamapps").glob("appmanifest_*.acf")):
                    app = self._parse_vdf(manifest.read_text(errors="replace")).get("AppState", {})
                    if not self._is_launchable_app(app):
                        continue
                    games.append(
                        InstalledSteamGame(
                            app_id=str(app["appid"]),
                            title=str(app["name"]),
                            install_dir=str(library_root / "steamapps" / "common" / app["installdir"]),
                            library_root=str(library_root),
                            size_on_disk=int(app.get("SizeOnDisk", 0)),
                            last_played=int(app.get("LastPlayed", 0)),
                        )
                    )
        return sorted({game.app_id: game for game in games}.values(), key=lambda game: game.title.casefold())

    def _library_roots(self) -> tuple[Path, ...]:
        configured = os.environ.get("LULU_STEAM_ROOTS", "")
        if configured:
            return tuple(Path(item).expanduser() for item in configured.split(":"))
        return (Path.home() / ".local" / "share" / "Steam",)

    @staticmethod
    def _is_launchable_app(app: dict[str, object]) -> bool:
        try:
            name = str(app.get("name", ""))
            return (
                int(app.get("StateFlags", 0)) & 4 == 4
                and bool(app.get("appid"))
                and bool(name)
                and not name.startswith("Steam Linux Runtime")
                and not name.startswith("Proton")
                and name != "Steamworks Common Redistributables"
                and bool(app.get("installdir"))
            )
        except (TypeError, ValueError):
            return False

    @staticmethod
    def _parse_vdf(text: str) -> dict[str, object]:
        tokens = re.findall(r'"(?:\\.|[^"\\])*"|[{}]', text)
        position = 0

        def unquote(token: str) -> str:
            return bytes(token[1:-1], "utf-8").decode("unicode_escape")

        def parse_object() -> dict[str, object]:
            nonlocal position
            result: dict[str, object] = {}
            while position < len(tokens) and tokens[position] != "}":
                key = unquote(tokens[position])
                position += 1
                if position < len(tokens) and tokens[position] == "{":
                    position += 1
                    result[key] = parse_object()
                    position += 1
                elif position < len(tokens):
                    result[key] = unquote(tokens[position])
                    position += 1
            return result

        return parse_object()

    async def request_launch(self, app_id: str) -> SteamLaunchRequest:
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
        return SteamLaunchRequest(app_id, process)

    async def observe_launch(
        self, request: SteamLaunchRequest, token: str, orphan_watchdog: float = 300.0
    ) -> SteamLaunch:
        deadline = asyncio.get_running_loop().time() + orphan_watchdog
        rejected = False
        try:
            while True:
                for pid in self._candidate_pids(request.app_id):
                    try:
                        pgid = os.getpgid(pid)
                        argv = self._argv(pid)
                        executable = os.path.realpath(f"/proc/{pid}/exe")
                    except (FileNotFoundError, PermissionError, ProcessLookupError):
                        continue
                    return SteamLaunch(
                        request.app_id,
                        request.launcher,
                        LaunchIdentity(token, pid, pgid, executable, argv),
                    )

                if request.launcher.returncode is not None and request.launcher.returncode != 0:
                    rejected = True
                    if not self._steam_client_pids() and not self._steam_launch_markers(request.app_id):
                        raise ValueError(f"Steam rejected launch request with status {request.launcher.returncode}")
                if asyncio.get_running_loop().time() >= deadline:
                    raise TimeoutError(f"Steam launch became orphaned for AppID {request.app_id}")
                await asyncio.sleep(self.poll_interval)
        finally:
            if request.launcher.returncode is None and rejected:
                await request.launcher.wait()

    def _steam_client_pids(self) -> list[int]:
        pids: list[int] = []
        for entry in Path("/proc").iterdir():
            if not entry.name.isdecimal():
                continue
            try:
                if entry.stat().st_uid != os.getuid():
                    continue
                executable = os.path.realpath(f"/proc/{entry.name}/exe")
                if os.path.basename(executable).lower() == "steam":
                    pids.append(int(entry.name))
            except (FileNotFoundError, PermissionError, OSError):
                continue
        return pids

    def _steam_launch_markers(self, app_id: str) -> list[int]:
        markers: list[int] = []
        for entry in Path("/proc").iterdir():
            if not entry.name.isdecimal():
                continue
            try:
                if entry.stat().st_uid != os.getuid():
                    continue
                argv = self._argv(int(entry.name))
            except (FileNotFoundError, PermissionError, OSError):
                continue
            if "reaper" in " ".join(argv).lower() and f"appid={app_id}" in " ".join(argv).lower():
                markers.append(int(entry.name))
        return markers

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
