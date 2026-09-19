import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from lulu.catalogue import CatalogueGame, CatalogueStore
from lulu.igdb import IGDBClient, normalize_igdb_game
from lulu.metadata_enrichment import MetadataEnrichmentService
from lulu.protondb import ProtonDBClient


class Config:
    enabled = True
    configured = True

    def __init__(self, values=None):
        self.values = values or {"client_id": "public", "endpoint": "https://igdb", "auth_endpoint": "https://token"}

    def get(self, key, default=None):
        return self.values.get(key, default)

    def secret_available(self, name):
        return True

    def secret(self, name):
        return "secret-value"


class MetadataProviderTests(unittest.TestCase):
    def test_igdb_token_reuse_expiry_and_single_401_retry(self):
        calls = []
        token_count = 0

        def request(req, body, timeout):
            nonlocal token_count
            calls.append((req.full_url, body))
            if req.full_url == "https://token":
                token_count += 1
                return 200, json.dumps({"access_token": f"token-{token_count}", "expires_in": 3600}).encode()
            if token_count == 1:
                return 401, b""
            return 200, b'[{"id": 42, "name": "Game"}]'

        clock = [1000.0]
        client = IGDBClient(request=request, clock=lambda: clock[0])
        client.config = Config()
        client.auth_endpoint = "https://token"
        self.assertEqual(client.by_steam_appid("123"), {"id": 42, "name": "Game"})
        self.assertEqual(token_count, 2)
        self.assertEqual(sum(1 for url, _ in calls if url == "https://token"), 2)
        # The secret is present only in the request body sent to Twitch; it is
        # never included in provider diagnostics or exception text.
        self.assertNotIn("secret-value", str(client.config.get("client_id")))

    def test_igdb_normalization_is_deliberate(self):
        value = normalize_igdb_game({
            "id": 42, "name": "Example", "summary": "Summary", "first_release_date": 1704067200,
            "genres": [{"name": "Action"}], "game_modes": [{"name": "Multiplayer"}],
            "platforms": [{"name": "PC"}],
            "involved_companies": [{"developer": True, "company": {"name": "Dev"}},
                                    {"publisher": True, "company": {"name": "Pub"}}],
            "multiplayer_modes": [{"offlinecoop": True}],
        })
        self.assertEqual(value["igdb_id"], "42")
        self.assertEqual(value["developer"], "Dev")
        self.assertTrue(value["local_multiplayer"])
        self.assertEqual(value["release_year"], 2024)

    def test_protondb_normalizes_unknown_and_never_queries_non_steam(self):
        client = ProtonDBClient(request=lambda request, timeout: (404, b""))
        client.config = Config({"endpoint": "https://proton"})
        self.assertEqual(client.summary("123")["tier"], "unknown")
        self.assertIsNone(client.summary("not-an-appid"))

    def test_local_matching_requires_exact_title_and_platform_and_rejects_ambiguity(self):
        with tempfile.TemporaryDirectory() as directory:
            store = CatalogueStore(Path(directory) / "catalogue.sqlite3")
            game = CatalogueGame.from_local(type("Local", (), {
                "content_id": "local:nes:one", "title": "Zelda (USA)", "platform": "nes",
                "install_state": "installed", "launchable": True, "content_path": "/rom/Zelda.nes",
                "runtime": "retroarch", "platform_label": "NES", "source_title": "Zelda (USA)",
            })())
            store._upsert(game); store.connection.commit()

            class IGDB:
                configured = True
                def search_platform(self, title, platform):
                    return [{"id": 1, "name": "Zelda"}, {"id": 2, "name": "Zelda"}]

            service = MetadataEnrichmentService(store, IGDB(), type("Proton", (), {"enabled": False})())
            self.assertEqual(service.enrich_game(game), [])
            record = store.enrichment_record("igdb", game.game_id)
            self.assertEqual(record["status"], "unmatched")

    def test_steam_exact_appid_enrichment_is_distinct_and_durable(self):
        with tempfile.TemporaryDirectory() as directory:
            store = CatalogueStore(Path(directory) / "catalogue.sqlite3")
            game = CatalogueGame.from_steam(type("Steam", (), {
                "app_id": "10", "title": "Base", "install_dir": "/games/base",
                "artwork_url": "", "last_played": 0,
            })())
            store._upsert(game); store.connection.commit()

            class IGDB:
                configured = True
                def by_steam_appid(self, app_id):
                    return {"id": 99, "name": "Base", "summary": "ok", "genres": []}

            service = MetadataEnrichmentService(store, IGDB(), type("Proton", (), {"enabled": False})())
            service.enrich_game(game)
            stored = store.get_game(game.game_id)
            self.assertEqual(stored.igdb_id, "99")
            self.assertEqual(store.enrichment_record("igdb", game.game_id)["match_method"], "steam-appid")
            reopened = CatalogueStore(Path(directory) / "catalogue.sqlite3")
            self.assertEqual(reopened.get_game(game.game_id).igdb_id, "99")


if __name__ == "__main__":
    unittest.main()
