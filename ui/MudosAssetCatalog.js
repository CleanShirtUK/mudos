.pragma library

// Semantic asset authority. Screens request names, never filesystem paths or
// font codepoints. RomM platform artwork remains available for catalogue data;
// Mudos-owned Library navigation uses its separate supplied-artwork map.
var iconCodepoints = {
    wifi: "\uf1eb",
    wifiOff: "\uf6a9",
    bluetooth: "\uf293",
    volume: "\uf028",
    volumeMute: "\uf026",
    controller: "\uf11b",
    battery: "\uf240",
    download: "\uf019",
    storage: "\uf0a0",
    power: "\uf011",
    warning: "\uf071",
    error: "\uf057",
    info: "\uf05a",
    settings: "\uf013",
    clock: "\uf017",
    activity: "\uf1da",
    refresh: "\uf021",
    search: "\uf002",
    play: "\uf04b",
    back: "\uf060",
    check: "\uf00c",
    close: "\uf00d"
}

var platformAssets = {
    all: ["platforms/romm/default.ico", "raster"],
    pc: ["platforms/romm/default.ico", "raster"],
    nes: ["platforms/romm/nes.svg", "raster"],
    snes: ["platforms/romm/snes.svg", "raster"],
    genesis: ["platforms/romm/genesis.svg", "raster"],
    gb: ["platforms/romm/gb.svg", "raster"],
    gbc: ["platforms/romm/gbc.svg", "raster"],
    gba: ["platforms/romm/gba.svg", "raster"],
    nds: ["platforms/romm/nds.svg", "raster"],
    gamecube: ["platforms/romm/ngc.svg", "raster"],
    wii: ["platforms/romm/wii.svg", "raster"],
    switch: ["platforms/romm/switch.svg", "raster"],
    ps1: ["platforms/romm/psx.svg", "raster"],
    ps2: ["platforms/romm/ps2.svg", "raster"],
    ps3: ["platforms/romm/ps3.svg", "raster"]
}

var libraryPlatformAssets = {
    all: ["platform-all.svg", "icon"],
    pc: ["platform-pc.png", "raster"],
    nes: ["platform-nes.png", "raster"],
    snes: ["platform-snes.png", "raster"],
    genesis: ["platform-genesis.png", "raster"],
    gb: ["platform-gb.png", "raster"],
    gbc: ["platform-gbc.png", "raster"],
    gba: ["platform-gba.png", "raster"],
    nds: ["platform-nds.png", "raster"],
    gamecube: ["platform-gamecube.png", "raster"],
    wii: ["platform-wii.png", "raster"],
    switch: ["platform-switch.png", "raster"],
    ps1: ["platform-ps1.png", "raster"],
    ps2: ["platform-ps2.png", "raster"],
    ps3: ["platform-ps3.png", "raster"]
}

var platformAliases = {
    "platform:nes": "nes", "platform:snes": "snes",
    "platform:genesis": "genesis", "platform:gb": "gb",
    "platform:gbc": "gbc", "platform:gba": "gba",
    "platform:nds": "nds", "platform:gamecube": "gamecube",
    "platform:wii": "wii", "platform:switch": "switch",
    "platform:ps1": "ps1", "platform:ps2": "ps2", "platform:ps3": "ps3",
    ngc: "gamecube", psx: "ps1", "playstation-1": "ps1", "playstation 1": "ps1",
    "playstation-2": "ps2", "playstation 2": "ps2",
    "playstation-3": "ps3", "playstation 3": "ps3",
    "game-cube": "gamecube", "game cube": "gamecube",
    "nintendo-switch": "switch", "nintendo switch": "switch"
}

function icon(name) {
    return iconCodepoints[String(name || "")] || ""
}

function platformArtwork(platform) {
    var key = String(platform || "").toLowerCase()
    key = platformAliases[key] || key
    return platformAssets[key] || platformAssets.all
}

function libraryPlatformArtwork(platform) {
    var key = String(platform || "").toLowerCase()
    key = platformAliases[key] || key
    return libraryPlatformAssets[key] || libraryPlatformAssets.all
}

function systemArtwork(category) {
    var key = String(category || "").toLowerCase()
    return "artwork/system-" + key + ".svg"
}

function suppliedArtwork(name) {
    if (String(name || "") === "store")
        return "artwork/navigation/arrow-down-to-line-svgrepo-com.svg"
    return "artwork/navigation/" + String(name || "fallback") + ".png"
}

function metadataGlyph(name) {
    return "artwork/glyphs/metadata/" + String(name || "") + ".svg"
}
