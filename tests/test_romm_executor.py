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
    def test_saved_romm_configuration_is_observed_without_service_restart(self) -> None:
        from lulu.plugins.romm.client import RommConfig

        async def exercise() -> None:
            with tempfile.TemporaryDirectory() as directory:
                config = RommConfig("https://romm.example.invalid", "opaque-test-token")
                fake = FakeRomm(b"saved-setup")
                executor = RommExecutor(None, chunk_size=4)
                manager = JobManager()
                manager.register_executor("romm", executor)
                with patch.dict("os.environ", {"LULU_ROM_ROOT": directory}), \
                        patch("lulu.plugins.romm.executor.RommConfig.from_file", return_value=config), \
                        patch("lulu.plugins.romm.client.RommClient.list_games",
                              return_value=fake.list_games()), \
                        patch("lulu.plugins.romm.client.RommClient.open_file_stream",
                              side_effect=lambda romm_file, offset=0: fake.open_file_stream(romm_file)), \
                        patch("lulu.plugins.romm.executor.ensure_storage"):
                    job = manager.submit("romm", "romm:7", "Test Kart")
                    await manager._tasks[job.job_id]
                self.assertEqual(manager.jobs[job.job_id].state, JobState.COMPLETED,
                                 manager.jobs[job.job_id].error)
                self.assertEqual((Path(directory) / "nes/test.nes").read_bytes(), b"saved-setup")

        asyncio.run(exercise())

    def test_gba_romm_platform_resolves_to_retroarch_content_root(self) -> None:
        game = RommGame(145, "Apotris", 7, "gba", "Game Boy Advance", "Apotris.gba", ".gba",
                        1, "", False, (RommFile(1450, "Apotris.gba", 1),))
        destination = RommExecutor._destination(game, game.files[0])
        self.assertEqual(destination.name, "Apotris.gba")
        self.assertEqual(destination.parent.name, "gba")

    def test_romm_ngc_alias_resolves_to_canonical_gamecube_runtime(self) -> None:
        game = RommGame(145, "GameCube title", 21, "ngc", "Nintendo GameCube", "title.iso", ".iso",
                        1, "", False, (RommFile(1450, "title.iso", 1),))
        destination = RommExecutor._destination(game, game.files[0])
        self.assertEqual(destination.parent.name, "gamecube")

    def test_content_set_keeps_one_parent_lifecycle_across_components(self) -> None:
        async def exercise() -> None:
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                fake = FakeRomm(b"base")
                fake.game = RommGame(
                    7, "Test Kart", 1, "nes", "NES", "base.nes", ".nes", 4, "", False,
                    (RommFile(70, "base.nes", 4, "game"),
                     RommFile(71, "update.nes", 4, "update")),
                )
                executor = RommExecutor(fake, chunk_size=2)
                manager = JobManager()
                manager.register_executor("romm", executor, limit=1)
                with patch("lulu.romm_executor.ROM_ROOT", root):
                    job = manager.submit("romm", "romm-set:7", "Test Kart")
                    await manager._tasks[job.job_id]
                result = manager.jobs[job.job_id]
                self.assertEqual(result.state, JobState.COMPLETED)
                self.assertEqual(result.progress, 1.0)
                self.assertEqual((root / "nes/base.nes").read_bytes(), b"base")
                self.assertEqual((root / "nes/update.nes").read_bytes(), b"base")

        asyncio.run(exercise())

    def test_romm_pause_uses_staging_task_lifecycle(self) -> None:
        self.assertTrue(RommExecutor(None).supports_pause)

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
                fake.game = RommGame(7, "Unsupported", 99, "unsupported", "Unsupported", "test.zip", ".zip", 3, "", False,
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
