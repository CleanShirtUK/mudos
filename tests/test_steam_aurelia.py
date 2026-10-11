from __future__ import annotations

import asyncio
import json
import logging
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import AsyncMock, Mock, patch

from lulu.jobs import DownloadJob, JobOperation, JobState
from lulu.jobs import JobError
from lulu.acquisitiond import AcquisitionInterface
from lulu.acquisition_store import AcquisitionStore
from lulu.job_manager import JobExecutionError, JobManager, JobReporter
from lulu.plugins.steam.aurelia import (
    AureliaAcquisitionExecutor, AureliaCapabilities, AureliaClient, AureliaInstalledGame,
    AureliaEntitlementSource,
    AureliaError, PROVIDER_ID, map_progress,
)
from lulu.paths import PATHS
from lulu.provider_config import ProviderConfigurationService
from lulu.catalogue import CatalogueStore


class AureliaClientTests(unittest.IsolatedAsyncioTestCase):
    @staticmethod
    def update_fixture(tmp: str, *, installed: dict[str, str], remote: list[dict[str, object]],
                       state_flags: int = 4, branch: str = "public",
                       command_error: bool = False):
        root = Path(tmp) / "steamapps"
        game_dir = root / "common" / "Fixture"
        game_dir.mkdir(parents=True)
        installed_rows = "\n".join(
            f'        "{depot}" {{ "manifest" "{manifest}" }}'
            for depot, manifest in installed.items())
        beta = f'    "UserConfig" {{ "BetaKey" "{branch}" }}\n' if branch != "public" else ""
        raw = (f'"AppState" {{ "appid" "48000" "StateFlags" "{state_flags}" '
               f'"installdir" "Fixture" {beta} "InstalledDepots" {{ {installed_rows} }} }}')
        (root / "appmanifest_48000.acf").write_text(raw)
        def run(argv, **_kwargs):
            if argv[-2:] == ["list", "--installed"]:
                return 0, json.dumps([{"app_id": 48000, "name": "Fixture",
                    "is_installed": True, "install_path": str(game_dir)}]), ""
            if argv[-2:] == ["manifests", "48000"]:
                if command_error:
                    return 1, "", "provider response unavailable"
                return 0, json.dumps(remote), ""
            raise AssertionError(f"unexpected official Aurelia command: {argv}")
        return AureliaClient("fake", Path(tmp) / "aurelia", run=run), root / "appmanifest_48000.acf"

    async def test_aurelia_entitlements_reconcile_to_installable_without_installed_duplicate(self):
        with tempfile.TemporaryDirectory() as temp:
            store = CatalogueStore(Path(temp) / "catalogue.sqlite")
            owned = (
                type("Owned", (), {"provider_id": "440", "title": "Team Fortress 2",
                                    "platform": "Steam", "artwork_url": "art"})(),
                type("Owned", (), {"provider_id": "730", "title": "Counter-Strike 2",
                                    "platform": "Steam", "artwork_url": ""})(),
            )
            installed = (AureliaInstalledGame(PROVIDER_ID, "730", "Counter-Strike 2", True,
                                               "/games/cs2", "linux", False),)
            games = store.reconcile_owned_provider(PROVIDER_ID, owned, installed)
            installable = store.list_available_games()
            self.assertEqual([game.provider_id for game in installable], ["440"])
            self.assertEqual(installable[0].provider, "steam-aurelia")
            self.assertEqual(installable[0].provider_id, "440")
            installed_game = next(game for game in games if game.provider_id == "730")
            self.assertEqual(installed_game.install_state, "installed")
            self.assertEqual(installed_game.install_dir, "/games/cs2")
            self.assertIn("730", [game.provider_id for game in store.list_games("steam")])

    async def test_entitlement_source_filters_nonowned_and_preserves_installed_metadata(self):
        responses = iter([
            (0, json.dumps({"logged_in": True}), ""),
            (0, json.dumps([
                {"app_id": 440, "name": "Team Fortress 2", "is_owned": True,
                 "is_installed": False, "assets": {"header": "https://art/440.jpg"}},
                {"app_id": 730, "name": "Counter-Strike 2", "is_owned": True,
                 "is_installed": True, "install_path": "/steam/cs2", "platform": "linux",
                 "update_available": True},
                {"app_id": 999, "name": "Not owned", "is_owned": False,
                 "is_installed": False},
            ]), ""),
        ])
        client = AureliaClient("fake", Path(tempfile.mkdtemp()),
                               run=lambda *a, **kw: next(responses))
        source = AureliaEntitlementSource(client)
        await asyncio.to_thread(source.refresh)
        self.assertEqual([entry.provider_id for entry in source.snapshot], ["440", "730"])
        self.assertEqual(source.snapshot[0].artwork_url, "https://art/440.jpg")
        self.assertEqual([entry.app_id for entry in source.installed()], ["730"])
        self.assertEqual(source.installed()[0].install_dir, "/steam/cs2")
        self.assertTrue(source.installed()[0].update_available)

    async def test_entitlement_source_does_not_fall_back_when_unauthenticated(self):
        client = AureliaClient("fake", Path(tempfile.mkdtemp()),
                               run=lambda *a, **kw: (0, json.dumps({"logged_in": False}), ""))
        source = AureliaEntitlementSource(client)
        await asyncio.to_thread(source.refresh)
        self.assertEqual(source.auth_status, "unauthenticated")
        self.assertEqual(source.snapshot, ())
        self.assertEqual(source.last_error, "unauthenticated")

    async def test_auth_health_states_and_secret_free_errors(self):
        for payload, expected in [
            ({"logged_in": False}, "unauthenticated"),
            ({"logged_in": True}, "authenticated"),
            ({"authentication_required": True}, "authentication-required"),
            ({"session_expired": True}, "authentication-expired"),
        ]:
            client = AureliaClient("fake", Path(tempfile.mkdtemp()),
                                  run=lambda *a, value=payload, **kw: (0, json.dumps(value), ""))
            self.assertEqual(await client.auth_status(), expected)

        def fail(*_args, **_kwargs):
            return 1, "", "refresh_token=must-not-leak"
        client = AureliaClient("fake", Path(tempfile.mkdtemp()), run=fail)
        with self.assertRaises(AureliaError) as caught:
            await client.command("login", "--health")
        self.assertNotIn("must-not-leak", str(caught.exception))

    async def test_missing_and_malformed_output(self):
        self.assertEqual(await AureliaClient("/nonexistent/aurelia").auth_status(), "unavailable")
        client = AureliaClient("fake", Path(tempfile.mkdtemp()), run=lambda *a, **kw: (0, "{", ""))
        with self.assertRaises(AureliaError) as caught:
            await client.command("libraries")
        self.assertEqual(caught.exception.code, "malformed-output")

    async def test_installed_game_mapping(self):
        client = AureliaClient("fake", Path(tempfile.mkdtemp()),
                               run=lambda *a, **kw: (0, json.dumps([{
                                   "app_id": 40800, "name": "Super Meat Boy",
                                   "is_installed": True,
                                   "install_path": "/steamapps/common/Super Meat Boy",
                                   "platform": "linux", "update_available": False,
                               }]), ""))
        (game,) = await client.installed_games()
        self.assertEqual(game.provider, "steam-aurelia")
        self.assertEqual(game.app_id, "40800")
        self.assertTrue(game.installed)
        self.assertEqual(game.platform, "linux")

    async def test_daemon_config_directory_is_private(self):
        root = Path(tempfile.mkdtemp()) / "aurelia"
        client = AureliaClient("fake", root, run=lambda *a, **kw: (0, "{}", ""))
        await client.command("libraries")
        self.assertEqual(root.stat().st_mode & 0o777, 0o700)
        config = json.loads((root / "config.json").read_text())
        self.assertEqual(config["steam_library_path"], str(PATHS.steam_library_root))
        self.assertFalse(config["enable_cloud_sync"])
        self.assertEqual((root / "config.json").stat().st_mode & 0o777, 0o600)

    async def test_daemon_socket_is_stable_for_the_mudos_runtime(self):
        client = AureliaClient("fake", Path(tempfile.mkdtemp()),
                               run=lambda *a, **kw: (0, "{}", ""))
        with tempfile.TemporaryDirectory() as runtime:
            with patch.dict(os.environ, {"XDG_RUNTIME_DIR": runtime}):
                env = client._environment()
            self.assertEqual(env["AURELIA_DAEMON_SOCKET"],
                             f"{runtime}/aurelia-{os.geteuid()}.sock")

    async def test_acquisition_environment_does_not_gain_graphical_session_values(self):
        client = AureliaClient("fake", Path(tempfile.mkdtemp()),
                               run=lambda *a, **kw: (0, "{}", ""))
        with patch.dict(os.environ, {"DISPLAY": "", "WAYLAND_DISPLAY": "",
                                     "XDG_RUNTIME_DIR": "/run/user/test"}):
            env = client._environment()
        self.assertFalse(env.get("DISPLAY"))
        self.assertFalse(env.get("WAYLAND_DISPLAY"))

    async def test_existing_noncanonical_library_fails_closed(self):
        root = Path(tempfile.mkdtemp()) / "aurelia"
        root.mkdir(mode=0o700)
        (root / "config.json").write_text(json.dumps({"steam_library_path": "/not/the/mudos/library"}))
        client = AureliaClient("fake", root, run=lambda *a, **kw: (0, "{}", ""))
        with self.assertRaises(AureliaError) as caught:
            await client.command("libraries")
        self.assertEqual(caught.exception.code, "library-path-mismatch")

    async def test_windows_depot_current_ignores_newer_uninstalled_linux_depot(self):
        with tempfile.TemporaryDirectory() as tmp:
            client, _ = self.update_fixture(tmp, installed={"48001": "101"}, remote=[
                {"depot_id": 48001, "branch": "public", "manifest_id": 101},
                {"depot_id": 48004, "branch": "public", "manifest_id": 999},
            ])
            result = await client.update_availability("48000", force=True)
            self.assertEqual(result["status"], "current")
            self.assertEqual(result["target_depots"], {"48001": "101"})

    async def test_linux_depot_current_ignores_newer_uninstalled_windows_depot(self):
        with tempfile.TemporaryDirectory() as tmp:
            client, _ = self.update_fixture(tmp, installed={"48004": "202"}, remote=[
                {"depot_id": 48004, "branch": "public", "manifest_id": 202},
                {"depot_id": 48001, "branch": "public", "manifest_id": 999},
            ])
            self.assertEqual((await client.update_availability("48000", force=True))["status"], "current")

    async def test_changed_installed_manifest_is_update_available(self):
        with tempfile.TemporaryDirectory() as tmp:
            client, _ = self.update_fixture(tmp, installed={"48001": "101", "48002": "102"}, remote=[
                {"depot_id": 48001, "branch": "public", "manifest_id": 101},
                {"depot_id": 48002, "branch": "public", "manifest_id": 103},
            ])
            result = await client.update_availability("48000", force=True)
            self.assertEqual(result["status"], "update-available")
            self.assertEqual(result["changed_depots"], {"48002": {"installed": "102", "target": "103"}})

    async def test_matching_manifests_with_update_required_flag_are_inconsistent(self):
        with tempfile.TemporaryDirectory() as tmp:
            client, _ = self.update_fixture(tmp, installed={"48001": "101"}, state_flags=6,
                remote=[{"depot_id": 48001, "branch": "public", "manifest_id": 101}])
            result = await client.update_availability("48000", force=True)
            self.assertEqual(result["status"], "inconsistent")
            self.assertTrue(result["state_update_required"])

    async def test_missing_remote_depot_is_unverifiable(self):
        with tempfile.TemporaryDirectory() as tmp:
            client, _ = self.update_fixture(tmp, installed={"48001": "101"}, remote=[])
            result = await client.update_availability("48000", force=True)
            self.assertEqual(result["status"], "unverifiable")
            self.assertFalse(result["available"])

    async def test_nonpublic_branch_common_and_additional_installed_depots(self):
        with tempfile.TemporaryDirectory() as tmp:
            client, _ = self.update_fixture(tmp, installed={"48001": "101", "48002": "202"},
                branch="beta", remote=[
                    {"depot_id": 48001, "branch": "public", "manifest_id": 999},
                    {"depot_id": 48001, "branch": "beta", "manifest_id": 101},
                    {"depot_id": 48002, "branch": "beta", "manifest_id": 202},
                    {"depot_id": 48004, "branch": "beta", "manifest_id": 999},
                ])
            result = await client.update_availability("48000", force=True)
            self.assertEqual(result["branch"], "beta")
            self.assertEqual(result["status"], "current")
            self.assertEqual(set(result["target_depots"]), {"48001", "48002"})

    async def test_missing_installed_depot_record_and_provider_failure_are_unverifiable(self):
        with tempfile.TemporaryDirectory() as tmp:
            client, appmanifest = self.update_fixture(tmp, installed={}, remote=[])
            result = await client.update_availability("48000", force=True)
            self.assertEqual(result["status"], "unverifiable")
        with tempfile.TemporaryDirectory() as tmp:
            client, _ = self.update_fixture(tmp, installed={"48001": "101"}, remote=[], command_error=True)
            result = await client.update_availability("48000", force=True)
            self.assertEqual(result["status"], "unverifiable")
            self.assertEqual(result["provider_error_code"], "command-failed")

    async def test_update_availability_cache_is_app_scoped_and_force_refreshes_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            client, appmanifest = self.update_fixture(tmp, installed={"48001": "101"}, remote=[
                {"depot_id": 48001, "branch": "public", "manifest_id": 101}])
            current = await client.update_availability("48000")
            appmanifest.write_text(appmanifest.read_text().replace('"101"', '"100"'))
            cached = await client.update_availability("48000")
            fresh = await client.update_availability("48000", force=True)
            self.assertEqual(current["status"], "current")
            self.assertEqual(cached["status"], "current")
            self.assertEqual(fresh["status"], "update-available")

    async def test_available_platforms_requires_explicit_depot_os_metadata(self):
        client = AureliaClient(run=lambda _argv, **_kwargs: (0, json.dumps({"app_id": 1, "depots": [
            {"id": 10, "config": "os: windows"},
            {"id": 11, "config": "os: linux, lang: english"},
            {"id": 12, "config": {}},
        ]}), ""))
        self.assertEqual(await client.available_platforms("1"), ("windows", "linux"))
        unknown = AureliaClient(run=lambda _argv, **_kwargs: (0, json.dumps({"depots": [
            {"id": 12, "config": {}}
        ]}), ""))
        self.assertEqual(await unknown.available_platforms("1"), ())

