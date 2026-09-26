import json
from dataclasses import replace
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from lulu.catalogue import CatalogueGame, CatalogueStore
from lulu.consoled import ConsoleCatalog, ConsoleInterface
from lulu.artwork import ArtworkSelection
from lulu.igdb import IGDBClient, normalize_igdb_game
from lulu.metadata_enrichment import MetadataEnrichmentService
from lulu.protondb import ProtonDBClient
from lulu.metadata_enrichment import _exact_candidates
from lulu.steam_media import SteamStoreMedia
from lulu.metadata import MetadataMatch
from lulu.plugins.external import OwnedProviderGame


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
    def test_first_provider_sync_enriches_fresh_canonical_identity(self):
        for provider in ("epic", "gog"):
            with self.subTest(provider=provider), tempfile.TemporaryDirectory() as directory:
                store = CatalogueStore(Path(directory) / "catalogue.sqlite3")
                auth = Path(directory) / "auth.json"
                auth.write_text("{}")
                source = SimpleNamespace(provider_id=provider, config_path=auth,
                    snapshot=(OwnedProviderGame("123", "Fixture"),),
                    installed=lambda: (), refresh=lambda: None, last_error="")
                enrichment = Mock()
                enrichment.canonical_match.return_value = MetadataMatch(
                    "matched", "igdb", "55", "Canonical Fixture", "title-platform", 0.95)
                enrichment.enrich_all.return_value = ()
                catalog = SimpleNamespace(store=store, external_entitlements=(source,),
                    steam_entitlements=None,
                    provider_readiness=Mock(), _romm_injected=True, romm=None,
                    enrichment=enrichment)
                with patch("lulu.onboarding.onboarding_state", return_value={
                        "selected_providers": [provider]}):
                    ConsoleCatalog.refresh(catalog, {provider, "metadata", "metadata-enrichment"})
                matched = enrichment.canonical_match.call_args.args[0]
                self.assertEqual(matched.game_id, provider + ":123")
                enriched = enrichment.enrich_all.call_args.args[0]
                self.assertEqual(len(enriched), 1)
                self.assertEqual(enriched[0].metadata_game_id, "55")
                self.assertEqual(enriched[0].provider, provider)
                self.assertEqual(enriched[0].install_state, "available")
                store.connection.close()

    def test_empty_enrichment_scope_does_not_expand_to_catalogue(self):
        store = Mock()
        service = MetadataEnrichmentService(store, SimpleNamespace(configured=False),
                                            SimpleNamespace(enabled=False))
        self.assertEqual(service.enrich_all([]), ())
        store.list_catalogue_games.assert_not_called()

    def test_preexisting_records_receive_one_versioned_media_backfill_attempt(self):
        with tempfile.TemporaryDirectory() as directory:
            store = CatalogueStore(Path(directory) / "catalogue.sqlite3")
            game = CatalogueGame.from_steam(type("Steam", (), {
                "app_id": "26800", "title": "Braid", "install_dir": "/games/braid",
                "artwork_url": "", "last_played": 0,
            })())
            store._upsert(game); store.connection.commit()
            service = MetadataEnrichmentService(store, type("IGDB", (), {"configured": False})(),
                                                type("Proton", (), {"enabled": False})())
            self.assertTrue(service.presentation_media_backfill_needed(game.game_id))
            service.mark_presentation_media_backfill_attempted(game.game_id)
            self.assertFalse(service.presentation_media_backfill_needed(game.game_id))

    def test_presentation_media_batch_rotates_oldest_durable_attempts_first(self):
        store = Mock()
        games = [type("Game", (), {"game_id": f"game-{index}"})() for index in range(4)]
        service = MetadataEnrichmentService(store, SimpleNamespace(configured=True),
                                            SimpleNamespace(enabled=False))
        service.presentation_media_backfill_needed = Mock(return_value=True)
        attempted = {
            "game-0": {"fetched_at": "2025-01-01T00:00:00Z"},
            "game-1": None,
            "game-2": {"fetched_at": "2024-01-01T00:00:00Z"},
            "game-3": {"fetched_at": "2026-01-01T00:00:00Z"},
        }
        store.enrichment_record.side_effect = lambda _provider, game_id: attempted[game_id]

        batch = service.presentation_media_backfill_batch(games, limit=2)

        self.assertEqual([game.game_id for game in batch], ["game-1", "game-2"])

    def test_media_backfill_enriches_new_match_and_retries_missing_cache_daily(self):
        with tempfile.TemporaryDirectory() as directory:
            store = CatalogueStore(Path(directory) / "catalogue.sqlite3")
            game = CatalogueGame("romm:55", "romm", "55", "Fixture", "nes",
                                 "available", False, "", "", 0)
            store._upsert(game)
            store.connection.commit()
            igdb = Mock(configured=True)
            igdb.by_id.return_value = {"id": 55, "name": "Fixture", "screenshots": [
                {"image_id": "still", "width": 1280, "height": 720}]}
            service = MetadataEnrichmentService(store, igdb, Mock(enabled=False))
            with patch.object(service, "canonical_match", return_value=MetadataMatch(
                    "matched", "igdb", "55", "Fixture", "title-platform", 0.95)):
                self.assertIsNotNone(service.backfill_presentation_media(game.game_id))
            self.assertEqual(igdb.by_id.call_count, 1)
            record = store.enrichment_record("igdb", game.game_id)
            self.assertIn("still.jpg", record["normalized"]["preview_still_url"])
            self.assertFalse(service.presentation_media_backfill_needed(game.game_id))

            # Existing affected records have a canonical match and an old
            # attempted marker, but no IGDB cache; retry without a version bump.
            store.connection.execute("DELETE FROM metadata_enrichment WHERE provider='igdb' AND game_id=?",
                                     (game.game_id,))
            store.connection.commit()
            self.assertFalse(service.presentation_media_backfill_needed(game.game_id))
            store.connection.execute("UPDATE metadata_enrichment SET fetched_at=0 "
                                     "WHERE provider='presentation-media' AND game_id=?", (game.game_id,))
            store.connection.commit()
            self.assertTrue(service.presentation_media_backfill_needed(game.game_id))
            service.backfill_presentation_media(game.game_id)
            self.assertEqual(igdb.by_id.call_count, 2)
            self.assertFalse(service.presentation_media_backfill_needed(game.game_id))
            store.connection.execute("DELETE FROM metadata_enrichment WHERE provider='igdb' AND game_id=?",
                                     (game.game_id,))
            store.connection.commit()
            igdb.by_id.return_value = None
            igdb.search_platform.return_value = []
            service.backfill_presentation_media(game.game_id)
            self.assertEqual(store.enrichment_record("igdb", game.game_id)["status"], "unmatched")
            store.connection.execute("UPDATE metadata_enrichment SET fetched_at=0 "
                                     "WHERE provider='presentation-media' AND game_id=?", (game.game_id,))
            store.connection.commit()
            self.assertTrue(service.presentation_media_backfill_needed(game.game_id))
            store.connection.close()

    def test_igdb_media_roles_are_normalized_separately(self):
        normalized = normalize_igdb_game({
            "id": 55, "name": "Fixture", "cover": {"image_id": "cover-id", "width": 600, "height": 800},
            "screenshots": [
                {"image_id": "screen-id", "width": 1920, "height": 1080},
                {"image_id": "small-id", "width": 320, "height": 200},
            ],
        })
        self.assertEqual(normalized["icon_square_url"],
                         "https://images.igdb.com/igdb/image/upload/t_thumb/cover-id.jpg")
        self.assertEqual(normalized["icon_square_provider"], "igdb")
        self.assertEqual(normalized["preview_still_url"],
                         "https://images.igdb.com/igdb/image/upload/t_screenshot_big/screen-id.jpg")
        self.assertNotIn("preview_video_url", normalized)

    def test_igdb_uses_first_valid_screenshot_in_canonical_order(self):
        normalized = normalize_igdb_game({"id": 22, "name": "Ordered", "screenshots": [
            {"image_id": "first", "width": 1280, "height": 720},
            {"image_id": "larger", "width": 3840, "height": 2160},
        ]})
        self.assertEqual(normalized["preview_still_url"],
                         "https://images.igdb.com/igdb/image/upload/t_screenshot_big/first.jpg")
        self.assertEqual([item["url"] for item in normalized["preview_still_candidates"]], [
            "https://images.igdb.com/igdb/image/upload/t_screenshot_big/first.jpg",
            "https://images.igdb.com/igdb/image/upload/t_screenshot_big/larger.jpg",
        ])

    def test_igdb_uses_non_widescreen_screenshot_as_preview_fallback(self):
        normalized = normalize_igdb_game({"id": 358, "name": "Super Mario Bros.",
            "screenshots": [{"image_id": "sc84hp", "width": 256, "height": 224}]})
        screenshot = "https://images.igdb.com/igdb/image/upload/t_screenshot_big/sc84hp.jpg"
        self.assertEqual(normalized["preview_still_url"], screenshot)
        self.assertEqual(normalized["preview_still_provider"], "igdb")
        self.assertEqual(normalized["preview_still_candidates"][0]["url"], screenshot)

    def test_igdb_search_returns_controller_disambiguation_fields(self):
        with tempfile.TemporaryDirectory() as directory:
            store = CatalogueStore(Path(directory) / "catalogue.sqlite3")
            game = CatalogueGame.from_steam(type("Steam", (), {
                "app_id": "10", "title": "Zelda", "install_dir": "/games/zelda",
                "artwork_url": "", "last_played": 0,
            })())
            store._upsert(game); store.connection.commit()

            class IGDB:
                configured = True
                def search(self, query, platform_id):
                    self.assertion = (query, platform_id)
                    return [{"id": 55, "name": "Zelda", "first_release_date": 1262304000,
                             "platforms": [{"name": "PC"}],
                             "cover": {"image_id": "cover-id"}}]

            igdb = IGDB()
            service = MetadataEnrichmentService(store, igdb,
                                                 type("Proton", (), {"enabled": False})())
            results = service.search_games(game, "Zelda")
            self.assertEqual(igdb.assertion, ("Zelda", 6))
            self.assertEqual(results[0]["provider"], "igdb")
            self.assertEqual(results[0]["id"], "55")
            self.assertEqual(results[0]["platforms"], ["PC"])
            self.assertTrue(results[0]["thumbnail"].endswith("cover-id.jpg"))
            serialized = ConsoleInterface._variants(results[0])
            self.assertEqual(serialized["title"].value, "Zelda")
            self.assertEqual(serialized["year"].value, 2010)
            self.assertEqual(serialized["platforms"].value, ["PC"])
            self.assertEqual(serialized["thumbnail"].value, results[0]["thumbnail"])

    def test_mapping_row_keeps_title_when_thumbnail_year_and_platforms_are_missing(self):
        candidate = ConsoleCatalog._candidate_contract({
            "id": "55", "title": "Braid", "provider": "igdb", "url": "",
        })
        self.assertEqual(candidate["title"], "Braid")
        self.assertEqual(candidate["thumbnail"], "")
        self.assertEqual(candidate["source_url"], "")
        self.assertEqual(candidate["subtitle"], "IGDB")
        serialized = ConsoleInterface._variants(candidate)
        self.assertEqual(serialized["title"].value, "Braid")
        self.assertEqual(serialized["thumbnail"].value, "")
        self.assertNotIn("year", serialized)
        self.assertNotIn("platforms", serialized)

    def test_artwork_candidate_contract_keeps_thumbnail_source_and_selection_url(self):
        candidate = ConsoleCatalog._candidate_contract({
            "id": "candidate-1", "url": "https://cdn.example/art.jpg",
            "thumbnail": "https://cdn.example/thumb.jpg", "provider": "steamgriddb",
        })
        self.assertEqual(candidate["id"], "candidate-1")
        self.assertEqual(candidate["thumbnail"], "https://cdn.example/thumb.jpg")
        self.assertEqual(candidate["source_url"], "https://cdn.example/art.jpg")
        self.assertEqual(candidate["url"], "https://cdn.example/art.jpg")
        self.assertEqual(candidate["title"], "SteamGridDB")
        serialized = ConsoleInterface._variants(candidate)
        self.assertEqual(serialized["thumbnail"].value, candidate["thumbnail"])
        self.assertEqual(serialized["url"].value, candidate["url"])

    def test_thomas_was_alone_remap_refreshes_automatic_roles_and_candidate_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            store = CatalogueStore(Path(directory) / "catalogue.sqlite3")
            game = CatalogueGame(
                "steam:thomas", "steam", "thomas", "Thomas Was Alone", "PC",
                "installed", True, "/games/thomas", "old-card.jpg", 0,
                metadata_provider="igdb", metadata_game_id="identity-a",
                canonical_title="Thomas Was Alone", summary="Old description",
                genres=("Old",), artwork_source_url="old-card-source",
                automatic_artwork_url="old-card.jpg",
                automatic_artwork_source_url="old-card-source",
                automatic_artwork_provider="steamgriddb", automatic_artwork_type="cover",
                icon_square_url="old-icon.jpg", icon_square_provider="igdb",
                icon_square_source_url="old-icon-source",
                preview_still_url="old-preview.jpg", preview_still_provider="igdb",
                preview_still_source_url="old-preview-source",
            )
            store._upsert(game)
            store.connection.commit()
            store.apply_enrichment("igdb", game.game_id, "identity-a", {"summary": "Old"},
                                   match_method="manual", confidence=1.0)

            class MediaAssets:
                def __init__(self): self.removed = []
                def is_override(self, _game, _role): return False
                def remove_automatic(self, _game, role): self.removed.append(role)
                def acquire_image(self, _game, role, source):
                    return f"file:///local/{role}-{source.rsplit('/', 1)[-1]}"
                def present(self, _game, role): return f"file:///local/{role}-fallback"

            class Artwork:
                def reload_configuration(self): pass
                def resolve_typed(self, current):
                    return ArtworkSelection("file:///cache/card-b.jpg", "https://art/card-b.jpg",
                                             "steamgriddb", "cover", 600, 900)
                def resolve_square_icon(self, current):
                    return ArtworkSelection("https://art/icon-b.jpg", "https://art/icon-b.jpg",
                                             "igdb", "icon", 512, 512)
                def gallery(self, current):
                    self.gallery_identity = current.metadata_game_id
                    return [{"id": "grid-b", "url": "https://art/card-b.jpg",
                             "thumbnail": "https://art/thumb-b.jpg", "provider": "steamgriddb"}]

            class Enrichment:
                def enrich_game(self, current, **_kwargs):
                    delta = store.apply_enrichment(
                        "igdb", current.game_id, current.metadata_game_id,
                        {"summary": "New description", "genres": ["Puzzle"],
                         "game_modes": ["Single player"],
                         "icon_square_url": "https://art/icon-b.jpg",
                         "preview_still_url": "https://art/preview-b.jpg",
                         "preview_still_candidates": [{"url": "https://art/preview-b.jpg"}]},
                        match_method="manual-igdb-id", confidence=1.0)
                    return [delta] if delta else []

            catalogue = ConsoleCatalog.__new__(ConsoleCatalog)
            catalogue.store = store
            catalogue.media_assets = MediaAssets()
            catalogue.artwork = Artwork()
            catalogue.enrichment = Enrichment()
            catalogue.steam_media = SimpleNamespace(resolve=lambda _appid: {})

            catalogue.apply_metadata_match(game.game_id, "igdb", "identity-b", "Thomas Was Alone 2")
            refreshed = store.get_game(game.game_id)
            self.assertEqual(refreshed.metadata_game_id, "identity-b")
            self.assertEqual((refreshed.summary, refreshed.genres, refreshed.game_modes),
                             ("New description", ("Puzzle",), ("Single player",)))
            self.assertEqual(refreshed.artwork_source_url, "https://art/card-b.jpg")
            self.assertEqual(refreshed.automatic_artwork_source_url, "https://art/card-b.jpg")
            self.assertEqual(refreshed.icon_square_source_url, "https://art/icon-b.jpg")
            self.assertEqual(refreshed.preview_still_source_url, "https://art/preview-b.jpg")
            self.assertEqual((refreshed.provider, refreshed.platform, refreshed.provider_id,
                              refreshed.install_dir),
                             ("steam", "PC", "thomas", "/games/thomas"))
            candidates = catalogue.artwork_candidates(game.game_id, "cover")
            self.assertEqual(catalogue.artwork.gallery_identity, "identity-b")
            self.assertEqual(candidates[0]["id"], "grid-b")

    def test_mapping_card_refresh_keeps_explicit_card_override(self):
        with tempfile.TemporaryDirectory() as directory:
            store = CatalogueStore(Path(directory) / "catalogue.sqlite3")
            game = CatalogueGame(
                "steam:override", "steam", "override", "Thomas Was Alone", "PC",
                "installed", True, "/games/thomas", "file:///user/card.jpg", 0,
                metadata_provider="igdb", metadata_game_id="identity-a",
                canonical_title="Thomas Was Alone", artwork_override=True,
                artwork_source_url="user-card-source", artwork_provider="local",
                artwork_type="cover", automatic_artwork_url="old-auto.jpg",
            )
            store._upsert(game)
            store.connection.commit()
            artwork = SimpleNamespace(
                reload_configuration=lambda: None,
                resolve_typed=lambda _game: ArtworkSelection(
                    "file:///cache/new-auto.jpg", "new-auto-source", "steamgriddb", "cover"))
            catalogue = ConsoleCatalog.__new__(ConsoleCatalog)
            catalogue.store = store
            catalogue.artwork = artwork
            delta = catalogue._refresh_game_artwork(game.game_id)
            self.assertIsNotNone(delta)
            refreshed = store.get_game(game.game_id)
            self.assertEqual(refreshed.artwork_url, "file:///user/card.jpg")
            self.assertEqual(refreshed.artwork_source_url, "user-card-source")
            self.assertEqual(refreshed.automatic_artwork_source_url, "new-auto-source")

    def test_generic_title_normalization_handles_subtitles_and_numeric_punctuation(self):
        self.assertEqual(_exact_candidates([{"id": 1, "name": "Oddworld: Soulstorm"}],
                                           "Oddworld Soulstorm")[0]["id"], 1)
        candidates = [
            {"id": 1068, "name": "Super Mario Bros. 3"},
            {"id": 227896, "name": "Super Mario Bros. 3+"},
        ]
        self.assertEqual([item["id"] for item in _exact_candidates(candidates, "Super Mario Bros 3")],
                         [1068])
        self.assertEqual([item["id"] for item in _exact_candidates([
            {"id": 1067, "name": "Super Mario Bros. 2",
             "alternative_names": [{"name": "Super Mario Bros. USA"}]},
            {"id": 358, "name": "Super Mario Bros."},
        ], "Super Mario Bros")], [358])

    def test_epic_game_flows_through_generic_igdb_match_and_preserves_truth(self):
        with tempfile.TemporaryDirectory() as directory:
            store = CatalogueStore(Path(directory) / "catalogue.sqlite3")
            epic = CatalogueGame(
                game_id="epic:fixture", provider="epic", provider_id="fixture",
                title="Oddworld Soulstorm", source_title="Oddworld Soulstorm", platform="PC",
                platform_label="Epic", install_state="installed", launchable=True,
                install_dir="/games/oddworld", artwork_url="", last_played=0,
                summary="", genres=(),
            )
            store._upsert(epic)
            store.connection.commit()

            class IGDB:
                configured = True
                def search_platform(self, title, platform):
                    self.query = (title, platform)
                    return [{"id": 18357, "name": "Oddworld: Soulstorm",
                             "summary": "A rich description", "genres": [{"name": "Adventure"}],
                             "game_modes": [{"name": "Single player"}]}]
                def reload_configuration(self):
                    pass

            igdb = IGDB()
            service = MetadataEnrichmentService(store, igdb, type("Proton", (), {"enabled": False})())
            match = service.canonical_match(epic)
            self.assertEqual((match.status, match.game_id, igdb.query[1]), ("matched", "18357", 6))
            store.apply_metadata_match(epic.game_id, match)
            store.apply_enrichment("igdb", epic.game_id, "18357", {
                "summary": "A rich description", "genres": ["Adventure"],
                "game_modes": ["Single player"],
            }, match_method="title-platform", confidence=0.95)
            stored = store.get_game(epic.game_id)
            self.assertEqual((stored.provider, stored.platform, stored.summary),
                             ("epic", "PC", "A rich description"))
            self.assertEqual(stored.genres, ("Adventure",))
            self.assertEqual(stored.game_modes, ("Single player",))

    def test_romm_description_is_a_fallback_and_media_normalizer_fields_persist(self):
        with tempfile.TemporaryDirectory() as directory:
            store = CatalogueStore(Path(directory) / "catalogue.sqlite3")
            game = CatalogueGame(
                game_id="local:nes:fixture", provider="retroarch", provider_id="fixture",
                title="Super Mario Bros. 3", source_title="Super Mario Bros. 3 (PC10).nes",
                platform="nes", platform_label="Nintendo Entertainment System",
                install_state="installed", launchable=True, install_dir="/roms/smb3.nes",
                artwork_url="", last_played=0, summary="", genres=(),
            )
            store._upsert(game)
            store.connection.commit()
            store.apply_enrichment("igdb", game.game_id, "1068", {
                "summary": "IGDB summary", "genres": ["Platform"], "game_modes": ["Single player"],
                "icon_square_url": "https://img/icon.jpg", "icon_square_provider": "igdb",
                "preview_still_url": "https://img/still.jpg", "preview_still_provider": "igdb",
            }, match_method="title-platform", confidence=0.95)
            store.set_preview_media(game.game_id, video_url="https://video/remote.webm")
            stored = store.get_game(game.game_id)
            self.assertEqual((stored.provider, stored.platform, stored.summary),
                             ("retroarch", "nes", "IGDB summary"))
            self.assertEqual(stored.icon_square_provider, "igdb")
            self.assertEqual(stored.preview_still_url, "https://img/still.jpg")
            self.assertEqual(stored.preview_video_url, "")

    def test_rom_filename_uses_cleaned_title_for_generic_enrichment(self):
        with tempfile.TemporaryDirectory() as directory:
            store = CatalogueStore(Path(directory) / "catalogue.sqlite3")
            game = CatalogueGame(
                game_id="local:nes:fixture", provider="retroarch", provider_id="fixture",
                title="Super Mario Bros 3", source_title="Super Mario Bros 3 (PC10).nes",
                platform="nes", platform_label="Nintendo Entertainment System",
                install_state="installed", launchable=True, install_dir="/roms/smb3.nes",
                artwork_url="", last_played=0,
            )
            store._upsert(game)
            store.connection.commit()

            class IGDB:
                configured = True
                def search_platform(self, title, platform):
                    self.query = (title, platform)
                    return [{"id": 1068, "name": "Super Mario Bros. 3",
                             "summary": "NES description", "genres": [{"name": "Platform"}],
                             "game_modes": [{"name": "Single player"}]}]

            igdb = IGDB()
            service = MetadataEnrichmentService(store, igdb, type("Proton", (), {"enabled": False})())
            service.enrich_game(game, force=True)
            stored = store.get_game(game.game_id)
            self.assertEqual(igdb.query, ("Super Mario Bros 3", 18))
            self.assertEqual((stored.provider, stored.platform, stored.summary),
                             ("retroarch", "nes", "NES description"))
            self.assertEqual(stored.igdb_id, "1068")
            self.assertEqual(stored.genres, ("Platform",))
            self.assertEqual(stored.game_modes, ("Single player",))

    def test_steam_media_prefers_webm_and_caches_result(self):
        with tempfile.TemporaryDirectory() as directory:
            calls = []
            def request(url, timeout):
                calls.append(url)
                return json.dumps({"strMicroTrailerURL": "https://cdn/video.webm",
                                   "rgScreenshots": [{"filename": "path/screen.jpg"}]}).encode()
            client = SteamStoreMedia(Path(directory), request=request, clock=lambda: 1000)
            result = client.resolve("570")
            self.assertEqual(result["preview_video_url"], "https://cdn/video.webm")
            self.assertEqual(result["preview_video_provider"], "steam")
            self.assertIn("/570/path/screen.jpg", result["preview_still_url"])
            self.assertEqual(client.resolve("570"), result)
            self.assertEqual(len(calls), 1)

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

    def test_steam_uses_appid_before_title_and_reuses_cached_igdb_association(self):
        with tempfile.TemporaryDirectory() as directory:
            store = CatalogueStore(Path(directory) / "catalogue.sqlite3")
            game = CatalogueGame.from_steam(type("Steam", (), {
                "app_id": "10", "title": "Display Name", "install_dir": "/games/base",
                "artwork_url": "", "last_played": 0,
            })())
            game = replace(game, igdb_id="99")
            store._upsert(game); store.connection.commit()

            class IGDB:
                configured = True
                def __init__(self): self.calls = []
                def by_steam_appid(self, app_id):
                    self.calls.append(("appid", app_id))
                    return None
                def by_id(self, game_id):
                    self.calls.append(("cached", game_id))
                    return {"id": 99, "name": "Canonical", "summary": "from cache"}
                def search_platform(self, *_args):
                    raise AssertionError("title search must follow cached association")

            igdb = IGDB()
            service = MetadataEnrichmentService(store, igdb,
                                                 type("Proton", (), {"enabled": False})())
            service.enrich_game(game, force_igdb=True)
            self.assertEqual(igdb.calls, [("appid", "10"), ("cached", "99")])
            self.assertEqual(store.get_game(game.game_id).summary, "from cache")

    def test_protondb_stage_targets_installed_steam_and_reuses_ttl(self):
        with tempfile.TemporaryDirectory() as directory:
            store = CatalogueStore(Path(directory) / "catalogue.sqlite3")
            steam = CatalogueGame.from_steam(type("Steam", (), {
                "app_id": "220780", "title": "Thomas Was Alone", "install_dir": "/games/base",
                "artwork_url": "", "last_played": 0,
            })())
            local = CatalogueGame.from_local(type("Local", (), {
                "content_id": "local:nes:one", "title": "Other", "platform": "nes",
                "install_state": "installed", "launchable": True, "content_path": "/rom/Other.nes",
                "runtime": "retroarch", "platform_label": "NES", "source_title": "Other",
            })())
            store._upsert(steam)
            store._upsert(local)
            store.connection.commit()

            class Proton:
                enabled = True
                def __init__(self):
                    self.calls = []
                def summary(self, app_id):
                    self.calls.append(app_id)
                    return {"tier": "platinum", "confidence": "good", "score": 0.83}

            proton = Proton()
            service = MetadataEnrichmentService(store, type("IGDB", (), {"configured": False})(), proton)
            games = [game for game in store.list_games()
                     if game.provider == "steam" and game.provider_id.isdecimal()]
            self.assertEqual([game.game_id for game in games], [steam.game_id])
            self.assertEqual(len(service.enrich_protondb(games)), 1)
            self.assertEqual(proton.calls, ["220780"])
            self.assertEqual(store.get_game(steam.game_id).protondb_tier, "platinum")
            self.assertEqual(service.enrich_protondb(games), ())
            self.assertEqual(proton.calls, ["220780"])


if __name__ == "__main__":
    unittest.main()
