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
    @staticmethod
    def _game_statements(store: CatalogueStore) -> list[str]:
        statements: list[str] = []
        store.connection.set_trace_callback(
            lambda statement: statements.append(statement)
            if any(token in statement.upper() for token in ("INSERT INTO GAMES", "UPDATE GAMES", "DELETE FROM GAMES"))
            else None
        )
        return statements

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

    def test_combined_available_catalogue_contains_steam_and_romm_sources(self) -> None:
        romm = RommGame(43, "F-Zero", 1, "snes", "SNES", "F-Zero.sfc", ".sfc", 10, "", False)
        with tempfile.TemporaryDirectory() as directory:
            store = CatalogueStore(Path(directory) / "catalogue.sqlite3")
            store.reconcile_romm([
                CatalogueGame.from_romm(romm),
                CatalogueGame.from_romm(romm, app_id="263980"),
            ])
            available = store.list_available_games()

        self.assertEqual({game.provider for game in available}, {"romm", "steam"})
        self.assertEqual({game.game_id for game in available}, {"romm:43", "steam:263980"})

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

    def test_native_steam_row_remains_available_when_entitlement_refresh_is_unavailable(self) -> None:
        installed = InstalledSteamGame("263980", "Out There Somewhere", "/games/out", "/games", 1, 0)
        with tempfile.TemporaryDirectory() as directory:
            store = CatalogueStore(Path(directory) / "catalogue.sqlite3")
            store.reconcile_steam(FakeSteamProvider([installed]))
            store.reconcile_steam(FakeSteamProvider([]))
            game = store.get_game("steam:263980")
            self.assertEqual(game.install_state, "available")
            self.assertEqual(game.availability_state, "available")
            self.assertEqual(store.list_available_games("steam")[0].game_id, "steam:263980")

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

    def test_unchanged_steam_reconcile_has_no_write_or_delta(self) -> None:
        game = InstalledSteamGame("40800", "Super Meat Boy", "/games/Super Meat Boy", "/games", 123, 0)
        with tempfile.TemporaryDirectory() as directory:
            store = CatalogueStore(Path(directory) / "catalogue.sqlite3")
            provider = FakeSteamProvider([game])
            store.reconcile_steam(provider)
            statements = self._game_statements(store)
            store.reconcile_steam(provider)

        self.assertEqual(store.last_deltas, ())
        self.assertEqual(store.last_write_counts, {"insert": 0, "update": 0, "delete": 0})
        self.assertEqual(statements, [])

    def test_provider_change_is_one_update_with_deterministic_delta(self) -> None:
        original = InstalledSteamGame("40800", "Super Meat Boy", "/games/Super Meat Boy", "/games", 123, 0)
        changed = InstalledSteamGame("40800", "Super Meat Boy Updated", "/games/Super Meat Boy", "/games", 123, 0)
        with tempfile.TemporaryDirectory() as directory:
            store = CatalogueStore(Path(directory) / "catalogue.sqlite3")
            provider = FakeSteamProvider([original])
            store.reconcile_steam(provider)
            statements = self._game_statements(store)
            provider.games = [changed]
            store.reconcile_steam(provider)

        self.assertEqual(store.last_write_counts, {"insert": 0, "update": 1, "delete": 0})
        self.assertEqual(len(store.last_deltas), 1)
        self.assertEqual(store.last_deltas[0].kind, "update")
        self.assertEqual(store.last_deltas[0].game_id, "steam:40800")
        self.assertEqual(store.last_deltas[0].changed_fields,
                         ("normalized_search_title", "source_title", "title"))
        self.assertEqual(len(statements), 1)
        self.assertTrue(statements[0].upper().startswith("UPDATE GAMES"))

    def test_mark_played_reports_one_update(self) -> None:
        game = InstalledSteamGame("40800", "Super Meat Boy", "/games/Super Meat Boy", "/games", 123, 0)
        with tempfile.TemporaryDirectory() as directory:
            store = CatalogueStore(Path(directory) / "catalogue.sqlite3")
            store.reconcile_steam(FakeSteamProvider([game]))
            delta = store.mark_played("steam:40800")

        self.assertIsNotNone(delta)
        self.assertEqual(delta.changed_fields, ("last_played",))
        self.assertEqual(store.last_write_counts, {"insert": 0, "update": 1, "delete": 0})

    def test_romm_unchanged_reconcile_and_presentation_have_no_writes(self) -> None:
        romm = RommGame(43, "F-Zero", 1, "snes", "SNES", "F-Zero.sfc", ".sfc", 10, "", False,
                        genres=("Racing",), release_year=1998)
        record = CatalogueGame.from_romm(romm)
        with tempfile.TemporaryDirectory() as directory:
            store = CatalogueStore(Path(directory) / "catalogue.sqlite3")
            store.reconcile_romm([record])
            store.reconcile_romm([record])
            self.assertEqual(store.last_deltas, ())
            self.assertEqual(store.last_write_counts, {"insert": 0, "update": 0, "delete": 0})
            self.assertIsNone(store.apply_romm_presentation(record.game_id, record))

    def test_new_and_unavailable_records_have_one_logical_mutation_each(self) -> None:
        game = InstalledSteamGame("40800", "Super Meat Boy", "/games/Super Meat Boy", "/games", 123, 0)
        with tempfile.TemporaryDirectory() as directory:
            store = CatalogueStore(Path(directory) / "catalogue.sqlite3")
            store.reconcile_steam(FakeSteamProvider([game]))
            self.assertEqual(store.last_write_counts, {"insert": 1, "update": 0, "delete": 0})
            store.reconcile_steam(FakeSteamProvider([]))

        self.assertEqual(store.last_write_counts, {"insert": 0, "update": 1, "delete": 0})
        self.assertEqual(store.last_deltas[0].changed_fields,
                         ("availability_state", "install_dir", "install_state", "launchable"))

    def test_unchanged_local_reconcile_has_no_write_or_delta(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "roms"
            (root / "nes").mkdir(parents=True)
            (root / "nes" / "Mario.nes").write_bytes(b"fixture")
            store = CatalogueStore(Path(directory) / "catalogue.sqlite3")
            provider = LocalContentProvider({"nes": Path("/usr/bin/true")})
            store.reconcile_local(provider, root)
            statements = self._game_statements(store)
            store.reconcile_local(provider, root)

        self.assertEqual(store.last_deltas, ())
        self.assertEqual(store.last_write_counts, {"insert": 0, "update": 0, "delete": 0})
        self.assertEqual(statements, [])

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

    def test_romm_links_to_local_without_duplicate_library_cards_or_title_dedupe(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "roms"
            (root / "switch").mkdir(parents=True)
            base = root / "switch" / "Mario Kart 8 Deluxe.nsp"
            dlc = root / "switch" / "Mario Kart 8 Deluxe DLC.nsp"
            base.write_bytes(b"base")
            dlc.write_bytes(b"dlc")
            store = CatalogueStore(Path(directory) / "catalogue.sqlite3")
            provider = LocalContentProvider({"switch": Path("/usr/bin/true")})
            store.reconcile_local(provider, root)
            local = {game.source_title: game for game in store.list_games()}
            romm_games = [
                CatalogueGame.from_romm(RommGame(
                    243, "Mario Kart 8 Deluxe", 1, "switch", "Switch",
                    base.name, ".nsp", base.stat().st_size, "", False,
                    (RommFile(2430, base.name),)
                )),
                CatalogueGame.from_romm(RommGame(
                    245, "Mario Kart 8 Deluxe", 1, "switch", "Switch",
                    dlc.name, ".nsp", dlc.stat().st_size, "", False,
                    (RommFile(2450, dlc.name),)
                )),
            ]
            store.reconcile_romm(romm_games)
            visible = store.list_games()

            self.assertEqual({game.provider for game in visible}, {"local"})
            self.assertEqual({game.game_id for game in visible}, set(local[name].game_id for name in local))
            self.assertEqual(len(visible), 2)
            self.assertEqual(store.get_game("romm:243").installed_game_id, local[base.name].game_id)
            self.assertEqual(store.get_game("romm:245").installed_game_id, local[dlc.name].game_id)
            self.assertEqual(store.list_available_games("romm"), [])

            store.reconcile_romm(romm_games)
            self.assertEqual(len(store.list_games()), 2)

    def test_missing_local_file_clears_romm_association_and_restores_store_availability(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "roms"
            (root / "nes").mkdir(parents=True)
            content = root / "nes" / "Mario.nes"
            content.write_bytes(b"fixture")
            store = CatalogueStore(Path(directory) / "catalogue.sqlite3")
            provider = LocalContentProvider({"nes": Path("/usr/bin/true")})
            store.reconcile_local(provider, root)
            romm = CatalogueGame.from_romm(RommGame(
                186, "Mario", 1, "nes", "NES", content.name, ".nes", content.stat().st_size,
                "", False, (RommFile(1860, content.name),)
            ))
            store.reconcile_romm([romm])
            local_id = next(game.game_id for game in store.list_games() if game.provider == "local")
            self.assertEqual(store.get_game("romm:186").installed_game_id, local_id)

            content.unlink()
            store.reconcile_local(provider, root)
            remote = store.get_game("romm:186")

        self.assertEqual(remote.installed_game_id, "")
        self.assertEqual(remote.install_state, "available")
        self.assertEqual(remote.availability_state, "available")
        self.assertEqual([game.game_id for game in store.list_available_games("romm")], ["romm:186"])
        self.assertEqual(store.list_games(), [])

    def test_local_only_rom_remains_visible_and_steam_identity_is_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "roms"
            (root / "nes").mkdir(parents=True)
            (root / "nes" / "Local Only.nes").write_bytes(b"fixture")
            store = CatalogueStore(Path(directory) / "catalogue.sqlite3")
            store.reconcile_steam(FakeSteamProvider([
                InstalledSteamGame("40800", "Super Meat Boy", "/games/Super Meat Boy", "/games", 1, 0)
            ]))
            store.reconcile_local(LocalContentProvider({"nes": Path("/usr/bin/true")}), root)
            games = store.list_games()

        self.assertEqual({game.provider for game in games}, {"local", "steam"})
        self.assertEqual(store.get_game("steam:40800").provider_id, "40800")
        self.assertEqual(store.get_game("steam:40800").game_id, "steam:40800")

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
