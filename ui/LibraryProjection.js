.pragma library

function providerLabel(provider) {
    var labels = ({steam: "Steam", epic: "Epic", gog: "GOG", flatpak: "Flatpak",
        lutris: "Lutris", retroarch: "RetroArch", dolphin: "Dolphin",
        eden: "Eden", pcsx2: "PCSX2"})
    var key = String(provider || "").toLowerCase()
    return labels[key] || (key && key !== "local" ? key.charAt(0).toUpperCase() + key.slice(1) : "Other")
}

function valuesFor(game, mode) {
    if (!game) return [{key: "other", label: "Other"}]
    var values = []
    if (mode === "platform") {
        var platformLabel = String(game.platform_label || game.platform || "Other")
        values = [{key: String(game.platform || platformLabel).toLowerCase(), label: platformLabel}]
    } else if (mode === "provider") {
        var provider = String(game.provider || "other").toLowerCase()
        values = [{key: provider === "local" ? "other" : provider, label: providerLabel(provider)}]
    } else if (mode === "genre") {
        values = game.genres && game.genres.length ? game.genres : ["Other"]
    } else {
        values = game.game_modes && game.game_modes.length ? game.game_modes : [game.game_mode || "Other"]
    }
    if (!values.length) values = ["Other"]
    return values.map(function(value) {
        var label = value && value.label !== undefined ? String(value.label) : String(value)
        var key = value && value.key !== undefined ? String(value.key) : label.trim().toLowerCase()
        return {key: key || "other", label: label || "Other"}
    })
}

function build(canonicalGames, mode, requestedCategoryKey, requestedGameId, savedCategoryKey, savedGameIds) {
    var groups = ({})
    for (var i = 0; i < canonicalGames.length; ++i) {
        var game = canonicalGames[i]
        if (!game) continue
        var values = valuesFor(game, mode)
        for (var j = 0; j < values.length; ++j) {
            var key = values[j].key
            if (!groups[key]) groups[key] = {key: key, label: values[j].label, games: []}
            groups[key].games.push(game)
        }
    }
    var categories = Object.keys(groups).map(function(key) { return groups[key] })
    categories.sort(function(a, b) {
        var byLabel = a.label.localeCompare(b.label)
        return byLabel || a.key.localeCompare(b.key)
    })
    var wantedKey = requestedCategoryKey || savedCategoryKey || ""
    var categoryIndex = categories.findIndex(function(category) { return category.key === wantedKey })
    if (categoryIndex < 0) categoryIndex = 0
    var selectedCategory = categories.length ? categories[categoryIndex] : null
    var games = selectedCategory ? selectedCategory.games : []
    var wantedGameId = requestedGameId || String((savedGameIds || {})[selectedCategory ? selectedCategory.key : ""] || "")
    var selectedIndex = -1
    for (var gameIndex = 0; gameIndex < games.length; ++gameIndex) {
        if (String(games[gameIndex].game_id) === wantedGameId) {
            selectedIndex = gameIndex
            break
        }
    }
    if (selectedIndex < 0) selectedIndex = 0
    return {
        categories: categories,
        categoryKey: selectedCategory ? selectedCategory.key : "",
        categoryIndex: categoryIndex,
        games: games,
        selectedIndex: selectedIndex
    }
}
