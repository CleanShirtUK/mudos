.pragma library

function nerdGlyph(codepoint) {
    return String.fromCodePoint(codepoint)
}

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
    collection: "\ueb9c",
    gameMode: nerdGlyph(0xF0C0),
    genre: nerdGlyph(0xEEB6),
    platform: nerdGlyph(0xF11B),
    flathub: nerdGlyph(0xF324),
    battery: "\uf240",
    download: "\uf019",
    applications: nerdGlyph(0xF00A),
    empty: nerdGlyph(0xF071),
    bluetoothOn: nerdGlyph(0xF00AF),
    bluetoothOff: nerdGlyph(0xF00B0),
    ethernet: nerdGlyph(0xF0201),
    storage: "\uf0a0",
    plug: "\uf1e6",
    display: "\uf108",
    wrench: "\uf0ad",
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
    close: "\uf00d",
    fallback: nerdGlyph(0xF420),
    steam: nerdGlyph(0xF1B6),
    addStore: nerdGlyph(0xF055)
}

// Logical asset IDs are the presentation-side counterpart of the Python
// AssetRegistry. Keep repository-relative paths in this one catalog; screens
// ask for a namespace/name rather than constructing paths themselves.
function logicalAsset(namespace, name) {
    return "artwork/" + (namespace ? namespace + "/" : "") + name
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

function libraryDimensionIcon(mode) {
    var icons = {platform: "platform", provider: "plug",
                 game_mode: "gameMode", genre: "genre"}
    return icon(icons[String(mode || "")] || "collection")
}

function storeIcon(id, kind) {
    if (kind === "store" && String(id || "") === "steam")
        return icon("steam")
    if (kind === "store" && String(id || "") === "flathub")
        return icon("flathub")
    if (kind === "add")
        return icon("addStore")
    if (kind === "catalogue")
        return icon("download")
    return icon("fallback")
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

var systemIcons = {
    "Mudos Menu": "settings",
    Plugins: "plug",
    Display: "display",
    Audio: "volume",
    Network: "wifi",
    Bluetooth: "bluetooth",
    Controllers: "controller",
    Storage: "storage",
    Utilities: "applications",
    System: "wrench",
    Lulu: "settings"
}

function systemIcon(category) {
    return icon(systemIcons[String(category || "")] || "settings")
}

// The category model is deliberately based on the implemented System pages;
// labels and glyphs remain tied to the existing semantic icon vocabulary.
function settingsCategories(systemCategories) {
    var source = Array.isArray(systemCategories) ? systemCategories : []
    var order = ["Network", "Bluetooth", "Display", "Audio", "Controllers", "Storage", "System"]
    var pages = {Network: "internetSettings", Bluetooth: "systemSpace",
                 Display: "displaySettings", Audio: "audioSettings",
                 Controllers: "controllerSettings", Storage: "storageSettings",
                 System: "systemSpace"}
    return order.filter(function(label) { return source.indexOf(label) >= 0 })
        .concat(source.filter(function(label) {
            return label !== "Utilities" && order.indexOf(label) < 0
        }))
        .map(function(label) {
            return {id: label.toLowerCase(), label: label, glyph: systemIcon(label),
                    component: pages[label] || "systemSpace", target: label}
        })
}

function suppliedArtwork(name) {
    if (String(name || "") === "store")
        return logicalAsset("navigation", "arrow-down-to-line-svgrepo-com.svg")
    return logicalAsset("navigation", String(name || "fallback") + ".png")
}

function metadataGlyph(name) {
    return logicalAsset("glyphs/metadata", String(name || "") + ".svg")
}
