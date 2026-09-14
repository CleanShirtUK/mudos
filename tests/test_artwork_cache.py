import tempfile
import unittest
from pathlib import Path

from lulu.artwork import LocalArtworkCache


class ArtworkCacheTests(unittest.TestCase):
    def test_remote_artwork_is_local_and_unchanged_assets_are_not_downloaded(self) -> None:
        calls = []

        def download(url: str) -> bytes:
            calls.append(url)
            return b"image"

        with tempfile.TemporaryDirectory() as directory:
            cache = LocalArtworkCache(Path(directory), downloader=download)
            first = cache.cache_remote("steam:104200", "https://romm.test/beep.jpg")
            second = cache.cache_remote("steam:104200", "https://romm.test/beep.jpg")
            self.assertTrue(first.startswith("file:"))
            self.assertEqual(first, second)
            self.assertEqual(calls, ["https://romm.test/beep.jpg"])
            self.assertEqual(len(list(Path(directory).glob("*.img"))), 1)
