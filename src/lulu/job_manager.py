"""Dedicated provider-neutral acquisition job manager."""

from __future__ import annotations

import asyncio
from collections import defaultdict, deque
from dataclasses import asdict
from typing import Awaitable, Callable, Protocol
from uuid import uuid4

from .jobs import DownloadJob, JobError, JobOperation, JobState, utc_now
from .acquisition_store import AcquisitionStore


class JobCancelled(Exception):
    """Provider executor reports that cancellation completed."""


class JobExecutionError(Exception):
    """Provider failure carrying a normalized job error."""

    def __init__(self, code: str, message: str, *, retryable: bool = False,
                 details: dict[str, object] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.retryable = retryable
        self.details = details


class JobExecutor(Protocol):
    async def run(self, job: DownloadJob, reporter: "JobReporter") -> None: ...
    async def cancel(self, job: DownloadJob) -> None: ...


class JobReporter:
    def __init__(self, manager: "JobManager", job_id: str) -> None:
        self._manager = manager
        self._job_id = job_id

    async def progress(self, progress: float | None = None, *,
                       downloaded_bytes: int | None = None,
                       total_bytes: int | None = None,
                       stage: str | None = None) -> DownloadJob:
        return self._manager.update_progress(
            self._job_id, progress, downloaded_bytes=downloaded_bytes,
            total_bytes=total_bytes, stage=stage,
        )

    async def state(self, state: JobState, *, stage: str | None = None) -> DownloadJob:
        return self._manager.transition(self._job_id, state, stage=stage)

    async def metadata(self, **values: object) -> DownloadJob:
        return self._manager.update_metadata(self._job_id, **values)


class JobManager:
    """In-memory manager; persistence can be added without changing its API."""

    def __init__(self, *, provider_limits: dict[str, int] | None = None,
                 on_change: Callable[[tuple[DownloadJob, ...]], None] | None = None,
                 store: AcquisitionStore | None = None) -> None:
        self.provider_limits = dict(provider_limits or {})
        self.store = store
        self.jobs: dict[str, DownloadJob] = {
            job.job_id: job for job in (store.load() if store is not None else ())
        }
        self.executors: dict[str, JobExecutor] = {}
        self._queues: dict[str, deque[str]] = defaultdict(deque)
        self._running: dict[str, set[str]] = defaultdict(set)
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._on_change = on_change
        for job in self.jobs.values():
            if job.state == JobState.QUEUED:
                self._queues[job.provider].append(job.job_id)

    def register_executor(self, provider: str, executor: JobExecutor, *, limit: int = 1) -> None:
        if limit < 1:
            raise ValueError("provider concurrency limit must be positive")
        if provider in self.executors:
            raise ValueError(f"executor already registered: {provider}")
        self.executors[provider] = executor
        self.provider_limits[provider] = limit
        self._pump(provider)

    @property
    def active_download_count(self) -> int:
        return sum(job.is_active for job in self.jobs.values())

    def snapshot(self) -> tuple[DownloadJob, ...]:
        return tuple(self.jobs.values())

    def submit(self, provider: str, content_identity: str, title: str, *,
               operation: JobOperation = JobOperation.ACQUIRE,
               cancellation_supported: bool = False,
               provider_job_id: str | None = None, attempt: int = 1,
               parent_job_id: str | None = None) -> DownloadJob:
        if provider not in self.executors:
            raise ValueError(f"no executor registered for provider: {provider}")
        for existing in self.jobs.values():
            if (existing.provider == provider
                    and existing.content_identity == content_identity
                    and existing.operation != operation
                    and existing.state in {
                        JobState.QUEUED, JobState.STARTING, JobState.TRANSFERRING,
                        JobState.FINALIZING, JobState.PAUSED, JobState.CANCELLING,
                    }):
                raise ValueError("content has an active conflicting operation")
            if (existing.provider == provider
                    and existing.content_identity == content_identity
                    and existing.operation == operation
                    and existing.state in {
                        JobState.QUEUED, JobState.STARTING, JobState.TRANSFERRING,
                        JobState.FINALIZING, JobState.PAUSED, JobState.CANCELLING,
                    }):
                return existing
        job = DownloadJob(
            job_id=f"job-{uuid4().hex}", provider=provider, title=title,
            content_identity=content_identity, operation=operation,
            cancellation_supported=cancellation_supported,
            provider_job_id=provider_job_id,
            created_at=utc_now(), updated_at=utc_now(), attempt=attempt,
            parent_job_id=parent_job_id,
        )
        self.jobs[job.job_id] = job
        self._queues[provider].append(job.job_id)
        self._publish()
        self._pump(provider)
        return job

    def retry(self, job_id: str) -> DownloadJob:
        previous = self._require(job_id)
        if previous.state != JobState.FAILED:
            raise ValueError("job is not failed")
        return self.submit(
            previous.provider, previous.content_identity, previous.title,
            operation=previous.operation,
            cancellation_supported=previous.cancellation_supported,
            attempt=previous.attempt + 1,
            parent_job_id=previous.job_id,
        )

    def transition(self, job_id: str, state: JobState, *,
                   stage: str | None = None,
                   error: JobError | None = None) -> DownloadJob:
        job = self._require(job_id)
        self.jobs[job_id] = job.transition(state, stage=stage, error=error)
        self._publish()
        return self.jobs[job_id]

    def update_metadata(self, job_id: str, **values: object) -> DownloadJob:
        job = self._require(job_id)
        allowed = set(DownloadJob.__dataclass_fields__)
        unknown = set(values) - allowed
        if unknown:
            raise ValueError(f"unknown job metadata: {sorted(unknown)}")
        from dataclasses import replace
        self.jobs[job_id] = replace(job, **values, updated_at=utc_now())
        self._publish()
        return self.jobs[job_id]

    def update_progress(self, job_id: str, progress: float | None = None, *,
                        downloaded_bytes: int | None = None,
                        total_bytes: int | None = None,
                        stage: str | None = None) -> DownloadJob:
        job = self._require(job_id)
        self.jobs[job_id] = job.update_progress(
            progress, downloaded_bytes=downloaded_bytes,
            total_bytes=total_bytes, stage=stage,
        )
        self._publish()
        return self.jobs[job_id]

    async def cancel(self, job_id: str) -> DownloadJob:
        job = self._require(job_id)
        if not job.cancellation_supported:
            return job
        if job.state in {JobState.QUEUED, JobState.FAILED}:
            executor = self.executors.get(job.provider)
            cancel = getattr(executor, "cancel", None)
            if cancel is not None:
                await cancel(job)
            return self.transition(job_id, JobState.CANCELLED, stage="cancelled")
        if job.state == JobState.PAUSED:
            executor = self.executors.get(job.provider)
            cancel = getattr(executor, "cancel", None)
            if cancel is not None:
                await cancel(job)
            return self.transition(job_id, JobState.CANCELLED, stage="cancelled")
        if job.state not in {JobState.STARTING, JobState.TRANSFERRING,
                             JobState.FINALIZING}:
            return job
        self.transition(job_id, JobState.CANCELLING, stage="cancelling")
        executor = self.executors.get(job.provider)
        if executor is not None:
            await executor.cancel(job)
        task = self._tasks.get(job_id)
        if task is not None:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        if self.jobs[job_id].state == JobState.CANCELLING:
            self.transition(job_id, JobState.CANCELLED, stage="cancelled")
        return self.jobs[job_id]

    async def pause(self, job_id: str) -> DownloadJob:
        job = self._require(job_id)
        if not job.cancellation_supported:
            return job
        if job.state not in {JobState.STARTING, JobState.TRANSFERRING}:
            return job
        self.transition(job_id, JobState.PAUSED, stage="paused")
        executor = self.executors.get(job.provider)
        pause = getattr(executor, "pause", None)
        if pause is not None:
            await pause(job.provider_job_id) if job.provider_job_id else None
        task = self._tasks.get(job_id)
        if task is not None:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        return self.jobs[job_id]

    def resume(self, job_id: str) -> DownloadJob:
        job = self._require(job_id)
        if job.state != JobState.PAUSED:
            return job
        self.transition(job_id, JobState.QUEUED, stage="queued")
        self._queues[job.provider].append(job_id)
        self._pump(job.provider)
        return self.jobs[job_id]

    def _pump(self, provider: str) -> None:
        limit = self.provider_limits.get(provider, 1)
        while self._queues[provider] and len(self._running[provider]) < limit:
            job_id = self._queues[provider].popleft()
            if self.jobs[job_id].state != JobState.QUEUED:
                continue
            self._running[provider].add(job_id)
            self._tasks[job_id] = asyncio.create_task(self._run(job_id))

    async def _run(self, job_id: str) -> None:
        job = self.jobs[job_id]
        provider = job.provider
        try:
            self.transition(job_id, JobState.STARTING, stage="starting")
            await self.executors[provider].run(
                self.jobs[job_id], JobReporter(self, job_id)
            )
            if self.jobs[job_id].state == JobState.TRANSFERRING:
                self.transition(job_id, JobState.FINALIZING, stage="finalizing")
            if self.jobs[job_id].state == JobState.FINALIZING:
                current = self.jobs[job_id]
                self.update_progress(job_id, 1.0, downloaded_bytes=current.downloaded_bytes,
                                     total_bytes=current.total_bytes, stage="completed")
                self.transition(job_id, JobState.COMPLETED, stage="completed")
        except JobCancelled:
            if self.jobs[job_id].state == JobState.CANCELLING:
                self.transition(job_id, JobState.CANCELLED, stage="cancelled")
        except JobExecutionError as error:
            if self.jobs[job_id].state not in {JobState.CANCELLED, JobState.COMPLETED}:
                self.transition(job_id, JobState.FAILED, stage="failed", error=JobError(
                    error.code, str(error), retryable=error.retryable, details=error.details,
                ))
        except Exception as error:  # provider failures are normalized here
            if self.jobs[job_id].state not in {JobState.CANCELLED, JobState.COMPLETED}:
                self.transition(job_id, JobState.FAILED, stage="failed", error=JobError(
                    "provider-failure", str(error), retryable=self.jobs[job_id].retryable,
                ))
        finally:
            self._running[provider].discard(job_id)
            self._tasks.pop(job_id, None)
            self._pump(provider)

    def _require(self, job_id: str) -> DownloadJob:
        try:
            return self.jobs[job_id]
        except KeyError as error:
            raise KeyError(f"unknown job: {job_id}") from error

    def _publish(self) -> None:
        if self.store is not None:
            self.store.save_all(self.jobs.values())
            retained = self.store.job_ids()
            self.jobs = {
                job_id: job for job_id, job in self.jobs.items()
                if not job.state in {JobState.COMPLETED, JobState.FAILED, JobState.CANCELLED}
                or job_id in retained
            }
        if self._on_change is not None:
            self._on_change(self.snapshot())


def job_to_dict(job: DownloadJob) -> dict[str, object]:
    value = asdict(job)
    value["operation"] = job.operation.value
    value["state"] = job.state.value
    return value
