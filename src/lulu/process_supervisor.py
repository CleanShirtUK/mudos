"""Real OS process supervision for console-sessiond."""

from dataclasses import asdict, dataclass
import asyncio
import logging
import os
import signal
import subprocess
from pathlib import Path
from typing import Awaitable, Callable
from uuid import uuid4

from .console_sessiond import SessionStateModel
from .contracts import InputMode, LaunchDescriptor, Presentation
from .gamescope import GamescopePresentation
from .launch_identity import LaunchIdentity
from .process_observation import APP_ID_ENVIRONMENT_KEYS, process_argv, process_has_app_id
from .plugins.steam.provider import SteamLaunch, SteamProvider, SteamLaunchRequest
from .plugins.steam.aurelia import AureliaClient, AureliaError


def _redact_argv(argv: tuple[str, ...] | list[str]) -> tuple[str, ...]:
    """Hide ephemeral provider credentials from logs and public state."""
    redacted: list[str] = []
    for value in argv:
        if value.startswith("-AUTH_PASSWORD="):
            redacted.append("-AUTH_PASSWORD=<redacted>")
        else:
            redacted.append(value)
    return tuple(redacted)


@dataclass(frozen=True, slots=True)
class ProcessResult:
    token: str
    pid: int | None
    pgid: int | None
    executable: str
    argv: tuple[str, ...]
    exit_code: int | None
    signal: int | None
    outcome: str
    error: str | None = None

    def as_dict(self) -> dict[str, object]:
        value = asdict(self)
        value["argv"] = list(_redact_argv(self.argv))
        return value


StateChanged = Callable[[], Awaitable[None] | None]
InputModeChanged = Callable[[InputMode], object]