class AureliaAcquisitionTests(unittest.IsolatedAsyncioTestCase):
    async def test_update_job_runs_only_when_available_and_verifies_completion(self):
        class Client:
            def __init__(self): self.updates = 0; self.checks = 0
            async def command(self, *args, **kwargs):
                self.assert_command = args
                return []
            async def update_availability(self, _app_id, *, force=False):
                self.checks += 1
                return {"status": "update-available" if self.checks == 1 else "current",
                        "available": self.checks == 1, "reason": "fixture",
                        "installed_depots": {"48001": "1"}, "target_depots": {"48001": "2"}}
            async def update(self, _app_id): self.updates += 1
            async def installed_games(self):
                return (AureliaInstalledGame(PROVIDER_ID, "48000", "LIMBO", True,
                                             "/steam/common/Limbo", "windows", False),)
        client = Client()
        manager = JobManager()
        executor = AureliaAcquisitionExecutor(client)
        executor._steam_provider.presentation_pids = lambda _app_id: []
        manager.register_executor(PROVIDER_ID, executor)
        job = DownloadJob("update-1", PROVIDER_ID, "LIMBO",
                          content_identity="steam-aurelia:48000",
                          provider_job_id="48000", operation=JobOperation.UPDATE,
                          cancellation_supported=False, pause_supported=False)
        manager.jobs[job.job_id] = job
        await executor.run(job, JobReporter(manager, job.job_id))
        self.assertEqual(client.updates, 1)
        self.assertEqual(manager.jobs[job.job_id].state, JobState.COMPLETED)
        self.assertIsNone(manager.jobs[job.job_id].progress)
        self.assertFalse(manager.jobs[job.job_id].cancellation_supported)
        self.assertFalse(manager.jobs[job.job_id].pause_supported)


