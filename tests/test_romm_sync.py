import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from lulu.artwork import LocalArtworkCache
from lulu.catalogue import CatalogueStore
from lulu.consoled import ConsoleCatalog
from lulu.romm import RommFile, RommGame
from lulu import onboarding
from lulu.plugins.romm.client import RommConfig
from lulu.plugins.romm.readiness import RommReadinessStore


class EmptySteam:
    def list_installed(self):
        return []


class EmptyLocal:
    def list_installed(self, root):
        return []


class FakeRomm:
    def __init__(self, game, config):
        self.game = game
        self.config = config

    def list_games(self):
        return [self.game]


class RommSyncTests(unittest.TestCase):
    def test_sync_persists_metadata_and_local_artwork_and_reuses_asset(self):
        game = RommGame(
            272, "BEEP", 7, "gba", "GBA", "beep.rom", ".rom", 10,
            "https://romm.test/beep.jpg", False, (RommFile(2720, "beep.rom"),),
            ("Action",), "2001-04-20", 2001,
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store = CatalogueStore(root / "catalogue.sqlite3")
            config = RommConfig("https://romm.test", client_token="fixture-token")
            readiness = RommReadinessStore(root / "readiness.json")
            readiness.set("ready", config, message="fixture initial sync complete")
            catalog = ConsoleCatalog(store, EmptySteam(), EmptyLocal(),
                                     romm=FakeRomm(game, config), romm_readiness=readiness)
            calls = []
            catalog.romm_artwork = LocalArtworkCache(
                root / "artwork", downloader=lambda url: calls.append(url) or b"image"
            )
            with patch.object(onboarding, "_STATE_PATH", root / "onboarding.json"):
                onboarding.save_progress(integrations=["providers.romm"])
                catalog.refresh()
                catalog.refresh()
            record = store.get_game("romm:272")
            artwork = Path(record.artwork_url.removeprefix("file://"))
            self.assertEqual(record.catalogue_source, "romm")
            self.assertEqual(record.genres, ("Action",))
            self.assertEqual(record.platform, "gba")
            self.assertEqual(record.provider, "romm")
            self.assertEqual(record.provider_id, "272")
            self.assertTrue(artwork.is_file())
            self.assertEqual(calls, ["https://romm.test/beep.jpg"])
            store.connection.close()
            cached = CatalogueStore(root / "catalogue.sqlite3")
            self.assertEqual(cached.get_game("romm:272").title, "BEEP")
