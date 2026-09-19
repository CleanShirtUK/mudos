"""Durable, provider-neutral acquisition history and recovery journal."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import replace
from pathlib import Path
from typing import Iterable

from .jobs import DownloadJob, JobError, JobOperation, JobState, utc_now


TERMINAL_STATES = {JobState.COMPLETED, JobState.FAILED, JobState.CANCELLED}
HISTORY_LIMIT = 200


class AcquisitionStore:
    """SQLite backing store; it never schedules or executes provider work."""

    def __init__(self, path: Path, *, history_limit: int = HISTORY_LIMIT) -> None:
        self.path = Path(path)
        self.history_limit = history_limit
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(self.path)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA journal_mode=WAL")
        self._connection.execute("PRAGMA foreign_keys=ON")
        self._connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS acquisition_jobs (
                job_id TEXT PRIMARY KEY,
                provider TEXT NOT NULL,
                content_identity TEXT NOT NULL,
                title TEXT NOT NULL,
                operation TEXT NOT NULL,
                state TEXT NOT NULL,
                progress REAL,
                downloaded_bytes INTEGER,
                total_bytes INTEGER,
                stage TEXT NOT NULL,
                error_json TEXT,
                retryable INTEGER NOT NULL,
                cancellation_supported INTEGER NOT NULL,
                provider_job_id TEXT,
                created_at TEXT NOT NULL,
                started_at TEXT,
                updated_at TEXT NOT NULL,
                completed_at TEXT,
                 attempt INTEGER NOT NULL,
                 parent_job_id TEXT,
                 recovery_reason TEXT,
                 backend TEXT,
                 destination TEXT,
                 completion_path TEXT,
                 download_rate INTEGER,
                 upload_rate INTEGER,
                 eta_seconds INTEGER,
                 provider_state TEXT,
                 ownership_label TEXT,
                 deletion_policy TEXT NOT NULL DEFAULT 'preserve-partial',
                 artifact_files_json TEXT,
                 seeding INTEGER NOT NULL DEFAULT 0
                 , retired INTEGER NOT NULL DEFAULT 0
            );
            CREATE INDEX IF NOT EXISTS acquisition_jobs_updated
                ON acquisition_jobs(updated_at DESC);
            """
        )
        self._connection.commit()
        columns = {str(row[1]) for row in self._connection.execute("PRAGMA table_info(acquisition_jobs)")}
        additions = {
            "backend": "TEXT", "destination": "TEXT", "completion_path": "TEXT",
            "download_rate": "INTEGER", "upload_rate": "INTEGER", "eta_seconds": "INTEGER",
            "provider_state": "TEXT", "ownership_label": "TEXT",
            "deletion_policy": "TEXT NOT NULL DEFAULT 'preserve-partial'",
            "artifact_files_json": "TEXT", "seeding": "INTEGER NOT NULL DEFAULT 0",
            "retired": "INTEGER NOT NULL DEFAULT 0",
        }
        with self._connection:
            for name, declaration in additions.items():
                if name not in columns:
                    self._connection.execute(f"ALTER TABLE acquisition_jobs ADD COLUMN {name} {declaration}")
        self._prune()

    def close(self) -> None:
        self._connection.close()

    def job_ids(self) -> set[str]:
        return {str(row[0]) for row in self._connection.execute("SELECT job_id FROM acquisition_jobs")}

    def load(self) -> list[DownloadJob]:
        result: list[DownloadJob] = []
        for row in self._connection.execute("SELECT * FROM acquisition_jobs ORDER BY rowid"):
            try:
                result.append(self._decode(row))
            except (KeyError, TypeError, ValueError, json.JSONDecodeError):
                # A corrupt history row must not prevent acquisitiond startup.
                continue
        return self._recover_active(result)

    def save_all(self, jobs: Iterable[DownloadJob]) -> None:
        values = list(jobs)
        with self._connection:
            for job in values:
                self._connection.execute(
                    """INSERT INTO acquisition_jobs (
                        job_id, provider, content_identity, title, operation, state,
                        progress, downloaded_bytes, total_bytes, stage, error_json,
                        retryable, cancellation_supported, provider_job_id,
                        created_at, started_at, updated_at, completed_at, attempt,
                         parent_job_id, recovery_reason, backend, destination, completion_path,
                         download_rate, upload_rate, eta_seconds, provider_state, ownership_label,
                         deletion_policy, artifact_files_json, seeding, retired
                     ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(job_id) DO UPDATE SET
                        provider=excluded.provider, content_identity=excluded.content_identity,
                        title=excluded.title, operation=excluded.operation, state=excluded.state,
                        progress=excluded.progress, downloaded_bytes=excluded.downloaded_bytes,
                        total_bytes=excluded.total_bytes, stage=excluded.stage,
                        error_json=excluded.error_json, retryable=excluded.retryable,
                        cancellation_supported=excluded.cancellation_supported,
                        provider_job_id=excluded.provider_job_id, created_at=excluded.created_at,
                        started_at=excluded.started_at, updated_at=excluded.updated_at,
                        completed_at=excluded.completed_at, attempt=excluded.attempt,
                         parent_job_id=excluded.parent_job_id, recovery_reason=excluded.recovery_reason,
                         backend=excluded.backend, destination=excluded.destination,
                         completion_path=excluded.completion_path, download_rate=excluded.download_rate,
                         upload_rate=excluded.upload_rate, eta_seconds=excluded.eta_seconds,
                         provider_state=excluded.provider_state, ownership_label=excluded.ownership_label,
                          deletion_policy=excluded.deletion_policy, artifact_files_json=excluded.artifact_files_json,
                          seeding=excluded.seeding, retired=excluded.retired""",
                    self._encode(job),
                )
            self._connection.execute(
                """DELETE FROM acquisition_jobs
                   WHERE state IN ('completed', 'failed', 'cancelled')
                     AND job_id NOT IN (
                       SELECT job_id FROM acquisition_jobs
                       WHERE state IN ('completed', 'failed', 'cancelled')
                       ORDER BY COALESCE(completed_at, updated_at) DESC LIMIT ?
                     )""",
                (self.history_limit,),
            )

    def _prune(self) -> None:
        with self._connection:
            self._connection.execute(
                """DELETE FROM acquisition_jobs
                   WHERE state IN ('completed', 'failed', 'cancelled')
                     AND job_id NOT IN (
                       SELECT job_id FROM acquisition_jobs
                       WHERE state IN ('completed', 'failed', 'cancelled')
                       ORDER BY COALESCE(completed_at, updated_at) DESC LIMIT ?
                     )""",
                (self.history_limit,),
            )

    def _recover_active(self, jobs: list[DownloadJob]) -> list[DownloadJob]:
        recovered: list[DownloadJob] = []
        changed = False
        for job in jobs:
            if job.state in {
                    JobState.STARTING, JobState.TRANSFERRING,
                    JobState.FINALIZING, JobState.CANCELLING,
            }:
                now = utc_now()
                job = replace(job, state=JobState.QUEUED, stage="queued", updated_at=now,
                              recovery_reason="service-restart")
                changed = True
            recovered.append(job)
        if changed:
            self.save_all(recovered)
        return recovered

    @staticmethod
    def _encode(job: DownloadJob) -> tuple[object, ...]:
        error = None if job.error is None else json.dumps({
            "code": job.error.code, "message": job.error.message,
            "retryable": job.error.retryable, "details": job.error.details,
        }, sort_keys=True)
        return (
            job.job_id, job.provider, job.content_identity, job.title, job.operation.value,
            job.state.value, job.progress, job.downloaded_bytes, job.total_bytes, job.stage,
            error, int(job.retryable), int(job.cancellation_supported), job.provider_job_id,
            job.created_at, job.started_at, job.updated_at, job.completed_at, job.attempt,
            job.parent_job_id, job.recovery_reason, job.backend, job.destination,
            job.completion_path, job.download_rate, job.upload_rate, job.eta_seconds,
            job.provider_state, job.ownership_label, job.deletion_policy,
            json.dumps(list(job.artifact_files), sort_keys=True), int(job.seeding), int(job.retired),
        )

    @staticmethod
    def _decode(row: sqlite3.Row) -> DownloadJob:
        error_value = json.loads(row["error_json"]) if row["error_json"] else None
        error = None if error_value is None else JobError(
            str(error_value["code"]), str(error_value["message"]),
            bool(error_value.get("retryable", False)), error_value.get("details"),
        )
        return DownloadJob(
            job_id=str(row["job_id"]), provider=str(row["provider"]),
            content_identity=str(row["content_identity"]), title=str(row["title"]),
            operation=JobOperation(str(row["operation"])), state=JobState(str(row["state"])),
            progress=row["progress"], downloaded_bytes=row["downloaded_bytes"],
            total_bytes=row["total_bytes"], stage=str(row["stage"]), error=error,
            retryable=bool(row["retryable"]), cancellation_supported=bool(row["cancellation_supported"]),
            provider_job_id=row["provider_job_id"], created_at=str(row["created_at"]),
            started_at=row["started_at"], updated_at=str(row["updated_at"]),
            completed_at=row["completed_at"], attempt=int(row["attempt"]),
            parent_job_id=row["parent_job_id"], recovery_reason=row["recovery_reason"],
            backend=row["backend"], destination=row["destination"], completion_path=row["completion_path"],
            download_rate=row["download_rate"], upload_rate=row["upload_rate"], eta_seconds=row["eta_seconds"],
            provider_state=row["provider_state"], ownership_label=row["ownership_label"],
            deletion_policy=row["deletion_policy"] or "preserve-partial",
            artifact_files=tuple(json.loads(row["artifact_files_json"] or "[]")),
            seeding=bool(row["seeding"]),
            retired=bool(row["retired"]),
        )
