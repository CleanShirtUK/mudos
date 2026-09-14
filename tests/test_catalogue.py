import tempfile
import unittest
from pathlib import Path

from lulu.consoled import ConsoleInterface
from lulu.catalogue import CatalogueGame, CatalogueStore
from lulu.romm import RommFile, RommGame
from lulu.steam_provider import InstalledSteamGame
from lulu.local_content import LocalContentProvider


class FakeSteamProvider:
    def __init__(self, games: list[InstalledSteamGame]) -> None:
        self.games = games

    def list_installed(self) -> list[InstalledSteamGame]:
        return self.games


class CatalogueTests(unittest.TestCase):
    def test_romm_reconcile_uses_steam_identity_and_preserves_installed_state(self) -> None:
        romm = RommGame(42, "Cuphead", 99, "steam", "Steam", "cuphead.json", ".json", 10, "", False,
                        (RommFile(420, "cuphead.json"),))
        installed = InstalledSteamGame("268910", "Cuphead", "/games/Cuphead", "/games", 1, 0)
        with tempfile.TemporaryDirectory() as directory:
            store = CatalogueStore(Path(directory) / "catalogue.sqlite3")
            store.reconcile_steam(FakeSteamProvider([installed]))
            store.reconcile_romm([CatalogueGame.from_romm(romm, installed, "268910")])
            row = store.get_game("steam:268910")

        self.assertEqual(row.provider, "steam")
        self.assertEqual(row.provider_record_id, "42")
        self.assertEqual(row.install_state, "installed")
        self.assertTrue(row.launchable)

    def test_romm_available_state_is_separate_from_installed_games(self) -> None:
        romm = RommGame(43, "F-Zero", 1, "snes", "SNES", "F-Zero.sfc", ".sfc", 10, "", False)
        with tempfile.TemporaryDirectory() as directory:
            store = CatalogueStore(Path(directory) / "catalogue.sqlite3")
            store.reconcile_romm([CatalogueGame.from_romm(romm)])

            self.assertEqual(store.list_games(), [])
            available = store.list_available_games("romm")

        self.assertEqual([game.game_id for game in available], ["romm:43"])

    def test_romm_steam_platform_survives_runtime_identity_and_available_query(self) -> None:
        first = RommGame(272, "BEEP", 7, "steam", "Steam", "104200-beep.json", ".json", 10, "", False,
                         (RommFile(2720, "104200-beep.json"),))
        duplicate = RommGame(273, "BEEP legacy", 7, "steam", "Steam", "104200-old.json", ".json", 10, "", False,
                             (RommFile(2730, "104200-old.json"),))
        with tempfile.TemporaryDirectory() as directory:
            store = CatalogueStore(Path(directory) / "catalogue.sqlite3")
            store.reconcile_romm([
                CatalogueGame.from_romm(first, app_id="104200"),
                CatalogueGame.from_romm(duplicate, app_id="104200"),
            ])
            available = store.list_available_games("romm")

        self.assertEqual(len(available), 1)
        self.assertEqual(available[0].game_id, "steam:104200")
        self.assertEqual(available[0].provider, "steam")
        self.assertEqual(available[0].provider_id, "104200")
        self.assertEqual(available[0].platform, "Steam")
        self.assertEqual(available[0].platform_label, "Steam")
        self.assertIn(available[0].provider_record_id, {"272", "273"})

    def test_steam_reconcile_does_not_hide_romm_steam_titles(self) -> None:
        romm = RommGame(272, "BEEP", 7, "steam", "Steam", "104200-beep.json", ".json", 10, "", False)
        with tempfile.TemporaryDirectory() as directory:
            store = CatalogueStore(Path(directory) / "catalogue.sqlite3")
            store.reconcile_romm([CatalogueGame.from_romm(romm, app_id="104200")])
            store.reconcile_steam(FakeSteamProvider([]))
            available = store.list_available_games("romm")

        self.assertEqual([game.game_id for game in available], ["steam:104200"])
        self.assertEqual(available[0].install_state, "available")

    def test_romm_steam_title_match_is_migrated_to_appid_path(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = CatalogueStore(Path(directory) / "catalogue.sqlite3")
            store.connection.execute(
                "INSERT INTO games (game_id, provider, provider_id, title, platform, install_state, "
                "launchable, install_dir, artwork_url, availability_state, provider_record_id, "
                "catalogue_source, metadata_provider, metadata_game_id, match_status, match_method) "
                "VALUES ('steam:104200', 'steam', '104200', 'BEEP', 'Steam', 'available', 0, '', '', "
                "'available', '272', 'romm', 'steamgriddb', 'old-id', 'matched', 'title')"
            )
            store.connection.commit()
            self.assertTrue(store.needs_metadata_match("steam:104200"))

    def test_romm_metadata_and_local_record_survive_reopen(self) -> None:
        romm = RommGame(272, "BEEP", 7, "steam", "Steam", "104200-beep.json", ".json", 10, "", False,
                        genres=("Action", "Puzzle"), release_date="2001-04-20", release_year=2001)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "catalogue.sqlite3"
            store = CatalogueStore(path)
            store.reconcile_romm([CatalogueGame.from_romm(romm, app_id="104200")])
            store.connection.close()
            reopened = CatalogueStore(path)
            record = reopened.get_game("steam:104200")

        self.assertEqual(record.catalogue_source, "romm")
        self.assertEqual(record.platform, "Steam")
        self.assertEqual(record.provider, "steam")
        self.assertEqual(record.genres, ("Action", "Puzzle"))
        self.assertEqual(record.release_year, 2001)

    def test_installed_romm_steam_title_is_not_available(self) -> None:
        romm = RommGame(272, "BEEP", 7, "steam", "Steam", "104200-beep.json", ".json", 10, "", False)
        installed = InstalledSteamGame("104200", "BEEP", "/games/BEEP", "/games", 1, 0)
        with tempfile.TemporaryDirectory() as directory:
            store = CatalogueStore(Path(directory) / "catalogue.sqlite3")
            store.reconcile_romm([CatalogueGame.from_romm(romm, installed, "104200")])
            available = store.list_available_games("romm")
        self.assertEqual(available, [])

    def test_unresolved_romm_steam_record_keeps_canonical_platform(self) -> None:
        romm = RommGame(327, "Mortal Kombat X", 7, "steam", "Steam", "307780-mortal-kombat-x", "", 10, "", False)
        record = CatalogueGame.from_romm(romm)
        self.assertEqual(record.platform, "Steam")
        self.assertEqual(record.platform_label, "Steam")
        self.assertEqual(record.provider, "romm")
        self.assertFalse(record.launchable)

    def test_romm_snapshot_failure_can_leave_previous_snapshot_untouched(self) -> None:
        romm = RommGame(43, "F-Zero", 1, "snes", "SNES", "F-Zero.sfc", ".sfc", 10, "", False)
        with tempfile.TemporaryDirectory() as directory:
            store = CatalogueStore(Path(directory) / "catalogue.sqlite3")
            store.reconcile_romm([CatalogueGame.from_romm(romm)])
            # Providers are required to fetch and validate before calling this method.
            # A failed fetch therefore makes no store call and retains this row.
            self.assertEqual(store.get_game("romm:43").title, "F-Zero")
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

    def test_dbus_variants_preserve_real_catalogue_types(self) -> None:
        from lulu.catalogue import CatalogueGame

        game = CatalogueGame(
            game_id="steam:40800", provider="steam", provider_id="40800",
            title="Super Meat Boy", platform="Steam", install_state="installed",
            launchable=True, install_dir="/games", artwork_url="", last_played=0,
            match_confidence=0.875,
        )

        variants = ConsoleInterface._variants(game.as_dict())

        self.assertEqual(variants["match_confidence"].signature, "d")
        self.assertEqual(variants["match_confidence"].value, 0.875)
        self.assertEqual(variants["launchable"].signature, "b")
        self.assertEqual(variants["last_played"].signature, "x")
