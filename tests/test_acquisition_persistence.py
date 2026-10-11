import asyncio
import sqlite3
import tempfile
import unittest
from pathlib import Path

from lulu.acquisition_store import AcquisitionStore, reconcile_orphaned_remove
from lulu.acquisitiond import _completed_job_refresh_stages
from lulu.job_manager import JobManager, JobReporter
from lulu.jobs import DownloadJob, JobError, JobOperation, JobState


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

    def test_provider_owned_origin_correlation_survives_job_store_restart(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "acquisition.sqlite3"
            store = AcquisitionStore(path)
            acquired = DownloadJob(
                "acquired-job", "usenet", "Safe NZB", content_identity="file:///safe.nzb",
                origin="mudos", origin_metadata={"transport": "usenet", "external_client_id": 17},
            )
            store.save_all([acquired])
            reopened = AcquisitionStore(path)
            restored = reopened.load()[0]
            self.assertEqual(restored.origin, "mudos")
            self.assertEqual(restored.origin_metadata,
                             {"transport": "usenet", "external_client_id": 17})
            reopened.close()
            store.close()

    def test_legacy_provider_origin_migrates_to_generic_owned_origin(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "acquisition.sqlite3"
            store = AcquisitionStore(path)
            store.save_all([DownloadJob("legacy", "usenet", "Payload",
                                        content_identity="file:///completed/payload.nzb")])
            store._connection.execute(
                "UPDATE acquisition_jobs SET origin = ? WHERE job_id = ?",
                ("questarr", "legacy"))
            store._connection.commit()
            reopened = AcquisitionStore(path)
            restored = reopened.load()[0]
            self.assertEqual(restored.origin, "mudos")
            self.assertEqual(restored.content_identity, "file:///completed/payload.nzb")
            reopened.close()
            store.close()

    def test_active_jobs_recover_as_queued_for_provider_reconciliation(self) -> None:
        async def exercise() -> None:
          with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "acquisition.sqlite3"
            store = AcquisitionStore(path)
            active = DownloadJob("active", "fake", "Active", content_identity="fake:active",
                                 state=JobState.TRANSFERRING, stage="transferring")
            update = DownloadJob("update", "fake", "Update", content_identity="fake:update",
                                 operation=JobOperation.UPDATE, state=JobState.TRANSFERRING,
                                 stage="updating")
            queued = DownloadJob("queued", "fake", "Queued", content_identity="fake:queued")
            store.save_all([active, update, queued])
            reopened = AcquisitionStore(path)
            recovered = {job.job_id: job for job in reopened.load()}
            self.assertEqual(recovered["active"].state, JobState.QUEUED)
            self.assertIsNone(recovered["active"].error)
            self.assertEqual(recovered["active"].recovery_reason, "service-restart")
            self.assertEqual(recovered["update"].state, JobState.QUEUED)
            self.assertEqual(recovered["update"].recovery_reason, "service-restart")
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

    def test_interrupted_removal_fails_closed_and_is_not_scheduled_after_restart(self) -> None:
        async def exercise() -> None:
            with tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "acquisition.sqlite3"
                store = AcquisitionStore(path)
                remove = DownloadJob(
                    "remove", "fake-provider", "Title", content_identity="provider:42",
                    provider_job_id="42", operation=JobOperation.REMOVE,
                    state=JobState.TRANSFERRING, stage="provider-removing",
                    completed_at="2026-01-01T00:00:01.000Z", updated_at="2026-01-01T00:00:02.000Z",
                    provider_state="removing", origin_metadata={"retained": True},
                )
                acquire = DownloadJob("acquire", "fake-provider", "Other", content_identity="provider:other",
                                      state=JobState.TRANSFERRING)
                store.save_all([remove, acquire])
                store.close()

                reopened = AcquisitionStore(path)
                jobs = {job.job_id: job for job in reopened.load()}
                failed = jobs["remove"]
                self.assertEqual(failed.state, JobState.FAILED)
                self.assertEqual(failed.error.code, "orphaned-removal-incomplete")
                self.assertFalse(failed.retryable)
                self.assertFalse(failed.error.retryable)
                self.assertEqual(failed.completed_at, "2026-01-01T00:00:01.000Z")
                self.assertEqual(failed.error.details["original_state"], "transferring")
                self.assertEqual(failed.error.details["original_stage"], "provider-removing")
                self.assertEqual(failed.error.details["original_origin_metadata"], {"retained": True})
                self.assertEqual(jobs["acquire"].state, JobState.QUEUED)

                class NeverRun:
                    def __init__(self):
                        self.started = []

                    async def run(self, job, reporter):
                        self.started.append(job.job_id)

                executor = NeverRun()
                manager = JobManager(store=reopened)
                manager.register_executor("fake-provider", executor)
                await asyncio.sleep(0)
                self.assertNotIn("remove", executor.started)
                self.assertIn("acquire", executor.started)
                with self.assertRaisesRegex(ValueError, "corrective action"):
                    manager.retry("remove")
                executor_started = list(executor.started)
                self.assertEqual(executor_started.count("remove"), 0)
                reopened.close()

        asyncio.run(exercise())

    def test_offline_orphan_reconciliation_is_exact_backed_up_and_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "acquisition.sqlite3"
            backup_path = Path(directory) / "maintenance" / "acquisition-before.sqlite3"
            store = AcquisitionStore(path)
            target = DownloadJob(
                "target", "steam-aurelia", "Rocket League", content_identity="steam-aurelia:252950",
                provider_job_id="252950", operation=JobOperation.REMOVE,
                state=JobState.TRANSFERRING, stage="Downloading depot 252951",
                progress=0.001, downloaded_bytes=37668642, total_bytes=43680602059,
                completed_at="2026-10-11T07:46:26.837Z", updated_at="2026-10-11T07:47:13.218Z",
            )
            other = DownloadJob("other", "fake", "Other", content_identity="fake:other")
            store.save_all([target, other])
            raw = store._connection.execute(
                "SELECT * FROM acquisition_jobs WHERE job_id='target'").fetchone()
            names = [column[1] for column in store._connection.execute("PRAGMA table_info(acquisition_jobs)")]
            original = dict(zip(names, raw))
            expected = {key: original[key] for key in (
                "job_id", "provider", "provider_job_id", "content_identity", "operation",
                "state", "updated_at", "completed_at", "stage", "progress",
                "downloaded_bytes", "total_bytes",
            )}
            store.close()
            result = reconcile_orphaned_remove(
                path, backup_path, expected=expected,
                diagnostic={"provider_installed": False, "residual_files_present": True},
            )
            self.assertTrue(backup_path.exists())
            self.assertEqual(backup_path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(sqlite3.connect(backup_path).execute("PRAGMA integrity_check").fetchone(), ("ok",))
            self.assertEqual(len(result["backup_sha256"]), 64)
            with sqlite3.connect(path) as connection:
                row = connection.execute("SELECT state, stage, retryable, error_json, completed_at FROM acquisition_jobs WHERE job_id='target'").fetchone()
                unrelated = connection.execute("SELECT state FROM acquisition_jobs WHERE job_id='other'").fetchone()
            self.assertEqual(row[0:3], ("failed", "orphaned-removal-incomplete", 0))
            self.assertEqual(row[4], expected["completed_at"])
            error = __import__("json").loads(row[3])
            self.assertEqual(error["code"], "orphaned-removal-incomplete")
            self.assertFalse(error["retryable"])
            self.assertEqual(error["details"]["original_record"]["state"], "transferring")
            self.assertEqual(unrelated, ("queued",))
            reopened = {job.job_id: job for job in AcquisitionStore(path).load()}
            self.assertEqual(reopened["target"].state, JobState.FAILED)
            self.assertFalse(reopened["target"].retryable)
            self.assertEqual(reopened["target"].error.code, "orphaned-removal-incomplete")
            with self.assertRaisesRegex(ValueError, "must not already exist"):
                reconcile_orphaned_remove(path, backup_path, expected=expected, diagnostic={})

    def test_offline_reconciliation_rejects_mismatch_or_backup_failure_without_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "acquisition.sqlite3"
            store = AcquisitionStore(path)
            target = DownloadJob("target", "steam-aurelia", "Rocket League",
                                 content_identity="steam-aurelia:252950", provider_job_id="252950",
                                 operation=JobOperation.REMOVE, state=JobState.TRANSFERRING,
                                 completed_at="2026-01-01T00:00:00Z")
            store.save_all([target])
            raw = store._connection.execute("SELECT * FROM acquisition_jobs WHERE job_id='target'").fetchone()
            names = [column[1] for column in store._connection.execute("PRAGMA table_info(acquisition_jobs)")]
            expected = dict(zip(names, raw))
            store.close()
            mismatch = dict(expected, provider_job_id="wrong")
            with self.assertRaisesRegex(ValueError, "mismatch for provider_job_id"):
                reconcile_orphaned_remove(path, Path(directory) / "bad-backup.db",
                                          expected=mismatch, diagnostic={})
            import lulu.acquisition_store as acquisition_store
            real_connect = sqlite3.connect
            def fail_backup_connect(target_path, *args, **kwargs):
                if Path(target_path) == path:
                    return real_connect(target_path, *args, **kwargs)
                raise sqlite3.OperationalError("injected backup failure")
            from unittest.mock import patch
            with patch.object(acquisition_store.sqlite3, "connect", side_effect=fail_backup_connect):
                with self.assertRaisesRegex(sqlite3.OperationalError, "injected backup failure"):
                    reconcile_orphaned_remove(path, Path(directory) / "failed-backup.db",
                                              expected=expected, diagnostic={})
            with sqlite3.connect(path) as connection:
                self.assertEqual(connection.execute("SELECT state FROM acquisition_jobs WHERE job_id='target'").fetchone(),
                                 ("transferring",))

    def test_offline_reconciliation_rejects_unexpected_identity_operation_or_state(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "acquisition.sqlite3"
            store = AcquisitionStore(path)
            store.save_all([DownloadJob(
                "target", "steam-aurelia", "Rocket League", content_identity="steam-aurelia:252950",
                provider_job_id="252950", operation=JobOperation.REMOVE,
                state=JobState.TRANSFERRING, completed_at="2026-01-01T00:00:00Z")])
            raw = store._connection.execute("SELECT * FROM acquisition_jobs WHERE job_id='target'").fetchone()
            names = [column[1] for column in store._connection.execute("PRAGMA table_info(acquisition_jobs)")]
            expected = dict(zip(names, raw))
            store.close()
            for index, change in enumerate((
                    {"job_id": "wrong-id"}, {"content_identity": "steam-aurelia:7"},
                    {"operation": "acquire"}, {"state": "queued"})):
                with self.subTest(change=change):
                    with self.assertRaises(ValueError):
                        reconcile_orphaned_remove(
                            path, Path(directory) / f"mismatch-{index}.db",
                            expected=dict(expected, **change), diagnostic={})
                    with sqlite3.connect(path) as connection:
                        self.assertEqual(connection.execute(
                            "SELECT state FROM acquisition_jobs WHERE job_id='target'").fetchone(),
                            ("transferring",))

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

    def test_concurrent_same_app_acquire_and_remove_are_rejected(self) -> None:
        async def exercise() -> None:
            manager = JobManager()
            executor = HoldingExecutor()
            manager.register_executor("steam-aurelia", executor)
            acquired = manager.submit("steam-aurelia", "steam-aurelia:252950", "Rocket League")
            with self.assertRaisesRegex(ValueError, "active conflicting operation"):
                manager.submit("steam-aurelia", "steam-aurelia:252950", "Rocket League",
                               operation=JobOperation.REMOVE, provider_job_id="252950")
            self.assertEqual(len(manager.jobs), 1)
            executor.release.set()
            await manager._tasks[acquired.job_id]
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
