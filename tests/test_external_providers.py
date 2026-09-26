import tempfile
import asyncio
from types import SimpleNamespace
from unittest.mock import patch
from pathlib import Path
import unittest

from lulu.catalogue import CatalogueStore
from lulu.plugins.external import (CliAcquisitionExecutor, OwnedProviderGame,
                                   SnapshotEntitlementSource, normalize_game)
from lulu.plugins.epic import EpicAcquisitionExecutor, EpicAuthentication
from lulu.plugins.gog import GogAuthentication
from lulu.jobs import DownloadJob, JobOperation


class ExternalProviderTests(unittest.TestCase):
    def test_epic_installer_targets_the_canonical_app_id_directory(self) -> None:
        executor = EpicAcquisitionExecutor()
        command = executor.command_builder("epic:Fortnite", Path("/games/Executables/epic"))
        self.assertIn("--base-path", command)
        self.assertEqual(command[command.index("--base-path") + 1], "/games/Executables/epic")
        self.assertIn("--game-folder", command)
        self.assertEqual(command[command.index("--game-folder") + 1], "Fortnite")

    def test_epic_and_gog_completed_jobs_project_through_installed_manifest(self) -> None:
        class Output:
            async def __aiter__(self):
                yield b"installed successfully\n"

        class Process:
            stdout = Output()
            returncode = 0
            async def wait(self): return 0

        class Reporter:
            async def state(self, *_args, **_kwargs): pass
            async def progress(self, *_args, **_kwargs): pass
            async def metadata(self, *_args, **_kwargs): pass

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for provider, source_module, source_type in (
                    ("epic", "lulu.plugins.epic", "EpicEntitlementSource"),
                    ("gog", "lulu.plugins.gog", "GogEntitlementSource")):
                library = root / provider
                identity = f"{provider}-fixture"
                destination = library / identity
                destination.mkdir(parents=True)
                (destination / "game.bin").write_bytes(b"provider payload")
                executor = CliAcquisitionExecutor(
                    provider, "/usr/bin/true", library, lambda *_args: ["fixture"])
                job = DownloadJob(
                    job_id=f"job-{provider}", provider=provider, title=f"{provider.title()} Fixture",
                    content_identity=f"{provider}:{identity}", operation=JobOperation.INSTALL)
                with patch("lulu.plugins.external.asyncio.create_subprocess_exec",
                           return_value=Process()), patch(
                           f"{source_module}.PATHS", SimpleNamespace(
                               provider_root=lambda _id: root / f"{provider}-state",
                               provider_config_root=lambda _id: root / f"{provider}-config",
                               epic_library_root=library, gog_library_root=library)):
                    asyncio.run(executor.run(job, Reporter()))
                    source_class = getattr(__import__(source_module, fromlist=[source_type]), source_type)
                    source = source_class()
                    # The entitlement source can be stale or unavailable; the
                    # successful Mudos-owned marker must still project install.
                    source.update((OwnedProviderGame(identity, job.title),), ())
                    installed = source.installed()
                    self.assertEqual(len(installed), 1)
                    self.assertEqual(installed[0].provider_id, identity)
                    self.assertEqual(Path(installed[0].install_dir), destination)
                    store = CatalogueStore(root / f"{provider}-catalogue.sqlite3")
                    store.reconcile_owned_provider(provider, source.snapshot, installed)
                    projected = store.get_game(f"{provider}:{identity}")
                    self.assertIsNotNone(projected)
                    self.assertEqual(projected.install_state, "installed")
                    self.assertTrue(projected.launchable)
                    self.assertEqual(projected.install_dir, str(destination))

    def test_cli_install_is_not_complete_without_real_provider_payload(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            executor = CliAcquisitionExecutor("gog", "gogdl", root, lambda *_: [])
            empty = root / "game"
            empty.mkdir()
            with self.assertRaisesRegex(Exception, "without installing content"):
                executor._validate_installed_payload(empty)
            (empty / "game.bin").write_bytes(b"provider payload")
            executor._validate_installed_payload(empty)

    def test_normalized_identity_does_not_require_metadata(self) -> None:
        game = normalize_game({"app_name": "abc", "app_title": "Owned game"},
                              provider_id_keys=("app_name",), title_keys=("app_title",))
        self.assertEqual(game, OwnedProviderGame("abc", "Owned game"))

    def test_owned_uninstalled_game_is_reconciled_to_installable(self) -> None:
        owned = OwnedProviderGame("one", "GOG One")
        installed = OwnedProviderGame("two", "GOG Two", "/home/lulu/Games/Executables/gog/two")
        with tempfile.TemporaryDirectory() as directory:
            store = CatalogueStore(Path(directory) / "catalogue.sqlite3")
            rows = store.reconcile_owned_provider("gog", (owned, installed), (installed,))
            self.assertEqual({row.game_id for row in rows}, {"gog:one", "gog:two"})
            self.assertEqual([row.game_id for row in store.list_available_games()], ["gog:one"])
            self.assertEqual([row.game_id for row in store.list_games()], ["gog:two"])
            self.assertFalse(next(row for row in rows if row.provider_id == "one").metadata_game_id)

    def test_snapshot_round_trip_is_last_known_good(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = SnapshotEntitlementSource("epic", Path(directory) / "entitlements.json")
            source.update((OwnedProviderGame("one", "One"),), ())
            restored = SnapshotEntitlementSource("epic", Path(directory) / "entitlements.json")
            self.assertEqual(restored.snapshot[0].provider_id, "one")

    def test_authentication_is_generic(self) -> None:
        self.assertEqual(GogAuthentication().status()["provider_id"], "gog")
        self.assertEqual(EpicAuthentication().status()["provider_id"], "epic")
