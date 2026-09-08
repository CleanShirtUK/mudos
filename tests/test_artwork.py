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
