import asyncio
import sqlite3
import tempfile
import unittest
from pathlib import Path

from lulu.acquisition_store import AcquisitionStore
from lulu.acquisitiond import _completed_job_refresh_stages
from lulu.job_manager import JobManager, JobReporter
from lulu.jobs import DownloadJob, JobError, JobState


class HoldingExecutor:
    def __init__(self) -> None:
        self.started: list[str] = []
        self.release = asyncio.Event()
        self.active = 0

    async def run(self, job: DownloadJob, reporter: JobReporter) -> None:
        self.started.append(job.job_id)
        self.active += 1
        await reporter.state(JobState.TRANSFERRING)
        await self.release.wait()
        await reporter.state(JobState.FINALIZING)
        self.active -= 1

    async def cancel(self, job: DownloadJob) -> None:
        self.release.set()


class AcquisitionPersistenceTests(unittest.TestCase):
    def test_romm_completion_refreshes_remote_and_local_catalogues(self) -> None:
        self.assertEqual(_completed_job_refresh_stages("romm"), ["romm", "local"])
        self.assertEqual(_completed_job_refresh_stages("steam"), ["steam"])
        self.assertEqual(_completed_job_refresh_stages("steam-aurelia"), ["steam"])
        self.assertEqual(_completed_job_refresh_stages("gog"), ["gog"])

    def test_timestamps_and_reconstruction(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = AcquisitionStore(Path(directory) / "acquisition.sqlite3")
            created = DownloadJob("one", "fake", "One", content_identity="fake:one").created_at
            self.assertTrue(created.endswith("Z"))
            terminal = DownloadJob(job_id="done", provider="fake", title="Done",
                                   content_identity="fake:done", state=JobState.COMPLETED,
                                   stage="completed", completed_at=created,
                                   created_at=created, updated_at=created)
            store.save_all([terminal])
            reopened = AcquisitionStore(Path(directory) / "acquisition.sqlite3")
            restored = {item.job_id: item for item in reopened.load()}
            self.assertEqual(restored["done"].state, JobState.COMPLETED)
            self.assertEqual(restored["done"].created_at, created)
            self.assertEqual(restored["done"].completed_at, created)
            self.assertEqual(restored["done"].recovery_reason, None)
            reopened.close()
            store.close()

    def test_questarr_origin_correlation_survives_job_store_restart(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "acquisition.sqlite3"
            store = AcquisitionStore(path)
            questarr = DownloadJob(
                "questarr-job", "usenet", "Safe NZB", content_identity="file:///safe.nzb",
                origin="questarr", origin_metadata={"transport": "usenet", "external_client_id": 17},
            )
            store.save_all([questarr])
            reopened = AcquisitionStore(path)
            restored = reopened.load()[0]
            self.assertEqual(restored.origin, "questarr")
            self.assertEqual(restored.origin_metadata,
                             {"transport": "usenet", "external_client_id": 17})
            reopened.close()
            store.close()

    def test_active_jobs_recover_as_queued_for_provider_reconciliation(self) -> None:
        async def exercise() -> None:
          with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "acquisition.sqlite3"
            store = AcquisitionStore(path)
            active = DownloadJob("active", "fake", "Active", content_identity="fake:active",
                                 state=JobState.TRANSFERRING, stage="transferring")
            queued = DownloadJob("queued", "fake", "Queued", content_identity="fake:queued")
            store.save_all([active, queued])
            reopened = AcquisitionStore(path)
            recovered = {job.job_id: job for job in reopened.load()}
            self.assertEqual(recovered["active"].state, JobState.QUEUED)
            self.assertIsNone(recovered["active"].error)
            self.assertEqual(recovered["active"].recovery_reason, "service-restart")
            self.assertEqual(recovered["queued"].state, JobState.QUEUED)
            reopened.close()
            executor = HoldingExecutor()
            manager = JobManager(store=AcquisitionStore(path))
            manager.register_executor("fake", executor)
            await asyncio.sleep(0)
            await asyncio.sleep(0)
            self.assertIn("active", executor.started)
            executor.release.set()
            await manager._tasks["active"]
            manager.store.close()
            store.close()
        asyncio.run(exercise())

    def test_retry_is_new_linked_attempt_and_duplicate_suppression_survives_recovery(self) -> None:
        async def exercise() -> None:
            with tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "acquisition.sqlite3"
                store = AcquisitionStore(path)
                failed = DownloadJob("failed", "fake", "Title", content_identity="fake:1",
                                     state=JobState.FAILED, stage="failed",
                                     error=JobError("transient", "temporary failure", retryable=True),
                                     completed_at="2026-01-01T00:00:00.000Z")
                store.save_all([failed])
                executor = HoldingExecutor()
                manager = JobManager(store=AcquisitionStore(path))
                manager.register_executor("fake", executor)
                retry = manager.retry("failed")
                duplicate = manager.submit("fake", "fake:1", "Title")
                self.assertEqual(retry.job_id, duplicate.job_id)
                self.assertEqual(retry.parent_job_id, "failed")
                self.assertEqual(retry.attempt, 2)
                executor.release.set()
                await manager._tasks[retry.job_id]
                store.close()
                manager.store.close()
        asyncio.run(exercise())

    def test_retired_failed_attempt_persists_without_retiring_retry(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "acquisition.sqlite3"
            store = AcquisitionStore(path)
            failed = DownloadJob("failed", "fake", "Title", content_identity="fake:1",
                                 state=JobState.FAILED, stage="failed", retired=True)
            retry = DownloadJob("retry", "fake", "Title", content_identity="fake:1",
                                parent_job_id="failed", attempt=2)
            store.save_all([failed, retry])
            restored = {job.job_id: job for job in AcquisitionStore(path).load()}
            self.assertTrue(restored["failed"].retired)
            self.assertFalse(restored["retry"].retired)
            self.assertEqual(restored["retry"].parent_job_id, "failed")

    def test_retention_and_corrupt_rows_fail_safe(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "acquisition.sqlite3"
            store = AcquisitionStore(path, history_limit=2)
            jobs = [DownloadJob(f"job-{i}", "fake", str(i), content_identity=f"fake:{i}",
                                state=JobState.COMPLETED, stage="completed",
                                completed_at=f"2026-01-01T00:00:0{i}.000Z") for i in range(3)]
            store.save_all(jobs)
            with sqlite3.connect(path) as connection:
                connection.execute("INSERT INTO acquisition_jobs (job_id, provider, content_identity, title, operation, state, progress, downloaded_bytes, total_bytes, stage, error_json, retryable, cancellation_supported, provider_job_id, created_at, started_at, updated_at, completed_at, attempt, parent_job_id, recovery_reason) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                                    ("bad", "fake", "bad", "bad", "not-an-operation", "queued", None, None, None,
                                    "queued", "{bad", 1, 0, None, "bad", None, "bad", "bad", 1, None, None))
            reopened = AcquisitionStore(path, history_limit=2)
            restored = reopened.load()
            self.assertEqual(len(restored), 2)
            self.assertNotIn("bad", {job.job_id for job in restored})
            reopened.close()

    def test_cross_provider_topology_and_event_snapshots(self) -> None:
        async def exercise() -> None:
            snapshots = []
            steam = HoldingExecutor()
            romm = HoldingExecutor()
            manager = JobManager(on_change=lambda jobs: snapshots.append(jobs))
            manager.register_executor("steam", steam, limit=1)
            manager.register_executor("romm", romm, limit=1)
            first = manager.submit("steam", "steam:a", "A")
            second = manager.submit("steam", "steam:b", "B")
            other = manager.submit("romm", "romm:a", "C")
            await asyncio.sleep(0)
            self.assertEqual(manager.active_download_count, 2)
            self.assertEqual(manager.jobs[second.job_id].state, JobState.QUEUED)
            self.assertEqual(manager.jobs[first.job_id].state, JobState.TRANSFERRING)
            self.assertEqual(manager.jobs[other.job_id].state, JobState.TRANSFERRING)
            steam.release.set()
            romm.release.set()
            first_task = manager._tasks[first.job_id]
            other_task = manager._tasks[other.job_id]
            await first_task
            await other_task
            await asyncio.sleep(0)
            self.assertIn(second.job_id, steam.started)
            await asyncio.sleep(0)
            self.assertEqual(manager.active_download_count, 0)
            self.assertTrue(any(any(job.job_id == first.job_id and job.state == JobState.COMPLETED
                                    for job in snapshot) for snapshot in snapshots))
        asyncio.run(exercise())


if __name__ == "__main__":
    unittest.main()
