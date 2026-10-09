import asyncio
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from lulu.plugins.flatpak import FlatpakAdapter, FlatpakApplication
from lulu.plugins.flatpak.adapter import _flatpak_operation_failure
from lulu.jobs import DownloadJob, JobOperation, JobState
from lulu.statistics_overlay import launch_environment


class FakeFlatpak(FlatpakAdapter):
    def __init__(self):
        super().__init__(command="/usr/bin/flatpak")

    async def catalog(self, query=""):
        return (FlatpakApplication("org.openttd.OpenTTD", "OpenTTD", "Transport game",
                                   version="14", branch="stable", remote="flathub",
                                   categories=("Game",), icon="https://example/icon.png"),)

    async def installed(self, *, user=True):
        if user:
            return (FlatpakApplication("org.openttd.OpenTTD", "OpenTTD", "Transport game",
                                       version="14", branch="stable", remote="flathub",
                                       scope="user", installed=True, categories=("Game",)),)
        return ()

    async def remotes(self, *, user=True):
        return ({"name": "flathub", "url": "https://dl.flathub.org/repo/flathub.flatpakrepo",
                 "options": "", "scope": "user"},)


class FlatpakTests(unittest.TestCase):
    def test_appstream_metadata_is_the_shared_game_utility_classifier(self):
        fixtures = Path(__file__).parent / "fixtures/flatpak"
        game_metadata = FlatpakAdapter._appstream_records(
            str(fixtures / "org.supertuxproject.SuperTux.metainfo.xml"))["org.supertuxproject.SuperTux"]
        utility_metadata = FlatpakAdapter._appstream_records(
            str(fixtures / "org.example.Graphics.metainfo.xml"))["org.example.Graphics"]
        game = FlatpakApplication("org.supertuxproject.SuperTux", "SuperTux",
                                  categories=tuple(game_metadata["categories"]),
                                  component_type=str(game_metadata["component_type"]))
        utility = FlatpakApplication("org.example.Graphics", str(utility_metadata["name"]),
                                     categories=tuple(utility_metadata["categories"]),
                                     component_type=str(utility_metadata["component_type"]),
                                     summary=str(utility_metadata["summary"]),
                                     description=str(utility_metadata["description"]),
                                     developer=str(utility_metadata["developer"]),
                                     publisher=str(utility_metadata["publisher"]),
                                     screenshots=tuple(utility_metadata["screenshots"]),
                                     source_metadata=utility_metadata)
        unknown = FlatpakApplication("org.example.Unknown", "Unknown")
        misleading = FlatpakApplication("org.example.Misleading", "Misleading",
                                        categories=("NotAGame",),
                                        component_type="desktop-application")

        self.assertTrue(game.is_game)
        self.assertEqual(game.classification, "game")
        self.assertEqual(utility.classification, "utility")
        self.assertFalse(utility.is_game)
        self.assertEqual(utility.name, "Example Graphics")
        self.assertEqual(utility.summary, "Create and edit images")
        self.assertEqual(utility.description,
                         "A representative desktop graphics application.\n\nIncludes layered editing tools.\n\nEnglish feature.")
        self.assertEqual(utility.developer, "Example Person")
        self.assertEqual(utility.source_metadata["developer_id"], "org.example")
        self.assertEqual(utility.publisher, "Example Publishing")
        self.assertEqual(len(utility.screenshots), 2)
        self.assertEqual(utility.source_metadata["categories"], ("Graphics", "2DGraphics"))
        self.assertEqual(unknown.classification, "unclassified")
        self.assertEqual(misleading.classification, "utility")

    def test_missing_runtime_error_names_application_and_exact_required_ref(self):
        error = _flatpak_operation_failure("org.example.Game", [
            "The application requires the runtime org.freedesktop.Platform/x86_64/26.08 which was not found"
        ])
        self.assertEqual(error.code, "runtime-resolution-failed")
        self.assertIn("org.example.Game", str(error))
        self.assertIn("org.freedesktop.Platform/x86_64/26.08", str(error))
        self.assertIn("The provider reported", str(error))

    def test_flatpak_no_such_ref_diagnostic_is_classified_as_missing_dependency(self):
        error = _flatpak_operation_failure("org.example.Game", [
            "error: No such ref 'runtime/org.freedesktop.Platform/x86_64/99.99-fixture' in remote flathub"
        ])
        self.assertEqual(error.code, "runtime-resolution-failed")
        self.assertIn("org.freedesktop.Platform/x86_64/99.99-fixture", str(error))
        self.assertIn("No such ref", str(error))

    def test_flatpak_install_keeps_default_dependency_resolution_enabled(self):
        from pathlib import Path
        source = Path(__file__).parents[1] / "src/lulu/plugins/flatpak/adapter.py"
        text = source.read_text()
        self.assertIn('("install", "--noninteractive", "--or-update", "flathub", app_id)', text)
        self.assertIn('transaction.add_install("flathub", f"app/{app_id}/x86_64/stable")', text)
        self.assertIn('flatpakref_install = (job.operation is JobOperation.INSTALL and job.provider_job_id', text)
        self.assertIn('self._gi is not None and not flatpakref_install', text)
        self.assertIn('args = ("install", "--noninteractive", job.provider_job_id)', text)
        self.assertNotIn("--no-deps", text)
        self.assertIn("diagnostic_lines.append(line[:1000])", text)

    def test_other_flatpak_errors_retain_provider_diagnostic(self):
        error = _flatpak_operation_failure("org.example.Game", ["warning: repo metadata", "error: transaction failed"])
        self.assertEqual(error.code, "operation-failed")
        self.assertIn("warning: repo metadata", str(error))
        self.assertIn("error: transaction failed", str(error))

    def test_flatpakref_install_uses_cli_dependency_resolution_and_surfaces_stderr(self):
        class Output:
            def __init__(self, lines):
                self.lines = lines

            def __aiter__(self):
                self.iterator = iter(self.lines)
                return self

            async def __anext__(self):
                try:
                    return next(self.iterator)
                except StopIteration:
                    raise StopAsyncIteration

        class Process:
            returncode = 1
            stdout = Output([b"error: runtime org.freedesktop.Platform/x86_64/26.08 was not found (8)\n"])

            async def wait(self):
                return self.returncode

        class Reporter:
            async def state(self, *_args, **_kwargs):
                return None

        adapter = FlatpakAdapter(command="/usr/bin/flatpak")
        job = DownloadJob(
            job_id="fixture", provider="flatpak", title="SuperTux",
            content_identity="flatpak:org.supertuxproject.SuperTux",
            operation=JobOperation.INSTALL,
            provider_job_id="/tmp/supertux.flatpakref",
        )

        async def invoke():
            async def create_process(*args, **kwargs):
                self.assertEqual(args, ("/usr/bin/flatpak", "--user", "install", "--noninteractive",
                                        "/tmp/supertux.flatpakref"))
                self.assertEqual(kwargs["stderr"], asyncio.subprocess.STDOUT)
                return Process()

            with patch("lulu.plugins.flatpak.adapter.asyncio.create_subprocess_exec", create_process):
                with self.assertRaises(Exception) as raised:
                    await adapter.operation(job, Reporter())
            self.assertIn("was not found (8)", str(raised.exception))
            self.assertIn("org.freedesktop.Platform/x86_64/26.08", str(raised.exception))

        asyncio.run(invoke())

    def test_native_api_is_preferred_when_gi_is_available(self):
        adapter = FlatpakAdapter()
        if adapter._gi is not None:
            self.assertEqual(adapter.api, "libflatpak")
            self.assertTrue(adapter.available)

    def test_stable_identity_and_game_classification(self):
        app = FlatpakApplication("org.openttd.OpenTTD", "OpenTTD", categories=("Game",))
        non_game = FlatpakApplication("org.example.Editor", "Editor", categories=("Office",))
        self.assertEqual(app.game_id, "flatpak:org.openttd.OpenTTD")
        self.assertTrue(app.game)
        self.assertFalse(non_game.game)

    def test_reconcile_merges_user_and_system_scope_without_duplicate_identity(self):
        apps = asyncio.run(FakeFlatpak().reconcile())
        self.assertEqual(len(apps), 1)
        self.assertEqual(apps[0].application_id, "org.openttd.OpenTTD")
        self.assertEqual(apps[0].scope, "user")

    def test_launch_is_supervised_command_and_uninstall_preserves_data_by_default(self):
        adapter = FakeFlatpak()
        self.assertEqual(adapter.launch_command("org.openttd.OpenTTD"),
                         ["/usr/bin/flatpak", "run", "--socket=x11", "--env=SDL_VIDEODRIVER=x11",
                          "--env=GDK_BACKEND=x11", "--env=QT_QPA_PLATFORM=xcb",
                          "org.openttd.OpenTTD"])
        self.assertEqual(adapter.launch_command("app/org.example.Graphics/x86_64/stable")[-1],
                         "app/org.example.Graphics/x86_64/stable")
        with tempfile.TemporaryDirectory() as directory:
            deploy = Path(directory)
            icon = deploy / "export/share/icons/hicolor/512x512/apps/org.example.Graphics.png"
            icon.parent.mkdir(parents=True)
            icon.write_bytes(b"icon")
            self.assertEqual(FlatpakAdapter._deployed_icon(deploy, "org.example.Graphics", "org.example.Graphics"),
                             icon.as_uri())
        # The operation command is intentionally constructed without
        # --delete-data; Flatpak owns application data retention policy.
        self.assertNotIn("--delete-data", " ".join(["flatpak", "--user", "uninstall", "--noninteractive"]))

    def test_launch_forwards_selected_profile_at_flatpak_app_boundary(self):
        adapter = FakeFlatpak()
        with patch.object(adapter, "_mangohud_extension_ready", return_value=True) as ensure, \
                patch.object(adapter, "_application_command", return_value="openttd"):
            command = adapter.launch_command("org.openttd.OpenTTD", {
                "MANGOHUD": "1", "MANGOHUD_CONFIG": "fps_only=1",
            })
        ensure.assert_called_once_with("org.openttd.OpenTTD")
        self.assertIn("--env=MANGOHUD=1", command)
        self.assertIn("--env=MANGOHUD_CONFIG=fps_only=1", command)
        self.assertIn("--command=/usr/lib/extensions/vulkan/MangoHud/bin/mangohud", command)
        self.assertEqual(command[-3:], ["org.openttd.OpenTTD", "--dlsym", "openttd"])

    def test_unavailable_runtime_extension_disables_instead_of_claiming_overlay(self):
        adapter = FakeFlatpak()
        with patch.object(adapter, "_mangohud_extension_ready", return_value=False), \
                patch.object(adapter, "_application_command", return_value="openttd"):
            command = adapter.launch_command("org.openttd.OpenTTD", {
                "MANGOHUD": "1", "MANGOHUD_CONFIG": "full",
            })
        self.assertIn("--env=MANGOHUD=0", command)
        self.assertNotIn("--env=MANGOHUD_CONFIG=full", command)

    def test_extension_provisioning_uses_runtime_declared_branch(self):
        adapter = FakeFlatpak()
        responses = iter((
            subprocess.CompletedProcess([], 0, "org.kde.Platform/x86_64/6.10\n", ""),
            subprocess.CompletedProcess([], 0,
                "[Extension org.freedesktop.Platform.VulkanLayer]\nversion=25.08\n", ""),
            subprocess.CompletedProcess([], 0, "", ""),
            subprocess.CompletedProcess([], 0, "", ""),
        ))
        with patch.object(adapter, "_flatpak_result", side_effect=lambda _command: next(responses)) as run:
            self.assertTrue(adapter._mangohud_extension_ready("org.example.Game"))
        self.assertEqual(run.call_args_list[-1].args[0][-1],
                         "org.freedesktop.Platform.VulkanLayer.MangoHud//25.08")

    def test_all_profiles_cross_flatpak_boundary_and_off_never_wraps(self):
        adapter = FakeFlatpak()
        with patch.object(adapter, "_mangohud_extension_ready", return_value=True) as ensure, \
                patch.object(adapter, "_application_command", return_value="game"):
            for mode in ("fps", "minimal", "detailed"):
                with self.subTest(mode=mode):
                    command = adapter.launch_command("org.example.Game", launch_environment(mode))
                    self.assertIn("--command=/usr/lib/extensions/vulkan/MangoHud/bin/mangohud", command)
                    self.assertIn(f"--env=MANGOHUD_CONFIG={launch_environment(mode)['MANGOHUD_CONFIG']}", command)
            off_command = adapter.launch_command("org.example.Game", launch_environment("off"))
        self.assertEqual(ensure.call_count, 3)
        self.assertIn("--env=MANGOHUD=0", off_command)
        self.assertFalse(any("MangoHud/bin/mangohud" in item for item in off_command))

    def test_remove_uses_user_scoped_flatpak_uninstall_and_reconciles(self):
        class AppAdapter(FlatpakAdapter):
            def __init__(self):
                super().__init__(command="/usr/bin/flatpak")
                self._gi = None
                self.present = True
            async def installed(self, *, user=True):
                if user and self.present:
                    return (FlatpakApplication("org.example.Game", "Game", branch="beta",
                                               arch="aarch64", scope="user", installed=True),)
                return ()

        class Output:
            def __aiter__(self): return self
            async def __anext__(self): raise StopAsyncIteration

        class Process:
            returncode = 0
            stdout = Output()
            def __init__(self, adapter): self.adapter = adapter
            async def wait(self):
                self.adapter.present = False
                return 0

        class Reporter:
            def __init__(self): self.states = []
            async def state(self, state, **kwargs): self.states.append((state, kwargs))

        async def exercise():
            adapter = AppAdapter()
            adapter._require = lambda: "/usr/bin/flatpak"
            job = DownloadJob(job_id="remove", provider="flatpak", title="Game",
                              content_identity="flatpak:org.example.Game", operation=JobOperation.REMOVE)
            reporter = Reporter()

            async def create(*args, **kwargs):
                self.assertEqual(args, ("/usr/bin/flatpak", "--user", "uninstall",
                                        "--noninteractive", "org.example.Game"))
                self.assertNotIn("--delete-data", args)
                return Process(adapter)

            with patch("lulu.plugins.flatpak.adapter.asyncio.create_subprocess_exec", create):
                await adapter.operation(job, reporter)
            self.assertTrue(reporter.states)

        asyncio.run(exercise())

    def test_remove_of_already_missing_flatpak_is_idempotent(self):
        class MissingAdapter(FakeFlatpak):
            async def installed(self, *, user=True): return ()

        class Reporter:
            def __init__(self): self.states = []
            async def state(self, state, **kwargs): self.states.append(state)

        async def exercise():
            adapter = MissingAdapter()
            job = DownloadJob(job_id="remove-missing", provider="flatpak", title="Game",
                              content_identity="flatpak:org.example.Game", operation=JobOperation.REMOVE)
            reporter = Reporter()
            with patch("lulu.plugins.flatpak.adapter.asyncio.create_subprocess_exec",
                       side_effect=AssertionError("missing apps must not invoke the provider")):
                await adapter.operation(job, reporter)
            self.assertEqual(reporter.states, [JobState.STARTING, JobState.FINALIZING])

        asyncio.run(exercise())

    def test_unavailable_native_dependency_is_reported_cleanly(self):
        adapter = FlatpakAdapter(command=None)
        adapter.command = None
        adapter._gi = None
        self.assertFalse(adapter.available)
        self.assertEqual(adapter.api, "unavailable")
        with self.assertRaisesRegex(Exception, "Flatpak is not installed"):
            adapter.launch_command("org.openttd.OpenTTD")

    def test_flathub_remote_provisioning_is_idempotent_and_user_scoped(self):
        adapter = FakeFlatpak()
        asyncio.run(adapter.ensure_flathub())
