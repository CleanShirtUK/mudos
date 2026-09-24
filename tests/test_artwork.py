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

    def test_explicit_igdb_mapping_uses_new_canonical_association_for_card_art(self) -> None:
        provider = SteamGridDBArtwork(api_key="test", cache_dir=Path(tempfile.mkdtemp()))
        with patch.object(SteamGridDBArtwork, "_find_canonical_image",
                          return_value="https://cdn.example/new.jpg") as find:
            result = provider._find_image("steam", "123", "Mapped Title", "igdb", "identity-b")
        self.assertEqual(result, "https://cdn.example/new.jpg")
        find.assert_called_once_with("Mapped Title", "identity-b")

    def test_typed_steam_cover_prefers_explicit_igdb_identity_after_remap(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            provider = SteamGridDBArtwork(api_key="test", cache_dir=Path(directory))
            game = type("Game", (), {
                "game_id": "steam:123", "provider": "steam", "provider_id": "123",
                "title": "Old title", "canonical_title": "New title",
                "metadata_provider": "igdb", "metadata_game_id": "identity-b",
                "artwork_suppressed": False, "artwork_url": "", "artwork_type": "",
                "artwork_provider": "", "canonical_cover_url": "",
            })()
            with patch.object(SteamGridDBArtwork, "_find_canonical_image",
                              return_value="https://cdn.example/new-map.jpg") as find_canonical, \
                    patch.object(SteamGridDBArtwork, "_find_image") as find_steam, \
                    patch.object(SteamGridDBArtwork, "_download") as download:
                def materialize(_url, destination):
                    Path(destination).write_bytes(b"image")
                download.side_effect = materialize
                selection = provider.resolve_typed(game)
            self.assertEqual(selection.source_url, "https://cdn.example/new-map.jpg")
            find_canonical.assert_called_once_with("New title", "identity-b")
            find_steam.assert_not_called()

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

    def test_remapped_steam_square_roles_prefer_new_igdb_association(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            provider = SteamGridDBArtwork(api_key="test", cache_dir=Path(directory))
            game = type("Game", (), {
                "game_id": "steam:123", "provider": "steam", "provider_id": "123",
                "title": "Old title", "canonical_title": "Mapped title",
                "metadata_provider": "igdb", "metadata_game_id": "identity-b",
                "artwork_suppressed": False, "icon_square_url": "",
                "icon_square_provider": "", "icon_square_source_url": "", "icon_url": "",
            })()
            calls = []
            def request(path):
                calls.append(path)
                return {"data": [{"id": 2, "url": "https://cdn.example/square.png",
                                  "width": 512, "height": 512}]}
            with patch.object(SteamGridDBArtwork, "_search_sgdb_game_id", return_value="sgdb-b") as association, \
                    patch.object(SteamGridDBArtwork, "_find_canonical_game_id", return_value="sgdb-b") as gallery_association, \
                    patch.object(SteamGridDBArtwork, "_request_json", side_effect=request):
                selection = provider.resolve_square_icon(game)
                gallery = provider.square_gallery(game)
            association.assert_called_with("Mapped title", "identity-b")
            gallery_association.assert_called_with("Mapped title", "identity-b")
            self.assertTrue(calls)
            self.assertTrue(all("/game/sgdb-b" in path for path in calls))
            self.assertEqual(selection.source_url, "https://cdn.example/square.png")
            self.assertEqual(gallery[0]["url"], "https://cdn.example/square.png")

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
        self.assertEqual(rows[0]["provider"], "steamgriddb")
        self.assertEqual(rows[0]["source"], "SteamGridDB")
        self.assertEqual(rows[0]["thumbnail"], "https://cdn/current-thumb.jpg")
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
