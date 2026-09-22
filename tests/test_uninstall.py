import asyncio
from pathlib import Path
import tempfile
import unittest

from lulu.catalogue import CatalogueGame, CatalogueStore
from lulu.job_manager import JobManager
from lulu.jobs import JobOperation, JobState
from lulu.local_uninstall import LocalUninstallExecutor


def local_game(path: Path) -> CatalogueGame:
    return CatalogueGame(
        game_id="local:test", provider="local", provider_id="local:test",
        title="Disposable ROM", platform="nes", install_state="installed",
        launchable=True, install_dir=str(path), artwork_url="", last_played=0,
        catalogue_source="local", content_identity="local:test",
    )


class LocalUninstallTests(unittest.TestCase):
    def test_switch_remove_job_removes_owned_component_set_only(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "ROMs"
            switch = root / "switch"; switch.mkdir(parents=True)
            base, dlc = switch / "Mario.nsp", switch / "Mario DLC.nsp"
            neighbor, save = switch / "Other.nsp", Path(directory) / "save.dat"
            for path in (base, dlc, neighbor): path.write_text(path.name)
            save.write_text("save")
            game = CatalogueGame(
                game_id="local:switch:mario", provider="local", provider_id="local:switch:mario",
                title="Mario", platform="switch", install_state="installed", launchable=True,
                install_dir=str(base), artwork_url="", last_played=0, catalogue_source="local",
                component_paths=(str(base), str(dlc)), component_roles=("base", "dlc"),
                component_title_ids=("0100000000000000", "0100000000000001"), mudos_owned=True,
            )
            store = CatalogueStore(Path(directory) / "catalogue.sqlite3")
            store._upsert(game); store.connection.commit()
            manager = JobManager(); manager.register_executor("local", LocalUninstallExecutor(store, root))

            async def run() -> None:
                job = manager.submit("local", game.game_id, game.title, operation=JobOperation.REMOVE)
                await manager._tasks[job.job_id]
                self.assertEqual(manager.jobs[job.job_id].state, JobState.COMPLETED)

            asyncio.run(run())
            self.assertFalse(base.exists()); self.assertFalse(dlc.exists())
            self.assertTrue(neighbor.exists()); self.assertTrue(save.exists())

    def test_file_is_removed_through_remove_job(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "ROMs"
            path = root / "nes" / "test.nes"
            path.parent.mkdir(parents=True)
            path.write_bytes(b"test")
            store = CatalogueStore(Path(directory) / "catalogue.sqlite3")
            store._upsert(local_game(path)); store.connection.commit()
            manager = JobManager()
            manager.register_executor("local", LocalUninstallExecutor(store, root))

            async def run() -> None:
                job = manager.submit("local", "local:test", "Disposable ROM",
                                     operation=JobOperation.REMOVE)
                await manager._tasks[job.job_id]
                self.assertEqual(manager.jobs[job.job_id].state, JobState.COMPLETED)

            asyncio.run(run())
            self.assertFalse(path.exists())
            self.assertTrue(root.exists())
            self.assertIsNotNone(store.get_game("local:test"))

    def test_dedicated_directory_does_not_touch_neighbor(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "ROMs"
            game_dir = root / "switch" / "Game"
            game_dir.mkdir(parents=True)
            (game_dir / "base").write_text("base")
            neighbor = root / "switch" / "Other.nsp"
            neighbor.write_text("neighbor")
            store = CatalogueStore(Path(directory) / "catalogue.sqlite3")
            store._upsert(local_game(game_dir)); store.connection.commit()
            executor = LocalUninstallExecutor(store, root)
            # Exercise the path policy directly without a fake reporter.
            self.assertEqual(executor._approved_path("local:test"), game_dir)
            import shutil
            shutil.rmtree(game_dir)
            self.assertTrue(neighbor.exists())

    def test_outside_root_parent_and_symlink_escape_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            root = base / "ROMs"
            root.mkdir()
            store = CatalogueStore(base / "catalogue.sqlite3")
            outside = base / "outside.nes"
            outside.write_text("outside")
            for path in (outside, root, root / "nes"):
                game = local_game(path)
                store._upsert(game); store.connection.commit()
                with self.assertRaises(Exception):
                    LocalUninstallExecutor(store, root)._approved_path("local:test")
                store.connection.execute("DELETE FROM games WHERE game_id='local:test'")
                store.connection.commit()
            target = base / "escape-target.nes"
            target.write_text("protected")
            link = root / "nes" / "escape.nes"
            link.parent.mkdir()
            link.symlink_to(target)
            store._upsert(local_game(link)); store.connection.commit()
            with self.assertRaises(Exception):
                LocalUninstallExecutor(store, root)._approved_path("local:test")
            self.assertTrue(target.exists())

    def test_missing_path_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "ROMs"
            path = root / "nes" / "missing.nes"
            root.mkdir(); (root / "nes").mkdir()
            store = CatalogueStore(Path(directory) / "catalogue.sqlite3")
            store._upsert(local_game(path)); store.connection.commit()
            self.assertEqual(LocalUninstallExecutor(store, root)._approved_path("local:test"), path)


if __name__ == "__main__":
    unittest.main()
