import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from lulu.catalogue import CatalogueStore
from lulu.steam_entitlements import (
    SteamEntitlement, SteamEntitlementConfig, SteamEntitlementError, SteamEntitlementSource,
)
from lulu.steam_provider import InstalledSteamGame


ROOT = Path(__file__).resolve().parent


class FakeSteamProvider:
    def __init__(self, games):
        self.games = games

    def list_installed(self):
        return self.games


class SteamEntitlementTests(unittest.TestCase):
    def test_reload_config_picks_up_credentials_saved_after_source_startup(self) -> None:
        config = SteamEntitlementConfig("76561198000000000", Path("/unused/key"))
        source = SteamEntitlementSource(config=None)
        with patch("lulu.plugins.steam.entitlements.SteamEntitlementConfig.from_file",
                   return_value=config):
            self.assertIs(source.reload_config(), config)

    def test_entitlement_config_keeps_username_and_resolved_account_id(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            key = root / "steam-key"
            key.write_text("fixture")
            key.chmod(0o600)
            config_path = root / "steam.json"
            config_path.write_text(json.dumps({
                "steam_id": "76561198000000000",
                "steam_username": "fixtureuser",
                "api_key_file": str(key),
            }))
            config = SteamEntitlementConfig.from_file(config_path)
        self.assertIsNotNone(config)
        self.assertEqual(config.steam_id, "76561198000000000")
        self.assertEqual(config.steam_username, "fixtureuser")

    def test_mullock_sparse_marker_fixture_parity(self) -> None:
        markers = json.loads((ROOT / "fixtures/steam-owned-markers.json").read_text())
        entitlements = tuple(SteamEntitlement(str(item["id"]), {
            "263980": "Out There Somewhere",
            "40800": "Super Meat Boy",
            "268910": "Cuphead",
        }[str(item["id"])]) for item in markers)
        installed = InstalledSteamGame("40800", "Super Meat Boy", "/games/Super Meat Boy", "/games", 1, 0)
        with tempfile.TemporaryDirectory() as directory:
            store = CatalogueStore(Path(directory) / "catalogue.sqlite3")
            rows = store.reconcile_steam_entitlements(entitlements, FakeSteamProvider([installed]))

        self.assertEqual({row.game_id for row in rows}, {"steam:263980", "steam:40800", "steam:268910"})
        available = {row.game_id for row in rows if row.install_state == "available"}
        self.assertEqual(available, {"steam:263980", "steam:268910"})
        installed_row = next(row for row in rows if row.game_id == "steam:40800")
        self.assertEqual(installed_row.install_state, "installed")
        self.assertTrue(installed_row.launchable)
        self.assertEqual(installed_row.provider_id, "40800")
        self.assertEqual(installed_row.catalogue_source, "steam")
        self.assertEqual(installed_row.platform, "PC")
        installable = store.list_available_games("steam")
        self.assertEqual({game.game_id for game in installable}, {"steam:263980", "steam:268910"})
        self.assertEqual(sum(game.game_id == "steam:40800" for game in store.list_games("steam")), 1)

    def test_valve_response_validation_is_fail_closed(self) -> None:
        valid = {"response": {"games": [{"appid": 263980, "name": "Out There Somewhere"}]}}
        self.assertEqual(SteamEntitlementSource.parse_response(valid),
                         (SteamEntitlement("263980", "Out There Somewhere"),))
        for invalid in (
            {"response": {}}, {"response": {"games": []}},
            {"response": {"games": [{"appid": 0, "name": "bad"}]}},
            {"response": {"games": [{"appid": 1, "name": ""}]}},
        ):
            with self.assertRaises(SteamEntitlementError):
                SteamEntitlementSource.parse_response(invalid)

    def test_failed_refresh_retains_last_good_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            key = Path(directory) / "steam-web-api-key"
            key.write_text("test-key")
            key.chmod(0o600)
            config = SteamEntitlementConfig("76561198000000000", key)
            responses = [
                json.dumps({"response": {"games": [{"appid": 263980, "name": "Out There Somewhere"}]}}).encode(),
                b"not json",
            ]
            snapshot = Path(directory) / "snapshot.json"
            source = SteamEntitlementSource(config, lambda _url, _timeout: responses.pop(0), snapshot)
            self.assertEqual(len(source.refresh()), 1)
            self.assertEqual(source.refresh(), (SteamEntitlement("263980", "Out There Somewhere"),))
            self.assertFalse(source.last_refresh_succeeded)
            self.assertTrue(source.has_snapshot)
            restarted = SteamEntitlementSource(config, lambda _url, _timeout: b"broken", snapshot)
            self.assertEqual(restarted.snapshot, source.snapshot)

    def test_manifest_is_authoritative_for_install_state_without_revoking_ownership(self) -> None:
        entitlement = (SteamEntitlement("263980", "Out There Somewhere"),)
        installed = InstalledSteamGame("263980", "Out There Somewhere", "/games/out", "/games", 1, 0)
        with tempfile.TemporaryDirectory() as directory:
            store = CatalogueStore(Path(directory) / "catalogue.sqlite3")
            provider = FakeSteamProvider([installed])
            store.reconcile_steam_entitlements(entitlement, provider)
            provider.games = []
            rows = store.reconcile_steam_entitlements(entitlement, provider)

        self.assertEqual(rows[0].install_state, "available")
        self.assertFalse(rows[0].launchable)
        self.assertEqual(store.get_game("steam:263980").availability_state, "available")

    def test_owned_available_transitions_to_installed_without_restart(self) -> None:
        entitlement = (SteamEntitlement("220780", "Thomas Was Alone"),)
        with tempfile.TemporaryDirectory() as directory:
            store = CatalogueStore(Path(directory) / "catalogue.sqlite3")
            provider = FakeSteamProvider([])
            store.reconcile_steam_entitlements(entitlement, provider)
            self.assertEqual([game.game_id for game in store.list_available_games("romm")],
                             ["steam:220780"])
            provider.games = [InstalledSteamGame(
                "220780", "Thomas Was Alone", "/games/Thomas", "/games", 1, 0
            )]
            store.reconcile_steam_entitlements(entitlement, provider)
            self.assertEqual(store.list_available_games("romm"), [])
            self.assertEqual([game.game_id for game in store.list_games("steam")],
                             ["steam:220780"])


if __name__ == "__main__":
    unittest.main()
