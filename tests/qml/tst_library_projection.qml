import QtQuick
import QtTest
import "../../ui/LibraryProjection.js" as LibraryProjection

TestCase {
    name: "LibraryProjection"

    function catalog() {
        return [
            {game_id: "steam-1", platform: "pc", platform_label: "PC", provider: "steam",
             genres: ["Action", "Adventure"], game_modes: ["Single Player", "Multiplayer"]},
            {game_id: "steam-2", platform: "pc", platform_label: "PC", provider: "steam",
             genres: ["Action"], game_modes: ["Single Player"]},
            {game_id: "epic-1", platform: "pc", platform_label: "PC", provider: "epic",
             genres: ["Adventure"], game_modes: ["Co-operative"]},
            {game_id: "nes-1", platform: "nes", platform_label: "NES", provider: "retroarch",
             genres: [], game_modes: ["Single Player"]}
        ]
    }

    function test_first_dimension_change_rebuilds_provider_projection() {
        var canonical = catalog()
        var initialized = LibraryProjection.build(canonical, "platform", "", "", "", ({}))
        compare(initialized.categories[0].label, "NES")

        // One transition from the freshly initialized Platform projection.
        var provider = LibraryProjection.build(canonical, "provider", "", "", "", ({}))
        compare(provider.categories[provider.categoryIndex].label, "Epic")
        compare(provider.games.map(function(game) { return game.game_id }), ["epic-1"])
        var platform = LibraryProjection.build(canonical, "platform", "pc", "", "", ({}))
        compare(platform.categories[platform.categoryIndex].label, "PC")
        compare(platform.games.map(function(game) { return game.game_id }), ["steam-1", "steam-2", "epic-1"])

        // First reverse transition is also built directly from the catalogue.
        var reverseProvider = LibraryProjection.build(canonical, "provider", "steam", "", "", ({}))
        var reversePlatform = LibraryProjection.build(canonical, "platform", "", "", "", ({}))
        compare(reverseProvider.games.map(function(game) { return game.provider }), ["steam", "steam"])
        compare(reversePlatform.categories[reversePlatform.categoryIndex].label, "NES")
        compare(reversePlatform.games.map(function(game) { return game.game_id }), ["nes-1"])

        var steam = LibraryProjection.build(canonical, "provider", "steam", "", "", ({}))
        compare(steam.categoryKey, "steam")
        compare(steam.games.map(function(game) { return game.game_id }), ["steam-1", "steam-2"])
    }

    function test_provider_round_trip_and_multi_membership_preserve_canonical_catalogue() {
        var canonical = catalog()
        var originalIds = canonical.map(function(game) { return game.game_id })
        var steam = LibraryProjection.build(canonical, "provider", "steam", "steam-2", "", ({}))
        var epic = LibraryProjection.build(canonical, "provider", "epic", "", "", ({}))
        var returnedSteam = LibraryProjection.build(canonical, "provider", "steam", "", "", ({}))
        compare(steam.games.map(function(game) { return game.game_id }), ["steam-1", "steam-2"])
        compare(epic.games.map(function(game) { return game.game_id }), ["epic-1"])
        compare(returnedSteam.games.map(function(game) { return game.game_id }), ["steam-1", "steam-2"])
        compare(steam.games[steam.selectedIndex].game_id, "steam-2")
        compare(canonical.map(function(game) { return game.game_id }), originalIds)
        compare(canonical.length, 4)
        var repeated = LibraryProjection.build(canonical, "provider", "steam", "", "", ({}))
        compare(repeated.games.map(function(game) { return game.game_id }), ["steam-1", "steam-2"])

        var action = LibraryProjection.build(canonical, "genre", "action", "", "", ({}))
        var adventure = LibraryProjection.build(canonical, "genre", "adventure", "", "", ({}))
        compare(action.games.map(function(game) { return game.game_id }), ["steam-1", "steam-2"])
        compare(adventure.games.map(function(game) { return game.game_id }), ["steam-1", "epic-1"])

        var singlePlayer = LibraryProjection.build(canonical, "game_mode", "single player", "", "", ({}))
        compare(singlePlayer.games.map(function(game) { return game.game_id }), ["steam-1", "steam-2", "nes-1"])
    }
}
