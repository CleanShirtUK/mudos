import asyncio
from dataclasses import replace
from pathlib import Path
import tempfile
import unittest

from lulu.job_manager import JobCancelled, JobManager, JobReporter
from lulu.jobs import DownloadJob, JobError, JobOperation, JobState


class ControlledExecutor:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.started: list[str] = []
        self.release = asyncio.Event()
        self.cancelled = asyncio.Event()
        self.active = 0
        self.maximum_active = 0

    async def run(self, job: DownloadJob, reporter: JobReporter) -> None:
        self.started.append(job.job_id)
        self.active += 1
        self.maximum_active = max(self.maximum_active, self.active)
        try:
            await reporter.state(JobState.TRANSFERRING, stage="transferring")
            await reporter.progress(None, downloaded_bytes=5, total_bytes=10)
            if self.fail:
                raise RuntimeError("controlled failure")
            release = asyncio.create_task(self.release.wait())
            cancelled = asyncio.create_task(self.cancelled.wait())
            try:
                await asyncio.wait([release, cancelled], return_when=asyncio.FIRST_COMPLETED)
            finally:
                release.cancel()
                cancelled.cancel()
            if self.cancelled.is_set():
                raise JobCancelled
            await reporter.state(JobState.FINALIZING, stage="finalizing")
        finally:
            self.active -= 1

    async def cancel(self, job: DownloadJob) -> None:
        self.cancelled.set()


class ControlledExecutorWithPause(ControlledExecutor):
    supports_pause = True


class TerminalCancellationExecutor:
    async def run(self, job: DownloadJob, reporter: JobReporter) -> None:
        raise JobCancelled

    async def cancel(self, job: DownloadJob) -> None:
        return None


