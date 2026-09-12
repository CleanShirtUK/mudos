import json
from pathlib import Path
import tempfile
import unittest
from urllib.parse import parse_qs, urlparse

from lulu.romm import RommClient, RommConfig, RommInstaller


FIXTURES = Path(__file__).parent / "fixtures" / "romm"


class FixtureTransport:
    def __init__(self) -> None:
        self.requests: list[tuple[str, str, dict[str, str]]] = []

    def request(self, method: str, url: str, headers: dict[str, str], data: bytes | None = None) -> bytes:
        self.requests.append((method, url, headers))
        path = urlparse(url).path
        if path.endswith("/platforms"):
            return (FIXTURES / "platforms.json").read_bytes()
        if path.endswith("/roms"):
            return (FIXTURES / "roms.json").read_bytes()
        if path.endswith("/roms/42/simple"):
            game = json.loads((FIXTURES / "roms.json").read_text())["items"][0]
            return json.dumps(game).encode()
        if path.endswith("/roms/42/content/Super%20Mario%20World.sfc"):
            return b"rom-data"
        raise AssertionError(f"unexpected fixture request: {method} {url}")


class RommClientTests(unittest.TestCase):
    def setUp(self) -> None:
        self.transport = FixtureTransport()
        self.client = RommClient(
            RommConfig("https://romm.example.test", client_token="rmm_fixture_token"), self.transport
        )

    def test_reads_documented_platform_and_paginated_library_shapes(self) -> None:
        platforms = self.client.list_platforms()
        library = self.client.list_games(search_term="Mario")

        self.assertEqual(platforms[0].display_name, "SNES")
        self.assertEqual(library.total, 1)
        self.assertEqual(library.games[0].id, 42)
        request = self.transport.requests[-1]
        self.assertEqual(parse_qs(urlparse(request[1]).query)["search_term"], ["Mario"])
        self.assertEqual(request[2]["Authorization"], "Bearer rmm_fixture_token")

    def test_installer_downloads_to_platform_root_without_live_server(self) -> None:
        game = self.client.list_games().games[0]
        with tempfile.TemporaryDirectory() as directory:
            installed = RommInstaller(self.client).install(game, Path(directory))

            self.assertEqual(installed.read_bytes(), b"rom-data")
            self.assertEqual(installed.relative_to(directory), Path("snes/Super Mario World.sfc"))

    def test_config_supports_documented_basic_and_bearer_auth(self) -> None:
        self.assertTrue(RommConfig("https://romm.test", username="alice", password="secret").auth_header().startswith("Basic "))
        self.assertEqual(RommConfig("https://romm.test", access_token="jwt").auth_header(), "Bearer jwt")
        self.assertEqual(RommConfig("https://romm.test/").api_url, "https://romm.test/api")

    def test_rejects_invalid_download_filename_and_page_values(self) -> None:
        game = self.client.list_games().games[0]
        with self.assertRaises(ValueError):
            self.client.list_games(limit=0)
        with self.assertRaises(ValueError):
            self.client.download_game(game, Path("/tmp/out"), "../escape.sfc")


if __name__ == "__main__":
    unittest.main()
