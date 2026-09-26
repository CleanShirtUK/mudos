"""Session-scoped, provider-neutral Mudos notifications."""

from __future__ import annotations

from collections import deque
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Awaitable, Callable, Deque, Iterable

from .jobs import DownloadJob, JobOperation, JobState


LOGGER = logging.getLogger("lulu.notifications")


@dataclass(frozen=True, slots=True)
class Notification:
    event_id: str
    event_type: str
    title: str
    body: str
    glyph: str = ""
    source: str = ""
    timestamp: str = ""
    priority: int = 0

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


NotificationSink = Callable[[Notification], Awaitable[None]]


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


class NotificationBroker:
    """Queue transient events without becoming a second job database.

    The broker is deliberately session-scoped. Existing jobs are seeded at
    startup and are never replayed; only observed state transitions can create
    events. Deduplication is therefore durable for one running service while
    recovery remains quiet after restart.
    """

    def __init__(self, sink: NotificationSink | None = None) -> None:
        self._sink = sink
        self._queue: Deque[Notification] = deque()
        self._queued_ids: set[str] = set()
        self._emitted_ids: set[str] = set()
        self._states: dict[str, JobState] = {}
        self._worker: asyncio.Task[None] | None = None

    @property
    def pending(self) -> tuple[Notification, ...]:
        return tuple(self._queue)

    def seed(self, jobs: Iterable[DownloadJob]) -> None:
        """Record current state without generating historical notifications."""
        self._states = {job.job_id: job.state for job in jobs}

    def observe(self, jobs: Iterable[DownloadJob]) -> None:
        """Observe one authoritative JobManager snapshot."""
        for job in jobs:
            previous = self._states.get(job.job_id)
            self._states[job.job_id] = job.state
            if previous is None or previous == job.state:
                continue
            for notification in self._events_for(job, previous):
                self.enqueue(notification)

    def enqueue(self, notification: Notification) -> bool:
        if notification.event_id in self._emitted_ids or notification.event_id in self._queued_ids:
            return False
        self._queue.append(notification)
        self._queued_ids.add(notification.event_id)
        if self._sink is not None and (self._worker is None or self._worker.done()):
            self._worker = asyncio.create_task(self._drain(), name="notification-presenter")
        return True

    async def drain(self) -> None:
        """Wait for the current presenter queue, primarily for validation/tests."""
        if self._worker is not None:
            await self._worker

    def _events_for(self, job: DownloadJob, previous: JobState) -> tuple[Notification, ...]:
        if previous in {JobState.FAILED, JobState.CANCELLED}:
            return ()
        events: list[Notification] = []
        source = job.provider
        title = job.title or job.content_identity or job.provider
        if job.state is JobState.FAILED:
            reason = (job.error.message or job.error.code) if job.error else "No failure details available"
            guidance = ("Open Downloads to retry." if job.retryable
                        and (job.error is None or job.error.retryable)
                        else "Open Downloads for details; correct the cause before trying again.")
            operation = {
                JobOperation.ACQUIRE: "Download", JobOperation.INSTALL: "Installation",
                JobOperation.UPDATE: "Update", JobOperation.REMOVE: "Removal",
            }[job.operation]
            events.append(Notification(
                event_id=f"{job.job_id}:acquisition_failed", event_type="acquisition_failed",
                title=f"{operation} failed", body=f"{title}: {reason.rstrip('.')}. {guidance}",
                source=source, timestamp=_timestamp(), priority=1,
            ))
        if job.state is JobState.TRANSFERRING and previous is not JobState.TRANSFERRING \
                and job.operation is not JobOperation.REMOVE:
            events.append(Notification(
                event_id=f"{job.job_id}:download_started", event_type="download_started",
                title="Download started", body=title, source=source, timestamp=_timestamp(),
            ))
        if job.state is JobState.FINALIZING and previous is JobState.TRANSFERRING:
            events.append(Notification(
                event_id=f"{job.job_id}:download_finished", event_type="download_finished",
                title="Download finished", body=title, source=source, timestamp=_timestamp(),
            ))
        if job.state is JobState.COMPLETED and job.operation is JobOperation.ACQUIRE \
                and previous in {JobState.TRANSFERRING, JobState.FINALIZING}:
            events.append(Notification(
                event_id=f"{job.job_id}:download_finished", event_type="download_finished",
                title="Download finished", body=title, source=source, timestamp=_timestamp(),
            ))
        if job.state is JobState.COMPLETED and job.operation is JobOperation.INSTALL:
            events.append(Notification(
                event_id=f"{job.job_id}:installation_succeeded",
                event_type="installation_succeeded", title="Installed successfully",
                body=f"{title} is ready to play", source=source, timestamp=_timestamp(),
            ))
        return tuple(events)

    async def _drain(self) -> None:
        assert self._sink is not None
        while self._queue:
            notification = self._queue.popleft()
            self._queued_ids.discard(notification.event_id)
            try:
                await self._sink(notification)
            except Exception:
                LOGGER.exception("notification presentation failed event_id=%s", notification.event_id)
            finally:
                self._emitted_ids.add(notification.event_id)


class NotificationPresenter:
    """Passive external-overlay presenter with one-at-a-time FIFO display."""

    def __init__(self, executable: str | None = None, duration: float = 4.0) -> None:
        self.executable = executable or str(
            Path(os.environ.get("LULU_INSTALL_ROOT", "/opt/lulu/dev-current"))
            / "bin" / "mudos-notification"
        )
        self.duration = duration
        self._process: asyncio.subprocess.Process | None = None

    async def _ensure_process(self) -> asyncio.subprocess.Process:
        if self._process is not None and self._process.returncode is None:
            return self._process
        install_root = Path(os.environ.get("LULU_INSTALL_ROOT", "/opt/lulu/dev-current"))
        env = {**os.environ, "DISPLAY": os.environ.get("DISPLAY", ":0"),
               "WAYLAND_DISPLAY": os.environ.get("WAYLAND_DISPLAY", "gamescope-0"),
               "XDG_RUNTIME_DIR": os.environ.get("XDG_RUNTIME_DIR", "/run/user/958"),
               "QT_QPA_PLATFORM": os.environ.get("QT_QPA_PLATFORM", "xcb"),
               "LULU_NOTIFICATION_UI_FILE": os.environ.get(
                   "LULU_NOTIFICATION_UI_FILE", str(install_root / "ui" / "MudosNotification.qml"),
               )}
        self._process = await asyncio.create_subprocess_exec(
            self.executable, stdin=asyncio.subprocess.PIPE, env=env,
        )
        return self._process

    async def __call__(self, notification: Notification) -> None:
        process = await self._ensure_process()
        if process.stdin is None:
            raise RuntimeError("notification presenter stdin is unavailable")
        process.stdin.write((json.dumps(notification.as_dict()) + "\n").encode())
        await process.stdin.drain()
        await asyncio.sleep(self.duration)
        process.stdin.write(b'{"visible":false}\n')
        await process.stdin.drain()