class JobDomainTests(unittest.TestCase):
    def test_provider_terminal_cancellation_does_not_leave_starting_job(self) -> None:
        async def exercise() -> None:
            manager = JobManager()
            manager.register_executor("fake", TerminalCancellationExecutor())
            job = manager.submit("fake", "fixture", "Fixture")
            await asyncio.sleep(0)
            result = manager.jobs[job.job_id]
            self.assertEqual(result.state, JobState.CANCELLED)
            self.assertIsNotNone(result.completed_at)

        asyncio.run(exercise())

    def test_provider_pause_capability_is_persisted_on_recovery(self) -> None:
        async def exercise() -> None:
            from lulu.acquisition_store import AcquisitionStore

            with tempfile.TemporaryDirectory() as directory:
                store = AcquisitionStore(Path(directory) / "jobs.sqlite")
                recovered = DownloadJob("job-1", "torrent", "Torrent",
                                        content_identity="magnet:1",
                                        cancellation_supported=True)
                store.save_all([recovered])
                manager = JobManager(store=store)
                manager.register_executor("torrent", ControlledExecutorWithPause())
                self.assertTrue(manager.jobs[recovered.job_id].pause_supported)
                store.close()

                reopened = AcquisitionStore(Path(directory) / "jobs.sqlite")
                persisted = {job.job_id: job for job in reopened.load()}[recovered.job_id]
                self.assertTrue(persisted.pause_supported)
                reopened.close()

        asyncio.run(exercise())
    def test_transition_and_validation(self) -> None:
        job = DownloadJob("job-1", "fake", "Title", content_identity="fake:1",
                          operation=JobOperation.INSTALL)
        for state in (JobState.STARTING, JobState.TRANSFERRING,
                      JobState.FINALIZING, JobState.COMPLETED):
            job = job.transition(state)
        self.assertEqual(job.state, JobState.COMPLETED)
        with self.assertRaises(ValueError):
            job.transition(JobState.FAILED)

    def test_nullable_progress_bytes_errors_and_retryability(self) -> None:
        job = DownloadJob("job-1", "fake", "Title")
        self.assertIsNone(job.progress)
        job = job.update_progress(None, downloaded_bytes=0, total_bytes=None)
        self.assertIsNone(job.progress)
        with self.assertRaises(ValueError):
            job.update_progress(0.5, downloaded_bytes=11, total_bytes=10)
        failed = job.transition(
            JobState.STARTING,
        ).transition(
            JobState.FAILED,
            error=JobError("io", "disk full", retryable=False),
        )
        self.assertFalse(failed.error.retryable)

    def test_manager_lifecycle_active_count_and_unknown_progress(self) -> None:
        async def exercise() -> None:
            executor = ControlledExecutor()
            manager = JobManager()
            manager.register_executor("fake", executor)
            job = manager.submit("fake", "fake:1", "Title", cancellation_supported=True)
            self.assertEqual(manager.active_download_count, 0)
            self.assertEqual(manager.actionable_download_count, 1)
            await asyncio.sleep(0)
            self.assertEqual(manager.active_download_count, 1)
            self.assertEqual(manager.actionable_download_count, 1)
            self.assertIsNone(manager.jobs[job.job_id].progress)
            self.assertEqual(manager.jobs[job.job_id].downloaded_bytes, 5)
            task = manager._tasks[job.job_id]
            executor.release.set()
            await task
            self.assertEqual(manager.active_download_count, 0)
            self.assertEqual(manager.jobs[job.job_id].state, JobState.COMPLETED)
            self.assertEqual(manager.jobs[job.job_id].progress, 1.0)
        asyncio.run(exercise())

    def test_actionable_count_includes_queued_and_paused_jobs(self) -> None:
        queued = DownloadJob("queued", "fake", "Queued")
        paused = DownloadJob("paused", "fake", "Paused").transition(
            JobState.STARTING).transition(JobState.PAUSED)
        completed = (DownloadJob("complete", "fake", "Complete")
                     .transition(JobState.STARTING)
                     .transition(JobState.TRANSFERRING)
                     .transition(JobState.FINALIZING)
                     .transition(JobState.COMPLETED))
        manager = JobManager()
        manager.jobs = {job.job_id: job for job in (queued, paused, completed)}
        self.assertEqual(manager.actionable_download_count, 2)
        self.assertEqual(manager.active_download_count, 0)

    def test_cancellation_is_visible_but_not_active(self) -> None:
        async def exercise() -> None:
            executor = ControlledExecutor()
            manager = JobManager()
            manager.register_executor("fake", executor)
            job = manager.submit("fake", "fake:1", "Title", cancellation_supported=True)
            await asyncio.sleep(0)
            cancel = asyncio.create_task(manager.cancel(job.job_id))
            await cancel
            self.assertEqual(manager.jobs[job.job_id].state, JobState.CANCELLED)
            self.assertEqual(manager.active_download_count, 0)
        asyncio.run(exercise())

    def test_paused_provider_cancel_is_immediate_and_not_failure(self) -> None:
        async def exercise() -> None:
            executor = ControlledExecutor()
            manager = JobManager()
            manager.register_executor("romm", executor)
            job = manager.submit("romm", "romm:1", "ROM", cancellation_supported=True,
                                 pause_supported=True)
            await asyncio.sleep(0)
            await manager.pause(job.job_id)
            self.assertEqual(manager.jobs[job.job_id].state, JobState.PAUSED)
            cancelled = await manager.cancel(job.job_id)
            self.assertEqual(cancelled.state, JobState.CANCELLED)
            self.assertTrue(cancelled.retired)
            self.assertNotEqual(cancelled.state, JobState.FAILED)
            self.assertFalse(manager.jobs[job.job_id].pause_supported is False)
            self.assertEqual(await manager.cancel(job.job_id), cancelled)
        asyncio.run(exercise())

    def test_unsupported_pause_does_not_mutate_job(self) -> None:
        async def exercise() -> None:
            executor = ControlledExecutor()
            manager = JobManager()
            manager.register_executor("steam", executor)
            job = manager.submit("steam", "steam:1", "Steam", cancellation_supported=True)
            await asyncio.sleep(0)
            result = await manager.pause(job.job_id)
            self.assertEqual(result.state, JobState.TRANSFERRING)
            self.assertFalse(result.pause_supported)
            await manager.cancel(job.job_id)
        asyncio.run(exercise())

    def test_failure_is_normalized(self) -> None:
        async def exercise() -> None:
            executor = ControlledExecutor(fail=True)
            manager = JobManager()
            manager.register_executor("fake", executor)
            job = manager.submit("fake", "fake:1", "Title")
            task = manager._tasks[job.job_id]
            await task
            result = manager.jobs[job.job_id]
            self.assertEqual(result.state, JobState.FAILED)
            self.assertEqual(result.error.code, "provider-failure")
        asyncio.run(exercise())

    def test_non_retryable_failure_requires_correction(self) -> None:
        manager = JobManager()
        failed = DownloadJob("failed", "fake", "Title", state=JobState.FAILED,
                             error=JobError("unsupported-platform", "No platform mapping"))
        manager.jobs[failed.job_id] = failed
        with self.assertRaisesRegex(ValueError, "corrective action"):
            manager.retry(failed.job_id)
        self.assertEqual(len(manager.jobs), 1)
        manager.jobs[failed.job_id] = replace(failed, retryable=False,
            error=JobError("temporary", "Temporary failure", retryable=True))
        with self.assertRaisesRegex(ValueError, "corrective action"):
            manager.retry(failed.job_id)
        self.assertEqual(len(manager.jobs), 1)

    def test_retire_only_failed_jobs_is_idempotent_and_preserves_retry_lineage(self) -> None:
        async def exercise() -> None:
            executor = ControlledExecutor()
            manager = JobManager()
            manager.register_executor("fake", executor)
            failed = DownloadJob("failed", "fake", "Title", content_identity="fake:1",
                                 state=JobState.FAILED, stage="failed")
            manager.jobs[failed.job_id] = failed
            retry = manager.retry(failed.job_id)
            self.assertFalse(manager.jobs[failed.job_id].retired)
            retired = manager.retire(failed.job_id)
            self.assertTrue(retired.retired)
            self.assertEqual(manager.jobs[retry.job_id].parent_job_id, failed.job_id)
            self.assertTrue(manager.retire(failed.job_id).retired)
            with self.assertRaises(ValueError):
                manager.retire(retry.job_id)
            executor.release.set()
            await manager._tasks[retry.job_id]
        asyncio.run(exercise())

    def test_duplicate_active_content_identity_returns_existing_job(self) -> None:
        async def exercise() -> None:
            executor = ControlledExecutor()
            manager = JobManager()
            manager.register_executor("steam", executor)
            first = manager.submit("steam", "steam:40800", "Super Meat Boy")
            await asyncio.sleep(0)
            duplicate = manager.submit("steam", "steam:40800", "Super Meat Boy")
            self.assertEqual(duplicate.job_id, first.job_id)
            self.assertEqual(len(manager.jobs), 1)
            executor.release.set()
            await manager._tasks[first.job_id]
        asyncio.run(exercise())

    def test_provider_limits_and_cross_provider_concurrency(self) -> None:
        async def exercise() -> None:
            first = ControlledExecutor()
            second = ControlledExecutor()
            manager = JobManager()
            manager.register_executor("one", first, limit=1)
            manager.register_executor("two", second, limit=1)
            one_a = manager.submit("one", "one:a", "A")
            one_b = manager.submit("one", "one:b", "B")
            two_a = manager.submit("two", "two:a", "C")
            await asyncio.sleep(0)
            self.assertEqual(first.maximum_active, 1)
            self.assertEqual(second.maximum_active, 1)
            self.assertNotIn(one_b.job_id, first.started)
            one_a_task = manager._tasks[one_a.job_id]
            two_a_task = manager._tasks[two_a.job_id]
            first.release.set()
            second.release.set()
            await one_a_task
            await two_a_task
            await asyncio.sleep(0)
            self.assertIn(one_b.job_id, first.started)
            one_b_task = manager._tasks[one_b.job_id]
            first.release.set()
            await one_b_task
        asyncio.run(exercise())

    def test_snapshots_publish_and_consumer_disconnect_does_not_cancel(self) -> None:
        async def exercise() -> None:
            snapshots: list[tuple[DownloadJob, ...]] = []
            executor = ControlledExecutor()
            manager = JobManager(on_change=snapshots.append)
            manager.register_executor("fake", executor)
            job = manager.submit("fake", "fake:1", "Title")
            await asyncio.sleep(0)
            self.assertTrue(any(item[0].state is JobState.STARTING
                                for item in snapshots if item))
            manager._on_change = None
            executor.release.set()
            task = manager._tasks[job.job_id]
            await task
            self.assertEqual(manager.jobs[job.job_id].state, JobState.COMPLETED)
        asyncio.run(exercise())


if __name__ == "__main__":
    unittest.main()
