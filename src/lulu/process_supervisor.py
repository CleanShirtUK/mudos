"""Real OS process supervision for console-sessiond."""

from dataclasses import asdict, dataclass
import asyncio
import os
import signal
from typing import Awaitable, Callable

from .console_sessiond import SessionStateModel


@dataclass(frozen=True, slots=True)
class LaunchIdentity:
    token: str
    pid: int
    pgid: int
    executable: str
    argv: tuple[str, ...]


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


class ProcessSupervisor:
    """Owns the primary process and its dedicated process group."""

    def __init__(self, model: SessionStateModel, state_changed: StateChanged | None = None) -> None:
        self.model = model
        self.state_changed = state_changed
        self.active_identity: LaunchIdentity | None = None
        self._process: asyncio.subprocess.Process | None = None
        self._launch_lock = asyncio.Lock()
        self._watch_task: asyncio.Task[None] | None = None

    async def _notify(self) -> None:
        if self.state_changed is not None:
            result = self.state_changed()
            if result is not None:
                await result

    async def launch(self, command: list[str], startup_timeout_ms: int) -> str:
        if not command or not command[0]:
            raise ValueError("launch command is required")
        if startup_timeout_ms < 1:
            raise ValueError("startup timeout must be positive")

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
                self.model.primary_started(token)
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
            "last_result": self.model.last_result.as_dict() if self.model.last_result else None,
        }
