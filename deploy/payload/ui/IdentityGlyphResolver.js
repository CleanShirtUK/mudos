.pragma library

// Compact semantic glyphs only. Portrait/card artwork has a separate resolver.
var mappings = {
    provider: {
        steam: "steam",
        romm: "romm",
        steamgriddb: "steamgriddb"
    },
    runtime: {
        retroarch: "retroarch",
        dolphin: "dolphin",
        pcsx2: "pcsx2",
        eden: "eden",
        steam: "steam"
    },
    platform: {
        all: "all",
        pc: "pc",
        nes: "nes",
        snes: "snes",
        genesis: "genesis",
        gb: "gb",
        gbc: "gbc",
        gba: "gba",
        nds: "nds",
        gamecube: "gamecube",
        wii: "wii",
        switch: "switch",
        ps1: "ps1",
        ps2: "ps2",
        ps3: "ps3"
    },
    metadata: {
        genres: "genres",
        "last-played": "last-played",
        playtime: "playtime",
        "local-multiplayer": "local-multiplayer",
        "online-multiplayer": "online-multiplayer",
        "game-mode": "game-mode",
        protondb: "protondb"
    }
}

var aliases = {
    provider: {},
    runtime: {},
    platform: {
        "game-cube": "gamecube",
        "game cube": "gamecube",
        "playstation-1": "ps1",
        "playstation 1": "ps1",
        "playstation-2": "ps2",
        "playstation 2": "ps2",
        "playstation-3": "ps3",
        "playstation 3": "ps3",
        "nintendo-switch": "switch",
        "nintendo switch": "switch"
    },
    metadata: {
        "last_played": "last-played",
        "local_multiplayer": "local-multiplayer",
        "online_multiplayer": "online-multiplayer",
        "game_mode": "game-mode"
    }
}

function normalize(namespace, identity) {
    var value = String(identity || "").trim().toLowerCase()
    if (!mappings[namespace] || !value)
        return ""
    value = value.replace(/_/g, "-")
    return aliases[namespace][value] || value
}

function resolve(namespace, identity) {
    var key = normalize(namespace, identity)
    var known = !!(mappings[namespace] && mappings[namespace][key])
    return {
        namespace: namespace,
        identity: key,
        assetKey: known ? mappings[namespace][key] : "",
        assetPath: known ? "artwork/glyphs/" + namespace + "/" + mappings[namespace][key] + ".svg" : "",
        known: known,
        // The component verifies file availability through Image.status. This keeps
        // the contract drop-in: adding an SVG requires no resolver change.
        available: false
    }
}
