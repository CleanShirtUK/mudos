from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from lulu.catalogue import CatalogueStore
from lulu.consoled import ConsoleCatalog
from lulu import onboarding
from lulu.plugins import PluginRegistry
from lulu.plugins.romm.client import RommConfig, RommFile, RommGame
from lulu.plugins.romm.readiness import RommReadinessStore
from lulu.provider_readiness import ProviderReadinessStore


class EmptySteam:
    def list_installed(self):
        return []


class EmptyLocal:
    def list_installed(self, root):
        return []


class FakeRomm:
    def __init__(self, games, config):
        self.games = games
        self.config = config
        self.calls = 0

    def list_games(self):
        self.calls += 1
        return self.games


class RommReadinessTests(unittest.TestCase):
    def test_in_flight_provider_states_become_failure_after_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "provider-readiness.json"
            path.write_text('{"retired-provider":{"status":"syncing","catalogue_count":4}}')
            store = ProviderReadinessStore(path)
            state = store.get("retired-provider")
            self.assertEqual(state["status"], "sync_failed")
            self.assertIn("interrupted", state["message"])

    def test_romm_syncing_state_is_recovered_on_restart(self):
        config = RommConfig("https://romm.example", client_token="fixture-token")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "readiness.json"
            before = RommReadinessStore(path)
            before.set("syncing", config, message="running")
            with patch("lulu.plugins.romm.readiness.RommConfig.from_file", return_value=config):
                restarted = RommReadinessStore(path)
            self.assertEqual(
                restarted.snapshot(selected=True, installed=True, config=config)["status"],
                "sync_failed",
            )

    def test_unselected_romm_never_reconciles_even_when_configured(self):
        config = RommConfig("https://romm.example", client_token="fixture-token")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry = PluginRegistry(root / "plugins")
            registry.discover()
            client = FakeRomm([], config)
            catalog = ConsoleCatalog(
                CatalogueStore(root / "catalogue.sqlite3"), EmptySteam(), EmptyLocal(),
                romm=client, plugin_registry=registry,
                romm_readiness=RommReadinessStore(root / "readiness.json"),
            )
            with patch.object(onboarding, "_STATE_PATH", root / "onboarding.json"):
                catalog.refresh({"romm"})
            self.assertEqual(client.calls, 0)

    def test_initial_reconcile_populates_normal_installable_and_persists_ready(self):
        config = RommConfig("https://romm.example", client_token="fixture-token")
        games = [
            RommGame(31, "Solar Drift", 2, "gba", "Game Boy Advance", "solar.gba", ".gba", 20,
                     "https://romm.example/art/solar.jpg", False, (RommFile(310, "solar.gba"),)),
            RommGame(32, "Moon Circuit", 8, "snes", "Super Nintendo", "moon.sfc", ".sfc", 30,
                     "", False, (RommFile(320, "moon.sfc"),)),
        ]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store = CatalogueStore(root / "catalogue.sqlite3")
            registry = PluginRegistry(root / "plugins")
            registry.discover()
            readiness = RommReadinessStore(root / "romm" / "readiness.json")
            readiness.set("authenticated", config, message="fixture validation")
            catalog = ConsoleCatalog(
                store, EmptySteam(), EmptyLocal(), romm=FakeRomm(games, config),
                plugin_registry=registry, romm_readiness=readiness,
            )

            with patch.object(onboarding, "_STATE_PATH", root / "onboarding.json"):
                onboarding.save_progress(integrations=["providers.romm"])
                catalog.refresh({"romm"})

            available = store.list_available_games("romm")
            self.assertEqual({game.game_id for game in available}, {"romm:31", "romm:32"})
            self.assertEqual(store.list_games(), [])
            self.assertEqual(available[0].catalogue_source, "romm")
            self.assertEqual({game.provider_id for game in available}, {"31", "32"})
            state = readiness.snapshot(selected=True, installed=True, config=config)
            self.assertEqual(state["status"], "ready")
            self.assertEqual(state["record_count"], 2)
            self.assertEqual(state["installable_count"], 2)
            self.assertNotIn("fixture-token", (root / "romm" / "readiness.json").read_text())

    def test_ready_requires_reconcile_and_is_invalidated_by_config_change(self):
        first = RommConfig("https://romm.example", client_token="first-token")
        second = RommConfig("https://romm.example", client_token="second-token")
        with tempfile.TemporaryDirectory() as directory:
            store = RommReadinessStore(Path(directory) / "readiness.json")
            state = store.snapshot(selected=True, installed=True, config=first)
            self.assertEqual(state["status"], "installed")
            store.set("configuration_invalid", first, message="Rejected token")
            self.assertEqual(store.snapshot(selected=True, installed=True, config=first)["status"],
                             "configuration_invalid")
            self.assertEqual(store.snapshot(selected=True, installed=True, config=second)["status"],
                             "installed")
            store.set("ready", first, record_count=3, installable_count=2)
            self.assertEqual(store.snapshot(selected=True, installed=True, config=first)["status"], "ready")
            self.assertEqual(store.snapshot(selected=True, installed=True, config=second)["status"],
                             "installed")

    def test_production_catalogue_refresh_reloads_saved_oobe_config(self):
        config = RommConfig("https://fresh.example", client_token="fresh-token")
        game = RommGame(41, "Fresh Start", 1, "nes", "Nintendo Entertainment System",
                        "fresh.nes", ".nes", 10, "", False)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry = PluginRegistry(root / "plugins")
            registry.discover()
            readiness = RommReadinessStore(root / "readiness.json")
            readiness.set("authenticated", config, message="fixture validation")
            catalog = ConsoleCatalog(
                CatalogueStore(root / "catalogue.sqlite3"), EmptySteam(), EmptyLocal(),
                plugin_registry=registry, romm_readiness=readiness,
            )
            with patch.object(onboarding, "_STATE_PATH", root / "onboarding.json"), \
                    patch("lulu.consoled.RommConfig.from_file", return_value=config), \
                    patch("lulu.consoled.RommClient", return_value=FakeRomm([game], config)):
                onboarding.save_progress(integrations=["providers.romm"])
                catalog.refresh({"romm"})
            self.assertEqual([item["game_id"] for item in catalog.available_games("romm")], ["romm:41"])
            self.assertEqual(readiness.snapshot(selected=True, installed=True, config=config)["status"], "ready")