class ProcessSupervisor:
    """Owns the primary process and its dedicated process group."""

    def __init__(
        self,
        model: SessionStateModel,
        state_changed: StateChanged | None = None,
        steam_provider: SteamProvider | None = None,
        presentation: GamescopePresentation | None = None,
        input_mode_changed: InputModeChanged | None = None,
    ) -> None:
        self.model = model
        self.state_changed = state_changed
        self.active_identity: LaunchIdentity | None = None
        self._process: asyncio.subprocess.Process | None = None
        self._launch_lock = asyncio.Lock()
        self._watch_task: asyncio.Task[None] | None = None
        self._steam_launch: SteamLaunch | None = None
        self._steam_provider = steam_provider
        self._presentation = presentation
        self._input_mode_changed = input_mode_changed
        self._shell_process: asyncio.subprocess.Process | None = None
        self._shell_identity: LaunchIdentity | None = None
        self._shell_watch_task: asyncio.Task[None] | None = None
        self._steam_launch_task: asyncio.Task[str] | None = None
        self._aurelia_launch_task: asyncio.Task[str] | None = None
        self._aurelia_process: asyncio.subprocess.Process | None = None
        self._aurelia_app_id: str | None = None
        self._aurelia_client: AureliaClient | None = None
        self._steam_store_watch_task: asyncio.Task[None] | None = None
        self._steam_store_window: int | None = None
        self._shell_output_tasks: list[asyncio.Task[None]] = []
        self._process_output_tasks: list[asyncio.Task[None]] = []
        self._logger = logging.getLogger("lulu.process-supervisor")
        self._presentation_watchdog = 10.0
        self._active_launch_task: asyncio.Task[object] | None = None
        self._delegated_launch_environment: dict[str, str] = {}

    def app_id_process_pids(self, app_id: str) -> list[int]:
        """Return provider-filtered process evidence for Sessiond ownership checks."""
        provider = self._steam_provider
        return provider.presentation_pids(app_id) if provider is not None else []

    def set_delegated_launch_environment(self, values: dict[str, str]) -> None:
        """Install the explicit graphical-session handoff for the next child."""
        allowed = {
            "DISPLAY", "WAYLAND_DISPLAY", "XDG_RUNTIME_DIR", "XDG_SESSION_TYPE",
            "DBUS_SESSION_BUS_ADDRESS", "XAUTHORITY", "HOME", "USER", "SDL_VIDEODRIVER",
        }
        self._delegated_launch_environment = {
            key: value for key, value in values.items()
            if key in allowed and isinstance(value, str) and value
        }

    def shell_graphical_environment(self) -> dict[str, str]:
        """Read the live graphical environment Gamescope gave its UI process.

        Sessiond itself is started by systemd and does not inherit Gamescope's
        Xwayland/Wayland variables. Gamescope's UI child is in its process
        group, so use that process group as the authority for the initial
        readiness snapshot rather than guessing socket names.
        """
        shell = self._shell_process
        if shell is None or shell.returncode is not None:
            return {}
        candidates: list[tuple[int, dict[str, str]]] = []
        try:
            entries = os.scandir("/proc")
        except OSError:
            return {}
        with entries:
            for entry in entries:
                if not entry.name.isdecimal():
                    continue
                pid = int(entry.name)
                if pid == shell.pid:
                    continue
                try:
                    if os.getpgid(pid) != shell.pid:
                        continue
                    raw = Path(entry.path, "environ").read_bytes().split(b"\0")
                    environment = {}
                    for item in raw:
                        if b"=" not in item:
                            continue
                        key, value = item.split(b"=", 1)
                        decoded_key = key.decode("ascii")
                        if decoded_key in ("DISPLAY", "WAYLAND_DISPLAY", "XDG_RUNTIME_DIR"):
                            environment[decoded_key] = value.decode()
                    if set(environment) == {"DISPLAY", "WAYLAND_DISPLAY", "XDG_RUNTIME_DIR"}:
                        candidates.append((pid, environment))
                except (OSError, ProcessLookupError, PermissionError, UnicodeDecodeError):
                    continue
        # Prefer the oldest process in the Gamescope group: the UI launcher
        # establishes the environment inherited by the actual shell surface.
        return min(candidates, key=lambda item: item[0])[1] if candidates else {}

    async def _drain_output(
        self, stream: asyncio.StreamReader, role: str, pid: int, channel: str
    ) -> None:
        while line := await stream.readline():
            text = line.decode(errors="replace").rstrip("\r\n")
            self._logger.info("child role=%s pid=%s %s: %s", role, pid, channel, text)

    def _capture_output(
        self,
        process: asyncio.subprocess.Process,
        command: list[str],
        role: str,
    ) -> list[asyncio.Task[None]]:
        self._logger.info("child start role=%s pid=%s command=%r", role, process.pid,
                          _redact_argv(command))
        tasks: list[asyncio.Task[None]] = []
        if process.stdout is not None:
            tasks.append(asyncio.create_task(self._drain_output(process.stdout, role, process.pid, "stdout")))
        if process.stderr is not None:
            tasks.append(asyncio.create_task(self._drain_output(process.stderr, role, process.pid, "stderr")))
        return tasks

    async def _finish_output(
        self, tasks: list[asyncio.Task[None]], role: str, pid: int, exit_code: int
    ) -> None:
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        status = f"exit_code={exit_code}" if exit_code >= 0 else f"signal={-exit_code}"
        self._logger.warning("child exit role=%s pid=%s %s", role, pid, status)

    async def _notify(self) -> None:
        if self.state_changed is not None:
            result = self.state_changed()
            if result is not None:
                await result

    async def _presentation_call(self, method, *args):
        """Finish an X11 presentation operation before cancellation cleanup.

        Cancelling ``asyncio.to_thread`` does not stop its worker. Let an
        in-flight map/unmap/selection finish before the caller restores the
        shell, so cancellation cannot race a late window unmap.
        """
        operation = asyncio.create_task(asyncio.to_thread(method, *args))
        try:
            return await asyncio.shield(operation)
        except asyncio.CancelledError:
            try:
                await operation
            except Exception:
                self._logger.exception("presentation operation failed during cancellation cleanup")
            raise

    async def launch(
        self,
        command: list[str],
        startup_timeout_ms: int,
        *,
        primary_id: str | None = None,
        presentation: Presentation = Presentation.GAME,
        input_mode: InputMode = InputMode.GAME,
        presentation_controller: GamescopePresentation | None = None,
        descriptor: LaunchDescriptor | None = None,
    ) -> str:
        if not command or not command[0]:
            raise ValueError("launch command is required")
        if startup_timeout_ms < 1:
            raise ValueError("startup timeout must be positive")

        presentation_controller = presentation_controller or self._presentation
        async with self._launch_lock:
            if self.active_identity is not None or self.model.state.lifecycle.value != "shell":
                raise ValueError("another launch owns the session")
            if descriptor is not None:
                primary_id = descriptor.primary_id
                presentation = descriptor.presentation
                input_mode = descriptor.input_mode
            token = self.model.request_launch(descriptor or primary_id or command[0])
            await self._notify()
            self._active_launch_task = asyncio.current_task()
            try:
                process = await asyncio.wait_for(
                    asyncio.create_subprocess_exec(
                        *command,
                        stdin=asyncio.subprocess.DEVNULL,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE,
                        env={**os.environ, **self._delegated_launch_environment},
                        start_new_session=True,
                    ),
                    timeout=startup_timeout_ms / 1000,
                )
                identity = LaunchIdentity(
                    token=token,
                    pid=process.pid,
                    pgid=self._pgid_or_pid(process.pid),
                    executable=os.path.realpath(f"/proc/{process.pid}/exe"),
                    argv=tuple(command),
                )
                self._process = process
                self._process_output_tasks = self._capture_output(process, command, "game")
                self.active_identity = identity
                self.model.launch_starting(token)
                await self._notify()
                if presentation_controller is not None:
                    if hasattr(presentation_controller, "select_pids"):
                        def launch_process_group() -> list[int]:
                            members = self._process_group_members(identity.pgid)
                            members.discard(os.getpid())
                            return sorted(members)

                        await self._presentation_call(
                            presentation_controller.select_pids, launch_process_group,
                            max(self._presentation_watchdog, startup_timeout_ms / 1000),
                            lambda: bool(launch_process_group()),
                        )
                    else:
                        await self._presentation_call(
                            presentation_controller.select_pid, process.pid
                        )
                self._set_input_mode(input_mode)
                self.model.primary_started(token, presentation=presentation, input_mode=input_mode)
                await self._notify()
                if (presentation is Presentation.GAME and presentation_controller is not None
                        and hasattr(presentation_controller, "suspend_shell_window")):
                    await self._presentation_call(presentation_controller.suspend_shell_window)
                self._watch_task = asyncio.create_task(self._watch(identity, process))
                self._active_launch_task = None
                return token
            except asyncio.CancelledError:
                if "process" in locals():
                    await self._terminate_group(os.getpgid(process.pid))
                if self.model.state.lifecycle.value != "shell":
                    self._restore_shell_input_mode()
                    self.model.fail(token, "launch cancelled")
                    if presentation_controller is not None and self._shell_process is not None:
                        await asyncio.to_thread(
                            presentation_controller.select_shell, self._shell_process.pid
                        )
                    self.model.return_complete(token)
                    await self._notify()
                self._active_launch_task = None
                raise
            except (OSError, RuntimeError, ValueError, asyncio.TimeoutError, TimeoutError,
                    subprocess.SubprocessError) as error:
                reason = f"launch failed: {error}"
                result_pid: int | None = None
                result_pgid: int | None = None
                result_executable = command[0]
                result_exit_code: int | None = None
                if "process" in locals():
                    result_pid = process.pid
                    try:
                        result_pgid = identity.pgid
                        result_executable = identity.executable
                        await self._terminate_group(result_pgid)
                    except ProcessLookupError:
                        pass
                    result_exit_code = await process.wait()
                    await self._finish_output(self._process_output_tasks, "game", process.pid,
                                              result_exit_code)
                self.active_identity = None
                self._process = None
                self._process_output_tasks = []
                self._restore_shell_input_mode()
                self.model.fail(token, reason)
                self.model.record_result(
                    ProcessResult(
                        token=token,
                        pid=result_pid,
                        pgid=result_pgid,
                        executable=result_executable,
                        argv=tuple(command),
                        exit_code=result_exit_code if result_exit_code is not None and result_exit_code >= 0 else None,
                        signal=-result_exit_code if result_exit_code is not None and result_exit_code < 0 else None,
                        outcome=("timeout" if isinstance(error, asyncio.TimeoutError) else
                                 "presentation-failed" if isinstance(error, RuntimeError) else "start-failed"),
                        error=reason,
                    )
                )
                if presentation_controller is not None and self._shell_process is not None:
                    try:
                        await asyncio.to_thread(
                            presentation_controller.select_shell, self._shell_process.pid
                        )
                    except (OSError, RuntimeError, TimeoutError, subprocess.SubprocessError) as recovery_error:
                        self.model.return_failed(token, f"Presentation recovery failed: {recovery_error}")
                        await self._notify()
                        self._active_launch_task = None
                        raise ValueError(f"{reason}; shell presentation recovery failed: {recovery_error}") from error
                self.model.return_complete(token)
                await self._notify()
                self._active_launch_task = None
                raise ValueError(reason) from error

    
    def _pgid_or_pid(self, pid: int) -> int:
        try:
            return os.getpgid(pid)
        except ProcessLookupError:
            return pid

    async def launch_shell(
        self,
        command: list[str],
        startup_timeout_ms: int,
        *,
        select_shell: bool = True,
    ) -> str:
        if not command or not command[0]:
            raise ValueError("launch command is required")
        if startup_timeout_ms < 1:
            raise ValueError("startup timeout must be positive")
        async with self._launch_lock:
            if self._shell_process is not None or self.active_identity is not None:
                raise ValueError("another presentation owns the session")
            try:
                process = await asyncio.wait_for(
                    asyncio.create_subprocess_exec(
                        *command,
                        stdin=asyncio.subprocess.DEVNULL,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE,
                        start_new_session=True,
                    ),
                    timeout=startup_timeout_ms / 1000,
                )
                identity = LaunchIdentity(
                    token=uuid4().hex,
                    pid=process.pid,
                    pgid=self._pgid_or_pid(process.pid),
                    executable=os.path.realpath(f"/proc/{process.pid}/exe"),
                    argv=tuple(command),
                )
                self._shell_process = process
                self._shell_identity = identity
                self._shell_output_tasks = self._capture_output(process, command, "shell")
                if self._presentation is not None and select_shell:
                    self._presentation.select_shell(process.pid)
                self._set_input_mode(InputMode.SHELL)
                self._shell_watch_task = asyncio.create_task(self._watch_shell(process))
                self._watch_task = self._shell_watch_task
                return identity.token
            except (OSError, subprocess.SubprocessError, asyncio.TimeoutError, TimeoutError) as error:
                if "process" in locals():
                    try:
                        pgid = os.getpgid(process.pid)
                    except ProcessLookupError:
                        pgid = None
                    if pgid is not None:
                        await self._terminate_group(pgid)
                self._shell_process = None
                self._shell_identity = None
                raise ValueError(f"shell launch failed: {error}") from error

    async def _watch_shell(self, process: asyncio.subprocess.Process) -> None:
        exit_code = await process.wait()
        await self._finish_output(self._shell_output_tasks, "shell", process.pid, exit_code)
        self._shell_output_tasks = []
        if self._shell_identity is not None:
            identity = self._shell_identity
            self.model.record_result(
                ProcessResult(
                    token=identity.token,
                    pid=identity.pid,
                    pgid=identity.pgid,
                    executable=identity.executable,
                    argv=identity.argv,
                    exit_code=exit_code if exit_code >= 0 else None,
                    signal=-exit_code if exit_code < 0 else None,
                    outcome="success" if exit_code == 0 else "failed",
                    error=None if exit_code == 0 else f"process exited with status {exit_code}",
                )
            )
        self._shell_process = None
        self._shell_identity = None
        await self._notify()

    def _set_input_mode(self, mode: InputMode) -> None:
        if self._input_mode_changed is not None:
            self._input_mode_changed(mode)

    def _restore_shell_input_mode(self) -> None:
        try:
            self._set_input_mode(InputMode.SHELL)
        except (OSError, RuntimeError, ValueError, subprocess.SubprocessError):
            self._logger.exception("shell input profile restoration failed")

    def ensure_shell_presentation(self) -> int | None:
        if self.model.state.lifecycle.value != "shell":
            return None
        if self._presentation is not None and self._shell_process is not None:
            window = self._presentation.ensure_shell(self._shell_process.pid)
            if (self._presentation.selected_base_window() == window
                    and self._presentation.window_is_focusable(window)):
                return window
        return None

    async def _watch(self, identity: LaunchIdentity, process: asyncio.subprocess.Process) -> None:
        exit_code = await process.wait()
        await self._finish_output(self._process_output_tasks, "game", process.pid, exit_code)
        self._process_output_tasks = []
        # A bootstrapper may hand the UI to a replacement child in the same
        # owned process group.  The original PID is not the transaction
        # boundary: keep delegation alive until the group is empty and make
        # the replacement surface current when it appears.
        while True:
            members = self._process_group_members(identity.pgid)
            members.discard(os.getpid())
            if not members:
                break
            if self._presentation is not None:
                try:
                    await asyncio.to_thread(self._presentation.select_pids, sorted(members), self._presentation_watchdog)
                except (OSError, TimeoutError) as error:
                    # A replacement may be between windows, or may only be a
                    # non-presenting helper.  Ownership remains group-based;
                    # do not terminate the transaction merely because there
                    # is temporarily no focusable XWayland surface.
                    self._logger.debug("replacement surface not ready pgid=%s members=%s error=%s",
                                       identity.pgid, sorted(members), error)
            await asyncio.sleep(0.1)
        await self._terminate_group(identity.pgid)
        result = ProcessResult(
            token=identity.token,
            pid=identity.pid,
            pgid=identity.pgid,
            executable=identity.executable,
            argv=identity.argv,
            exit_code=exit_code if exit_code >= 0 else None,
            signal=-exit_code if exit_code < 0 else None,
            outcome="success" if exit_code == 0 else "failed",
            error=None if exit_code == 0 else f"process exited with status {exit_code}",
        )
        self.model.primary_exited(identity.token, success=exit_code == 0)
        self.model.state.delegated_surface = None
        self.model.state.controller_mode = None
        self.model.record_result(result)
        self._restore_shell_input_mode()
        self.active_identity = None
        self._process = None
        if self._presentation is not None and self._shell_process is not None:
            try:
                # Keep the externally visible lifecycle in RETURNING until
                # Gamescope has remapped, discovered, and selected the shell.
                await asyncio.to_thread(self._presentation.select_shell, self._shell_process.pid)
            except (OSError, RuntimeError, TimeoutError, subprocess.SubprocessError) as error:
                self.model.return_failed(identity.token, f"Presentation recovery failed: {error}")
                await self._notify()
                return
        self.model.return_complete(identity.token)
        await self._notify()

    @staticmethod
    def _process_group_members(pgid: int) -> set[int]:
        members: set[int] = set()
        for entry in os.scandir("/proc"):
            if not entry.name.isdigit():
                continue
            try:
                fields = Path(entry.path, "stat").read_text().split()
                if len(fields) > 4 and fields[2] != "Z" and int(fields[4]) == pgid:
                    members.add(int(entry.name))
            except (OSError, ValueError):
                continue
        return members

    async def cancel_launch(self) -> None:
        if self._aurelia_app_id is not None and self.model.state.lifecycle.value == "game":
            raise ValueError("Aurelia game is already running; use StopGame, not CancelLaunch")
        task = self._active_launch_task or self._steam_launch_task or self._aurelia_launch_task
        if task is None:
            return
        if task is asyncio.current_task():
            raise ValueError("no launch is active")
        current = asyncio.current_task()
        self._logger.info(
            "CANCEL_LAUNCH_ENTER caller=%s caller_id=%s target=%s target_id=%s target_cancelling=%s",
            current.get_name() if current is not None else "none",
            id(current) if current is not None else None,
            task.get_name(),
            id(task),
            task.cancelling(),
        )
        if task.cancelling() == 0:
            self._logger.info("CANCEL_LAUNCH_CANCEL_CALL target=%s target_id=%s", task.get_name(), id(task))
            task.cancel()
            self._logger.info("CANCEL_LAUNCH_CANCEL_RETURN target=%s target_id=%s target_cancelling=%s", task.get_name(), id(task), task.cancelling())
        else:
            self._logger.info("CANCEL_LAUNCH_JOIN target=%s target_id=%s target_cancelling=%s", task.get_name(), id(task), task.cancelling())
        try:
            await asyncio.gather(task, return_exceptions=True)
        except asyncio.CancelledError:
            self._logger.exception("CANCEL_LAUNCH_GATHER_CANCELLED caller=%s caller_id=%s target=%s target_id=%s", current.get_name() if current is not None else "none", id(current) if current is not None else None, task.get_name(), id(task))
            raise
        finally:
            self._logger.info("CANCEL_LAUNCH_GATHER_FINALLY target=%s target_id=%s done=%s cancelled=%s", task.get_name(), id(task), task.done(), task.cancelled())
        if self._aurelia_app_id is not None and self.model.state.lifecycle.value == "game":
            raise ValueError("Aurelia game started during cancellation; use StopGame to stop it")
        if self._process is not None:
            try:
                await self._terminate_group(os.getpgid(self._process.pid))
            except ProcessLookupError:
                pass
            self._process = None
        provider = self._steam_provider or SteamProvider()
        if self._steam_launch is not None:
            await provider.stop(self._steam_launch)
            self._steam_launch = None
        if self._aurelia_app_id is None:
            await provider.stop_owned_client()
        if self.model.state.lifecycle.value != "shell":
            self.model.fail(self.model.state.launch_token, "launch cancelled")
            self._set_input_mode(InputMode.SHELL)
            if self._presentation is not None and self._shell_process is not None:
                self._presentation.select_shell(self._shell_process.pid)
            self.model.return_complete(self.model.state.launch_token)
        self.active_identity = None
        self._steam_store_window = None
        self._active_launch_task = None
        self._steam_launch_task = None
        self._aurelia_launch_task = None
        if self.model.state.lifecycle.value == "shell":
            self._aurelia_app_id = None
            self._aurelia_process = None
        await self._notify()

    async def launch_steam(self, app_id: str, startup_timeout_ms: int) -> str:
        return await self._launch_steam(app_id, startup_timeout_ms)

    async def launch_steam_store(self, startup_timeout_ms: int) -> str:
        async with self._launch_lock:
            if startup_timeout_ms < 1 or self.active_identity is not None or self.model.state.lifecycle.value != "shell":
                raise ValueError("another launch owns the session")
            token = self.model.request_launch("steam-store")
            await self._notify()
            self._active_launch_task = asyncio.current_task()
            provider = self._steam_provider or SteamProvider()
            self._steam_provider = provider
            try:
                await provider.ensure_client()
                self.model.launch_starting(token)
                if self._presentation is not None:
                    self._steam_store_window = await asyncio.to_thread(
                        self._presentation.select_pids, provider.desktop_pids, startup_timeout_ms / 1000
                    )
                await asyncio.to_thread(provider.open_store)
                self._set_input_mode(InputMode.GAME)
                self.model.primary_started(token, presentation=Presentation.FOREIGN_UI, input_mode=InputMode.GAME)
                await self._notify()
                self._steam_store_watch_task = asyncio.create_task(
                    self._watch_steam_store(token, self._steam_store_window)
                )
                self._active_launch_task = None
                return token
            except (OSError, TimeoutError, ValueError) as error:
                self.model.fail(token, f"Steam Store launch failed: {error}")
                self._set_input_mode(InputMode.SHELL)
                if self._presentation is not None and self._shell_process is not None:
                    self._presentation.select_shell(self._shell_process.pid)
                self._steam_store_window = None
                self.model.return_complete(token)
                await self._notify()
                self._active_launch_task = None
                raise ValueError(str(error)) from error

    async def launch_steam_install(self, app_id: str, startup_timeout_ms: int) -> str:
        """Hand Steam's install confirmation to the delegated Compat surface."""
        if startup_timeout_ms < 1:
            raise ValueError("startup timeout must be positive")
        async with self._launch_lock:
            if self.active_identity is not None or self.model.state.lifecycle.value != "shell":
                raise ValueError("another launch owns the session")
            provider = self._steam_provider or SteamProvider()
            self._steam_provider = provider
            provider._validate_app_id(app_id)
            token = self.model.request_launch(f"steam-install:{app_id}")
            await self._notify()
            self._active_launch_task = asyncio.current_task()
            try:
                await provider.ensure_client()
                self.model.launch_starting(token)
                if self._presentation is not None:
                    self._steam_store_window = await asyncio.to_thread(
                        self._presentation.select_pids, provider.desktop_pids, startup_timeout_ms / 1000
                    )
                await asyncio.to_thread(provider.install, app_id)
                self._set_input_mode(InputMode.COMPAT)
                self.model.primary_started(token, presentation=Presentation.FOREIGN_UI, input_mode=InputMode.COMPAT)
                await self._notify()
                self._active_launch_task = None
                return token
            except (OSError, TimeoutError, ValueError) as error:
                self.model.fail(token, f"Steam install launch failed: {error}")
                self._set_input_mode(InputMode.SHELL)
                if self._presentation is not None and self._shell_process is not None:
                    self._presentation.select_shell(self._shell_process.pid)
                self._steam_store_window = None
                self.model.return_complete(token)
                await self._notify()
                self._active_launch_task = None
                raise ValueError(str(error)) from error

    async def _watch_steam_store(self, token: str, window: int | None) -> None:
        while self.model.state.lifecycle.value == "game" and self.model.state.launch_token == token:
            if (window is not None and self._presentation is not None
                    and not self._presentation.window_is_focusable(window)):
                break
            await asyncio.sleep(0.1)
        if self.model.state.lifecycle.value == "game" and self.model.state.launch_token == token:
            await self._return_steam_store(token)

    async def _watch_delegated(self, token: str, window: int | None) -> None:
        while self.model.state.lifecycle.value == "game" and self.model.state.launch_token == token:
            if window is not None and self._presentation is not None and not self._presentation.window_is_focusable(window):
                break
            await asyncio.sleep(0.1)
        if self.model.state.lifecycle.value == "game" and self.model.state.launch_token == token:
            await self._return_delegated(token)

    async def _return_steam_store(self, token: str) -> None:
        await self._return_delegated(token)

    async def _return_delegated(self, token: str) -> None:
        await (self._steam_provider or SteamProvider()).stop_owned_client()
        self.model.primary_exited(token)
        self._set_input_mode(InputMode.SHELL)
        if self._presentation is not None and self._shell_process is not None:
            self._presentation.select_shell(self._shell_process.pid)
        self.model.return_complete(token)
        self._steam_store_window = None
        await self._notify()

    async def open_steam_store_surface(self) -> str:
        if self.model.state.primary_id != "steam-store" or self.model.state.lifecycle.value != "game":
            raise ValueError("Steam Store delegated surface is not active")
        uri = await asyncio.to_thread((self._steam_provider or SteamProvider()).open_store)
        self.model.set_delegated_surface("store")
        await self._notify()
        return uri

    async def quit_delegated(self) -> None:
        if str(self.model.state.primary_id or "").startswith("provider:lutris:install:"):
            if self.model.state.lifecycle.value != "game" or self.active_identity is None:
                raise ValueError("Lutris delegated surface is not active")
            identity = self.active_identity
            await self._terminate_group(identity.pgid)
            if self._watch_task is not None:
                await self._watch_task
            return
        if self.model.state.primary_id not in ("steam-store",) and not str(self.model.state.primary_id or "").startswith("steam-install:"):
            raise ValueError("Steam delegated surface is not active")
        if self.model.state.lifecycle.value != "game":
            raise ValueError("Steam delegated surface is not active")
        if self._steam_store_watch_task is not None:
            self._steam_store_watch_task.cancel()
            await asyncio.gather(self._steam_store_watch_task, return_exceptions=True)
            self._steam_store_watch_task = None
        await self._return_steam_store(self.model.state.launch_token)

    def queue_steam_launch(self, app_id: str, startup_timeout_ms: int) -> str:
        if startup_timeout_ms < 1:
            raise ValueError("startup timeout must be positive")
        if self.active_identity is not None or self.model.state.lifecycle.value != "shell":
            raise ValueError("another launch owns the session")
        token = self.model.request_launch(f"steam:{app_id}")
        self._logger.info("queued steam app_id=%s token=%s timeout_ms=%s", app_id, token, startup_timeout_ms)
        self._steam_launch_task = asyncio.create_task(self._launch_steam(app_id, startup_timeout_ms, token), name=f"steam-launch-{token}")
        self._logger.info("CANCEL_TASK_CREATE task=%s task_id=%s token=%s caller=queue_steam_launch", self._steam_launch_task.get_name(), id(self._steam_launch_task), token)
        return token

    async def _launch_steam(
        self, app_id: str, startup_timeout_ms: int, token: str | None = None
    ) -> str:
        if startup_timeout_ms < 1:
            raise ValueError("startup timeout must be positive")
        async with self._launch_lock:
            if token is None and (
                self.active_identity is not None or self.model.state.lifecycle.value != "shell"
            ):
                raise ValueError("another launch owns the session")
            token = token or self.model.request_launch(f"steam:{app_id}")
            await self._notify()
            self._active_launch_task = asyncio.current_task()
            provider = self._steam_provider or SteamProvider()
            launch: SteamLaunch | None = None
            request: SteamLaunchRequest | None = None
            try:
                request = await provider.request_launch(app_id)
                self._logger.info("steam request ready app_id=%s token=%s", app_id, token)
                self.model.launch_starting(token)
                await self._notify()
                launch = await provider.observe_launch(
                    request, token
                )
                self._logger.info("steam target observed app_id=%s token=%s pid=%s", app_id, token, launch.title.pid)
                self.model.primary_observed(token)
                await self._notify()
                if self._presentation is not None:
                    pids = getattr(provider, "presentation_pids", lambda _app_id: [launch.title.pid])
                    if hasattr(self._presentation, "select_pids"):
                        self._presentation.select_pids(
                            lambda: pids(app_id), timeout=self._presentation_watchdog
                        )
                    else:
                        self._presentation.select_pid(launch.title.pid)
                self._set_input_mode(InputMode.GAME)
                self.model.primary_started(token, presentation=Presentation.GAME, input_mode=InputMode.GAME)
                if hasattr(self._presentation, "suspend_shell_window"):
                    await self._presentation_call(self._presentation.suspend_shell_window)
                self._steam_launch = launch
                self.active_identity = launch.title
                await self._notify()
                self._watch_task = asyncio.create_task(self._watch_steam(provider, launch))
                self._active_launch_task = None
                return token
            except asyncio.CancelledError:
                self._logger.exception(
                    "CANCEL_LAUNCH_TASK_CANCELLED task=%s task_id=%s token=%s request=%s provider=%s",
                    asyncio.current_task().get_name() if asyncio.current_task() is not None else "none",
                    id(asyncio.current_task()) if asyncio.current_task() is not None else None,
                    token,
                    id(request) if request is not None else None,
                    type(provider).__name__,
                )
                if launch is not None:
                    await provider.stop(launch)
                elif request is not None:
                    try:
                        await provider.stop_owned_client()
                        await provider.stop_request(request)
                    except asyncio.CancelledError:
                        self._logger.exception("CANCEL_PROVIDER_STOP_CANCELLED task=%s task_id=%s request=%s token=%s", asyncio.current_task().get_name(), id(asyncio.current_task()), id(request), token)
                        raise
                    self._logger.info("CANCEL_PROVIDER_STOP_RETURN task=%s task_id=%s request=%s token=%s", asyncio.current_task().get_name(), id(asyncio.current_task()), id(request), token)
                raise
            except (OSError, RuntimeError, TimeoutError, ValueError) as error:
                if launch is not None:
                    await provider.stop(launch)
                reason = f"Steam launch failed: {error}"
                self._logger.warning("steam launch failed app_id=%s token=%s reason=%s", app_id, token, reason)
                self.model.fail(token, reason)
                self.model.record_result(ProcessResult(token, None, None, "steam", (app_id,), None, None, "start-failed", reason))
                if self._presentation is not None and self._shell_process is not None:
                    self._presentation.select_shell(self._shell_process.pid)
                self._set_input_mode(InputMode.SHELL)
                self.model.return_complete(token)
                await self._notify()
                self._active_launch_task = None
                raise ValueError(reason) from error

    async def _watch_steam(self, provider: SteamProvider, launch: SteamLaunch) -> None:
        await provider.wait_for_exit(launch)
        identity = launch.title
        self._logger.info("steam target exited token=%s pid=%s", identity.token, identity.pid)
        result = ProcessResult(
            token=identity.token,
            pid=identity.pid,
            pgid=identity.pgid,
            executable=identity.executable,
            argv=identity.argv,
            exit_code=None,
            signal=None,
            outcome="success",
        )
        self.model.primary_exited(identity.token)
        self.model.record_result(result)
        await provider.stop_owned_client()
        try:
            self._set_input_mode(InputMode.SHELL)
            if self._presentation is not None and self._shell_process is not None:
                self._presentation.select_shell(self._shell_process.pid)
            self._logger.info("steam return restored shell token=%s", identity.token)
        except Exception as error:
            self.model.return_failed(identity.token, f"Presentation recovery failed: {error}")
            await self._notify()
            return
        self.model.return_complete(identity.token)
        self.active_identity = None
        self._steam_launch = None
        await self._notify()

    def queue_aurelia_launch(self, app_id: str, startup_timeout_ms: int) -> str:
        if startup_timeout_ms < 1:
            raise ValueError("startup timeout must be positive")
        if not app_id.isdecimal() or int(app_id) < 1:
            raise ValueError("Steam AppID must be a positive integer")
        if self.active_identity is not None or self.model.state.lifecycle.value != "shell":
            raise ValueError("another launch owns the session")
        token = self.model.request_launch(f"steam-aurelia:{app_id}")
        self._aurelia_launch_task = asyncio.create_task(
            self._launch_aurelia(app_id, startup_timeout_ms, token),
            name=f"aurelia-launch-{token}",
        )
        return token

    async def _launch_aurelia(self, app_id: str, startup_timeout_ms: int, token: str) -> str:
        async with self._launch_lock:
            client = self._aurelia_client or AureliaClient()
            self._aurelia_client = client
            provider = self._steam_provider or SteamProvider()
            self._steam_provider = provider
            process: asyncio.subprocess.Process | None = None
            game: LaunchIdentity | None = None
            self._active_launch_task = asyncio.current_task()
            try:
                await self._notify()
                self.model.launch_starting(token)
                await self._notify()
                if provider.presentation_pids(app_id):
                    raise RuntimeError(f"AppID {app_id} already has a running Steam game process")
                process = await client.spawn_play(app_id)
                self._aurelia_process, self._aurelia_app_id = process, app_id
                loop = asyncio.get_running_loop()
                started_at = loop.time()
                deadline = started_at + startup_timeout_ms / 1000
                daemon_seen = False
                daemon_missing_since: float | None = None
                # Aurelia's JSON PID is only a hint and can be a runner. Verify
                # its exact AppID marker, then let SteamProvider select the actual
                # game PID from its established AppID-filtered candidate set.
                while game is None:
                    candidates = provider.presentation_pids(app_id)
                    row = await client.running_record(app_id)
                    pid = row.get("pid") if isinstance(row, dict) else None
                    if (isinstance(pid, int) and pid > 1
                            and process_has_app_id(pid, app_id,
                                                   environment_keys=APP_ID_ENVIRONMENT_KEYS)
                            and candidates):
                        # The verified Aurelia record establishes that Aurelia
                        # is tracking this AppID; it is not assumed to be the
                        # window-owning game. Select the actual game PID using
                        # SteamProvider's established candidate ordering.
                        game_pid = candidates[0]
                        if not process_has_app_id(game_pid, app_id,
                                                  environment_keys=APP_ID_ENVIRONMENT_KEYS):
                            raise RuntimeError("Steam process correlation returned a PID without the exact AppID marker")
                        game = LaunchIdentity(token, game_pid, os.getpgid(game_pid),
                                              os.path.realpath(f"/proc/{game_pid}/exe"),
                                              process_argv(game_pid))
                        break
                    if process.returncode is not None:
                        raise RuntimeError(f"Aurelia CLI exited before a verified game appeared (status {process.returncode})")
                    now = loop.time()
                    # Give the launch request time to spawn/refresh the daemon,
                    # then fail promptly if the daemon endpoint disappears.
                    daemon_alive = client.daemon_alive()
                    if daemon_alive:
                        daemon_seen = True
                        daemon_missing_since = None
                    else:
                        daemon_missing_since = daemon_missing_since or now
                        if ((daemon_seen and now - daemon_missing_since > 2)
                                or (not daemon_seen and now - started_at > 5)):
                            raise RuntimeError("Aurelia daemon disappeared before a verified game appeared")
                    if now >= deadline:
                        raise TimeoutError(f"Aurelia launch timed out waiting for verified AppID {app_id} process")
                    await asyncio.sleep(provider.poll_interval)

                self.model.primary_observed(token)
                await self._notify()
                if self._presentation is not None:
                    self._presentation.select_pids(lambda: provider.presentation_pids(app_id), timeout=self._presentation_watchdog)
                self._set_input_mode(InputMode.GAME)
                self.model.primary_started(token, presentation=Presentation.GAME, input_mode=InputMode.GAME)
                if hasattr(self._presentation, "suspend_shell_window"):
                    await self._presentation_call(self._presentation.suspend_shell_window)
                self.active_identity = game
                await self._notify()
                self._watch_task = asyncio.create_task(self._watch_aurelia(provider, app_id, game),
                                                       name=f"aurelia-game-watch-{token}")
                self._active_launch_task = None
                return token
            except asyncio.CancelledError:
                if process is not None and process.returncode is None:
                    process.terminate()
                    try:
                        await asyncio.wait_for(process.wait(), timeout=5)
                    except TimeoutError:
                        process.kill()
                        await process.wait()
                # Aurelia provides no play-cancel API. Observe a settling window
                # after reaping only our CLI child to catch a launch handoff race.
                deadline = asyncio.get_running_loop().time() + 2
                appeared = False
                while asyncio.get_running_loop().time() < deadline:
                    if provider.presentation_pids(app_id):
                        appeared = True
                        break
                    await asyncio.sleep(max(provider.poll_interval, 0.05))
                if appeared:
                    try:
                        await client.stop(app_id)
                    except AureliaError as error:
                        self._logger.error("Aurelia launch raced cancellation and stop failed app_id=%s error=%s", app_id, error)
                    deadline = asyncio.get_running_loop().time() + 10
                    while asyncio.get_running_loop().time() < deadline:
                        if not provider.presentation_pids(app_id):
                            break
                        await asyncio.sleep(max(provider.poll_interval, 0.05))
                    if provider.presentation_pids(app_id):
                        await self._adopt_aurelia_game(token, app_id, provider)
                        return token
                raise
            except (AureliaError, OSError, RuntimeError, TimeoutError, ValueError) as error:
                if process is not None and process.returncode is None:
                    process.terminate()
                    await process.wait()
                self.model.fail(token, f"Aurelia launch failed: {error}")
                self.model.record_result(ProcessResult(token, game.pid if game else None,
                    game.pgid if game else None, game.executable if game else "aurelia",
                    game.argv if game else ("aurelia", "play", app_id), None, None,
                    "start-failed", str(error)))
                self._set_input_mode(InputMode.SHELL)
                if self._presentation is not None and self._shell_process is not None:
                    await self._presentation_call(lambda: self._presentation.select_shell(self._shell_process.pid))
                self.model.return_complete(token)
                self._aurelia_app_id = None
                self._aurelia_process = None
                await self._notify()
                raise ValueError(f"Aurelia launch failed: {error}") from error
            finally:
                self._active_launch_task = None

    async def _adopt_aurelia_game(self, token: str, app_id: str, provider: SteamProvider) -> None:
        """Keep Sessiond authoritative if a game wins the cancellation race."""
        candidates = provider.presentation_pids(app_id)
        if not candidates:
            return
        pid = candidates[0]
        if not process_has_app_id(pid, app_id, environment_keys=APP_ID_ENVIRONMENT_KEYS):
            raise RuntimeError("cannot adopt Aurelia cancellation-race process without exact AppID evidence")
        identity = LaunchIdentity(token, pid, os.getpgid(pid),
                                  os.path.realpath(f"/proc/{pid}/exe"), process_argv(pid))
        self.model.primary_observed(token)
        if self._presentation is not None:
            self._presentation.select_pids(lambda: provider.presentation_pids(app_id), timeout=self._presentation_watchdog)
        self._set_input_mode(InputMode.GAME)
        self.model.primary_started(token, presentation=Presentation.GAME, input_mode=InputMode.GAME)
        self.active_identity = identity
        self._watch_task = asyncio.create_task(self._watch_aurelia(provider, app_id, identity),
                                               name=f"aurelia-game-watch-{token}")
        await self._notify()

    async def _watch_aurelia(self, provider: SteamProvider, app_id: str, identity: LaunchIdentity) -> None:
        # Track the verified AppID process set, not the blocking CLI or daemon.
        absent_since: float | None = None
        loop = asyncio.get_running_loop()
        while absent_since is None or loop.time() - absent_since < 0.5:
            if provider.presentation_pids(app_id):
                absent_since = None
            elif absent_since is None:
                absent_since = loop.time()
            await asyncio.sleep(provider.poll_interval)
        self.model.primary_exited(identity.token)
        self.model.record_result(ProcessResult(identity.token, identity.pid, identity.pgid,
            identity.executable, identity.argv, 0, None, "success"))
        try:
            self._set_input_mode(InputMode.SHELL)
            if self._presentation is not None and self._shell_process is not None:
                await self._presentation_call(lambda: self._presentation.select_shell(self._shell_process.pid))
        except Exception as error:
            self.model.return_failed(identity.token, f"Presentation recovery failed: {error}")
            await self._notify()
            return
        self.model.return_complete(identity.token)
        self.active_identity = None
        self._aurelia_app_id = None
        self._aurelia_process = None
        await self._notify()

    async def _terminate_group(self, pgid: int) -> None:
        try:
            os.killpg(pgid, signal.SIGTERM)
        except ProcessLookupError:
            return
        await asyncio.sleep(0.05)
        try:
            os.killpg(pgid, signal.SIGKILL)
        except ProcessLookupError:
            pass

    async def stop(self) -> None:
        if self._aurelia_launch_task is not None and not self._aurelia_launch_task.done():
            try:
                await self.cancel_launch()
            except ValueError:
                if self._aurelia_app_id is None or self.model.state.lifecycle.value != "game":
                    raise
                await self.stop_aurelia_game()
        if self._steam_store_watch_task is not None:
            self._steam_store_watch_task.cancel()
            await asyncio.gather(self._steam_store_watch_task, return_exceptions=True)
            self._steam_store_watch_task = None
        if self._steam_launch is not None:
            await (self._steam_provider or SteamProvider()).stop(self._steam_launch)
            if self._watch_task is not None:
                await self._watch_task
        if self._aurelia_app_id is not None:
            await self.stop_aurelia_game()
            return
        if self._shell_process is not None:
            await self._terminate_group(os.getpgid(self._shell_process.pid))
            if self._shell_watch_task is not None:
                await self._shell_watch_task
            self._shell_watch_task = None
        identity = self.active_identity
        if identity is None:
            return
        await self._terminate_group(identity.pgid)
        if self._watch_task is not None:
            await self._watch_task

    async def quit_active_session(self) -> None:
        """Quit only the process group owned by the active launch transaction."""
        identity = self.active_identity
        if identity is None or self.model.state.launch_token != identity.token:
            raise ValueError("no owned game session is active")
        if self._aurelia_app_id is not None:
            await self.stop_aurelia_game()
            return
        await self._terminate_group(identity.pgid)
        if self._watch_task is not None:
            await self._watch_task

    async def stop_aurelia_game(self) -> None:
        """Stop a verified running title through Aurelia, never by process group."""
        app_id = self._aurelia_app_id
        if app_id is None or self.model.state.lifecycle.value != "game":
            raise ValueError("no running Aurelia game is owned by this session")
        await (self._aurelia_client or AureliaClient()).stop(app_id)
        if self._watch_task is not None:
            await self._watch_task

    def state_details(self) -> dict[str, object]:
        identity = self.active_identity
        return {
            "active_identity": asdict(identity) if identity is not None else None,
            "shell_identity": asdict(self._shell_identity) if self._shell_identity is not None else None,
            "last_result": self.model.last_result.as_dict() if self.model.last_result else None,
        }