class SteamUpdateAcquisitionInterfaceTests(unittest.IsolatedAsyncioTestCase):
    @staticmethod
    def evidence():
        return {"app_id": "48000", "status": "update-available", "available": True,
                "branch": "public", "state_flags": 6, "state_update_required": True,
                "installed_depots": {"48001": "1"}, "target_depots": {"48001": "2"},
                "changed_depots": {"48001": {"installed": "1", "target": "2"}}}

    async def test_check_exposes_unresolved_noop_but_keeps_real_availability_visible(self):
        client = Mock(available=True)
        client.update_availability = AsyncMock(return_value=self.evidence())
        executor = Mock(client=client)
        manager = JobManager()
        previous_evidence = self.evidence()
        previous = DownloadJob(
            "failed-noop", PROVIDER_ID, "LIMBO", content_identity="steam-aurelia:48000",
            provider_job_id="48000", operation=JobOperation.UPDATE, state=JobState.FAILED,
            error=JobError("steam-update-unapplied", "No depot transition", False,
                           {"phase": "after", "evidence": previous_evidence}),
            retryable=False,
        )
        manager.jobs[previous.job_id] = previous
        manager.executors[PROVIDER_ID] = executor
        interface = object.__new__(AcquisitionInterface)
        interface.manager = manager
        value = json.loads(await AcquisitionInterface.CheckSteamUpdate.__wrapped__(interface, "48000"))
        self.assertEqual(value["status"], "inconsistent")
        self.assertTrue(value["available"])
        self.assertEqual(value["actual_status"], "update-available")
        self.assertTrue(value["unresolved_previous_attempt"])

    async def test_submit_refuses_same_evidence_after_nonconvergent_update(self):
        client = Mock(available=True)
        client.update_availability = AsyncMock(return_value=self.evidence())
        executor = Mock(client=client, capabilities=AureliaCapabilities())
        manager = JobManager()
        previous = DownloadJob(
            "failed-noop", PROVIDER_ID, "LIMBO", content_identity="steam-aurelia:48000",
            provider_job_id="48000", operation=JobOperation.UPDATE, state=JobState.FAILED,
            error=JobError("steam-update-unapplied", "No depot transition", False,
                           {"phase": "after", "evidence": self.evidence()}),
            retryable=False,
        )
        manager.jobs[previous.job_id] = previous
        manager.executors[PROVIDER_ID] = executor
        interface = object.__new__(AcquisitionInterface)
        interface.manager = manager
        interface.bus = None
        with self.assertRaises(Exception) as caught:
            await AcquisitionInterface.SubmitSteamUpdate.__wrapped__(interface, "48000", "LIMBO", "background")
        self.assertIn("did not converge", str(caught.exception))
        self.assertEqual(len(manager.jobs), 1)

    async def test_recovered_update_never_resubmits_when_update_remains_available(self):
        class Client:
            updates = 0
            async def command(self, *_args, **_kwargs): return []
            async def update_availability(self, _app_id, *, force=False):
                return {"status": "update-available", "available": True,
                        "reason": "unchanged", "installed_depots": {"48001": "1"},
                        "target_depots": {"48001": "2"}}
            async def update(self, _app_id): self.updates += 1
        client = Client()
        executor = AureliaAcquisitionExecutor(client)
        executor._steam_provider.presentation_pids = lambda _app_id: []
        job = DownloadJob("update-recovered", PROVIDER_ID, "LIMBO",
                          content_identity="steam-aurelia:48000",
                          provider_job_id="48000", operation=JobOperation.UPDATE,
                          recovery_reason="service-restart")
        reporter = Mock()
        reporter.metadata = AsyncMock()
        reporter.state = AsyncMock()
        reporter.progress = AsyncMock()
        with self.assertRaisesRegex(JobExecutionError, "not restarted automatically"):
            await executor.run(job, reporter)
        self.assertEqual(client.updates, 0)
        self.assertTrue(any(call.kwargs.get("origin_metadata", {}).get("launch_intent") == "none"
                            for call in reporter.metadata.await_args_list))

    async def test_successful_command_without_manifest_transition_is_nonretryable(self):
        class Client:
            checks = 0
            updates = 0
            async def command(self, *_args, **_kwargs): return []
            async def update_availability(self, _app_id, *, force=False):
                self.checks += 1
                return {"status": "update-available", "available": True,
                        "reason": "same installed depot remains old", "branch": "public",
                        "state_flags": 6, "state_update_required": True,
                        "installed_depots": {"48001": "1"}, "target_depots": {"48001": "2"},
                        "changed_depots": {"48001": {"installed": "1", "target": "2"}}}
            async def update(self, _app_id): self.updates += 1
        client = Client()
        executor = AureliaAcquisitionExecutor(client)
        executor._steam_provider.presentation_pids = lambda _app_id: []
        job = DownloadJob("update-noop", PROVIDER_ID, "LIMBO",
                          content_identity="steam-aurelia:48000", provider_job_id="48000",
                          operation=JobOperation.UPDATE)
        reporter = Mock()
        reporter.metadata = AsyncMock()
        reporter.state = AsyncMock()
        reporter.progress = AsyncMock()
        with self.assertRaisesRegex(JobExecutionError, "update-available after") as caught:
            await executor.run(job, reporter)
        self.assertEqual(caught.exception.code, "steam-update-unapplied")
        self.assertFalse(caught.exception.retryable)
        self.assertEqual(caught.exception.details["phase"], "after")
        self.assertEqual(client.updates, 1)

    async def test_uninstall_uses_aurelia_app_id_command_and_reconciles_installed_list(self):
        client = Mock()
        client.command = AsyncMock(return_value={"success": True})
        client.installed_games = AsyncMock(return_value=())
        executor = AureliaAcquisitionExecutor(client)
        job = DownloadJob("remove-1", PROVIDER_ID, "Fixture",
                          content_identity="steam-aurelia:1245620",
                          provider_job_id="1245620", operation=JobOperation.REMOVE)
        manager = JobManager()
        manager.jobs[job.job_id] = job
        reporter = JobReporter(manager, job.job_id)

        await executor.run(job, reporter)

        client.command.assert_awaited_once_with("uninstall", "1245620")
        client.installed_games.assert_awaited_once_with()
        self.assertEqual(manager.jobs[job.job_id].state, JobState.COMPLETED)
        self.assertEqual(manager.jobs[job.job_id].progress, 1.0)

    async def test_uninstall_fails_if_aurelia_still_reports_app_installed(self):
        client = Mock()
        client.command = AsyncMock(return_value=None)
        client.installed_games = AsyncMock(return_value=(
            AureliaInstalledGame(PROVIDER_ID, "1245620", "Fixture", True,
                                 None, None, None),))
        reporter = Mock()
        reporter.metadata = AsyncMock()
        reporter.state = AsyncMock()
        reporter.progress = AsyncMock()
        executor = AureliaAcquisitionExecutor(client)
        job = DownloadJob("remove-2", PROVIDER_ID, "Fixture",
                          content_identity="steam-aurelia:1245620",
                          provider_job_id="1245620", operation=JobOperation.REMOVE)

        with self.assertRaisesRegex(JobExecutionError, "still reports the game installed"):
            await executor.run(job, reporter)

    async def test_progress_mapping_preserves_unknown_fields(self):
        mapped = map_progress({"event": "progress", "state": "downloading",
                               "bytes_downloaded": 64, "total_bytes": 128, "percent": 50,
                               "speed_bps": 1024, "eta_seconds": 20})
        self.assertEqual(mapped["downloaded_bytes"], 64)
        self.assertEqual(mapped["total_bytes"], 128)
        self.assertEqual(mapped["progress"], 0.5)
        self.assertEqual(mapped["download_rate"], 1024)
        self.assertEqual(mapped["eta_seconds"], 20)
        listed = map_progress({"app_id": 123, "downloaded_bytes": 80,
                               "total_bytes": 100, "percent": 80,
                               "status": "Downloading"})
        self.assertEqual(listed["downloaded_bytes"], 80)
        self.assertEqual(listed["stage"], "Downloading")
        self.assertEqual(map_progress({"state": "verifying"})["progress"], None)

    async def test_executor_maps_success_and_failure(self):
        class Client:
            async def command(self, *_args): return []
            async def install_events(self, _app_id, platform):
                self.platform = platform
                yield {"event": "progress", "state": "downloading",
                       "bytes_downloaded": 2, "total_bytes": 4, "percent": 50,
                       "speed_bps": 12, "eta_seconds": 1}
            async def installed_games(self):
                from lulu.plugins.steam.aurelia import AureliaInstalledGame
                return (AureliaInstalledGame(PROVIDER_ID, "123", "Example", True,
                                             "/steam/common/Example", "windows", False),)

        class Reporter:
            def __init__(self): self.events = []
            async def state(self, state, **kw): self.events.append(("state", state, kw))
            async def progress(self, progress=None, **kw): self.events.append(("progress", progress, kw))
            async def metadata(self, **kw): self.events.append(("metadata", kw))

        reporter = Reporter()
        client = Client()
        executor = AureliaAcquisitionExecutor(client)
        job = DownloadJob("job", PROVIDER_ID, "Example", content_identity="steam-aurelia:123",
                          origin_metadata={"steam_platform": "windows"})
        await executor.run(job, reporter)
        self.assertEqual(client.platform, "windows")
        self.assertIn(("state", JobState.COMPLETED, {"stage": "completed"}), reporter.events)
        progress = next(event for event in reporter.events if event[0] == "progress")
        self.assertEqual(progress[2]["downloaded_bytes"], 2)
        final_progress = [event for event in reporter.events if event[0] == "progress"][-1]
        self.assertEqual(final_progress[1], 1.0)
        self.assertEqual(final_progress[2]["downloaded_bytes"], 2)
        self.assertEqual(final_progress[2]["total_bytes"], 4)
        metadata = [event[1] for event in reporter.events if event[0] == "metadata"]
        self.assertTrue(any(item.get("destination") == "/steam/common/Example" for item in metadata))
        self.assertTrue(any(item.get("provider_job_id") == "123" for item in metadata))

    async def test_successful_job_persists_aurelia_telemetry_and_destination(self):
        class Client:
            async def command(self, *_args):
                return []
            async def install_events(self, _app_id, _platform):
                yield {"event": "progress", "state": "downloading",
                       "bytes_downloaded": 90, "total_bytes": 100,
                       "percent": 90.0, "speed_bps": 40, "eta_seconds": 1,
                       "depot_id": 42, "depot_bytes_downloaded": 45,
                       "depot_total_bytes": 50, "depot_percent": 90.0,
                       "file": "depot_chunk_01"}
            async def installed_games(self):
                return (AureliaInstalledGame(PROVIDER_ID, "123", "Example", True,
                                             "/steamapps/common/Example", "windows", False),)

        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "jobs.sqlite3"
            store = AcquisitionStore(database)
            manager = JobManager(store=store)
            manager.register_executor(PROVIDER_ID, AureliaAcquisitionExecutor(Client()))
            job = manager.submit(PROVIDER_ID, "steam-aurelia:123", "Example",
                                 provider_job_id="123", cancellation_supported=True,
                                 origin_metadata={"steam_platform": "windows"})
            task = manager._tasks[job.job_id]
            await task
            restored_store = AcquisitionStore(database)
            (restored,) = [item for item in restored_store.load() if item.job_id == job.job_id]
            self.assertEqual(restored.state, JobState.COMPLETED, str(restored.error))
            self.assertEqual(restored.provider_job_id, "123")
            self.assertEqual(restored.backend, "aurelia")
            self.assertEqual(restored.provider_state, "installed")
            self.assertEqual(restored.downloaded_bytes, 90)
            self.assertEqual(restored.total_bytes, 100)
            self.assertEqual(restored.destination, "/steamapps/common/Example")
            self.assertEqual(restored.completion_path, "/steamapps/common/Example")
            self.assertEqual(restored.origin_metadata["aurelia_progress"]["depot_id"], 42)
            self.assertEqual(restored.origin_metadata["aurelia_progress"]["file"], "depot_chunk_01")
            restored_store.close()
            store.close()

    async def test_cancel_waits_for_aurelia_active_registry_to_clear(self):
        calls = []
        def run(argv, **_kwargs):
            args = tuple(argv[2:])
            calls.append(args)
            if args[:2] == ("install", "stop"):
                value = {"event": "stopping", "app_id": 123}
            elif len(calls) == 2:
                value = [{"app_id": 123, "is_downloading": True}]
            else:
                value = []
            return 0, json.dumps(value), ""

        client = AureliaClient("fake", Path(tempfile.mkdtemp()), run=run)
        await client.cancel_install("123", timeout=1)
        self.assertEqual(calls[0], ("install", "stop", "123"))
        self.assertEqual(calls[1], ("install", "list"))
        self.assertEqual(calls[-1], ("install", "list"))


