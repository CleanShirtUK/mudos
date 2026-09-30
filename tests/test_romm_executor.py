import asyncio
from io import BytesIO
import zipfile
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
    def test_romm_library_missing_file_is_a_nonretryable_content_error(self) -> None:
        client = FakeRomm(b"payload")
        client.game = RommGame(243, "Missing fixture", 1, "switch", "Switch", "missing.nsp",
                              ".nsp", 7, "", True,
                              (RommFile(717, "missing.nsp", 7, rom_id=243),))
        with self.assertRaises(Exception) as caught:
            RommExecutor(client)._resolve("romm:243")
        self.assertEqual(caught.exception.code, "romm-content-missing")
        self.assertFalse(caught.exception.retryable)
        self.assertIn("missing from storage", str(caught.exception))

    def test_romm_download_404_is_not_reported_as_provider_unavailable(self) -> None:
        from lulu.romm import RommApiError

        class MissingContent(FakeRomm):
            def open_file_stream(self, _romm_file, offset=0):
                raise RommApiError(
                    "RomM returned HTTP 404 for /roms/7/content/test.nes?file_ids=70"
                )

        async def exercise() -> None:
            client = MissingContent(b"payload")
            client.game = RommGame(7, "Test Kart", 1, "nes", "NES", "test.nes", ".nes",
                                  7, "", False, (RommFile(70, "test.nes", 7, rom_id=7),))
            manager = JobManager()
            manager.register_executor("romm", RommExecutor(client))
            job = manager.submit("romm", "romm:7", "Test Kart")
            with tempfile.TemporaryDirectory() as directory, \
                    patch.dict("os.environ", {"LULU_ROM_ROOT": directory}), \
                    patch("lulu.plugins.romm.executor.ensure_storage"):
                await manager._tasks[job.job_id]
            result = manager.jobs[job.job_id]
            self.assertEqual(result.state, JobState.FAILED)
            self.assertEqual(result.error.code, "romm-content-missing")
            self.assertFalse(result.error.retryable)
            self.assertIn("HTTP 404", result.error.details["provider_message"])

        asyncio.run(exercise())

    def test_ps1_cue_track_set_is_preserved_and_launches_the_cue(self) -> None:
        async def exercise() -> None:
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                cue = b'FILE "track 1.bin" BINARY\nFILE "track 2.bin" BINARY\n'
                files = (RommFile(701, "disc.cue", len(cue)),
                         RommFile(702, "track 1.bin", 3), RommFile(703, "track 2.bin", 3))

                class Client(FakeRomm):
                    def __init__(self):
                        self.game = RommGame(7, "Fixture Disc", 7, "psx", "PlayStation", "disc.cue",
                                             ".cue", len(cue), "", False, files)
                        self.payloads = {701: cue, 702: b"one", 703: b"two"}

                    def open_file_stream(self, romm_file, offset=0):
                        return BytesIO(self.payloads[romm_file.file_id][offset:])

                executor = RommExecutor(Client(), chunk_size=2)
                manager = JobManager()
                manager.register_executor("romm", executor, limit=1)
                with patch.dict("os.environ", {"LULU_ROM_ROOT": str(root)}), \
                        patch("lulu.plugins.romm.executor.ensure_storage"):
                    job = manager.submit("romm", "romm:7", "Fixture Disc")
                    await manager._tasks[job.job_id]
                self.assertEqual(manager.jobs[job.job_id].state, JobState.COMPLETED,
                                 manager.jobs[job.job_id].error)
                disc = root / "psx" / "romm-7"
                self.assertEqual((disc / "track 1.bin").read_bytes(), b"one")
                self.assertEqual((disc / "track 2.bin").read_bytes(), b"two")
                runtime = root / "retroarch"
                runtime.touch()
                from lulu.local_content import LocalContentProvider
                installed = LocalContentProvider(runtime_paths={"psx": runtime}).list_installed(root)
                self.assertEqual([Path(item.content_path).name for item in installed], ["disc.cue"])
                self.assertTrue(installed[0].launchable)

        asyncio.run(exercise())

    def test_ps1_zip_disc_archive_extracts_a_cue_and_related_tracks(self) -> None:
        async def exercise() -> None:
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                archive_bytes = BytesIO()
                with zipfile.ZipFile(archive_bytes, "w") as archive:
                    archive.writestr("Disc 1/game.cue", 'FILE "game.bin" BINARY\n')
                    archive.writestr("Disc 1/game.bin", b"disc-data")
                payload = archive_bytes.getvalue()
                class Client(FakeRomm):
                    def __init__(self):
                        self.game = RommGame(8, "Archive Disc", 7, "psx", "PlayStation", "disc-set.zip",
                                             ".zip", len(payload), "", False,
                                             (RommFile(801, "disc-set.zip", len(payload)),))
                    def open_file_stream(self, _romm_file, offset=0):
                        return BytesIO(payload[offset:])

                executor = RommExecutor(Client(), chunk_size=32)
                manager = JobManager()
                manager.register_executor("romm", executor, limit=1)
                with patch.dict("os.environ", {"LULU_ROM_ROOT": str(root)}), \
                        patch("lulu.plugins.romm.executor.ensure_storage"):
                    job = manager.submit("romm", "romm:8", "Archive Disc")
                    await manager._tasks[job.job_id]
                self.assertEqual(manager.jobs[job.job_id].state, JobState.COMPLETED)
                disc = root / "psx" / "romm-8" / "Disc 1"
                self.assertTrue((disc / "game.cue").is_file())
                self.assertEqual((disc / "game.bin").read_bytes(), b"disc-data")
                runtime = root / "retroarch"
                runtime.touch()
                from lulu.local_content import LocalContentProvider
                installed = LocalContentProvider(runtime_paths={"psx": runtime}).list_installed(root)
                self.assertEqual(len(installed), 1)
                self.assertEqual(Path(installed[0].content_path), disc / "game.cue")
                self.assertTrue(installed[0].launchable)

        asyncio.run(exercise())

    def test_ps1_zip_multi_disc_tracks_with_quoted_names_generates_launchable_playlist(self) -> None:
        async def exercise() -> None:
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                archive_bytes = BytesIO()
                with zipfile.ZipFile(archive_bytes, "w") as archive:
                    archive.writestr("Disc One/O'Brien.cue",
                                     'FILE "O’Brien track 1.BIN" BINARY\n'
                                     'FILE "O’Brien track 2.bin" BINARY\n')
                    archive.writestr("Disc One/O’Brien track 1.BIN", b"one-a")
                    archive.writestr("Disc One/O’Brien track 2.bin", b"one-b")
                    archive.writestr("Disc Two/Second Disc.CUE",
                                     'FILE "Second Disc Track 1.bin" BINARY\n'
                                     'FILE "Second Disc Track 2.BIN" BINARY\n')
                    archive.writestr("Disc Two/Second Disc Track 1.bin", b"two-a")
                    archive.writestr("Disc Two/Second Disc Track 2.BIN", b"two-b")
                payload = archive_bytes.getvalue()

                class Client(FakeRomm):
                    def __init__(self):
                        self.game = RommGame(18, "O'Brien Disc Set", 7, "psx", "PlayStation",
                                             "Disc Set.zip", ".zip", len(payload), "", False,
                                             (RommFile(1801, "Disc Set.zip", len(payload)),))

                    def open_file_stream(self, _romm_file, offset=0):
                        return BytesIO(payload[offset:])

                executor = RommExecutor(Client(), chunk_size=32)
                manager = JobManager()
                manager.register_executor("romm", executor, limit=1)
                with patch.dict("os.environ", {"LULU_ROM_ROOT": str(root)}), \
                        patch("lulu.plugins.romm.executor.ensure_storage"):
                    job = manager.submit("romm", "romm:18", "O'Brien Multi Disc")
                    await manager._tasks[job.job_id]
                self.assertEqual(manager.jobs[job.job_id].state, JobState.COMPLETED,
                                 manager.jobs[job.job_id].error)
                disc_root = root / "psx" / "romm-18"
                self.assertEqual((disc_root / "Disc One" / "O’Brien track 1.BIN").read_bytes(), b"one-a")
                self.assertEqual((disc_root / "Disc Two" / "Second Disc Track 2.BIN").read_bytes(), b"two-b")
                playlist = root / "psx" / f"O_Brien Disc Set [{job.job_id[:8]}].m3u"
                self.assertEqual(playlist.read_text().splitlines(), [
                    "romm-18/Disc One/O'Brien.cue", "romm-18/Disc Two/Second Disc.CUE"])
                runtime = root / "retroarch"
                runtime.touch()
                from lulu.local_content import LocalContentProvider
                installed = LocalContentProvider(runtime_paths={"psx": runtime}).list_installed(root)
                self.assertEqual(len(installed), 1)
                self.assertEqual(Path(installed[0].content_path), playlist)
                self.assertTrue(installed[0].launchable)

        asyncio.run(exercise())

    def test_multi_disc_romm_content_set_creates_one_retroarch_playlist_target(self) -> None:
        async def exercise() -> None:
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                games = []
                payloads = {}
                for rom_id, label in ((7, "disc1"), (8, "disc2")):
                    cue = f'FILE "{label}.bin" BINARY\n'.encode()
                    cue_file = RommFile(rom_id * 100, f"{label}.cue", len(cue), "game", rom_id=rom_id)
                    bin_file = RommFile(rom_id * 100 + 1, f"{label}.bin", 4, "game", rom_id=rom_id)
                    games.append(RommGame(rom_id, f"Fixture Disc {rom_id}", 7, "psx", "PlayStation",
                                          cue_file.name, ".cue", len(cue), "", False, (cue_file, bin_file)))
                    payloads[cue_file.file_id] = cue
                    payloads[bin_file.file_id] = label.encode()

                class Client:
                    def list_games(self): return games
                    def open_file_stream(self, romm_file, offset=0):
                        return BytesIO(payloads[romm_file.file_id][offset:])

                executor = RommExecutor(Client(), chunk_size=16)
                manager = JobManager()
                manager.register_executor("romm", executor, limit=1)
                with patch.dict("os.environ", {"LULU_ROM_ROOT": str(root)}), \
                        patch("lulu.plugins.romm.executor.ensure_storage"):
                    job = manager.submit("romm", "romm-set:7,8", "Fixture Multi Disc")
                    await manager._tasks[job.job_id]
                self.assertEqual(manager.jobs[job.job_id].state, JobState.COMPLETED)
                playlist = root / "psx" / f"Fixture Multi Disc [{job.job_id[:8]}].m3u"
                self.assertEqual(playlist.read_text().splitlines(), [
                    "romm-7/disc1.cue", "romm-8/disc2.cue"])
                runtime = root / "retroarch"
                runtime.touch()
                from lulu.local_content import LocalContentProvider
                installed = LocalContentProvider(runtime_paths={"psx": runtime}).list_installed(root)
                self.assertEqual(len(installed), 1)
                self.assertEqual(Path(installed[0].content_path), playlist)
                self.assertTrue(installed[0].launchable)

        asyncio.run(exercise())

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
