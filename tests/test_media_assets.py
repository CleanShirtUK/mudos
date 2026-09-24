import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from PIL import Image

from lulu.media_assets import LocalMediaAssets, media_asset_path


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
