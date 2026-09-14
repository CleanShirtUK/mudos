import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from lulu.artwork import SteamGridDBArtwork
from lulu.catalogue import CatalogueStore
from lulu.metadata import MetadataCandidate, MetadataMatch, MetadataMatcher, SteamGridDBMetadata, clean_local_title


class FakeMetadata:
    provider_name = "steamgriddb"

    def __init__(self, candidates=None):
        self.candidates = candidates

    def search(self, query, platform):
        return self.candidates

    def search_steam_app(self, app_id):
        return None


class MetadataTests(unittest.TestCase):
    def test_filename_cleanup_removes_rom_noise_but_keeps_title_punctuation(self):
        self.assertEqual(clean_local_title("Super Mario Bros. (USA) (Rev 1).nes"), "Super Mario Bros")
        self.assertEqual(clean_local_title("mario_kart_wii_RMCP01"), "mario kart wii")
        self.assertEqual(clean_local_title("The.Legend.of.Zelda.Ocarina.of.Time.(Europe).nes"), "The Legend of Zelda Ocarina of Time")
        self.assertEqual(clean_local_title("Tom & Jerry: War of the Whiskers (USA).iso"), "Tom & Jerry: War of the Whiskers")
        self.assertEqual(clean_local_title("Sonic & Knuckles [!].bin"), "Sonic & Knuckles")
        self.assertEqual(clean_local_title("Mario Kart 8 Deluxe [0100152000022000][v0].nsp"), "Mario Kart 8 Deluxe")
        self.assertEqual(clean_local_title("Mario Kart Wii (Europe, Australia) (En,Fr,De,Es,It).rvz"), "Mario Kart Wii")
        self.assertEqual(clean_local_title("Mario.Kart.8.Deluxe.DLC.Booster.Course.Pass.0100152000023001.v65536.nsp"), "Mario Kart 8 Deluxe")
        self.assertEqual(clean_local_title("Sonic the Hedgehog (JUE) [!].bin"), "Sonic the Hedgehog")
        self.assertEqual(clean_local_title("Super Mario Bros. Wonder[010015100B514000][1.0.0][0][16.0.3].nsp"), "Super Mario Bros Wonder")

    def test_platform_match_beats_wrong_platform_and_ambiguity_is_preserved(self):
        candidates = [
            MetadataCandidate("1", "Mario Kart", platforms=("Nintendo 64",)),
            MetadataCandidate("2", "Mario Kart", platforms=("Wii",)),
        ]
        result = MetadataMatcher(FakeMetadata(candidates)).match("Mario Kart (USA).rvz", "wii")
        self.assertEqual((result.status, result.game_id), ("matched", "2"))

        ambiguous = MetadataMatcher(FakeMetadata([
            MetadataCandidate("1", "Zelda", platforms=("NES",)),
            MetadataCandidate("2", "Zelda", platforms=("NES",)),
        ])).match("Zelda.nes", "nes")
        self.assertEqual(ambiguous.status, "ambiguous")

    def test_steam_catalogue_matching_uses_appid_and_presentation_metadata(self):
        from lulu.catalogue import CatalogueGame
        candidate = MetadataCandidate(
            "sgdb-104200", "Canonical BEEP", raw={
                "id": "sgdb-104200", "name": "Canonical BEEP", "genres": ["Action"],
                "release_date": 1304701380,
            }
        )

        class SteamMetadata(FakeMetadata):
            def search_steam_app(self, app_id):
                self.app_id = app_id
                return candidate

        provider = SteamMetadata()
        game = CatalogueGame("steam:104200", "steam", "104200", "RomM BEEP", "Steam",
                             "available", False, "", "", 0)
        result = MetadataMatcher(provider).match_game(game)
        self.assertEqual(provider.app_id, "104200")
        self.assertEqual((result.method, result.canonical_title), ("steam-appid", "Canonical BEEP"))
        self.assertEqual(result.presentation["genres"], ["Action"])
        self.assertEqual(result.presentation["release_date"], "2011-05-06")

    def test_strongest_credible_title_wins_close_sequel_results(self):
        result = MetadataMatcher(FakeMetadata([
            MetadataCandidate("1", "Crazy Taxi"),
            MetadataCandidate("2", "Crazy Taxi 2"),
        ])).match("Crazy Taxi (USA).cue", "ps2")
        self.assertEqual((result.status, result.game_id), ("matched", "1"))

    def test_no_result_and_network_failure_are_unmatched(self):
        self.assertEqual(MetadataMatcher(FakeMetadata([])).match("Unknown.nes", "nes").status, "unmatched")
        self.assertEqual(MetadataMatcher(FakeMetadata(None)).match("Unknown.nes", "nes").method, "network-error")

    def test_search_cache_avoids_second_request(self):
        with tempfile.TemporaryDirectory() as directory:
            provider = SteamGridDBMetadata("test", Path(directory))
            with patch.object(provider, "_request_json", return_value={"data": [{"id": 7, "name": "Mario", "platforms": ["NES"]}]}) as request:
                self.assertEqual(provider.search("Mario", "nes")[0].game_id, "7")
                self.assertEqual(provider.search("Mario", "nes")[0].game_id, "7")
            request.assert_called_once()

    def test_persisted_automatic_and_manual_matches_survive_rescan_and_clear(self):
        with tempfile.TemporaryDirectory() as directory:
            store = CatalogueStore(Path(directory) / "catalogue.sqlite3")
            from lulu.local_content import LocalContentProvider
            root = Path(directory) / "roms"; (root / "nes").mkdir(parents=True)
            (root / "nes" / "Mario Kart (USA).nes").write_bytes(b"rom")
            store.reconcile_local(LocalContentProvider({"nes": Path("/bin/true")}), root)
            game = store.list_games()[0]
            store.apply_metadata_match(game.game_id, MetadataMatch("matched", "steamgriddb", "42", "Mario Kart", "title", .99, "Mario Kart"))
            store.reconcile_local(LocalContentProvider({"nes": Path("/bin/true")}), root)
            self.assertEqual(store.list_games()[0].title, "Mario Kart")
            store.set_metadata_match(game.game_id, "steamgriddb", "99", "Manual Choice")
            store.reconcile_local(LocalContentProvider({"nes": Path("/bin/true")}), root)
            self.assertEqual(store.list_games()[0].match_status, "manual")
            self.assertEqual(store.list_games()[0].title, "Manual Choice")
            store.clear_metadata_match(game.game_id)
            self.assertEqual(store.get_game(game.game_id).metadata_game_id, "")

    def test_artwork_uses_persisted_canonical_id(self):
        game = type("Game", (), {"game_id": "local:nes:1", "provider": "local", "provider_id": "local:nes:1", "title": "Mario Kart", "metadata_provider": "steamgriddb", "metadata_game_id": "42"})()
        provider = SteamGridDBArtwork("test", Path(tempfile.mkdtemp()))
        with patch.object(SteamGridDBArtwork, "_request_json", return_value={"data": [{"url": "https://cdn.example/grid.jpg"}]}) as request:
            with patch.object(SteamGridDBArtwork, "_download"):
                provider.enrich([game])
        self.assertEqual(request.call_args.args[0], "/v2/grids/game/42?dimensions=600x900")

    def test_network_error_has_a_short_but_nonzero_retry_cooldown(self):
        with tempfile.TemporaryDirectory() as directory:
            store = CatalogueStore(Path(directory) / "catalogue.sqlite3")
            store.connection.execute(
                "INSERT INTO games (game_id, provider, provider_id, title, platform, install_state, "
                "launchable, install_dir, artwork_url, match_status, match_method, metadata_checked_at) "
                "VALUES ('local:1', 'local', '1', 'Mario', 'nes', 'installed', 1, '/rom', '', "
                "'unmatched', 'network-error', 1000)"
            )
            store.connection.commit()
            self.assertFalse(store.needs_metadata_match("local:1", 1000 + 899))
            self.assertTrue(store.needs_metadata_match("local:1", 1000 + 900))

    def test_no_result_ambiguous_and_low_confidence_use_the_long_cooldown(self):
        for method in ("no-result", "close-results", "low-confidence"):
            with self.subTest(method=method), tempfile.TemporaryDirectory() as directory:
                store = CatalogueStore(Path(directory) / "catalogue.sqlite3")
                store.connection.execute(
                    "INSERT INTO games (game_id, provider, provider_id, title, platform, install_state, "
                    "launchable, install_dir, artwork_url, match_status, match_method, metadata_checked_at) "
                    "VALUES (?, 'local', ?, 'Mario', 'nes', 'installed', 1, '/rom', '', 'unmatched', ?, 1000)",
                    (f"local:{method}", method, method),
                )
                store.connection.commit()
                self.assertFalse(store.needs_metadata_match(f"local:{method}", 1000 + 86400 - 1))
                self.assertTrue(store.needs_metadata_match(f"local:{method}", 1000 + 86400))

    def test_manual_and_confirmed_matches_never_need_automatic_search(self):
        with tempfile.TemporaryDirectory() as directory:
            store = CatalogueStore(Path(directory) / "catalogue.sqlite3")
            store.connection.execute(
                "INSERT INTO games (game_id, provider, provider_id, title, platform, install_state, "
                "launchable, install_dir, artwork_url, metadata_game_id, match_status, match_method, "
                "metadata_checked_at, match_locked) VALUES "
                "('manual', 'local', 'manual', 'Manual', 'nes', 'installed', 1, '/rom', '', '9', 'manual', 'manual', 1000, 1), "
                "('confirmed', 'local', 'confirmed', 'Confirmed', 'nes', 'installed', 1, '/rom', '', '8', 'matched', 'title', 1000, 0)"
            )
            store.connection.commit()
            self.assertFalse(store.needs_metadata_match("manual", 1000 + 999999))
            self.assertFalse(store.needs_metadata_match("confirmed", 1000 + 999999))


if __name__ == "__main__":
    unittest.main()
