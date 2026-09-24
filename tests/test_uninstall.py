import asyncio
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace

from lulu.acquisitiond import AcquisitionInterface
from lulu.catalogue import CatalogueGame, CatalogueStore
from lulu.job_manager import JobManager
from lulu.jobs import JobOperation, JobState
from lulu.local_uninstall import LocalUninstallExecutor
from lulu.lutris_install import LutrisInstallExecutor
from lulu.plugins.epic import EpicAcquisitionExecutor
from lulu.plugins.flatpak.adapter import FlatpakJobExecutor
from lulu.plugins.gog import GogAcquisitionExecutor
from lulu.plugins.romm.executor import RommExecutor
from lulu.plugins.steam.cmd import SteamCmdExecutor


def local_game(path: Path) -> CatalogueGame:
    return CatalogueGame(
        game_id="local:test", provider="local", provider_id="local:test",
        title="Disposable ROM", platform="nes", install_state="installed",
        launchable=True, install_dir=str(path), artwork_url="", last_played=0,
        catalogue_source="local", content_identity="local:test",
    )


class LocalUninstallTests(unittest.TestCase):
    def test_provider_capability_matrix_matches_owned_remove_operations(self) -> None:
        matrix = {
            "steam": SteamCmdExecutor.supports_uninstall,
            "epic": EpicAcquisitionExecutor.supports_uninstall,
            "gog": GogAcquisitionExecutor.supports_uninstall,
            "flatpak": FlatpakJobExecutor.supports_uninstall,
            "lutris": LutrisInstallExecutor.supports_uninstall,
            "local": LocalUninstallExecutor.supports_uninstall,
            "romm": getattr(RommExecutor, "supports_uninstall", False),
        }
        self.assertEqual(matrix, {
            "steam": True, "epic": True, "gog": True, "flatpak": True,
            "lutris": True, "local": True, "romm": False,
        })

    def test_gog_remove_is_limited_to_direct_mudos_managed_install_directory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "gog"
            owned = root / "fixture"
            owned.mkdir(parents=True)
            (owned / ".mudos-game.json").write_text("{}")
            executor = GogAcquisitionExecutor.__new__(GogAcquisitionExecutor)
            executor.provider = "gog"
            executor.install_root = root
            self.assertTrue(executor.can_uninstall("gog:fixture"))
            self.assertFalse(executor.can_uninstall("gog:../../outside"))
            self.assertFalse(executor.can_uninstall("gog:unmanaged"))

    def test_acquisition_capability_uses_registered_provider_executor(self) -> None:
        interface = AcquisitionInterface.__new__(AcquisitionInterface)
        game = SimpleNamespace(game_id="fixture", provider="steam", provider_id="123",
                               title="Fixture", install_state="installed",
                               installed_game_id="")
        interface.catalogue = SimpleNamespace(get_game=lambda _game_id: game)
        interface.manager = SimpleNamespace(executors={"steam": SimpleNamespace(supports_uninstall=True)})
        self.assertEqual(interface._uninstall_target("fixture")[1:3], ("steam", "steam:123"))
        interface.manager.executors["steam"].supports_uninstall = False
        with self.assertRaises(Exception):
            interface._uninstall_target("fixture")

    def test_emulator_runtime_rows_route_rom_removal_to_local_owner(self) -> None:
        for runtime in ("retroarch", "dolphin", "eden", "pcsx2"):
            with self.subTest(runtime=runtime):
                interface = AcquisitionInterface.__new__(AcquisitionInterface)
                game = SimpleNamespace(
                    game_id="local:fixture", provider=runtime, provider_id="local:fixture",
                    title="Disposable ROM", install_state="installed", installed_game_id="",
                    catalogue_source="local")
                interface.catalogue = SimpleNamespace(get_game=lambda _game_id: game)
                interface.manager = SimpleNamespace(executors={
                    "local": SimpleNamespace(supports_uninstall=True)})
                _, provider, identity, _ = interface._uninstall_target(game.game_id)
                self.assertEqual((provider, identity), ("local", game.game_id))

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
            self.assertFalse(executor.can_uninstall("local:test"))
            self.assertTrue(neighbor.exists())

    def test_directories_and_multifile_cue_content_are_not_uninstallable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "ROMs"
            ps2 = root / "ps2"
            ps2.mkdir(parents=True)
            game_dir = ps2 / "Game"
            game_dir.mkdir()
            cue = ps2 / "disc.cue"
            cue.write_text('FILE "disc.bin" BINARY\n')
            store = CatalogueStore(Path(directory) / "catalogue.sqlite3")
            directory_game = CatalogueGame(
                "local:ps2:dir", "local", "local:ps2:dir", "Game", "ps2", "installed",
                True, str(game_dir), "", 0, catalogue_source="local")
            cue_game = CatalogueGame(
                "local:ps2:cue", "local", "local:ps2:cue", "Disc", "ps2", "installed",
                True, str(cue), "", 0, catalogue_source="local")
            store._upsert(directory_game)
            store._upsert(cue_game)
            store.connection.commit()
            executor = LocalUninstallExecutor(store, root)
            self.assertFalse(executor.can_uninstall(directory_game.game_id))
            self.assertFalse(executor.can_uninstall(cue_game.game_id))
            self.assertTrue(game_dir.exists())
            self.assertTrue(cue.exists())

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
