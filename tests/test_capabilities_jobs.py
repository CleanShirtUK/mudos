import unittest

from lulu.capabilities import Capability, LOCAL_EMULATION_CAPABILITIES, STEAM_CAPABILITIES
from lulu.jobs import DownloadJob, JobState


class CapabilitiesJobsTests(unittest.TestCase):
    def test_providers_do_not_share_unsupported_operations(self) -> None:
        self.assertTrue(STEAM_CAPABILITIES.supports(Capability.OWNERSHIP))
        self.assertFalse(LOCAL_EMULATION_CAPABILITIES.supports(Capability.CHECKOUT_HANDOFF))
        self.assertFalse(LOCAL_EMULATION_CAPABILITIES.supports(Capability.DOWNLOAD_PROGRESS))

    def test_job_lifecycle_supports_pause_failure_and_restart(self) -> None:
        job = DownloadJob("job-1", "steam", "Example")
        job = job.transition(JobState.RUNNING, progress=0.1)
        job = job.transition(JobState.PAUSED, progress=0.4)
        job = job.transition(JobState.RUNNING, progress=0.4)
        job = job.transition(JobState.FAILED, error="network unavailable")
        job = job.transition(JobState.QUEUED)
        self.assertEqual(job.state, JobState.QUEUED)
        with self.assertRaises(ValueError):
            job.transition(JobState.COMPLETED)


if __name__ == "__main__":
    unittest.main()
