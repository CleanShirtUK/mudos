import tempfile
import asyncio
import json
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
from lulu.consoled import ConsoleCatalog, ConsoleInterface
from lulu.acquisitiond import AcquisitionInterface
from lulu.job_manager import JobManager
from lulu.jobs import JobState


class ExternalProviderTests(unittest.TestCase):
    def test_acquisitiond_reports_secret_free_loaded_usenet_executor_status(self) -> None:
        interface = object.__new__(AcquisitionInterface)
        interface._usenet_startup_config = {
            "enabled": True, "configured": True, "rpc_secret_available": True,
        }
        interface.manager = SimpleNamespace(executors={"usenet": object()})
        self.assertEqual(json.loads(AcquisitionInterface.GetUsenetReadiness.__wrapped__(interface)), {
            "provider": "usenet", "enabled": True, "configured": True,
            "rpc_secret_available": True, "executor_registered": True,
        })

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

    def test_gog_completion_refresh_projects_library_and_dispatches_managed_launch(self) -> None:
        from unittest.mock import AsyncMock, Mock
        from lulu.plugins.gog import GogEntitlementSource, GogLauncher

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            library = root / "Games" / "Executables" / "gog"
            install = library / "black-flower"
            payload = install / "game" / "gameinfo"
            payload.parent.mkdir(parents=True)
            payload.write_text("fixture")
            (install / ".mudos-game.json").write_text(json.dumps({
                "provider_id": "black-flower", "title": "Black Flower",
                "install_dir": str(install),
            }))
            auth_path = root / "config" / "heroic" / "gog_store" / "auth.json"
            auth_path.parent.mkdir(parents=True)
            auth_path.write_text("{}")

            class Plugins:
                def with_capability(self, capability):
                    if capability == "installed_catalogue":
                        return (GogEntitlementSource(),)
                    return ()

            with patch("lulu.plugins.gog.PATHS", SimpleNamespace(
                    provider_root=lambda _id: root / "state",
                    provider_config_root=lambda _id: root / "config",
                    gog_library_root=library)), \
                    patch("lulu.onboarding.onboarding_state", return_value={
                        "selected_providers": ["gog"], "selected_integrations": []}), \
                    patch("lulu.consoled._load_plugin_registry", return_value=Plugins()):
                source = GogEntitlementSource()
                # A failed entitlement network sync must still leave the
                # Mudos-owned installation marker eligible for projection.
                source.refresh = Mock(return_value=())
                source._last_good = ()
                plugins = Plugins()
                plugins.with_capability = Mock(side_effect=lambda capability: (
                    (source,) if capability == "installed_catalogue" else ()))
                store = CatalogueStore(root / "catalogue.sqlite3")
                catalog = ConsoleCatalog(store=store, plugin_registry=plugins)
                catalog.external_entitlements = (source,)
                job = DownloadJob("completed-gog", "gog", "Black Flower",
                                  content_identity="gog:black-flower", state=JobState.COMPLETED)
                manager = JobManager()
                manager.jobs[job.job_id] = job

                class Bus:
                    async def introspect(self, *_args):
                        return object()
                    def get_proxy_object(self, *_args):
                        class Proxy:
                            @staticmethod
                            def get_interface(_name):
                                class Consoled:
                                    @staticmethod
                                    async def call_refresh_stages(stages):
                                        self_ref = catalog
                                        self_ref.refresh(set(stages))
                                return Consoled()
                        return Proxy()

                acquisition = AcquisitionInterface(manager, store, plugins, bus=Bus())
                asyncio.run(acquisition._reconcile_completed_job(job.job_id))

                game = store.get_game("gog:black-flower")
                self.assertIsNotNone(game)
                self.assertEqual(game.install_state, "installed")
                self.assertTrue(game.launchable)
                self.assertEqual(game.install_dir, str(install))

                session = SimpleNamespace(
                    call_set_delegated_launch_context=AsyncMock(),
                    call_request_game_launch=AsyncMock(return_value="token"),
                )
                interface = object.__new__(ConsoleInterface)
                interface.catalogue = catalog
                interface._plugins = SimpleNamespace(with_capability=lambda _cap: (GogLauncher(),))
                interface.sessiond = session
                interface._publish_delta = Mock()
                interface.CatalogueChanged = Mock()
                with patch("lulu.plugins.gog.PATHS", SimpleNamespace(
                        gog_library_root=library,
                        provider_config_root=lambda _id: root / "config")):
                    command = GogLauncher().launch_command("black-flower")
                self.assertEqual(command[command.index("launch") + 1], str(payload.parent))
                self.assertEqual(asyncio.run(ConsoleInterface.LaunchGame.__wrapped__(
                    interface, game.game_id, 15000)), "token")
                session.call_request_game_launch.assert_awaited_once_with(game.game_id, command, 15000)

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
