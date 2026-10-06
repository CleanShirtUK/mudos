import asyncio
import json
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from lulu.acquisitiond import AcquisitionInterface
from lulu.catalogue import CatalogueGame, CatalogueStore
from lulu.job_manager import JobExecutionError, JobManager
from lulu.jobs import JobOperation, JobState
from lulu.local_uninstall import LocalUninstallExecutor
from lulu.lutris_install import LutrisInstallExecutor
from lulu.plugins.epic import EpicAcquisitionExecutor
from lulu.plugins.flatpak.adapter import FlatpakJobExecutor
from lulu.plugins.gog import GogAcquisitionExecutor
from lulu.plugins.romm.executor import RommExecutor
from lulu.plugins.steam.aurelia import AureliaAcquisitionExecutor
from lulu.plugins.steam.cmd import SteamCmdExecutor


def local_game(path: Path) -> CatalogueGame:
    return CatalogueGame(
        game_id="local:test", provider="local", provider_id="local:test",
        title="Disposable ROM", platform="nes", install_state="installed",
        launchable=True, install_dir=str(path), artwork_url="", last_played=0,
        catalogue_source="local", content_identity="local:test", mudos_owned=True,
    )


class LocalUninstallTests(unittest.TestCase):
    def test_provider_capability_matrix_matches_owned_remove_operations(self) -> None:
        matrix = {
            "steam-aurelia": AureliaAcquisitionExecutor.supports_uninstall,
            "steamcmd-legacy": SteamCmdExecutor.supports_uninstall,
            "epic": EpicAcquisitionExecutor.supports_uninstall,
            "gog": GogAcquisitionExecutor.supports_uninstall,
            "flatpak": FlatpakJobExecutor.supports_uninstall,
            "lutris": LutrisInstallExecutor.supports_uninstall,
            "local": LocalUninstallExecutor.supports_uninstall,
            "romm": getattr(RommExecutor, "supports_uninstall", False),
        }
        self.assertEqual(matrix, {
            "steam-aurelia": True, "steamcmd-legacy": False,
            "epic": True, "gog": True, "flatpak": True,
            "lutris": True, "local": True, "romm": False,
        })

    def test_gog_remove_is_limited_to_direct_mudos_managed_install_directory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "gog"
            owned = root / "fixture"
            owned.mkdir(parents=True)
            (owned / ".mudos-game.json").write_text(
                '{"provider_id":"fixture","install_dir":"' + str(owned) + '"}')
            game_file = owned / "game.bin"
            game_file.write_bytes(b"still installed")
            executor = GogAcquisitionExecutor.__new__(GogAcquisitionExecutor)
            executor.provider = "gog"
            executor.install_root = root
            executor.uninstall_builder = None
            self.assertTrue(executor.can_uninstall("gog:fixture"))
            self.assertFalse(executor.can_uninstall("gog:../../outside"))
            self.assertFalse(executor.can_uninstall("gog:unmanaged"))

    def test_acquisition_capability_uses_registered_provider_executor(self) -> None:
        interface = AcquisitionInterface.__new__(AcquisitionInterface)
        game = SimpleNamespace(game_id="fixture", provider="steam", provider_id="123",
                               title="Fixture", install_state="installed",
                               installed_game_id="")
        interface.catalogue = SimpleNamespace(get_game=lambda _game_id: game)
        interface.manager = SimpleNamespace(executors={
            "steam-aurelia": SimpleNamespace(supports_uninstall=True)})
        self.assertEqual(interface._uninstall_target("fixture")[1:3],
                         ("steam-aurelia", "steam-aurelia:123"))
        interface.manager.executors["steam-aurelia"].supports_uninstall = False
        with self.assertRaises(Exception):
            interface._uninstall_target("fixture")

    def test_current_steam_rows_resolve_to_aurelia_uninstall(self) -> None:
        from lulu.plugins.steam.aurelia import AureliaAcquisitionExecutor

        game = SimpleNamespace(game_id="steam:440", provider="steam", provider_id="440",
                               title="Team Fortress 2", install_state="installed",
                               installed_game_id="", catalogue_source="steam")
        interface = AcquisitionInterface.__new__(AcquisitionInterface)
        interface.catalogue = SimpleNamespace(get_game=lambda _game_id: game)
        interface.manager = SimpleNamespace(executors={
            "steam-aurelia": AureliaAcquisitionExecutor(),
        })
        target, provider, identity, _title, capability = interface._resolve_uninstall("steam:440")
        self.assertIs(target, game)
        self.assertEqual((provider, identity), ("steam-aurelia", "steam-aurelia:440"))
        self.assertTrue(capability["supported"])
        self.assertIn("Aurelia", capability["description"])

    def test_aurelia_capability_rejects_invalid_app_id(self) -> None:
        executor = AureliaAcquisitionExecutor()
        capability = executor.uninstall_capability(SimpleNamespace(provider_id="../../outside"))
        self.assertFalse(capability["supported"])

    def test_capability_reports_confirmation_progress_and_active_state(self) -> None:
        import json

        game = SimpleNamespace(game_id="fixture:7", provider="fixture", provider_id="7",
                               title="Fixture", install_state="installed", installed_game_id="")
        executor = SimpleNamespace(supports_uninstall=True, uninstall_progress_supported=True,
                                   can_uninstall=lambda _game_id: True)
        manager = SimpleNamespace(executors={"fixture": executor}, jobs={})
        interface = AcquisitionInterface.__new__(AcquisitionInterface)
        interface.catalogue = SimpleNamespace(get_game=lambda _game_id: game)
        interface.manager = manager
        result = json.loads(AcquisitionInterface.CanUninstall.__wrapped__(interface, "fixture:7"))
        self.assertTrue(result["supported"])
        self.assertTrue(result["requires_confirmation"])
        self.assertTrue(result["progress_measurable"])
        self.assertFalse(result["in_progress"])

        manager.jobs["remove"] = SimpleNamespace(
            provider="fixture", content_identity="fixture:7", operation=JobOperation.REMOVE,
            state=JobState.TRANSFERRING,
        )
        result = json.loads(AcquisitionInterface.CanUninstall.__wrapped__(interface, "fixture:7"))
        self.assertTrue(result["in_progress"])

    def test_repeated_active_remove_request_returns_same_job_identity(self) -> None:
        class WaitingExecutor:
            supports_uninstall = True
            def __init__(self): self.release = asyncio.Event()
            async def run(self, _job, reporter):
                await reporter.state(JobState.TRANSFERRING, stage="removing")
                await self.release.wait()
                await reporter.state(JobState.FINALIZING, stage="reconciling")
            async def cancel(self, _job): return None

        async def exercise() -> None:
            game = SimpleNamespace(game_id="fixture:7", provider="fixture", provider_id="7",
                                   title="Fixture", install_state="installed", installed_game_id="")
            executor = WaitingExecutor()
            manager = JobManager()
            manager.register_executor("fixture", executor)
            interface = AcquisitionInterface.__new__(AcquisitionInterface)
            interface.catalogue = SimpleNamespace(get_game=lambda _game_id: game)
            interface.manager = manager
            first = AcquisitionInterface.UninstallGame.__wrapped__(interface, "fixture:7")
            second = AcquisitionInterface.UninstallGame.__wrapped__(interface, "fixture:7")
            self.assertEqual(first, second)
            job = manager.jobs[first]
            self.assertEqual(job.content_identity, "fixture:7")
            self.assertEqual(job.operation, JobOperation.REMOVE)
            executor.release.set()
            await manager._tasks[first]
            self.assertEqual(manager.jobs[first].state, JobState.COMPLETED)

        asyncio.run(exercise())

    def test_provider_failure_keeps_catalogue_install_state(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "gog"
            owned = root / "fixture"
            owned.mkdir(parents=True)
            (owned / ".mudos-game.json").write_text(
                '{"provider_id":"fixture","install_dir":"' + str(owned) + '"}')
            game_file = owned / "game.bin"
            game_file.write_bytes(b"still installed")
            store = CatalogueStore(Path(directory) / "catalogue.sqlite3")
            game = CatalogueGame("gog:fixture", "gog", "fixture", "Fixture", "PC",
                                 "installed", True, str(owned), "", 0, catalogue_source="gog")
            store._upsert(game); store.connection.commit()

            class FailingGog(GogAcquisitionExecutor):
                async def _remove_managed_payload(self, _job, _reporter):
                    raise JobExecutionError("remove-failed", "fixture provider failure", retryable=True)

            executor = FailingGog.__new__(FailingGog)
            executor.provider, executor.install_root, executor.uninstall_builder = "gog", root, None
            manager = JobManager()
            manager.register_executor("gog", executor)

            async def run() -> None:
                job = manager.submit("gog", "gog:fixture", "Fixture", operation=JobOperation.REMOVE)
                await manager._tasks[job.job_id]
                self.assertEqual(manager.jobs[job.job_id].state, JobState.FAILED)
                self.assertEqual(manager.jobs[job.job_id].error.code, "remove-failed")

            asyncio.run(run())
            self.assertTrue(game_file.exists())
            self.assertEqual(store.get_game("gog:fixture").install_state, "installed")

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
                with self.assertRaises(JobExecutionError):
                    LocalUninstallExecutor(store, root)._approved_paths("local:test")
                store.connection.execute("DELETE FROM games WHERE game_id='local:test'")
                store.connection.commit()
            target = base / "escape-target.nes"
            target.write_text("protected")
            link = root / "nes" / "escape.nes"
            link.parent.mkdir()
            link.symlink_to(target)
            store._upsert(local_game(link)); store.connection.commit()
            with self.assertRaises(JobExecutionError):
                LocalUninstallExecutor(store, root)._approved_paths("local:test")
            self.assertTrue(target.exists())

    def test_missing_path_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "ROMs"
            path = root / "nes" / "missing.nes"
            root.mkdir(); (root / "nes").mkdir()
            store = CatalogueStore(Path(directory) / "catalogue.sqlite3")
            store._upsert(local_game(path)); store.connection.commit()
            self.assertEqual(LocalUninstallExecutor(store, root)._approved_paths("local:test"), (path,))
            self.assertTrue(LocalUninstallExecutor(store, root).can_uninstall("local:test"))

    def test_external_cli_executor_does_not_claim_uninstall_by_default(self) -> None:
        from lulu.plugins.external import CliAcquisitionExecutor
        executor = CliAcquisitionExecutor("fixture", "fixture", Path("/tmp/fixture"),
                                          lambda _identity, _root: ["fixture", "install"])
        self.assertFalse(executor.supports_uninstall)

    def test_gog_managed_removal_deletes_only_marked_direct_child_and_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "gog"
            owned = root / "fixture"
            owned.mkdir(parents=True)
            marker = owned / ".mudos-game.json"
            marker.write_text('{"provider_id":"fixture","install_dir":"' + str(owned) + '"}')
            (owned / "game.bin").write_bytes(b"fixture")
            neighbor = root / "neighbor"
            neighbor.mkdir()
            (neighbor / "keep.bin").write_bytes(b"keep")
            executor = GogAcquisitionExecutor.__new__(GogAcquisitionExecutor)
            executor.provider = "gog"
            executor.install_root = root
            executor.uninstall_builder = None
            manager = JobManager()
            manager.register_executor("gog", executor)

            async def remove() -> None:
                job = manager.submit("gog", "gog:fixture", "Fixture", operation=JobOperation.REMOVE)
                await manager._tasks[job.job_id]
                self.assertEqual(manager.jobs[job.job_id].state, JobState.COMPLETED)

            asyncio.run(remove())
            self.assertFalse(owned.exists())
            self.assertTrue((neighbor / "keep.bin").exists())

            async def retry_missing() -> None:
                retry = manager.submit("gog", "gog:fixture", "Fixture", operation=JobOperation.REMOVE)
                await manager._tasks[retry.job_id]
                self.assertEqual(manager.jobs[retry.job_id].state, JobState.COMPLETED)

            asyncio.run(retry_missing())

    def test_gog_removal_refuses_symlink_or_mismatched_marker(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            root = base / "gog"
            outside = base / "outside"
            outside.mkdir()
            (outside / "keep").write_text("keep")
            root.mkdir()
            link = root / "fixture"
            link.symlink_to(outside, target_is_directory=True)
            executor = GogAcquisitionExecutor.__new__(GogAcquisitionExecutor)
            executor.provider, executor.install_root = "gog", root
            self.assertFalse(executor.can_uninstall("gog:fixture"))
            link.unlink()
            owned = root / "fixture"
            owned.mkdir()
            (owned / ".mudos-game.json").write_text('{"provider_id":"other","install_dir":"' + str(owned) + '"}')
            self.assertFalse(executor.can_uninstall("gog:fixture"))
            self.assertTrue((outside / "keep").exists())

    def test_epic_capability_validates_identity_managed_path_and_third_party_store(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "epic"
            root.mkdir()
            owned = root / "fixture-app"
            owned.mkdir()
            executor = EpicAcquisitionExecutor.__new__(EpicAcquisitionExecutor)
            executor.provider = "epic"
            executor.install_root = root
            executor.config_dir = Path(directory) / "config"
            executor.config_dir.mkdir()
            with patch("lulu.plugins.epic.PATHS", SimpleNamespace(epic_library_root=root)):
                self.assertTrue(executor.can_uninstall("epic:fixture-app"))
                self.assertFalse(executor.can_uninstall("epic:../../outside"))
                link = root / "linked-app"
                link.symlink_to(owned, target_is_directory=True)
                self.assertFalse(executor.can_uninstall("epic:linked-app"))
                metadata = executor.config_dir / "metadata" / "fixture-app.json"
                metadata.parent.mkdir()
                metadata.write_text(json.dumps({"metadata": {"customAttributes": {
                    "ThirdPartyManagedProvider": {"value": "lutris"},
                }}}))
                self.assertFalse(executor.can_uninstall("epic:fixture-app"))
                self.assertTrue(owned.is_dir())

    def test_epic_remove_replay_is_idempotent_only_after_authoritative_inventory(self) -> None:
        class Reporter:
            def __init__(self): self.states = []
            async def state(self, state, **kwargs): self.states.append(state)

        async def exercise():
            executor = EpicAcquisitionExecutor.__new__(EpicAcquisitionExecutor)
            executor.provider = "epic"
            executor.install_root = Path("/unused")
            executor.config_dir = Path("/unused-config")
            executor._third_party_store = lambda _app_id: ""
            executor.provider_installed_record = lambda _app_id: None
            job = SimpleNamespace(operation=JobOperation.REMOVE, content_identity="epic:123",
                                  provider_job_id="123")
            reporter = Reporter()
            await executor.run(job, reporter)
            self.assertEqual(reporter.states, [JobState.STARTING, JobState.FINALIZING])

            executor.provider_installed_record = lambda _app_id: {
                "provider_id": "123", "install_dir": "/outside/123",
            }
            with self.assertRaises(JobExecutionError):
                await executor.run(job, Reporter())

        asyncio.run(exercise())

    def test_epic_inventory_uses_legendary_json_and_capability_checks_catalogue_path(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "epic"
            install = root / "fixture-app"
            install.mkdir(parents=True)
            executor = EpicAcquisitionExecutor.__new__(EpicAcquisitionExecutor)
            executor.provider = "epic"
            executor.environment = {"LEGENDARY_CONFIG_PATH": directory}
            executor._require = lambda: "/usr/bin/legendary"
            executor.config_dir = Path(directory) / "config"
            executor.config_dir.mkdir()
            with patch("lulu.plugins.epic.PATHS", SimpleNamespace(epic_library_root=root)):
                with patch("lulu.plugins.epic.subprocess.run") as run:
                    run.return_value = SimpleNamespace(stdout=json.dumps([{
                        "app_name": "fixture-app", "app_title": "Fixture",
                        "install_path": str(install),
                    }]))
                    record = executor.provider_installed_record("fixture-app")
                self.assertEqual(record["install_dir"], str(install))
                game = SimpleNamespace(provider="epic", provider_id="fixture-app",
                                       install_state="installed", install_dir=str(install))
                self.assertTrue(executor.uninstall_capability(game)["supported"])
                unsafe = SimpleNamespace(provider="epic", provider_id="fixture-app",
                                         install_state="installed", install_dir=str(Path(directory) / "other"))
                self.assertFalse(executor.uninstall_capability(unsafe)["supported"])

    def test_lutris_recipe_payload_deletes_but_manual_registration_preserves_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            root = base / "Games"
            lutris_root = root / "Executables" / "lutris"
            lutris_root.mkdir(parents=True)
            neighbour = lutris_root / "neighbor"
            neighbour.mkdir()
            (neighbour / "keep.bin").write_bytes(b"keep")

            class LutrisFixture:
                def __init__(self): self.calls = []
                def uninstall(self, slug, *, delete_files, expected_directory):
                    self.calls.append((slug, delete_files, expected_directory))
                    return {"slug": slug, "directory": str(expected_directory)}

            store = CatalogueStore(base / "catalogue.sqlite3")
            adapter = LutrisFixture()
            executor = LutrisInstallExecutor(catalogue=store, adapter=adapter)
            with patch("lulu.lutris_install.PATHS", SimpleNamespace(game_install_root=root)):
                for slug, source, delete_payload in (
                        ("recipe-game", "lutris-recipe", True),
                        ("manual-game", "mudos-local", False)):
                    game_dir = lutris_root / slug
                    game_dir.mkdir()
                    payload = game_dir / "game.bin"
                    payload.write_bytes(b"game")
                    if source == "lutris-recipe":
                        (game_dir / ".mudos-install-owner.json").write_text(json.dumps({
                            "schema": 1, "provider": "lutris", "slug": slug,
                            "directory": str(game_dir.resolve()),
                        }))
                    game = CatalogueGame(
                        f"lutris:{slug}", "lutris", slug, slug, "PC", "installed", True,
                        str(game_dir), "", 0, catalogue_source=source, mudos_owned=True,
                    )
                    store._upsert(game); store.connection.commit()
                    self.assertTrue(executor.can_uninstall(game.game_id))
                    manager = JobManager()
                    manager.register_executor("lutris", executor)

                    async def remove() -> None:
                        job = manager.submit("lutris", game.game_id, slug,
                                             operation=JobOperation.REMOVE, provider_job_id=slug)
                        await manager._tasks[job.job_id]
                        self.assertEqual(manager.jobs[job.job_id].state, JobState.COMPLETED)

                    asyncio.run(remove())
                    self.assertEqual(adapter.calls[-1][1], delete_payload)
                    self.assertEqual(payload.exists(), not delete_payload)
                    self.assertEqual(
                        store.get_game(game.game_id).install_state,
                        "missing" if source == "mudos-local" else "available",
                    )
                self.assertTrue((neighbour / "keep.bin").exists())

    def test_lutris_recipe_uninstall_rejects_outside_parent_and_symlink_paths(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            root = base / "Games"
            lutris_root = root / "Executables" / "lutris"
            lutris_root.mkdir(parents=True)
            outside = base / "outside"
            outside.mkdir()
            store = CatalogueStore(base / "catalogue.sqlite3")
            executor = LutrisInstallExecutor(catalogue=store, adapter=SimpleNamespace())
            with patch("lulu.lutris_install.PATHS", SimpleNamespace(game_install_root=root)):
                cases = [
                    CatalogueGame("lutris:outside", "lutris", "outside", "Outside", "PC", "installed",
                                  True, str(outside), "", 0, catalogue_source="lutris-recipe", mudos_owned=True),
                    CatalogueGame("lutris:parent", "lutris", "lutris", "Parent", "PC", "installed",
                                  True, str(lutris_root), "", 0, catalogue_source="lutris-recipe", mudos_owned=True),
                ]
                link = lutris_root / "escape-game"
                link.symlink_to(outside, target_is_directory=True)
                cases.append(CatalogueGame("lutris:escape-game", "lutris", "escape-game", "Escape", "PC",
                                           "installed", True, str(link), "", 0,
                                           catalogue_source="lutris-recipe", mudos_owned=True))
                for game in cases:
                    self.assertIsNone(executor._owned_install_directory(game))
                self.assertTrue((outside).is_dir())


if __name__ == "__main__":
    unittest.main()
