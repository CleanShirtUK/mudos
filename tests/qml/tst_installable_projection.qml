import QtQuick
import QtTest
import "../../ui/InstallableProjection.js" as Projection

TestCase {
    name: "InstallableProjection"

    function test_provider_and_platform_are_distinct() {
        var games = [
            {game_id: "steam:1", provider: "steam", platform: "pc", platform_label: "PC", availability_state: "available", install_state: "available"},
            {game_id: "epic:1", provider: "epic", platform: "pc", platform_label: "PC", availability_state: "available", install_state: "available"},
            {game_id: "gog:1", provider: "gog", platform: "pc", platform_label: "PC", availability_state: "available", install_state: "available"}
        ]
        var categories = Projection.categories(games)
        compare(categories.map(function(c) { return c.label }), ["All", "Steam", "Epic", "GOG", "PC"])
        compare(games.filter(function(g) { return Projection.matches(g, categories[4]) }).length, 3)
        for (var i = 1; i <= 3; ++i) {
            var selected = games.filter(function(g) { return Projection.matches(g, categories[i]) })
            compare(selected.length, 1)
            compare(selected[0].provider, categories[i].provider)
        }
        games[0].install_state = "installed"
        verify(!Projection.matches(games[0], categories[0]))
        verify(!Projection.matches(null, categories[0]))
    }
}
