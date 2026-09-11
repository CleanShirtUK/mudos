import tempfile
import unittest
from pathlib import Path

from lulu.catalogue import CatalogueStore
from lulu.steam_provider import InstalledSteamGame
from lulu.local_content import LocalContentProvider


class FakeSteamProvider:
    def __init__(self, games: list[InstalledSteamGame]) -> None:
        self.games = games

    def list_installed(self) -> list[InstalledSteamGame]:
        return self.games


class CatalogueTests(unittest.TestCase):
    def test_reconcile_persists_launchable_steam_records(self) -> None:
        game = InstalledSteamGame(
            "40800",
            "Super Meat Boy",
            "/games/Super Meat Boy",
            "/games",
            123,
            0,
        )
        with tempfile.TemporaryDirectory() as directory:
            store = CatalogueStore(Path(directory) / "catalogue.sqlite3")
            store.reconcile_steam(FakeSteamProvider([game]))

            record = store.list_games()[0]

        self.assertEqual(record.game_id, "steam:40800")
        self.assertEqual(record.provider_id, "40800")
        self.assertTrue(record.launchable)
        self.assertEqual(record.install_state, "installed")

    def test_missing_manifest_removes_game_from_launchable_library(self) -> None:
        game = InstalledSteamGame("40800", "Super Meat Boy", "/games/Super Meat Boy", "/games", 123, 0)
        with tempfile.TemporaryDirectory() as directory:
            store = CatalogueStore(Path(directory) / "catalogue.sqlite3")
            provider = FakeSteamProvider([game])
            store.reconcile_steam(provider)
            provider.games = []
            store.reconcile_steam(provider)

            self.assertEqual(store.list_games(), [])

    def test_mark_played_populates_recent_without_changing_identity(self) -> None:
        game = InstalledSteamGame("40800", "Super Meat Boy", "/games/Super Meat Boy", "/games", 123, 0)
        with tempfile.TemporaryDirectory() as directory:
            store = CatalogueStore(Path(directory) / "catalogue.sqlite3")
            store.reconcile_steam(FakeSteamProvider([game]))
            store.mark_played("steam:40800")

            recent = store.list_recent()

        self.assertEqual([record.game_id for record in recent], ["steam:40800"])

    def test_local_reconcile_normalizes_content_and_removes_stale_records(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "roms"
            (root / "nes").mkdir(parents=True)
            content = root / "nes" / "Long Unicode - Cafe.nes"
            content.write_bytes(b"fixture")
            runtime = Path(directory) / "retroarch"
            runtime.write_bytes(b"runtime")
            store = CatalogueStore(Path(directory) / "catalogue.sqlite3")
            provider = LocalContentProvider({"nes": runtime})

            store.reconcile_local(provider, root)
            record = store.list_games()[0]
            content.unlink()
            store.reconcile_local(provider, root)

        self.assertEqual(record.provider, "local")
        self.assertEqual(record.platform, "nes")
        self.assertEqual(store.list_games(), [])

    def test_all_games_combines_steam_and_discovered_platforms(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "roms"
            (root / "nes").mkdir(parents=True)
            (root / "nes" / "Mario.nes").write_bytes(b"fixture")
            store = CatalogueStore(Path(directory) / "catalogue.sqlite3")
            store.reconcile_steam(FakeSteamProvider([
                InstalledSteamGame("10", "Steam Game", "/games/a", "/games", 1, 0)
            ]))
            store.reconcile_local(LocalContentProvider({"nes": Path("/usr/bin/true")}), root)
            games = store.list_games()

        self.assertEqual({game.provider for game in games}, {"steam", "local"})
        self.assertEqual(store.list_games("platform:nes")[0].title, "Mario")
        self.assertEqual(store.list_platforms(), [("nes", "Nintendo Entertainment System")])

    def test_user_presentation_and_artwork_overrides_survive_rescan(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "roms"
            (root / "nes").mkdir(parents=True)
            (root / "nes" / "Mario.nes").write_bytes(b"fixture")
            store = CatalogueStore(Path(directory) / "catalogue.sqlite3")
            provider = LocalContentProvider({"nes": Path("/usr/bin/true")})
            store.reconcile_local(provider, root)
            game_id = store.list_games()[0].game_id

            store.set_display_title_override(game_id, "My Mario")
            store.suppress_artwork(game_id)
            store.reconcile_local(provider, root)
            record = store.get_game(game_id)

        self.assertEqual(record.title, "My Mario")
        self.assertEqual(record.display_title_override, "My Mario")
        self.assertTrue(record.artwork_suppressed)
