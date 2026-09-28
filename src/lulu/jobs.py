"""Provider-neutral immutable acquisition/job domain objects."""

from dataclasses import dataclass, field, replace
from enum import StrEnum
from datetime import datetime, timezone
from typing import Any


@dataclass(frozen=True, slots=True)
class ExternalAcquisition:
    content_identity: str
    title: str
    origin: str
    provenance: str
    provider_job_id: str
    state: "JobState"
    progress: float | None
    downloaded_bytes: int | None
    total_bytes: int | None
    stage: str
    rate: int | None
    provider_state: str
    destination: str | None = None
    backend: str = "nzbget"
    metadata: dict[str, object] = field(default_factory=dict)
    error: "JobError | None" = None


def utc_now() -> str:
    """Return the stable UTC representation used at API and storage boundaries."""
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


class JobState(StrEnum):
    QUEUED = "queued"
    STARTING = "starting"
    TRANSFERRING = "transferring"
    AWAITING_INTERACTION = "awaiting_interaction"
    # Compatibility alias for the original foundation model.
    RUNNING = "transferring"
    FINALIZING = "finalizing"
    PAUSED = "paused"
    PAUSING = "pausing"
    RESUMING = "resuming"
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
    pause_supported: bool = False
    provider_job_id: str | None = None
    backend: str | None = None
    destination: str | None = None
    completion_path: str | None = None
    download_rate: int | None = None
    upload_rate: int | None = None
    eta_seconds: int | None = None
    provider_state: str | None = None
    ownership_label: str | None = None
    origin: str = "mudos"
    origin_metadata: dict[str, object] = field(default_factory=dict)
    deletion_policy: str = "preserve-partial"
    artifact_files: tuple[dict[str, object], ...] = ()
    seeding: bool = False
    created_at: str = field(default_factory=utc_now)
    started_at: str | None = None
    updated_at: str = field(default_factory=utc_now)
    completed_at: str | None = None
    attempt: int = 1
    parent_job_id: str | None = None
    recovery_reason: str | None = None
    retired: bool = False

    @property
    def is_active(self) -> bool:
        return self.state in {
            JobState.STARTING, JobState.TRANSFERRING, JobState.FINALIZING,
            JobState.AWAITING_INTERACTION,
            JobState.PAUSING, JobState.RESUMING, JobState.CANCELLING,
        }

    def transition(self, state: JobState, *, progress: float | None = None,
                   stage: str | None = None,
                   error: JobError | str | None = None) -> "DownloadJob":
        if isinstance(error, str):
            error = JobError("provider-failure", error, retryable=self.retryable)
        allowed = {
            JobState.QUEUED: {JobState.STARTING, JobState.TRANSFERRING, JobState.CANCELLED},
            JobState.STARTING: {JobState.TRANSFERRING, JobState.PAUSING, JobState.PAUSED, JobState.FINALIZING,
                                JobState.CANCELLING, JobState.CANCELLED, JobState.FAILED},
            JobState.TRANSFERRING: {JobState.PAUSING, JobState.PAUSED, JobState.FINALIZING,
                                    JobState.AWAITING_INTERACTION, JobState.CANCELLING, JobState.CANCELLED, JobState.FAILED},
            JobState.AWAITING_INTERACTION: {JobState.TRANSFERRING, JobState.CANCELLING, JobState.CANCELLED, JobState.FAILED},
            JobState.FINALIZING: {JobState.COMPLETED, JobState.CANCELLING, JobState.CANCELLED,
                                  JobState.FAILED},
            JobState.PAUSED: {JobState.RESUMING, JobState.QUEUED, JobState.TRANSFERRING, JobState.CANCELLING, JobState.CANCELLED,
                              JobState.FAILED},
            JobState.PAUSING: {JobState.PAUSED, JobState.CANCELLING, JobState.CANCELLED, JobState.FAILED},
            JobState.RESUMING: {JobState.STARTING, JobState.QUEUED, JobState.TRANSFERRING,
                                JobState.PAUSED, JobState.CANCELLING, JobState.CANCELLED, JobState.FAILED},
            JobState.CANCELLING: {JobState.CANCELLED, JobState.FAILED},
            JobState.FAILED: {JobState.QUEUED, JobState.CANCELLED},
            JobState.COMPLETED: set(),
            JobState.CANCELLED: set(),
        }
        now = utc_now()
        started_at = self.started_at
        if started_at is None and state in {
                JobState.STARTING, JobState.TRANSFERRING, JobState.FINALIZING,
        }:
            started_at = now
        completed_at = self.completed_at
        if state in {JobState.COMPLETED, JobState.FAILED, JobState.CANCELLED}:
            completed_at = completed_at or now
        if state == self.state:
            if state == JobState.FINALIZING:
                return replace(self, stage=stage or self.stage,
                               error=error, started_at=started_at,
                               completed_at=completed_at, updated_at=now)
            return replace(self, progress=progress if progress is not None else self.progress,
                           stage=stage or self.stage, error=error,
                           started_at=started_at, completed_at=completed_at,
                           updated_at=now)
        if state not in allowed[self.state]:
            raise ValueError(f"invalid job transition: {self.state} -> {state}")
        if state == JobState.COMPLETED and self.progress not in (None, 1.0):
            raise ValueError("completed job must have unknown or complete progress")
        return replace(self, state=state,
                       progress=progress if progress is not None else self.progress,
                       downloaded_bytes=self.downloaded_bytes,
                       total_bytes=self.total_bytes,
                       stage=stage or self.stage, error=error,
                       started_at=started_at, completed_at=completed_at,
                       updated_at=now)

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
            updated_at=utc_now(),
        )
