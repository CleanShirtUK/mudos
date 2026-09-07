"""Real OS process supervision for console-sessiond."""

from dataclasses import asdict, dataclass
import asyncio
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
            try:
                process = await asyncio.wait_for(
                    asyncio.create_subprocess_exec(
                        *command,
                        stdin=asyncio.subprocess.DEVNULL,
                        stdout=asyncio.subprocess.DEVNULL,
                        stderr=asyncio.subprocess.DEVNULL,
                        start_new_session=True,
                    ),
                    timeout=startup_timeout_ms / 1000,
                )
                identity = LaunchIdentity(
                    token=token,
                    pid=process.pid,
                    pgid=os.getpgid(process.pid),
                    executable=os.path.realpath(f"/proc/{process.pid}/exe"),
                    argv=tuple(command),
                )
                self._process = process
                self.active_identity = identity
                if presentation_controller is not None:
                    presentation_controller.clear_selection()
                self._set_input_mode(input_mode)
                self.model.primary_started(token, presentation=presentation, input_mode=input_mode)
                await self._notify()
                self._watch_task = asyncio.create_task(self._watch(identity, process))
                return token
            except (OSError, asyncio.TimeoutError) as error:
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
                raise ValueError(reason) from error

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
                        stdout=asyncio.subprocess.DEVNULL,
                        stderr=asyncio.subprocess.DEVNULL,
                        start_new_session=True,
                    ),
                    timeout=startup_timeout_ms / 1000,
                )
                identity = LaunchIdentity(
                    token=uuid4().hex,
                    pid=process.pid,
                    pgid=os.getpgid(process.pid),
                    executable=os.path.realpath(f"/proc/{process.pid}/exe"),
                    argv=tuple(command),
                )
                self._shell_process = process
                self._shell_identity = identity
                if self._presentation is not None and select_shell:
                    self._presentation.select_shell(process.pid)
                self._set_input_mode(InputMode.SHELL)
                self._shell_watch_task = asyncio.create_task(self._watch_shell(process))
                self._watch_task = self._shell_watch_task
                return identity.token
            except (OSError, subprocess.SubprocessError, asyncio.TimeoutError, TimeoutError) as error:
                if "process" in locals():
                    await self._terminate_group(os.getpgid(process.pid))
                self._shell_process = None
                self._shell_identity = None
                raise ValueError(f"shell launch failed: {error}") from error

    async def _watch_shell(self, process: asyncio.subprocess.Process) -> None:
        exit_code = await process.wait()
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

    async def _watch(self, identity: LaunchIdentity, process: asyncio.subprocess.Process) -> None:
        exit_code = await process.wait()
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

    async def launch_steam(self, app_id: str, startup_timeout_ms: int) -> str:
        if startup_timeout_ms < 1:
            raise ValueError("startup timeout must be positive")
        async with self._launch_lock:
            if self.active_identity is not None or self.model.state.lifecycle.value != "shell":
                raise ValueError("another launch owns the session")
            token = self.model.request_launch(f"steam:{app_id}")
            await self._notify()
            provider = self._steam_provider or SteamProvider()
            launch: SteamLaunch | None = None
            try:
                request: SteamLaunchRequest = await provider.request_launch(app_id)
                self.model.launch_starting(token)
                self._set_input_mode(InputMode.GAME)
                if self._presentation is not None:
                    self._presentation.clear_selection()
                await self._notify()
                launch = await provider.observe_launch(request, token)
                if self._presentation is not None:
                    self._presentation.select_pid(launch.title.pid)
                self.model.primary_started(token, presentation=Presentation.GAME, input_mode=InputMode.GAME)
                self._steam_launch = launch
                self.active_identity = launch.title
                await self._notify()
                self._watch_task = asyncio.create_task(self._watch_steam(provider, launch))
                return token
            except (OSError, asyncio.TimeoutError, ValueError) as error:
                if launch is not None:
                    await provider.stop(launch)
                reason = f"Steam launch failed: {error}"
                self.model.fail(token, reason)
                self.model.record_result(ProcessResult(token, None, None, "steam", (app_id,), None, None, "start-failed", reason))
                if self._presentation is not None and self._shell_process is not None:
                    self._presentation.select_shell(self._shell_process.pid)
                self._set_input_mode(InputMode.SHELL)
                self.model.return_complete(token)
                await self._notify()
                raise ValueError(reason) from error

    async def _watch_steam(self, provider: SteamProvider, launch: SteamLaunch) -> None:
        await provider.wait_for_exit(launch)
        identity = launch.title
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
        if self._presentation is not None and self._shell_process is not None:
            self._presentation.select_shell(self._shell_process.pid)
        self._set_input_mode(InputMode.SHELL)
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
