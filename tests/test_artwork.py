import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from lulu.artwork import SteamGridDBArtwork


class ArtworkTests(unittest.TestCase):
    def test_missing_key_is_a_noop(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            provider = SteamGridDBArtwork(api_key="", cache_dir=Path(directory))
            self.assertEqual(provider.enrich([]), {})
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_steam_id_matching_uses_stable_catalogue_identity(self) -> None:
        provider = SteamGridDBArtwork(api_key="test", cache_dir=Path("/tmp/lulu-test-cache"))
        calls: list[str] = []

        def request(path: str) -> dict[str, object]:
            calls.append(path)
            return {"data": [{"url": "https://cdn.example/grid.jpg"}]}

        with patch("lulu.artwork.SteamGridDBArtwork._request_json", side_effect=request):
            self.assertEqual(provider._find_image("steam", "440", "Team Fortress 2"), "https://cdn.example/grid.jpg")
        self.assertEqual(calls, ["/v2/grids/steam/440?dimensions=600x900"])

    def test_steam_square_grid_uses_appid_and_cached_association(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            provider = SteamGridDBArtwork(api_key="test", cache_dir=Path(directory))
            game = type("Game", (), {
                "game_id": "steam:440", "provider": "steam", "provider_id": "440",
                "title": "Team Fortress 2", "canonical_title": "TF2",
                "artwork_suppressed": False, "icon_square_url": "",
                "icon_square_provider": "", "icon_square_source_url": "",
                "icon_url": "",
            })()
            calls: list[str] = []

            def request(path: str) -> dict[str, object]:
                calls.append(path)
                return {"data": [{"url": "https://cdn.example/grid.png",
                                  "width": 512, "height": 512}]}

            with patch("lulu.artwork.SteamGridDBArtwork._request_json", side_effect=request):
                first = provider.resolve_square_icon(game)
            self.assertEqual(first.source_url, "https://cdn.example/grid.png")
            self.assertEqual(calls, ["/v2/grids/steam/440"])
            game.icon_square_url = "file:///persisted-local-grid.png"
            game.icon_square_provider = "steamgriddb"
            with patch("lulu.artwork.SteamGridDBArtwork._request_json") as request_again:
                second = provider.resolve_square_icon(game)
            self.assertEqual(second.url, "file:///persisted-local-grid.png")
            request_again.assert_not_called()

    def test_suppressed_artwork_is_not_resolved(self) -> None:
        provider = SteamGridDBArtwork(api_key="test", cache_dir=Path(tempfile.mkdtemp()))
        game = type("Game", (), {"game_id": "local:1", "artwork_suppressed": True})()
        with patch("lulu.artwork.SteamGridDBArtwork._resolve") as resolve:
            self.assertEqual(provider.enrich([game]), {})
        resolve.assert_not_called()

    def test_gallery_uses_canonical_identity_and_portrait_grids_only(self) -> None:
        provider = SteamGridDBArtwork(api_key="test", cache_dir=Path(tempfile.mkdtemp()))
        game = type("Game", (), {
            "metadata_provider": "igdb", "metadata_game_id": "51231",
            "canonical_title": "SuperTux", "automatic_artwork_source_url": "https://cdn/current.jpg",
            "selected_artwork_source_url": "",
        })()
        calls: list[str] = []

        def request(path: str) -> dict[str, object]:
            calls.append(path)
            if path.startswith("/v2/search/autocomplete/"):
                return {"data": [{"id": 77, "name": "SuperTux"}]}
            return {"data": [
                {"id": 1, "url": "https://cdn/current.jpg", "thumb": "https://cdn/current-thumb.jpg",
                 "width": 600, "height": 900},
                {"id": 2, "url": "https://cdn/wide.jpg", "width": 1200, "height": 600},
                {"id": 3, "url": "https://cdn/small.jpg", "width": 300, "height": 450},
            ]}

        with patch("lulu.artwork.SteamGridDBArtwork._request_json", side_effect=request):
            rows = provider.gallery(game)
        self.assertEqual([row["url"] for row in rows], ["https://cdn/current.jpg"])
        self.assertTrue(rows[0]["current"])
        self.assertIn("/v2/search/autocomplete/SuperTux", calls)
        self.assertIn("/v2/grids/game/77", calls)

    def test_landscape_artwork_uses_wide_sgdb_hero_not_portrait_grid(self) -> None:
        provider = SteamGridDBArtwork(api_key="test", cache_dir=Path(tempfile.mkdtemp()))
        game = type("Game", (), {
            "game_id": "steam:440", "provider": "steam", "provider_id": "440",
            "artwork_suppressed": False, "landscape_artwork_url": "",
        })()
        calls: list[str] = []

        def request(path: str) -> dict[str, object]:
            calls.append(path)
            return {"data": [
                {"url": "https://cdn.example/portrait.jpg", "width": 600, "height": 900},
                {"url": "https://cdn.example/hero.jpg", "width": 1920, "height": 620},
            ]}

        with patch("lulu.artwork.SteamGridDBArtwork._request_json", side_effect=request):
            self.assertEqual(provider.resolve_landscape(game), "https://cdn.example/hero.jpg")
        self.assertEqual(calls, ["/v2/heroes/steam/440"])
