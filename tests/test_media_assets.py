import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from PIL import Image

from lulu.media_assets import LocalMediaAssets, media_asset_path
from lulu.catalogue import CatalogueGame, CatalogueStore
from lulu.consoled import ConsoleCatalog


class LocalMediaAssetTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.game = SimpleNamespace(provider="steam", game_id="steam:26800",
                                    provider_id="26800", title="Braid")
        self.root = Path(self.temp.name) / "data"
        self.paths = patch("lulu.media_assets.PATHS", SimpleNamespace(
            data_root=self.root, cache_home=self.root / "cache"))
        self.paths.start()
        self.addCleanup(self.paths.stop)
        self.downloads: list[str] = []

        def downloader(url: str, destination: Path, _timeout: float) -> None:
            self.downloads.append(url)
            destination.parent.mkdir(parents=True, exist_ok=True)
            Image.new("RGB", (32, 18), "red").save(destination, format="JPEG")

        self.assets = LocalMediaAssets(downloader=downloader, ffmpeg="ffmpeg")

    def test_roles_use_stable_canonical_local_directory_and_user_replacement_wins(self) -> None:
        url = "https://images.igdb.com/screenshot.jpg"
        local = self.assets.acquire_image(self.game, "preview_still", url)
        path = media_asset_path(self.game, "preview_still")
        self.assertTrue(local.startswith("file://"))
        self.assertIn("steam/steam_26800/preview_still.jpg", str(path))
        original_mtime = path.stat().st_mtime_ns
        self.assertEqual(self.assets.acquire_image(self.game, "preview_still", url), local)
        self.assertEqual(self.downloads, [url])
        Image.new("RGB", (40, 22), "blue").save(path, format="JPEG")
        if path.stat().st_mtime_ns == original_mtime:
            import os
            os.utime(path, ns=(original_mtime + 1_000_000, original_mtime + 1_000_000))
        replacement_mtime = path.stat().st_mtime_ns
        result = self.assets.acquire_image(self.game, "preview_still", "https://new/source.jpg")
        self.assertTrue(result.startswith(path.as_uri() + "?v="))
        self.assertEqual(path.stat().st_mtime_ns, replacement_mtime)
        self.assertEqual(len(self.downloads), 1)
        state = json.loads((path.parent / ".media-assets.json").read_text())
        self.assertTrue(state["preview_still"]["override"])

    def test_existing_local_asset_is_available_offline_without_redownload(self) -> None:
        url = "https://cdn.example/icon.png"
        local = self.assets.acquire_image(self.game, "icon_square", url)
        self.assets.downloader = lambda *_args: self.fail("unexpected download")
        self.assertEqual(self.assets.present(self.game, "icon_square"), local)
        self.assertTrue(Path(media_asset_path(self.game, "icon_square")).is_file())

    def test_explicit_integrated_selection_becomes_non_overwritable_override(self) -> None:
        selected = self.assets.install_override(
            self.game, "icon_square", "https://sgdb.example/selected.png")
        path = media_asset_path(self.game, "icon_square")
        content = path.read_bytes()
        replacement = self.assets.acquire_image(
            self.game, "icon_square", "https://sgdb.example/automatic-later.png")
        self.assertEqual(replacement, selected)
        self.assertEqual(path.read_bytes(), content)
        self.assertEqual(self.downloads, ["https://sgdb.example/selected.png"])
        state = json.loads((path.parent / ".media-assets.json").read_text())
        self.assertTrue(state["icon_square"]["override"])

    def test_catalogue_artwork_selection_persists_role_override_locally(self) -> None:
        from types import SimpleNamespace

        with tempfile.TemporaryDirectory() as directory:
            store = CatalogueStore(Path(directory) / "catalogue.sqlite3")
            game = CatalogueGame("steam:26800", "steam", "26800", "Braid", "Steam",
                                 "installed", True, "/games/braid", "", 0)
            store._upsert(game); store.connection.commit()
            catalogue = SimpleNamespace(
                store=store,
                artwork_candidates=lambda _game_id, _role: [{
                    "url": "https://sgdb.example/square.png", "provider": "steamgriddb"}],
                media_assets=self.assets,
            )
            delta = ConsoleCatalog.select_presentation_artwork(
                catalogue, game.game_id, "icon_square", "https://sgdb.example/square.png")
            stored = store.get_game(game.game_id)
            path = media_asset_path(game, "icon_square")
            self.assertIsNotNone(delta)
            self.assertEqual(stored.icon_square_url.split("?", 1)[0], path.as_uri())
            self.assertEqual(stored.icon_square_source_url, "https://sgdb.example/square.png")
            before = path.read_bytes()
            store.apply_enrichment("igdb", game.game_id, "55", {
                "icon_square_url": "https://igdb.example/automatic.png",
            }, match_method="test", confidence=1)
            self.assertEqual(path.read_bytes(), before)
            self.assertEqual(store.get_game(game.game_id).icon_square_url, stored.icon_square_url)

    def test_card_square_and_preview_artwork_roles_are_independent(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = CatalogueStore(Path(directory) / "catalogue.sqlite3")
            game = CatalogueGame("steam:26800", "steam", "26800", "Braid", "PC",
                                 "installed", True, "/games/braid", "", 0)
            store._upsert(game)
            store.connection.commit()
            cover_path = Path(directory) / "selected-cover.jpg"
            cover_path.write_bytes(b"cover")
            store.set_selected_artwork(game.game_id, str(cover_path),
                                       "https://sgdb.example/card.png", 600, 900)
            after_cover = store.get_game(game.game_id)
            self.assertTrue(after_cover.artwork_override)
            self.assertEqual(after_cover.artwork_url.split("?", 1)[0], cover_path.as_uri())
            self.assertEqual(after_cover.icon_square_url, "")
            self.assertEqual(after_cover.preview_still_url, "")

            square = self.assets.install_override(
                self.game, "icon_square", "https://sgdb.example/square.png")
            store.set_icon_square_media(game.game_id, url=square, provider="steamgriddb",
                                        source_url="https://sgdb.example/square.png")
            preview = self.assets.install_override(
                self.game, "preview_still", "https://igdb.example/screenshot.jpg")
            store.set_preview_media(game.game_id, still_url=preview, still_provider="igdb",
                                    still_source_url="https://igdb.example/screenshot.jpg",
                                    prefer_still=True)
            all_roles = store.get_game(game.game_id)
            self.assertEqual(all_roles.artwork_url.split("?", 1)[0], cover_path.as_uri())
            self.assertEqual(all_roles.icon_square_url.split("?", 1)[0],
                             media_asset_path(game, "icon_square").as_uri())
            self.assertEqual(all_roles.preview_still_url.split("?", 1)[0],
                             media_asset_path(game, "preview_still").as_uri())
            self.assertEqual(all_roles.preview_animation_url, "")

    def test_mapping_artwork_refresh_preserves_explicit_card_override_and_updates_automatic(self) -> None:
        from types import SimpleNamespace
        from lulu.artwork import ArtworkSelection

        with tempfile.TemporaryDirectory() as directory:
            store = CatalogueStore(Path(directory) / "catalogue.sqlite3")
            game = CatalogueGame("steam:26800", "steam", "26800", "Braid", "PC",
                                 "installed", True, "/games/braid", "", 0)
            store._upsert(game)
            store.connection.commit()
            cover = Path(directory) / "cover.jpg"
            cover.write_bytes(b"explicit-card-art")
            store.set_selected_artwork(game.game_id, str(cover),
                                       "https://sgdb.example/card.png", 600, 900)
            artwork = SimpleNamespace(
                reload_configuration=lambda: None,
                resolve_typed=lambda _game: ArtworkSelection(
                    "file:///cache/automatic.jpg", "https://sgdb.example/new-auto.png",
                    "steamgriddb", "cover", 600, 900))
            catalogue = SimpleNamespace(store=store, artwork=artwork)
            self.assertIsNotNone(ConsoleCatalog._refresh_game_artwork(catalogue, game.game_id))
            stored = store.get_game(game.game_id)
            self.assertEqual(stored.artwork_url.split("?", 1)[0], cover.as_uri())
            self.assertEqual(stored.automatic_artwork_source_url,
                             "https://sgdb.example/new-auto.png")

    def test_mapping_change_preserves_explicit_overrides_for_all_three_roles(self) -> None:
        from lulu.artwork import ArtworkSelection

        with tempfile.TemporaryDirectory() as directory:
            store = CatalogueStore(Path(directory) / "catalogue.sqlite3")
            game = CatalogueGame(
                "steam:26800", "steam", "26800", "Braid", "PC", "installed", True,
                "/games/braid", "", 0, metadata_provider="igdb", metadata_game_id="old-id",
                canonical_title="Braid", icon_square_provider="igdb",
                preview_still_provider="igdb")
            store._upsert(game)
            store.connection.commit()
            cover = Path(directory) / "user-cover.jpg"
            cover.write_bytes(b"cover")
            store.set_selected_artwork(game.game_id, str(cover), "user-cover-source", 600, 900)
            square = self.assets.install_override(self.game, "icon_square", "user-square-source")
            preview = self.assets.install_override(self.game, "preview_still", "user-preview-source")
            store.set_icon_square_media(game.game_id, url=square, provider="steamgriddb",
                                        source_url="user-square-source")
            store.set_preview_media(game.game_id, still_url=preview, still_provider="igdb",
                                    still_source_url="user-preview-source", prefer_still=True)

            class Artwork:
                def reload_configuration(self): pass
                def resolve_typed(self, _game):
                    return ArtworkSelection("file:///automatic/card.jpg", "automatic-card",
                                            "steamgriddb", "cover", 600, 900)

            catalogue = ConsoleCatalog.__new__(ConsoleCatalog)
            catalogue.store = store
            catalogue.media_assets = self.assets
            catalogue.artwork = Artwork()
            catalogue.enrichment = SimpleNamespace(enrich_game=lambda *_args, **_kwargs: [])
            catalogue.apply_metadata_match(game.game_id, "igdb", "new-id", "Braid Remapped")
            updated = store.get_game(game.game_id)
            self.assertEqual(updated.metadata_game_id, "new-id")
            self.assertEqual(updated.artwork_source_url, "user-cover-source")
            self.assertEqual(updated.icon_square_source_url, "user-square-source")
            self.assertEqual(updated.preview_still_source_url, "user-preview-source")
            self.assertTrue(self.assets.is_override(updated, "icon_square"))
            self.assertTrue(self.assets.is_override(updated, "preview_still"))

    def test_preview_candidate_gallery_uses_screenshots_not_hero_images(self) -> None:
        from types import SimpleNamespace

        with tempfile.TemporaryDirectory() as directory:
            store = CatalogueStore(Path(directory) / "catalogue.sqlite3")
            game = CatalogueGame("flatpak:org.example.Game", "flatpak", "org.example.Game",
                                 "Example", "PC", "installed", True, "/games/example", "", 0)
            store._upsert(game); store.connection.commit()
            screenshot_url = "https://images.igdb.com/screenshot.jpg"
            store.apply_enrichment("igdb", game.game_id, "55", {
                "preview_still_candidates": [{"url": screenshot_url,
                                               "thumbnail": screenshot_url,
                                               "provider": "igdb"}],
                "hero_url": "https://cdn.example/steamgriddb-hero.jpg",
            }, match_method="test", confidence=1)
            catalogue = SimpleNamespace(store=store)
            candidates = ConsoleCatalog.artwork_candidates(
                catalogue, game.game_id, "preview_still")
            self.assertEqual([item["url"] for item in candidates], [screenshot_url])

    def test_failed_refresh_preserves_existing_local_asset(self) -> None:
        old = self.assets.acquire_image(self.game, "preview_still", "https://old/still.jpg")
        self.assets.downloader = lambda *_args: (_ for _ in ()).throw(OSError("offline"))
        self.assertEqual(self.assets.acquire_image(self.game, "preview_still", "https://new/still.jpg"), old)
        self.assertTrue(Path(media_asset_path(self.game, "preview_still")).is_file())

    def test_animation_transcode_is_acquisition_time_and_source_is_removed(self) -> None:
        source_url = "https://video.akamai.steamstatic.com/trailer.webm"

        def downloader(_url: str, destination: Path, _timeout: float) -> None:
            destination.write_bytes(b"webm")

        self.assets.downloader = downloader

        def transcode(arguments, **_kwargs):
            Path(arguments[-1]).write_bytes(b"animated-webp")
            return subprocess.CompletedProcess(arguments, 0, b"", b"")

        with patch("lulu.media_assets.subprocess.run", side_effect=transcode) as run:
            local = self.assets.acquire_animation(self.game, source_url)
        path = media_asset_path(self.game, "preview_animation")
        self.assertTrue(local.startswith(path.as_uri() + "?v="))
        self.assertIn("libwebp_anim", run.call_args.args[0])
        self.assertIn("force_original_aspect_ratio=increase", " ".join(run.call_args.args[0]))
        self.assertFalse((path.parent / "preview_animation.source.part.webm").exists())

    def test_failed_animation_refresh_keeps_old_asset(self) -> None:
        path = media_asset_path(self.game, "preview_animation")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"existing-custom-animation")
        result = self.assets.acquire_animation(self.game, "https://video.example/a.webm")
        self.assertTrue(result.startswith(path.as_uri() + "?v="))
        self.assertEqual(path.read_bytes(), b"existing-custom-animation")


if __name__ == "__main__":
    unittest.main()
