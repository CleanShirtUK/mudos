.pragma library

function glyph(name) {
    var glyphs = {
        genres: "genre", lastPlayed: "clock", clock: "clock",
        gameModes: "gameMode", localMultiplayer: "gameMode",
        onlineMultiplayer: "wifi", protondb: "info",
        platform: "platform", provider: "plug", release: "clock",
        developer: "info", publisher: "info"
    }
    return glyphs[name] || "info"
}

function semanticIcon(name) {
    var icons = {
        genres: "genre", lastPlayed: "clock", clock: "clock",
        gameModes: "gameMode", localMultiplayer: "gameMode",
        onlineMultiplayer: "wifi", protondb: "info",
        platform: "platform", provider: "plug", release: "clock",
        developer: "info", publisher: "info"
    }
    return icons[name] || "info"
}

function formatPlaytime(value) {
    var minutes = Math.max(0, Math.floor(Number(value) || 0))
    var hours = Math.floor(minutes / 60)
    var remainder = minutes % 60
    return hours > 0 ? hours + "h " + remainder + "m" : minutes + "m"
}

function displayPlatform(value) {
    var key = String(value || "").trim().toLowerCase()
    var labels = {
        pc: "PC", nes: "NES", snes: "SNES", genesis: "Genesis",
        gb: "Game Boy", gbc: "Game Boy Color", gba: "Game Boy Advance",
        nds: "Nintendo DS", gamecube: "GameCube", ngc: "GameCube",
        wii: "Wii", switch: "Nintendo Switch", ps1: "PlayStation",
        ps2: "PlayStation", ps3: "PlayStation"
    }
    return labels[key] || (String(value || "").trim() || "Unknown")
}

function displayProvider(provider, runtime) {
    var key = String(runtime || provider || "").trim().toLowerCase()
    var labels = {
        steam: "Steam", epic: "Epic", gog: "GOG", flatpak: "Flatpak",
        lutris: "Lutris", romm: "RomM", retroarch: "RetroArch",
        dolphin: "Dolphin", pcsx2: "PCSX2", eden: "Eden"
    }
    return labels[key] || (String(runtime || provider || "").trim() || "Unknown")
}

function protonDbText(provider, platform, rating) {
    var providerKey = String(provider || "").trim().toLowerCase()
    var platformKey = String(platform || "").trim().toLowerCase()
    if (providerKey !== "steam" && platformKey !== "pc")
        return ""
    var normalized = String(rating || "").trim().toLowerCase()
    if (!normalized)
        return "Pending"
    var labels = {
        platinum: "Platinum", gold: "Gold", silver: "Silver",
        bronze: "Bronze", borked: "Borked", pending: "Pending", unknown: "Unknown"
    }
    return labels[normalized] || "Unknown"
}

function rows(game, dateLabel) {
    var result = []
    if (!game)
        return result
    function add(text, glyphName) {
        var value = String(text || "").trim()
        if (value)
            result.push({text: value, glyph: glyph(glyphName), iconName: semanticIcon(glyphName)})
    }
    var genres = game.genres || []
    if (genres.length)
        add(genres.map(function(value) { return String(value).trim() }).filter(Boolean).join(" · "), "genres")
    var modes = game.game_modes || (game.game_mode ? [game.game_mode] : [])
    if (modes.length)
        add(modes.map(function(value) { return String(value).trim() }).filter(Boolean).join(" · "), "gameModes")
    if (Number(game.last_played) > 0 && dateLabel)
        add(dateLabel(Number(game.last_played)), "lastPlayed")
    if (Number(game.total_playtime) > 0)
        add("Total Playtime  " + formatPlaytime(game.total_playtime), "clock")
    if (game.local_multiplayer === true)
        add("Local Multiplayer", "localMultiplayer")
    if (game.online_multiplayer === true)
        add("Online Multiplayer", "onlineMultiplayer")
    add(game.release_year || game.release_date, "release")
    add(game.developer, "developer")
    add(game.publisher, "publisher")
    var proton = protonDbText(game.provider, game.platform, game.protondb_rating)
    if (proton)
        add(proton, "protondb")
    add(displayPlatform(game.platform_label || game.platform), "platform")
    add(displayProvider(game.provider, game.runtime), "provider")
    return result
}
