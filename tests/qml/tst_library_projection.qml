import QtQuick
import QtTest
import "../../ui/LibraryProjection.js" as LibraryProjection
import "../../ui/GameArtwork.js" as GameArtwork
import "../../ui/GameMetadata.js" as GameMetadata
import "../../ui/DescriptionFit.js" as DescriptionFit

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

    function test_artwork_roles_and_shared_metadata_rows() {
        var game = {provider: "steam", runtime: "steam", platform: "pc", platform_label: "PC",
            artwork_url: "https://cdn.example/portrait.jpg", artwork_width: 600, artwork_height: 900,
            icon_url: "https://cdn.example/icon.png", icon_square_url: "file:///home/lulu/art/icon.png",
            landscape_artwork_url: "https://cdn.example/hero.jpg",
            preview_still_url: "https://cdn.example/hero.jpg",
            genres: ["Action"], game_modes: ["Single Player"], last_played: 1,
            total_playtime: 125, local_multiplayer: true, online_multiplayer: true,
            protondb_rating: "gold"}
        compare(GameArtwork.portraitIcon(game), "image://mudos-artwork/file%3A%2F%2F%2Fhome%2Flulu%2Fart%2Ficon.png")
        compare(GameArtwork.previewStill(game), "")
        game.preview_still_url = "file:///home/lulu/art/preview.jpg"
        compare(GameArtwork.previewStill(game), "image://mudos-artwork/file%3A%2F%2F%2Fhome%2Flulu%2Fart%2Fpreview.jpg")
        var rows = GameMetadata.rows(game, function() { return "1 Jan 1970" })
        compare(rows.map(function(row) { return row.text }), ["Action", "Single Player",
            "1 Jan 1970", "Total Playtime  2h 5m", "Local Multiplayer", "Online Multiplayer",
            "Gold", "PC", "Steam"])
        verify(rows.every(function(row) { return row.glyph.length > 0 }))
        var nfsModes = ["Single player", "Multiplayer", "Split screen"]
        var nfsRows = GameMetadata.rows({game_modes: nfsModes, platform: "PC", provider: "romm"}, function() {})
        var modeRows = nfsRows.filter(function(row) { return row.glyph === GameMetadata.glyph("gameModes") })
        compare(modeRows.length, 1)
        compare(modeRows[0].text, "Single player · Multiplayer · Split screen")

        var braidGenres = ["Platform", "Puzzle", "Strategy", "Adventure", "Indie"]
        var braidRows = GameMetadata.rows({genres: braidGenres, platform: "PC", provider: "steam"}, function() {})
        var genreRows = braidRows.filter(function(row) { return row.glyph === GameMetadata.glyph("genres") })
        compare(genreRows.length, 1)
        compare(genreRows[0].text, "Platform · Puzzle · Strategy · Adventure · Indie")
    }

    function test_description_fit_uses_sentences_then_elides() {
        var shortText = "A short description."
        var unchanged = DescriptionFit.select(shortText, function(candidate) {
            return candidate === shortText
        })
        compare(unchanged.text, shortText)
        verify(!unchanged.elide)

        var longText = "First complete sentence. Second complete sentence. Third sentence."
        var measured = []
        var shortened = DescriptionFit.select(longText, function(candidate) {
            measured.push(candidate)
            return candidate.length <= "First complete sentence. Second complete sentence.".length
        })
        compare(shortened.text, "First complete sentence. Second complete sentence.")
        verify(shortened.shortened)
        verify(measured.indexOf(shortened.text) >= 0)
        verify(!shortened.elide)

        var noBoundary = DescriptionFit.select("unbroken".repeat(20), function() { return false })
        verify(noBoundary.elide)
        compare(noBoundary.text, "unbroken".repeat(20))

        var empty = DescriptionFit.select("", function() { return false })
        compare(empty.text, "")
        verify(!empty.elide)
    }
}
