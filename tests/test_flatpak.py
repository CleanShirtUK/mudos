import asyncio
import unittest

from lulu.plugins.flatpak import FlatpakAdapter, FlatpakApplication


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
                          "org.openttd.OpenTTD"])
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
