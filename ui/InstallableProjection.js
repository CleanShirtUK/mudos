.pragma library

function categories(games) {
    var result = [{label: "All", scope: "all"}]
    var providers = ["steam", "epic", "gog"]
    var labels = ["Steam", "Epic", "GOG"]
    for (var p = 0; p < providers.length; ++p)
        result.push({label: labels[p], scope: "provider:" + providers[p], provider: providers[p]})
    var seen = ({})
    for (var i = 0; i < games.length; ++i) {
        var game = games[i]
        var platform = String(game.platform || "")
        if (platform && !seen[platform]) {
            seen[platform] = true
            result.push({label: String(game.platform_label || platform), scope: platform})
        }
    }
    return result
}

function matches(game, category) {
    if (!game || game.availability_state !== "available" || game.install_state !== "available")
        return false
    if (!category || category.scope === "all") return true
    if (category.provider) return game.provider === category.provider
    return game.platform === category.scope
}
