import json
from pathlib import Path
import unittest
from urllib.parse import parse_qs, urlparse

from lulu.romm import RommApiError, RommClient, RommConfig, RommGame, RommPlatform, SteamManifest


FIXTURES = Path(__file__).parent / "fixtures" / "romm"


class Transport:
    def __init__(self, pages=None):
        self.pages = pages or []
        self.requests = []

    def request(self, method, url, headers, timeout):
        self.requests.append((method, url, headers, timeout))
        path = urlparse(url).path
        if path.endswith("/platforms"):
            return 200, (FIXTURES / "platforms-current.json").read_bytes()
        if path.endswith("/roms"):
            offset = int(parse_qs(urlparse(url).query)["offset"][0])
            return 200, (FIXTURES / ("roms-page-1.json" if offset == 0 else "roms-page-2.json")).read_bytes()
        raise AssertionError(url)


class RommTests(unittest.TestCase):
    def test_paginated_catalogue_and_authentication(self):
        transport = Transport()
        client = RommClient(RommConfig("https://romm.test", client_token="secret"), transport)
        games = client.list_games(limit=1)
        self.assertEqual([game.rom_id for game in games], [42, 43])
        self.assertEqual(parse_qs(urlparse(transport.requests[1][1]).query)["with_files"], ["true"])
        self.assertEqual(transport.requests[1][2]["Authorization"], "Bearer secret")
        self.assertNotIn("secret", repr(games))

    def test_empty_catalogue_and_platform_filter(self):
        transport = Transport()
        transport.request = lambda method, url, headers, timeout: (200, b"[]")
        client = RommClient(RommConfig("https://romm.test"), transport)
        self.assertEqual(client.list_games(), [])
        self.assertEqual(client.list_games(platform_slug="nes"), [])

    def test_normalizes_optional_presentation_metadata(self):
        value = {
            "id": 44, "name": "Metadata Game", "platform_id": 1,
            "platform_slug": "snes", "fs_name": "metadata.sfc",
            "genres": [{"name": "Action"}, "Puzzle"],
            "release_date": "1994-01-01", "release_year": 1994,
        }
        game = RommGame.from_json(value, {1: RommPlatform(1, "snes", "SNES")})
        self.assertEqual(game.genres, ("Action", "Puzzle"))
        self.assertEqual(game.release_date, "1994-01-01")
        self.assertEqual(game.release_year, 1994)

    def test_reads_nested_romm_metadata_and_multiplayer_modes(self):
        value = {
            "id": 45, "name": "Nested Metadata Game", "platform_id": 1,
            "platform_slug": "snes", "fs_name": "nested.sfc",
            "metadatum": {
                "genres": ["Action", "Puzzle"],
                "game_modes": ["Multiplayer", "Single player"],
            },
            "igdb_metadata": {
                "multiplayer_modes": [{
                    "offlinecoop": True, "offlinecoopmax": 4,
                    "onlinecoop": False, "onlinemax": 0,
                }],
            },
        }
        game = RommGame.from_json(value, {1: RommPlatform(1, "snes", "SNES")})
        self.assertEqual(game.genres, ("Action", "Puzzle"))
        self.assertEqual(game.game_mode, "Multiplayer, Single player")
        self.assertTrue(game.local_multiplayer)
        self.assertFalse(game.online_multiplayer)
        self.assertIsNone(game.total_playtime)

    def test_malformed_response_and_failure_are_errors(self):
        transport = Transport()
        transport.request = lambda *args: (200, b"not-json")
        with self.assertRaises(RommApiError):
            RommClient(RommConfig("https://romm.test"), transport).list_platforms()
        transport.request = lambda *args: (503, b"")
        with self.assertRaises(RommApiError):
            RommClient(RommConfig("https://romm.test"), transport).list_platforms()

    def test_manifest_validates_identity_and_ignores_unknown_admin_fields(self):
        manifest = SteamManifest.from_bytes(json.dumps({
            "schema": 1, "provider": "steam", "id": "268910",
            "managed_by": "mudos-steam-sync", "unknown_admin_field": True,
        }).encode())
        self.assertEqual(manifest.app_id, "268910")
        for value in (
            {"schema": 2, "provider": "steam", "id": "1"},
            {"schema": 1, "provider": "romm", "id": "1"},
            {"schema": 1, "provider": "steam", "id": "steam://run"},
        ):
            with self.subTest(value=value), self.assertRaises(RommApiError):
                SteamManifest.from_bytes(json.dumps(value).encode())
