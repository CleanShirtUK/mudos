"""Provider-neutral download/job state model."""

from dataclasses import dataclass, replace
from enum import StrEnum


class JobState(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(frozen=True, slots=True)
class DownloadJob:
    job_id: str
    provider: str
    title: str
    state: JobState = JobState.QUEUED
    progress: float | None = None
    error: str | None = None
    restartable: bool = True

    def transition(self, state: JobState, *, progress: float | None = None, error: str | None = None) -> "DownloadJob":
        allowed = {
            JobState.QUEUED: {JobState.RUNNING, JobState.CANCELLED},
            JobState.RUNNING: {JobState.PAUSED, JobState.COMPLETED, JobState.FAILED, JobState.CANCELLED},
            JobState.PAUSED: {JobState.RUNNING, JobState.CANCELLED},
            JobState.FAILED: {JobState.QUEUED, JobState.CANCELLED},
            JobState.COMPLETED: set(),
            JobState.CANCELLED: set(),
        }
        if state not in allowed[self.state]:
            raise ValueError(f"invalid job transition: {self.state} -> {state}")
        if progress is not None and not 0 <= progress <= 1:
            raise ValueError("job progress must be between 0 and 1")
        return replace(self, state=state, progress=progress, error=error)
