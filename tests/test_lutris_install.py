import asyncio
from pathlib import Path
import tempfile
import time
import unittest

from lulu.job_manager import JobManager
from lulu.jobs import JobOperation, JobState
from lulu.lutris_adapter import LutrisAdapter, LutrisRecipe
from lulu.lutris_install import LutrisInstallExecutor
from lulu.pc_install import PcInstallSource, PcSourceType, PcSourceFile
from lulu.pc_install_store import PcInstallSourceStore


class FakeLutris:
    def __init__(self, fail=False):
        self.fail = fail
        self.executed = []

    def search(self, title):
        return ({"slug": "free-game"},)

    def recipes(self, slug):
        return (LutrisRecipe("free-game", "free-game-local", "Free Game", "linux", {
            "game_slug": "free-game", "slug": "free-game-local", "name": "Free Game",
            "version": "1", "runner": "linux", "script": {"files": [], "installer": []},
        }),)

    def match(self, source, recipes):
        return recipes[0]

    def execute(self, source, recipe, destination, *, status=None, transaction_id=None):
        if self.fail:
            raise RuntimeError("fixture failure")
        self.executed.append((source.source_id, recipe.installer_slug, destination))
        destination.mkdir(parents=True, exist_ok=True)
        return {"lutris_id": "42", "config_id": "42.yml", "slug": "free-game",
                "title": "Free Game", "runner": "linux", "directory": str(destination)}


class InteractiveFake(FakeLutris):
    def execute(self, source, recipe, destination, *, status=None, transaction_id=None):
        destination.mkdir(parents=True, exist_ok=True)
        if status:
            status("awaiting_interaction")
        time.sleep(0.05)
        if status:
            status("interaction_complete")
        return {"lutris_id": "43", "config_id": "43.yml", "slug": "free-game",
                "title": "Free Game", "runner": "linux", "directory": str(destination)}


class LutrisInstallTests(unittest.TestCase):
    def test_recipe_classifier_is_conservative_and_does_not_mutate_upstream(self):
        source = PcInstallSource("pc:x", "X", "manual", PcSourceType.WINDOWS_INSTALLER,
                                 "/tmp/setup.exe", (PcSourceFile("/tmp/setup.exe", "setup.exe", 1, "exe"),), True)
        raw = {"script": {"files": [{"setup": {"url": "N/A: select", "filename": "setup.exe"}}],
                           "installer": [
                               {"task": {"name": "wine.wineexec", "executable": "setup", "args": "/SILENT"}},
                               {"task": {"name": "wine.wineexec", "executable": "setup", "args": ""}},
                           ]}}
        recipe = LutrisRecipe("x", "x-installer", "X", "wine", raw)
        self.assertEqual(LutrisAdapter.classify_interactive_commands(source, recipe), (1,))
        self.assertNotIn("MUDOS_INTERACTIVE", raw["script"]["installer"][1]["task"])

    def test_linux_recipe_never_delegates(self):
        source = PcInstallSource("pc:x", "X", "manual", PcSourceType.DIRECTORY,
                                 "/tmp/x", (), True)
        recipe = LutrisRecipe("x", "x", "X", "linux", {"script": {"files": [],
                           "installer": [{"execute": {"file": "setup", "args": ""}}]}})
        self.assertEqual(LutrisAdapter.classify_interactive_commands(source, recipe), ())

    def test_interaction_state_returns_to_installing_on_same_parent_job(self):
        async def exercise():
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory); payload = root / "payload.exe"; payload.write_bytes(b"fixture")
                source = PcInstallSource("pc:free-game", "Free Game", "manual",
                                         PcSourceType.WINDOWS_INSTALLER, str(payload),
                                         (PcSourceFile(str(payload), "payload.exe", 7, "exe"),), True)
                store = PcInstallSourceStore(root / "sources.json")
                executor = LutrisInstallExecutor(store, InteractiveFake())
                source_id = executor.register_source(source); manager = JobManager(); manager.register_executor("lutris", executor)
                job = manager.submit("lutris", source_id, "Free Game", operation=JobOperation.INSTALL)
                await manager._tasks[job.job_id]
                self.assertEqual(manager.jobs[job.job_id].state, JobState.COMPLETED)
                self.assertEqual(manager.jobs[job.job_id].provider_job_id, "43")

        asyncio.run(exercise())

    def test_one_parent_install_job_registers_source_and_completes(self):
        async def exercise():
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                payload = root / "payload.exe"
                payload.write_bytes(b"fixture")
                source = PcInstallSource("pc:free-game", "Free Game", "manual",
                                         PcSourceType.WINDOWS_INSTALLER, str(payload),
                                         (PcSourceFile(str(payload), "payload.exe", 7, "exe"),), True)
                store = PcInstallSourceStore(root / "sources.json")
                adapter = FakeLutris()
                executor = LutrisInstallExecutor(store, adapter)
                source_id = executor.register_source(source)
                manager = JobManager()
                manager.register_executor("lutris", executor)
                job = manager.submit("lutris", source_id, "Free Game", operation=JobOperation.INSTALL)
                await manager._tasks[job.job_id]
                result = manager.jobs[job.job_id]
                self.assertEqual(result.state, JobState.COMPLETED)
                self.assertEqual(result.provider_job_id, "42")
                self.assertEqual(len(adapter.executed), 1)

        asyncio.run(exercise())

    def test_failed_install_preserves_source_and_is_retryable(self):
        async def exercise():
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory); payload = root / "payload.exe"; payload.write_bytes(b"fixture")
                source = PcInstallSource("pc:free-game", "Free Game", "questarr",
                                         PcSourceType.WINDOWS_INSTALLER, str(payload),
                                         (PcSourceFile(str(payload), "payload.exe", 7, "exe"),), True,
                                         questarr_game_id="game", questarr_download_id="download")
                store = PcInstallSourceStore(root / "sources.json"); executor = LutrisInstallExecutor(store, FakeLutris(True))
                source_id = executor.register_source(source); manager = JobManager(); manager.register_executor("lutris", executor)
                job = manager.submit("lutris", source_id, "Free Game", operation=JobOperation.INSTALL)
                await manager._tasks[job.job_id]
                result = manager.jobs[job.job_id]
                self.assertEqual(result.state, JobState.FAILED); self.assertTrue(result.retryable)
                self.assertTrue(payload.exists()); self.assertIsNotNone(store.get(source_id))

        asyncio.run(exercise())


if __name__ == "__main__":
    unittest.main()
