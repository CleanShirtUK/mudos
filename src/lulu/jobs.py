"""Provider-neutral immutable acquisition/job domain objects."""

from dataclasses import dataclass, replace
from enum import StrEnum
from typing import Any


class JobState(StrEnum):
    QUEUED = "queued"
    STARTING = "starting"
    TRANSFERRING = "transferring"
    # Compatibility alias for the original foundation model.
    RUNNING = "transferring"
    FINALIZING = "finalizing"
    PAUSED = "paused"
    CANCELLING = "cancelling"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class JobOperation(StrEnum):
    ACQUIRE = "acquire"
    INSTALL = "install"
    UPDATE = "update"
    REMOVE = "remove"


@dataclass(frozen=True, slots=True)
class JobError:
    code: str
    message: str
    retryable: bool = False
    details: dict[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class DownloadJob:
    job_id: str
    provider: str
    title: str
    content_identity: str = ""
    operation: JobOperation = JobOperation.ACQUIRE
    state: JobState = JobState.QUEUED
    progress: float | None = None
    downloaded_bytes: int | None = None
    total_bytes: int | None = None
    stage: str = "queued"
    error: JobError | None = None
    retryable: bool = True
    cancellation_supported: bool = False
    provider_job_id: str | None = None

    @property
    def is_active(self) -> bool:
        return self.state in {
            JobState.STARTING, JobState.TRANSFERRING, JobState.FINALIZING
        }

    def transition(self, state: JobState, *, progress: float | None = None,
                   stage: str | None = None,
                   error: JobError | str | None = None) -> "DownloadJob":
        if isinstance(error, str):
            error = JobError("provider-failure", error, retryable=self.retryable)
        allowed = {
            JobState.QUEUED: {JobState.STARTING, JobState.TRANSFERRING, JobState.CANCELLED},
            JobState.STARTING: {JobState.TRANSFERRING, JobState.FINALIZING,
                                JobState.CANCELLING, JobState.FAILED},
            JobState.TRANSFERRING: {JobState.PAUSED, JobState.FINALIZING,
                                    JobState.CANCELLING, JobState.FAILED},
            JobState.FINALIZING: {JobState.COMPLETED, JobState.CANCELLING,
                                  JobState.FAILED},
            JobState.PAUSED: {JobState.TRANSFERRING, JobState.CANCELLING,
                              JobState.FAILED},
            JobState.CANCELLING: {JobState.CANCELLED, JobState.FAILED},
            JobState.FAILED: {JobState.QUEUED, JobState.CANCELLED},
            JobState.COMPLETED: set(),
            JobState.CANCELLED: set(),
        }
        if state == self.state:
            if state == JobState.FINALIZING:
                return replace(self, progress=None, downloaded_bytes=None,
                               total_bytes=None, stage=stage or self.stage,
                               error=error)
            return replace(self, progress=progress if progress is not None else self.progress,
                           stage=stage or self.stage, error=error)
        if state not in allowed[self.state]:
            raise ValueError(f"invalid job transition: {self.state} -> {state}")
        if state == JobState.COMPLETED and self.progress not in (None, 1.0):
            raise ValueError("completed job must have unknown or complete progress")
        finalizing = state == JobState.FINALIZING
        return replace(self, state=state,
                       progress=None if finalizing else (progress if progress is not None else self.progress),
                       downloaded_bytes=None if finalizing else self.downloaded_bytes,
                       total_bytes=None if finalizing else self.total_bytes,
                       stage=stage or self.stage, error=error)

    def update_progress(self, progress: float | None = None, *,
                        downloaded_bytes: int | None = None,
                        total_bytes: int | None = None,
                        stage: str | None = None) -> "DownloadJob":
        if progress is not None and not 0 <= progress <= 1:
            raise ValueError("job progress must be between 0 and 1")
        for name, value in (("downloaded bytes", downloaded_bytes),
                            ("total bytes", total_bytes)):
            if value is not None and (not isinstance(value, int) or value < 0):
                raise ValueError(f"{name} must be a non-negative integer or None")
        if downloaded_bytes is not None and total_bytes is not None \
                and downloaded_bytes > total_bytes:
            raise ValueError("downloaded bytes cannot exceed total bytes")
        return replace(
            self,
            progress=progress,
            downloaded_bytes=downloaded_bytes,
            total_bytes=total_bytes,
            stage=stage or self.stage,
        )
