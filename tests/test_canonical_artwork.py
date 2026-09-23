import tempfile
import unittest
from pathlib import Path

from lulu.artwork import SteamGridDBArtwork
from lulu.catalogue import CatalogueGame, CatalogueStore
from lulu.metadata import MetadataMatch


class CanonicalArtworkTests(unittest.TestCase):
    def test_flatpak_icon_is_not_card_cover(self) -> None:
        game = CatalogueGame.from_component_app({
            "application_id": "org.example.Game", "name": "Example Game",
            "icon": "https://example/icon.png", "categories": ["Game"],
        })
        self.assertEqual(game.artwork_type, "icon")
        self.assertEqual(game.icon_url, "https://example/icon.png")
        self.assertEqual(game.artwork_url, "")

    def test_cover_candidate_rejects_square_and_wide_images(self) -> None:
        selected = SteamGridDBArtwork._choose_cover([
            {"url": "square", "width": 512, "height": 512},
            {"url": "wide", "width": 920, "height": 518},
            {"url": "cover", "width": 600, "height": 900},
        ])
        self.assertEqual(selected, "cover")

    def test_failed_canonical_match_preserves_provider_artwork(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = CatalogueStore(Path(directory) / "catalogue.sqlite3")
            game = CatalogueGame(
                "steam:10", "steam", "10", "Example", "Steam", "installed", True,
                "/games/example", "file:///cover.jpg", 0,
                artwork_type="cover", artwork_provider="steam",
            )
            store._upsert(game)
            store.connection.commit()
            store.apply_metadata_match(
                game.game_id,
                MetadataMatch("unmatched", normalized_search_title="example",
                              method="igdb-network-error"),
            )
            stored = store.get_game(game.game_id)
            self.assertEqual(stored.artwork_url, "file:///cover.jpg")
            self.assertEqual(stored.artwork_provider, "steam")


if __name__ == "__main__":
    unittest.main()
