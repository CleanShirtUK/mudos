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


class MetadataTests(unittest.TestCase):
    def test_filename_cleanup_removes_rom_noise_but_keeps_title_punctuation(self):
        self.assertEqual(clean_local_title("Super Mario Bros. (USA) (Rev 1).nes"), "Super Mario Bros")
        self.assertEqual(clean_local_title("mario_kart_wii_RMCP01"), "mario kart wii")
        self.assertEqual(clean_local_title("The.Legend.of.Zelda.Ocarina.of.Time.(Europe).nes"), "The Legend of Zelda Ocarina of Time")
        self.assertEqual(clean_local_title("Tom & Jerry: War of the Whiskers (USA).iso"), "Tom & Jerry: War of the Whiskers")
        self.assertEqual(clean_local_title("Sonic & Knuckles [!].bin"), "Sonic & Knuckles")

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

    def test_no_result_and_network_failure_are_unmatched(self):
        self.assertEqual(MetadataMatcher(FakeMetadata([])).match("Unknown.nes", "nes").status, "unmatched")
        self.assertEqual(MetadataMatcher(FakeMetadata(None)).match("Unknown.nes", "nes").method, "network-error")

    def test_search_cache_avoids_second_request(self):
        with tempfile.TemporaryDirectory() as directory:
            provider = SteamGridDBMetadata("test", Path(directory))
            with patch.object(provider, "_request_json", return_value={"data": [{"id": 7, "name": "Mario"}]}) as request:
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
            with patch.object(provider, "_download"):
                provider.enrich([game])
        self.assertEqual(request.call_args.args[1], "/v2/grids/game/42?dimensions=600x900")


if __name__ == "__main__":
    unittest.main()
