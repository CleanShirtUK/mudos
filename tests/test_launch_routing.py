from __future__ import annotations

import unittest

from lulu.launch_routing import LaunchDispatch, resolve_game_launch_route


class GameLaunchRoutingTests(unittest.TestCase):
    def test_legacy_steam_id_selects_steam_session_route(self):
        route = resolve_game_launch_route("steam:40800")
        self.assertEqual(route.dispatch, LaunchDispatch.STEAM)
        self.assertEqual((route.provider_id, route.provider_game_id), ("steam", "40800"))

    def test_explicit_aurelia_identity_selects_aurelia_independent_of_override(self):
        route = resolve_game_launch_route(
            "steam-aurelia:104200", steam_launch_provider="steam",
        )
        self.assertEqual(route.dispatch, LaunchDispatch.AURELIA)
        self.assertEqual((route.provider_id, route.provider_game_id), ("steam-aurelia", "104200"))

    def test_legacy_steam_identity_obeys_aurelia_override(self):
        route = resolve_game_launch_route(
            "steam:104200", steam_launch_provider="steam-aurelia",
        )
        self.assertEqual(route.dispatch, LaunchDispatch.AURELIA)
        self.assertEqual(route.provider_id, "steam")
        self.assertEqual(route.provider_game_id, "104200")

    def test_malformed_steam_ids_are_rejected(self):
        for game_id in (
            "steam:", "steam:0", "steam:-1", "steam:abc", "steam:12:tail",
            "steam-aurelia:", "steam-aurelia:0", "steam-aurelia:12x",
        ):
            with self.subTest(game_id=game_id), self.assertRaises(ValueError):
                resolve_game_launch_route(game_id)

    def test_nonsteam_ids_remain_catalogue_dispatched(self):
        for game_id, provider, provider_game_id in (
            ("epic:Fortnite", "epic", "Fortnite"),
            ("flatpak:org.example.Game", "flatpak", "org.example.Game"),
            ("gog:12345", "gog", "12345"),
        ):
            with self.subTest(game_id=game_id):
                route = resolve_game_launch_route(game_id)
                self.assertEqual(route.dispatch, LaunchDispatch.CONSOLED)
                self.assertEqual(route.provider_id, provider)
                self.assertEqual(route.provider_game_id, provider_game_id)

    def test_consoled_catalogue_identity_remains_provider_authoritative(self):
        route = resolve_game_launch_route(
            "steam:104200", catalogue_provider="steam", catalogue_provider_id="104200",
        )
        self.assertEqual(route.dispatch, LaunchDispatch.STEAM)
        self.assertEqual((route.provider_id, route.provider_game_id), ("steam", "104200"))

    def test_http_and_dbus_boundaries_share_the_same_interpretation(self):
        # Both production boundaries import this one resolver; catalogue
        # metadata in Consoled supplies the same provider/id pair as the ID.
        bridge_route = resolve_game_launch_route(
            "steam:104200", steam_launch_provider="steam-aurelia",
        )
        dbus_route = resolve_game_launch_route(
            "steam:104200", steam_launch_provider="steam-aurelia",
            catalogue_provider="steam", catalogue_provider_id="104200",
        )
        self.assertEqual(bridge_route, dbus_route)


if __name__ == "__main__":
    unittest.main()