class AureliaLaunchTests(unittest.IsolatedAsyncioTestCase):
    def test_launch_failure_detail_uses_verification_when_stage_event_is_missing(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory)
            session = config / "logs" / "session-one"
            session.mkdir(parents=True)
            (session / "summary.json").write_text(json.dumps({
                "app_id": 2706170,
                "result": "Failure",
                "timestamp": 100,
                "verification": {
                    "status": "failed_after_spawn",
                    "detailed_status": "missing_required_module",
                    "exit_code": 1,
                },
            }))
            (session / "events.jsonl").write_text('{"event_type":"launch_final_status"}\n')
            client = AureliaClient(executable="aurelia", config_dir=config, run=lambda *_a, **_k: None)
            self.assertEqual(
                client.launch_failure_detail("2706170", 100),
                "Launch verification missing required module (exit code 1)",
            )

    def test_launch_failure_detail_does_not_require_failure_result_if_event_has_stage_error(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory)
            session = config / "logs" / "session-one"
            session.mkdir(parents=True)
            (session / "summary.json").write_text(json.dumps({
                "app_id": 2706170,
                "result": "Success",
                "timestamp": 100,
                "verification": {"detailed_status": "game_executable_not_found"},
            }))
            (session / "events.jsonl").write_text(json.dumps({
                "event_type": "stage_failure",
                "stage": "SpawnProcess",
                "metadata": {"error_message": "process could not start"},
            }) + "\n")
            client = AureliaClient(executable="aurelia", config_dir=config, run=lambda *_a, **_k: None)
            self.assertEqual(
                client.launch_failure_detail("2706170", 100),
                "SpawnProcess: process could not start",
            )

    def test_launch_failure_detail_ignores_executable_not_found_in_verified_success_summary(self):
        """Aurelia may inspect Proton's wrapped `run` command, not the game target."""
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory)
            session = config / "logs" / "session-one"
            session.mkdir(parents=True)
            (session / "summary.json").write_text(json.dumps({
                "app_id": 2706170,
                "result": "Success",
                "timestamp": 100,
                "verification": {
                    "status": "verified",
                    "detailed_status": "game_executable_not_found",
                    "process_lifetime_ms": 2001,
                },
            }))
            (session / "events.jsonl").write_text(json.dumps({
                "event_type": "launch_final_status",
                "message": "Launch successful",
            }) + "\n")
            client = AureliaClient(executable="aurelia", config_dir=config, run=lambda *_a, **_k: None)
            self.assertIsNone(client.launch_failure_detail("2706170", 100))

    async def test_running_record_reads_aurelia_runner_pid_without_cli_query(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory)
            running = config / "running"
            running.mkdir()
            (running / "104200.json").write_text(
                json.dumps({"app_id": 104200, "name": "BEEP", "pid": 4321})
            )
            client = AureliaClient(executable="aurelia", config_dir=config, run=lambda *_a, **_k: None)
            self.assertEqual(await client.running_record("104200"),
                             {"app_id": 104200, "name": "BEEP", "pid": 4321})
            self.assertIsNone(await client.running_record("945360"))

    async def test_malformed_running_record_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory)
            running = config / "running"
            running.mkdir()
            (running / "104200.json").write_text('{"app_id":104200,"pid":"not-a-pid"}')
            client = AureliaClient(executable="aurelia", config_dir=config, run=lambda *_a, **_k: None)
            with self.assertRaisesRegex(AureliaError, "invalid AppID/PID"):
                await client.running_record("104200")

    async def test_running_game_stop_bypasses_aurelia_daemon(self):
        with tempfile.TemporaryDirectory() as directory:
            client = AureliaClient(executable="/usr/bin/aurelia", config_dir=Path(directory))
            process = Mock(returncode=0)
            process.communicate = AsyncMock(return_value=(b'{"status":"stopped"}', b""))
            with patch("lulu.plugins.steam.aurelia.asyncio.create_subprocess_exec",
                       new_callable=AsyncMock, return_value=process) as spawn:
                result = await client.stop("104200")
            self.assertEqual(result["status"], "stopped")
            self.assertEqual(spawn.call_args.args[:4], ("/usr/bin/aurelia", "--json", "stop", "104200"))
            self.assertEqual(spawn.call_args.kwargs["env"]["AURELIA_NO_DAEMON"], "1")

class AureliaOptInTests(unittest.TestCase):
    def test_backend_disabled_by_default(self):
        config = ProviderConfigurationService(system_path=Path("/nonexistent"),
                                              user_path=Path("/nonexistent"))
        self.assertFalse(config.provider("providers.steam_aurelia").enabled)
        self.assertEqual(PROVIDER_ID, "steam-aurelia")
        self.assertEqual(AureliaCapabilities().detailed_launch_progress, False)


if __name__ == "__main__":
    unittest.main()
