import asyncio
from io import BytesIO
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from lulu.job_manager import JobManager
from lulu.jobs import JobState
from lulu.romm import RommFile, RommGame
from lulu.romm_executor import RommExecutor


class FakeRomm:
    def __init__(self, payload: bytes, *, total: int | None = None) -> None:
        self.payload = payload
        self.total = total
        self.game = RommGame(7, "Test Kart", 1, "nes", "NES", "test.nes", ".nes",
                             len(payload), "", False, (RommFile(70, "test.nes", len(payload)),))

    def list_games(self):
        return [self.game]

    def open_file_stream(self, romm_file):
        class Stream(BytesIO):
            pass
        stream = Stream(self.payload)
        if self.total is not None:
            stream.headers = {"Content-Length": str(self.total)}
        return stream


class RommExecutorTests(unittest.TestCase):
    def test_streams_to_canonical_staging_path_and_completes(self) -> None:
        async def exercise() -> None:
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                fake = FakeRomm(b"123456", total=6)
                executor = RommExecutor(fake, chunk_size=2)
                manager = JobManager()
                manager.register_executor("romm", executor, limit=1)
                with patch("lulu.romm_executor.ROM_ROOT", root):
                    job = manager.submit("romm", "romm:7", "Test Kart")
                    await manager._tasks[job.job_id]
                result = manager.jobs[job.job_id]
                self.assertEqual(result.state, JobState.COMPLETED)
                self.assertEqual(result.progress, 1.0)
                self.assertEqual((root / "nes/test.nes").read_bytes(), b"123456")
                self.assertFalse(list((root / "nes").glob("*.part")))

        asyncio.run(exercise())

    def test_unknown_length_does_not_fabricate_progress(self) -> None:
        async def exercise() -> None:
            with tempfile.TemporaryDirectory() as directory:
                fake = FakeRomm(b"1234")
                executor = RommExecutor(fake, chunk_size=2)
                manager = JobManager()
                manager.register_executor("romm", executor, limit=1)
                with patch("lulu.romm_executor.ROM_ROOT", Path(directory)):
                    job = manager.submit("romm", "romm:7", "Test Kart")
                    await manager._tasks[job.job_id]
                self.assertEqual(manager.jobs[job.job_id].state, JobState.COMPLETED)
                self.assertEqual(manager.jobs[job.job_id].progress, 1.0)

        asyncio.run(exercise())

    def test_unsupported_platform_fails_without_creating_content(self) -> None:
        async def exercise() -> None:
            with tempfile.TemporaryDirectory() as directory:
                fake = FakeRomm(b"rom")
                fake.game = RommGame(7, "Unsupported", 99, "arcade", "Arcade", "test.zip", ".zip", 3, "", False,
                                     (RommFile(70, "test.zip", 3),))
                executor = RommExecutor(fake)
                manager = JobManager()
                manager.register_executor("romm", executor)
                with patch("lulu.romm_executor.ROM_ROOT", Path(directory)):
                    job = manager.submit("romm", "romm:7", "Unsupported")
                    await manager._tasks[job.job_id]
                result = manager.jobs[job.job_id]
                self.assertEqual(result.state, JobState.FAILED)
                self.assertEqual(result.error.code, "unsupported-platform")
                self.assertEqual(list(Path(directory).rglob("*")), [])

        asyncio.run(exercise())


if __name__ == "__main__":
    unittest.main()
