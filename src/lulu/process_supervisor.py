"""Real OS process supervision for console-sessiond."""

from dataclasses import asdict, dataclass
import asyncio
import logging
import os
import signal
import subprocess
from typing import Awaitable, Callable
from uuid import uuid4

from .console_sessiond import SessionStateModel
from .contracts import InputMode, Presentation
from .gamescope import GamescopePresentation
from .launch_identity import LaunchIdentity
from .steam_provider import SteamLaunch, SteamProvider, SteamLaunchRequest


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
        return asdict(self)


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
        self._steam_store_watch_task: asyncio.Task[None] | None = None
        self._steam_store_window: int | None = None
        self._shell_output_tasks: list[asyncio.Task[None]] = []
        self._process_output_tasks: list[asyncio.Task[None]] = []
        self._logger = logging.getLogger("lulu.process-supervisor")
        self._presentation_watchdog = 10.0
        self._active_launch_task: asyncio.Task[object] | None = None

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
        self._logger.info("child start role=%s pid=%s command=%r", role, process.pid, command)
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

    async def launch(
        self,
        command: list[str],
        startup_timeout_ms: int,
        *,
        presentation: Presentation = Presentation.GAME,
        input_mode: InputMode = InputMode.GAME,
        presentation_controller: GamescopePresentation | None = None,
    ) -> str:
        if not command or not command[0]:
            raise ValueError("launch command is required")
        if startup_timeout_ms < 1:
            raise ValueError("startup timeout must be positive")

        presentation_controller = presentation_controller or self._presentation
        async with self._launch_lock:
            if self.active_identity is not None or self.model.state.lifecycle.value != "shell":
                raise ValueError("another launch owns the session")
            token = self.model.request_launch(command[0])
            await self._notify()
            self._active_launch_task = asyncio.current_task()
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
                        await asyncio.to_thread(
                            presentation_controller.select_pids, [process.pid], self._presentation_watchdog
                        )
                    else:
                        await asyncio.to_thread(
                            presentation_controller.select_pid, process.pid
                        )
                self._set_input_mode(input_mode)
                self.model.primary_started(token, presentation=presentation, input_mode=input_mode)
                await self._notify()
                self._watch_task = asyncio.create_task(self._watch(identity, process))
                self._active_launch_task = None
                return token
            except asyncio.CancelledError:
                if "process" in locals():
                    await self._terminate_group(os.getpgid(process.pid))
                if self.model.state.lifecycle.value != "shell":
                    self.model.fail(token, "launch cancelled")
                    self.model.return_complete(token)
                    await self._notify()
                self._active_launch_task = None
                raise
            except (OSError, asyncio.TimeoutError, TimeoutError) as error:
                reason = f"launch failed: {error}"
                self.model.fail(token, reason)
                self.model.record_result(
                    ProcessResult(
                        token=token,
                        pid=None,
                        pgid=None,
                        executable=command[0],
                        argv=tuple(command),
                        exit_code=None,
                        signal=None,
                        outcome="timeout" if isinstance(error, asyncio.TimeoutError) else "start-failed",
                        error=reason,
                    )
                )
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

    def ensure_shell_presentation(self) -> None:
        if self.model.state.lifecycle.value != "shell":
            return
        if self._presentation is not None and self._shell_process is not None:
            self._presentation.ensure_shell(self._shell_process.pid)

    async def _watch(self, identity: LaunchIdentity, process: asyncio.subprocess.Process) -> None:
        exit_code = await process.wait()
        await self._finish_output(self._process_output_tasks, "game", process.pid, exit_code)
        self._process_output_tasks = []
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
        self.model.record_result(result)
        self.model.return_complete(identity.token)
        self.active_identity = None
        self._process = None
        if self._presentation is not None and self._shell_process is not None:
            self._presentation.select_shell(self._shell_process.pid)
        self._set_input_mode(InputMode.SHELL)
        await self._notify()

    async def cancel_launch(self) -> None:
        task = self._active_launch_task or self._steam_launch_task
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
                await asyncio.to_thread(provider.open_gamepadui)
                if self._presentation is not None:
                    self._steam_store_window = await asyncio.to_thread(
                        self._presentation.select_pids, provider.gamepadui_pids, startup_timeout_ms / 1000
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
                await asyncio.to_thread(provider.open_gamepadui)
                if self._presentation is not None:
                    self._steam_store_window = await asyncio.to_thread(
                        self._presentation.select_pids, provider.gamepadui_pids, startup_timeout_ms / 1000
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

    async def open_steam_downloads(self) -> str:
        if self.model.state.primary_id != "steam-store" or self.model.state.lifecycle.value != "game":
            raise ValueError("Steam Store delegated surface is not active")
        uri = await asyncio.to_thread((self._steam_provider or SteamProvider()).open_downloads)
        self.model.set_delegated_surface("downloads")
        await self._notify()
        return uri

    async def open_steam_store_surface(self) -> str:
        if self.model.state.primary_id != "steam-store" or self.model.state.lifecycle.value != "game":
            raise ValueError("Steam Store delegated surface is not active")
        uri = await asyncio.to_thread((self._steam_provider or SteamProvider()).open_store)
        self.model.set_delegated_surface("store")
        await self._notify()
        return uri

    async def quit_delegated(self) -> None:
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
            except (OSError, TimeoutError, ValueError) as error:
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
        if self._steam_store_watch_task is not None:
            self._steam_store_watch_task.cancel()
            await asyncio.gather(self._steam_store_watch_task, return_exceptions=True)
            self._steam_store_watch_task = None
        if self._steam_launch is not None:
            await (self._steam_provider or SteamProvider()).stop(self._steam_launch)
            if self._watch_task is not None:
                await self._watch_task
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

    def state_details(self) -> dict[str, object]:
        identity = self.active_identity
        return {
            "active_identity": asdict(identity) if identity is not None else None,
            "shell_identity": asdict(self._shell_identity) if self._shell_identity is not None else None,
            "last_result": self.model.last_result.as_dict() if self.model.last_result else None,
        }
