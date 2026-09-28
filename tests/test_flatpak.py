import asyncio
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from lulu.plugins.flatpak import FlatpakAdapter, FlatpakApplication
from lulu.plugins.flatpak.adapter import _flatpak_operation_failure
from lulu.jobs import DownloadJob, JobOperation


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
