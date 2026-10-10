import tempfile
import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch
from pathlib import Path
import unittest

from lulu.catalogue import CatalogueStore
from lulu.plugins.external import (CliAcquisitionExecutor, OwnedProviderGame,
                                   SnapshotEntitlementSource, catalogue_authentication_state,
                                   normalize_game)
from lulu.plugins.epic import EpicAcquisitionExecutor, EpicAuthentication, EpicEntitlementSource
from lulu.plugins.gog import GogAuthentication
from lulu.jobs import DownloadJob, JobOperation
from lulu.consoled import ConsoleCatalog, ConsoleInterface
from lulu.acquisitiond import AcquisitionInterface
from lulu.job_manager import JobManager
from lulu.jobs import JobState
from lulu.job_manager import JobExecutionError


class ExternalProviderTests(unittest.TestCase):
    def test_missing_aurelia_never_falls_back_to_legacy_steam_install_inventory(self):
        class LegacySteamEntitlements:
            config = object()
            refresh = Mock()
            has_snapshot = True
            snapshot = ()

            def reload_config(self):
                return self.config

        with tempfile.TemporaryDirectory() as directory:
            steam = LegacySteamEntitlements()
            plugins = SimpleNamespace(with_capability=lambda _capability: ())
            catalog = ConsoleCatalog(
                store=CatalogueStore(Path(directory) / "catalogue.sqlite3"),
                provider=object(), steam_entitlements=steam, plugin_registry=plugins,
            )
            catalog.external_entitlements = ()
            with patch("lulu.onboarding.onboarding_state", return_value={
                    "selected_providers": ["steam"], "selected_integrations": []}):
                catalog.refresh({"steam"})

        steam.refresh.assert_not_called()
        self.assertEqual(catalog.store.list_catalogue_games(), [])

    def test_catalogue_authentication_supports_local_files_and_service_owned_sessions(self):
        with tempfile.TemporaryDirectory() as directory:
            auth_file = Path(directory) / "auth.json"
            auth_file.write_text("{}")
            self.assertEqual(catalogue_authentication_state(
                SimpleNamespace(auth_path=auth_file)), "authenticated")
        self.assertEqual(catalogue_authentication_state(
            SimpleNamespace(catalogue_authentication_status=lambda: "authenticated")),
            "authenticated")
        self.assertEqual(catalogue_authentication_state(
            SimpleNamespace(catalogue_authentication_status=lambda: "unauthenticated")),
            "unauthenticated")

    def test_aurelia_service_auth_reaches_catalogue_without_steam_fallback(self):
        class AureliaSource:
            provider_id = "steam-aurelia"
            last_error = ""
            snapshot = ()

            def __init__(self, authentication):
                self.authentication = authentication
                self.discoveries = 0

            def catalogue_authentication_status(self):
                return self.authentication

            def refresh(self):
                self.discoveries += 1
                self.snapshot = (OwnedProviderGame("440", "Team Fortress 2"),)

            def installed(self):
                return ()

        class SteamSource:
            config = object()
            refresh = Mock()

            def reload_config(self):
                return self.config

        for authentication, expected_discoveries, expected_available in (
                ("authenticated", 1, ["440"]), ("unauthenticated", 0, [])):
            with self.subTest(authentication=authentication), tempfile.TemporaryDirectory() as directory:
                aurelia = AureliaSource(authentication)
                steam = SteamSource()
                plugins = SimpleNamespace(with_capability=lambda capability: (
                    (aurelia,) if capability == "installed_catalogue" else ()))
                store = CatalogueStore(Path(directory) / "catalogue.sqlite3")
                catalog = ConsoleCatalog(store=store, provider=object(),
                                         steam_entitlements=steam, plugin_registry=plugins)
                catalog.external_entitlements = (aurelia,)
                with patch("lulu.onboarding.onboarding_state", return_value={
                        "selected_providers": ["steam"], "selected_integrations": []}):
                    catalog.refresh({"steam"})
                self.assertEqual(aurelia.discoveries, expected_discoveries)
                self.assertEqual([game.provider_id for game in store.list_available_games("steam-aurelia")],
                                 expected_available)
                steam.refresh.assert_not_called()

    def test_acquisitiond_reload_loads_rpc_secret_authenticates_and_registers_executor(self) -> None:
        executor = object()
        client = SimpleNamespace(health=AsyncMock(return_value={"version": "26.2"}))
        configuration = SimpleNamespace(
            enabled=True, configured=True,
            secret_available=lambda _name: True,
        )
        interface = object.__new__(AcquisitionInterface)
        interface._usenet_startup_config = {
            "enabled": False, "configured": False,
            "rpc_secret_available": False, "configuration_loaded": True,
            "reload_requested": False,
        }
        interface.manager = SimpleNamespace(
            executors={}, replace_executor=lambda name, value, limit: interface.manager.executors.update({name: value}))

        from lulu.provider_config import ProviderConfigurationService
        with patch.object(ProviderConfigurationService, "from_environment",
                          return_value=SimpleNamespace(provider=lambda _name: configuration)), \
                patch("lulu.plugins.usenet.build_executor", return_value=(client, executor)):
            result = asyncio.run(AcquisitionInterface.ReloadUsenetConfiguration.__wrapped__(interface))

        self.assertEqual(json.loads(result)["executor_registered"], True)
        self.assertIs(interface.manager.executors["usenet"], executor)
        client.health.assert_awaited_once()

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

    def test_epic_third_party_managed_entitlement_is_rejected_before_legendary_install(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = root / "provider-config" / "legendary"
            metadata = config / "metadata" / "Pigeon.json"
            metadata.parent.mkdir(parents=True)
            metadata.write_text(json.dumps({"metadata": {"customAttributes": {
                "ThirdPartyManagedProvider": {"type": "STRING", "value": "UbisoftConnect"},
            }}}))
            with patch("lulu.plugins.epic.PATHS", SimpleNamespace(
                    epic_library_root=root / "epic",
                    provider_config_root=lambda _provider: root / "provider-config")):
                executor = EpicAcquisitionExecutor()
                with self.assertRaises(JobExecutionError) as raised:
                    executor.command_builder("epic:Pigeon", root / "epic")
                self.assertEqual(raised.exception.code, "epic-third-party-managed")
                self.assertIn("UbisoftConnect", str(raised.exception))
                self.assertEqual(raised.exception.details["required_provider"], "UbisoftConnect")
                self.assertEqual(executor._command_for_install("epic:Pigeon", root / "epic"), [
                    "legendary", "-y", "install", "Pigeon", "--base-path", str(root / "epic"),
                    "--game-folder", "Pigeon", "--skip-sdl", "--skip-dlcs",
                ])

    def test_epic_third_party_failure_reaches_acquisition_job_with_structured_details(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            metadata = root / "provider-config" / "legendary" / "metadata" / "Pigeon.json"
            metadata.parent.mkdir(parents=True)
            metadata.write_text(json.dumps({"metadata": {"customAttributes": {
                "ThirdPartyManagedProvider": {"type": "STRING", "value": "UbisoftConnect"},
            }}}))
            with patch("lulu.plugins.epic.PATHS", SimpleNamespace(
                    epic_library_root=root / "epic",
                    provider_config_root=lambda _provider: root / "provider-config")):
                async def exercise():
                    manager = JobManager()
                    manager.register_executor("epic", EpicAcquisitionExecutor())
                    job = manager.submit("epic", "epic:Pigeon", "Trackmania Starter Access")
                    await asyncio.sleep(0.05)
                    failed = manager.jobs[job.job_id]
                    self.assertEqual(failed.state, JobState.FAILED)
                    self.assertEqual(failed.error.code, "epic-third-party-managed")
                    self.assertEqual(failed.error.details["required_provider"], "UbisoftConnect")

                asyncio.run(exercise())

    def test_epic_third_party_entitlement_is_not_projected_as_installable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            provider_root = root / "provider"
            config_dir = root / "config" / "legendary"
            metadata = config_dir / "metadata" / "Pigeon.json"
            metadata.parent.mkdir(parents=True)
            metadata.write_text(json.dumps({"metadata": {"customAttributes": {
                "ThirdPartyManagedProvider": {"type": "STRING", "value": "UbisoftConnect"},
            }}}))
            with patch("lulu.plugins.epic.PATHS", SimpleNamespace(
                    provider_root=lambda _provider: provider_root,
                    provider_config_root=lambda _provider: root / "config",
                    epic_library_root=root / "epic")):
                source = EpicEntitlementSource()
                source._json = lambda command: ([{"app_name": "Pigeon", "app_title": "Trackmania"}]
                                                if command[1] == "list" else [])
                owned = source.refresh()
                self.assertEqual(owned[0].availability_state, "unavailable")
                store = CatalogueStore(root / "catalogue.sqlite3")
                store.reconcile_owned_provider("epic", source.snapshot, source.installed())
                row = store.get_game("epic:Pigeon")
                self.assertEqual(row.availability_state, "unavailable")
                self.assertEqual(store.list_available_games("epic"), [])
                store.connection.close()

    def test_epic_installed_discovery_is_confined_to_canonical_provider_root(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            epic_root = root / "Games" / "Executables" / "epic"
            inside = epic_root / "EpicApp"
            outside = root / "other-store" / "OtherApp"
            inside.mkdir(parents=True)
            outside.mkdir(parents=True)
            (inside / "game.bin").write_bytes(b"payload")
            (outside / "game.bin").write_bytes(b"payload")
            with patch("lulu.plugins.epic.PATHS", SimpleNamespace(
                    provider_root=lambda _provider: root / "provider",
                    provider_config_root=lambda _provider: root / "config",
                    epic_library_root=epic_root)):
                source = EpicEntitlementSource()
                source._json = lambda _command: [
                    {"app_name": "EpicApp", "app_title": "Epic App", "install_path": str(inside)},
                    {"app_name": "OtherApp", "app_title": "Other Store App", "install_path": str(outside)},
                    {"app_name": "WrongFolder", "app_title": "Wrong Folder", "install_path": str(inside)},
                ]
                found = source.installed()
                self.assertEqual([game.provider_id for game in found], ["EpicApp"])
                self.assertEqual(found[0].install_dir, str(inside))

    def test_epic_zero_exit_without_payload_keeps_bounded_legendary_error(self) -> None:
        class Output:
            async def __aiter__(self):
                yield b"[cli] ERROR: selected game is managed by another store\n"

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
            with patch("lulu.plugins.epic.PATHS", SimpleNamespace(
                    epic_library_root=root / "epic",
                    provider_config_root=lambda _provider: root / "provider-config")), \
                    patch("lulu.plugins.external.asyncio.create_subprocess_exec",
                          return_value=Process()):
                executor = EpicAcquisitionExecutor()
                job = DownloadJob("job-epic", "epic", "Fixture", "epic:FixtureApp")
                with self.assertRaises(JobExecutionError) as raised:
                    asyncio.run(executor.run(job, Reporter()))
                self.assertEqual(raised.exception.code, "provider-install-incomplete")
                self.assertEqual(raised.exception.details["return_code"], 0)
                self.assertIn("managed by another store", raised.exception.details["provider_message"])
                self.assertIn("Legendary reported", str(raised.exception))

    def test_epic_cli_diagnostics_redact_secrets_and_bound_provider_message(self) -> None:
        executor = EpicAcquisitionExecutor()
        line = "ERROR password=hunter2 " + ("x" * 1000)
        diagnostic = executor._diagnostic_line(line)
        self.assertNotIn("hunter2", diagnostic)
        self.assertLessEqual(len(diagnostic), 400)

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
