"""Small Steam client adapter for on-demand and resident AppID launches."""

from dataclasses import dataclass
import asyncio
import logging
import os
from pathlib import Path
import re
import signal
import subprocess
from .launch_identity import LaunchIdentity
from .paths import PATHS


@dataclass(frozen=True, slots=True)
class SteamLaunchRequest:
    app_id: str
    launcher: asyncio.subprocess.Process
    existing_pids: tuple[int, ...] = ()
    submitted_at: float = 0.0


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
        self._logger = logging.getLogger("lulu.steam-provider")
        self._owned_client_pids: set[int] = set()
        self._owned_client_pgid: int | None = None

    def open_game_details(self, app_id: str) -> str:
        """Navigate the Steam client without taking lifecycle ownership."""
        if not app_id.isdecimal() or int(app_id) < 1:
            raise ValueError("Steam AppID must be a positive integer")
        uri = f"steam://nav/games/details/{app_id}"
        environment = os.environ.copy()
        environment.setdefault("DISPLAY", ":0")
        subprocess.Popen(
            [self.executable, uri],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
            env=environment,
        )
        self._logger.info("opened Steam game details app_id=%s uri=%s", app_id, uri)
        return uri

    def launch_gamepad_title(self, app_id: str) -> str:
        """Ask the Steam client to launch an AppID after navigation."""
        if not app_id.isdecimal() or int(app_id) < 1:
            raise ValueError("Steam AppID must be a positive integer")
        uri = f"steam://rungameid/{app_id}"
        environment = os.environ.copy()
        environment.setdefault("DISPLAY", ":0")
        self._logger.info("steam-launch-request appid=%s uri=%s", app_id, uri)
        subprocess.Popen(
            [self.executable, uri],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
            env=environment,
        )
        self._logger.info("requested Steam launch app_id=%s uri=%s", app_id, uri)
        return uri

    def _dispatch_uri(self, uri: str) -> str:
        environment = os.environ.copy()
        environment.setdefault("DISPLAY", ":0")
        subprocess.Popen([self.executable, uri], stdin=subprocess.DEVNULL,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         start_new_session=True, env=environment)
        return uri

    def open_store(self) -> str:
        return self._dispatch_uri("steam://open/store")

    def open_main(self) -> str:
        """Surface the already-started Steam client without relaunching it."""
        return self._dispatch_uri("steam://open/main")

    def hide_main(self) -> str:
        """Return focus from Steam while leaving the client available."""
        return self._dispatch_uri("steam://close")

    def main_window_visible(self) -> bool:
        """Report whether Steam's surfaced main window is still visible."""
        try:
            result = subprocess.run(
                ["xdotool", "search", "--onlyvisible", "--class", "steam", "getwindowname", "%@"],
                check=False, capture_output=True, text=True, timeout=2,
                env={**os.environ, "DISPLAY": os.environ.get("DISPLAY", ":0")},
            )
        except (OSError, subprocess.SubprocessError):
            return True
        return any(line.strip().casefold() == "steam" for line in result.stdout.splitlines())

    def install(self, app_id: str) -> str:
        """Open Steam's normal install confirmation for a validated AppID."""
        self._validate_app_id(app_id)
        return self._dispatch_uri(f"steam://install/{app_id}")

    @staticmethod
    def _validate_app_id(app_id: str) -> None:
        if not isinstance(app_id, str) or not app_id.isdecimal() or int(app_id) < 1:
            raise ValueError("Steam AppID must be a positive integer")

    def desktop_pids(self) -> list[int]:
        """Return standard desktop Steam client processes for presentation selection."""
        return self._steam_client_pids()

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
        return (PATHS.steam_library_root,)

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

    async def ensure_client(self, existing: set[int] | None = None) -> None:
        existing = set(self._steam_client_pids()) if existing is None else existing
        if existing:
            return
        environment = os.environ.copy()
        environment.setdefault("DISPLAY", ":0")
        launcher = await asyncio.create_subprocess_exec(
            self.executable, "-silent",
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
            start_new_session=True,
            env=environment,
        )
        self._owned_client_pids.add(launcher.pid)
        self._owned_client_pgid = os.getpgid(launcher.pid)
        try:
            ready = await self._wait_for_steam_client()
        except asyncio.CancelledError:
            await self.stop_owned_client()
            raise
        self._owned_client_pids.update(set(ready) - existing)

    def _process_tree(self, roots: set[int]) -> set[int]:
        owned = set(roots)
        changed = True
        while changed:
            changed = False
            for entry in Path("/proc").iterdir():
                if not entry.name.isdecimal():
                    continue
                try:
                    status = entry.joinpath("status").read_text()
                except (FileNotFoundError, PermissionError, OSError):
                    continue
                parent = re.search(r"^PPid:\s+(\d+)$", status, re.MULTILINE)
                if parent is not None and int(parent.group(1)) in owned and int(entry.name) not in owned:
                    owned.add(int(entry.name))
                    changed = True
        return owned

    def _process_group_members(self, pgid: int) -> set[int]:
        members: set[int] = set()
        for entry in Path("/proc").iterdir():
            if not entry.name.isdecimal():
                continue
            try:
                pid = int(entry.name)
                if os.getpgid(pid) == pgid:
                    members.add(pid)
            except (FileNotFoundError, PermissionError, ProcessLookupError, OSError):
                continue
        return members

    async def stop_owned_client(self) -> None:
        if not self._owned_client_pids and self._owned_client_pgid is None:
            return
        owned = set(self._owned_client_pids)
        if self._owned_client_pgid is not None:
            owned.update(self._process_group_members(self._owned_client_pgid))
        owned = self._process_tree(owned)
        if self._owned_client_pgid is not None:
            owned.update(self._process_group_members(self._owned_client_pgid))
            owned = self._process_tree(owned)
        for pid in sorted(owned, reverse=True):
            try:
                os.kill(pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
        deadline = asyncio.get_running_loop().time() + 5.0
        while asyncio.get_running_loop().time() < deadline:
            if not any(Path(f"/proc/{pid}").exists() for pid in owned):
                break
            await asyncio.sleep(self.poll_interval)
        for pid in sorted(owned, reverse=True):
            try:
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        self._owned_client_pids.clear()
        self._owned_client_pgid = None

    async def request_launch(self, app_id: str) -> SteamLaunchRequest:
        if not app_id.isdecimal() or int(app_id) < 1:
            raise ValueError("Steam AppID must be a positive integer")
        existing = self._candidate_pids(app_id)
        if existing:
            raise ValueError(f"Steam title is already running for AppID {app_id}: {existing}")
        environment = os.environ.copy()
        environment.setdefault("DISPLAY", ":0")
        steam_pids = self._steam_client_pids()
        self._logger.info("launch request app_id=%s steam_pids=%s", app_id, steam_pids)
        if not steam_pids:
            await self.ensure_client(set(steam_pids))
        process = await asyncio.create_subprocess_exec(
            self.executable,
            "-silent",
            "-applaunch",
            app_id,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
            start_new_session=True,
            env=environment,
        )
        self._logger.info("launch submitted app_id=%s launcher_pid=%s", app_id, process.pid)
        return SteamLaunchRequest(app_id, process, tuple(existing), asyncio.get_running_loop().time())

    async def stop_request(self, request: SteamLaunchRequest) -> None:
        task = asyncio.current_task()
        task_name = task.get_name() if task is not None else "none"
        task_id = id(task) if task is not None else None
        self._logger.info("CANCEL_STOP_REQUEST_ENTER request_id=%s task=%s task_id=%s", id(request), task_name, task_id)
        try:
            await self._stop_request_impl(request)
        except asyncio.CancelledError:
            self._logger.exception("CANCEL_STOP_REQUEST_CANCELLED request_id=%s task=%s task_id=%s cancelling=%s", id(request), task_name, task_id, task.cancelling() if task is not None else None)
            raise
        finally:
            self._logger.info("CANCEL_STOP_REQUEST_FINALLY request_id=%s task=%s task_id=%s", id(request), task_name, task_id)

    async def _stop_request_impl(self, request: SteamLaunchRequest) -> None:
        """Stop a pending launch and only targets created after its request."""
        loop = asyncio.get_running_loop()
        cancel_started = loop.time()
        request_id = f"{request.app_id}:{id(request)}"
        existing_pids = set(request.existing_pids)
        pids: set[int] = set()
        groups: set[int] = set()
        group_pids: dict[int, set[int]] = {}
        seen_evidence: set[int] = set()
        if request.launcher.returncode is None:
            try:
                group = os.getpgid(request.launcher.pid)
                groups.add(group)
                group_pids.setdefault(group, set()).add(request.launcher.pid)
            except ProcessLookupError:
                pass
        for group in groups:
            try:
                os.killpg(group, signal.SIGTERM)
                self._logger.info("CANCEL_KILL request_id=%s pid=%s pgid=%s reason=launcher signal=SIGTERM result=sent", request_id, request.launcher.pid, group)
            except ProcessLookupError:
                self._logger.info("CANCEL_KILL request_id=%s pid=%s pgid=%s reason=launcher signal=SIGTERM result=gone", request_id, request.launcher.pid, group)
        deadline = loop.time() + 5.0
        iteration = 0
        while loop.time() < deadline:
            iteration += 1
            scan_started = loop.time()
            self._logger.info(
                "CANCEL_SCAN_BEGIN request_id=%s appid=%s iteration=%s elapsed_since_cancel=%.6f elapsed_since_applaunch=%.6f",
                request_id,
                request.app_id,
                iteration,
                scan_started - cancel_started,
                scan_started - request.submitted_at if request.submitted_at else -1.0,
            )
            markers = self._steam_launch_markers(request.app_id)
            candidates = self._candidate_pids(request.app_id)
            self._logger.info("CANCEL_SCAN_EVIDENCE request_id=%s appid=%s markers=%s candidates=%s", request_id, request.app_id, markers, candidates)
            evidence = set(markers) | set(candidates)
            for pid in evidence - seen_evidence:
                try:
                    details = self._cancel_process_details(pid)
                except (AttributeError, FileNotFoundError, PermissionError, ProcessLookupError, OSError):
                    continue
                self._logger.info("CANCEL_PROCESS_APPEAR request_id=%s appid=%s pid=%s details=%r", request_id, request.app_id, pid, details)
            seen_evidence.update(evidence)
            for pid in set(candidates) - existing_pids - pids:
                pids.add(pid)
                try:
                    group = os.getpgid(pid)
                except ProcessLookupError:
                    continue
                groups.add(group)
                group_pids.setdefault(group, set()).add(pid)
                try:
                    os.killpg(group, signal.SIGTERM)
                    self._logger.info("CANCEL_KILL request_id=%s pid=%s pgid=%s reason=new AppID candidate signal=SIGTERM result=sent", request_id, pid, group)
                except ProcessLookupError:
                    self._logger.info("CANCEL_KILL request_id=%s pid=%s pgid=%s reason=new AppID candidate signal=SIGTERM result=gone", request_id, pid, group)
            await asyncio.sleep(self.poll_interval)
        for group in groups:
            try:
                os.killpg(group, signal.SIGKILL)
                for pid in group_pids.get(group, {request.launcher.pid}):
                    self._logger.info("CANCEL_KILL request_id=%s pid=%s pgid=%s reason=cleanup deadline signal=SIGKILL result=sent", request_id, pid, group)
            except ProcessLookupError:
                for pid in group_pids.get(group, {request.launcher.pid}):
                    self._logger.info("CANCEL_KILL request_id=%s pid=%s pgid=%s reason=cleanup deadline signal=SIGKILL result=gone", request_id, pid, group)
        remaining = self._candidate_pids(request.app_id)
        total_elapsed = loop.time() - cancel_started
        self._logger.info("CANCEL_CLEANUP_END request_id=%s appid=%s total_elapsed=%.6f scans=%s remaining_matching_pids=%s", request_id, request.app_id, total_elapsed, iteration, remaining)
        asyncio.create_task(self._observe_cancel_aftercare(request, request_id, cancel_started, seen_evidence))

    async def _observe_cancel_aftercare(
        self,
        request: SteamLaunchRequest,
        request_id: str,
        cancel_started: float,
        seen_evidence: set[int],
    ) -> None:
        loop = asyncio.get_running_loop()
        deadline = loop.time() + 2.0
        while loop.time() < deadline:
            evidence = set(self._steam_launch_markers(request.app_id)) | set(self._candidate_pids(request.app_id))
            for pid in evidence - seen_evidence:
                try:
                    details = self._cancel_process_details(pid)
                except (AttributeError, FileNotFoundError, PermissionError, ProcessLookupError, OSError):
                    continue
                self._logger.info("CANCEL_AFTERCARE_APPEAR request_id=%s appid=%s pid=%s elapsed_since_cancel=%.6f details=%r", request_id, request.app_id, pid, loop.time() - cancel_started, details)
            seen_evidence.update(evidence)
            await asyncio.sleep(self.poll_interval)

    def _cancel_process_details(self, pid: int) -> dict[str, object]:
        status = Path(f"/proc/{pid}/status").read_text()
        parent = re.search(r"^PPid:\s+(\d+)$", status, re.MULTILINE)
        environment = self._environment(pid)
        return {
            "ppid": int(parent.group(1)) if parent else None,
            "pgid": os.getpgid(pid),
            "executable": os.path.realpath(f"/proc/{pid}/exe"),
            "argv": self._argv(pid),
            "SteamAppId": environment.get("SteamAppId"),
            "SteamGameId": environment.get("SteamGameId"),
        }

    async def _wait_for_steam_client(self, timeout: float = 15.0) -> list[int]:
        deadline = asyncio.get_running_loop().time() + timeout
        pids = self._steam_client_pids()
        while not pids:
            if asyncio.get_running_loop().time() >= deadline:
                raise TimeoutError("Steam client did not become ready")
            await asyncio.sleep(self.poll_interval)
            pids = self._steam_client_pids()
        return pids

    async def observe_launch(
        self, request: SteamLaunchRequest, token: str, orphan_watchdog: float = 300.0
    ) -> SteamLaunch:
        self._logger.info("observe start app_id=%s token=%s watchdog=%.1f", request.app_id, token, orphan_watchdog)
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
                    self._logger.warning(
                        "observe timeout app_id=%s token=%s launcher_returncode=%s steam_pids=%s markers=%s candidates=%s",
                        request.app_id,
                        token,
                        request.launcher.returncode,
                        self._steam_client_pids(),
                        self._steam_launch_markers(request.app_id),
                        self._candidate_pids(request.app_id),
                    )
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

    def presentation_pids(self, app_id: str) -> list[int]:
        """Return current non-runtime AppID processes that may own its window."""
        return self._candidate_pids(app_id)

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
