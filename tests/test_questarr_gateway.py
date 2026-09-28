import asyncio
import base64
import tempfile
import threading
import unittest
from pathlib import Path
from http.server import ThreadingHTTPServer
from xmlrpc.client import Fault, ServerProxy

from lulu.acquisition_store import AcquisitionStore
from lulu.job_manager import JobManager
from lulu.jobs import JobError, JobState
from lulu.questarr_gateway import QuestarrGateway, make_handler


class HeldExecutor:
    supports_pause = True

    async def run(self, _job, _reporter):
        await _reporter.state(JobState.TRANSFERRING)
        await asyncio.Event().wait()

    async def cancel(self, _job):
        return None


class QuestarrGatewayTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        root = Path(self.temporary.name)
        self.loop = asyncio.new_event_loop()
        self.thread = threading.Thread(target=self.loop.run_forever, daemon=True)
        self.thread.start()
        async def initialize():
            self.store = AcquisitionStore(root / "acquisition.sqlite3")
            self.manager = JobManager(store=self.store)
            self.manager.register_executor("usenet", HeldExecutor())
        asyncio.run_coroutine_threadsafe(initialize(), self.loop).result(timeout=2)
        self.gateway = QuestarrGateway(self.manager, self.loop,
                                       database=root / "gateway.sqlite3",
                                       nzb_root=root / "usenet")
        self._start_http()

    def _start_http(self):
        self.http = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(self.gateway))
        self.http_thread = threading.Thread(target=self.http.serve_forever, daemon=True)
        self.http_thread.start()
        self.rpc = ServerProxy(f"http://127.0.0.1:{self.http.server_port}/xmlrpc")

    def _restart_http(self):
        self.http.shutdown()
        self.http.server_close()
        self.http_thread.join(timeout=2)
        self._start_http()

    def tearDown(self):
        self.http.shutdown()
        self.http.server_close()
        self.http_thread.join(timeout=2)
        self.gateway.close()
        async def shutdown():
            self.store.close()
            current = asyncio.current_task()
            pending = [task for task in asyncio.all_tasks() if task is not current]
            for task in pending:
                task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)
        asyncio.run_coroutine_threadsafe(shutdown(), self.loop).result(timeout=2)
        self.loop.call_soon_threadsafe(self.loop.stop)
        self.thread.join(timeout=2)
        self.loop.close()
        self.temporary.cleanup()

    def submit(self, title="Safe fixture", content=b"<?xml version='1.0'?><nzb></nzb>"):
        return self.rpc.append(title, base64.b64encode(content).decode(), "questarr")

    def test_version_connectivity_and_submission_are_acquisitiond_owned(self):
        self.assertIn("mudos-gateway", self.rpc.version())
        client_id = self.submit()
        jobs = self.gateway._jobs()
        self.assertEqual(len(jobs), 1)
        job = jobs[0]
        self.assertEqual(job.origin, "questarr")
        self.assertEqual(job.origin_metadata["transport"], "usenet")
        self.assertEqual(job.origin_metadata["external_client_id"], client_id)
        self.assertTrue(Path(job.content_identity.removeprefix("file://")).is_file())
        self.assertEqual(self.rpc.listgroups()[0]["NZBID"], client_id)
        self.assertIn(self.gateway._state(job), {"QUEUED", "DOWNLOADING"})

    def test_duplicate_submission_and_gateway_restart_reuse_stable_mapping(self):
        client_id = self.submit()
        job_id = self.gateway._jobs()[0].job_id
        database, nzb_root = self.gateway.database, self.gateway.nzb_root
        self.gateway.close()
        self.gateway = QuestarrGateway(self.manager, self.loop, database=database, nzb_root=nzb_root)
        self._restart_http()
        self.assertEqual(self.submit(), client_id)
        self.assertEqual(len(self.gateway._jobs()), 1)
        self.assertEqual(self.gateway._jobs()[0].job_id, job_id)

    def test_acquisitiond_restart_keeps_external_id_correlated_to_recovered_job(self):
        client_id = self.submit()
        job_id = self.gateway._jobs()[0].job_id
        database, nzb_root = self.gateway.database, self.gateway.nzb_root
        acquisition_path = Path(self.temporary.name) / "acquisition.sqlite3"
        self.gateway.close()

        async def restart_manager():
            await self.manager.cancel(job_id)
            self.store.close()
            self.store = AcquisitionStore(acquisition_path)
            self.manager = JobManager(store=self.store)
            self.manager.register_executor("usenet", HeldExecutor())
        asyncio.run_coroutine_threadsafe(restart_manager(), self.loop).result(timeout=2)
        self.gateway = QuestarrGateway(self.manager, self.loop, database=database, nzb_root=nzb_root)
        self._restart_http()
        self.assertEqual(self.submit(), client_id)
        restored = self.gateway._jobs()
        self.assertEqual(len(restored), 1)
        self.assertEqual(restored[0].job_id, job_id)

    def test_remove_cancels_the_authoritative_job_and_history_reflects_it(self):
        client_id = self.submit()
        self.rpc.editqueue("GroupDelete", 0, "", [client_id])
        job, _ = self.gateway._job_row(client_id)
        self.assertEqual(job.state.value, "cancelled")
        self.assertEqual(self.rpc.listgroups(), [])
        self.assertEqual(self.rpc.history()[0]["Status"], "DELETED")

    def test_progress_and_failure_are_projected_from_the_same_mudos_job(self):
        client_id = self.submit()
        job_id = self.gateway._jobs()[0].job_id
        async def update():
            self.manager.update_progress(job_id, 0.25, downloaded_bytes=25, total_bytes=100)
        asyncio.run_coroutine_threadsafe(update(), self.loop).result(timeout=2)
        queue = self.rpc.listgroups()
        self.assertEqual(queue[0]["NZBID"], client_id)
        self.assertEqual(queue[0]["DownloadedSizeMB"] * 1048576, 25)
        async def fail():
            self.manager.transition(job_id, JobState.FAILED,
                                    error=JobError("test-provider-failure", "safe test failure"))
        asyncio.run_coroutine_threadsafe(fail(), self.loop).result(timeout=2)
        self.assertEqual(self.rpc.history()[0]["Status"], "FAILURE")

    def test_invalid_nzb_and_unsupported_rpc_are_rejected(self):
        with self.assertRaises(Exception):
            self.submit(content=b"not an nzb")
        with self.assertRaises(Fault):
            self.rpc.arbitraryMethod()
        self.assertEqual(self.gateway._jobs(), ())

    def test_missing_compatible_executor_is_not_reported_as_accepted(self):
        async def without_executor():
            return JobManager()
        manager = asyncio.run_coroutine_threadsafe(without_executor(), self.loop).result(timeout=2)
        gateway = QuestarrGateway(manager, self.loop,
                                  database=Path(self.temporary.name) / "unavailable.sqlite3",
                                  nzb_root=Path(self.temporary.name) / "unavailable-nzb")
        try:
            with self.assertRaises(Fault) as caught:
                gateway.call("append", ("Safe fixture", base64.b64encode(
                    b"<?xml version='1.0'?><nzb></nzb>").decode(), "questarr"))
            self.assertIn("no executor registered for provider: usenet", str(caught.exception))
            self.assertEqual(manager.snapshot(), ())
        finally:
            gateway.close()


if __name__ == "__main__":
    unittest.main()
