import asyncio
import unittest

from lulu.job_manager import JobManager
from lulu.jobs import DownloadJob, JobState


class FailingProvider:
    provider_id = "torrent"
    supports_pause = True

    async def resume(self, _hash):
        raise RuntimeError("RPC unavailable")


class TransmissionRecoveryTests(unittest.TestCase):
    def test_resume_provider_outage_returns_to_paused_not_failed(self):
        async def exercise():
            manager = JobManager()
            manager.register_executor("torrent", FailingProvider())
            job = DownloadJob(job_id="job-fixture", provider="torrent", title="fixture",
                              content_identity="transmission:abc", state=JobState.PAUSED,
                              stage="paused", pause_supported=True, provider_job_id="abc")
            manager.jobs[job.job_id] = job
            await manager.resume(job.job_id)
            self.assertEqual(manager.jobs[job.job_id].state, JobState.PAUSED)
            self.assertEqual(manager.jobs[job.job_id].error.code, "resume-failed")

        asyncio.run(exercise())


if __name__ == "__main__":
    unittest.main()
