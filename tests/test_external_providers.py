import tempfile
from pathlib import Path
import unittest

from lulu.catalogue import CatalogueStore
from lulu.plugins.external import OwnedProviderGame, SnapshotEntitlementSource, normalize_game
from lulu.plugins.epic import EpicAuthentication
from lulu.plugins.gog import GogAuthentication


class ExternalProviderTests(unittest.TestCase):
    def test_normalized_identity_does_not_require_metadata(self) -> None:
        game = normalize_game({"app_name": "abc", "app_title": "Owned game"},
                              provider_id_keys=("app_name",), title_keys=("app_title",))
        self.assertEqual(game, OwnedProviderGame("abc", "Owned game"))

    def test_owned_uninstalled_game_is_reconciled_to_installable(self) -> None:
        owned = OwnedProviderGame("one", "GOG One")
        installed = OwnedProviderGame("two", "GOG Two", "/home/lulu/Games/Executables/gog/two")
        with tempfile.TemporaryDirectory() as directory:
            store = CatalogueStore(Path(directory) / "catalogue.sqlite3")
            rows = store.reconcile_owned_provider("gog", (owned, installed), (installed,))
            self.assertEqual({row.game_id for row in rows}, {"gog:one", "gog:two"})
            self.assertEqual([row.game_id for row in store.list_available_games()], ["gog:one"])
            self.assertEqual([row.game_id for row in store.list_games()], ["gog:two"])
            self.assertFalse(next(row for row in rows if row.provider_id == "one").metadata_game_id)

    def test_snapshot_round_trip_is_last_known_good(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = SnapshotEntitlementSource("epic", Path(directory) / "entitlements.json")
            source.update((OwnedProviderGame("one", "One"),), ())
            restored = SnapshotEntitlementSource("epic", Path(directory) / "entitlements.json")
            self.assertEqual(restored.snapshot[0].provider_id, "one")

    def test_authentication_is_generic(self) -> None:
        self.assertEqual(GogAuthentication().status()["provider_id"], "gog")
        self.assertEqual(EpicAuthentication().status()["provider_id"], "epic")
