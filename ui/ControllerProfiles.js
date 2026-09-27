.pragma library

// Semantic action -> physical control -> renderer glyph. The profile boundary
// is intentionally independent of the controller font renderer.
var profiles = {
    xbox: {
        confirm: "a", back: "b", menu: "menu", guide: "guide", view: "view",
        leftBumper: "leftBumper", rightBumper: "rightBumper",
        leftTrigger: "leftTrigger", rightTrigger: "rightTrigger",
        leftStick: "leftStick", rightStick: "rightStick", navigation: "dpad",
        up: "dpadUp", down: "dpadDown", left: "dpadLeft", right: "dpadRight",
        previousCollection: "leftBumper", nextCollection: "rightBumper",
        x: "x", y: "y", leftStickClick: "leftStickClick",
        rightStickClick: "rightStickClick", options: "x"
    },
    nintendo: {
        confirm: "b", back: "a", menu: "menu", guide: "guide", view: "view",
        leftBumper: "leftBumper", rightBumper: "rightBumper",
        leftTrigger: "leftTrigger", rightTrigger: "rightTrigger", leftStick: "leftStick",
        rightStick: "rightStick", navigation: "dpad",
        up: "dpadUp", down: "dpadDown", left: "dpadLeft", right: "dpadRight",
        previousCollection: "leftBumper", nextCollection: "rightBumper",
        x: "y", y: "x", leftStickClick: "leftStickClick",
        rightStickClick: "rightStickClick", options: "y", downloads: "x"
    }
}

var controllerGlyphs = {
    a: "\u0100", b: "\u0101", x: "\u0114", y: "\u0115",
    view: "\u0104", menu: "\u0105", guide: "\u011c",
    leftBumper: "\u0106", rightBumper: "\u0107",
    leftTrigger: "\u0108", rightTrigger: "\u0109",
    leftStick: "\u010a", rightStick: "\u010b", dpad: "\u0110",
    dpadUp: "\u010c", dpadRight: "\u010d", dpadLeft: "\u010e",
    dpadDown: "\u010f", leftStickClick: "\u011a", rightStickClick: "\u011b"
}

var fallbackGlyphs = {
    confirm: "SteamDeck_A.png",
    back: "SteamDeck_B.png",
    navigation: "SteamDeck_Dpad.png",
    up: "SteamDeck_Dpad_Up.png",
    down: "SteamDeck_Dpad_Down.png",
    left: "SteamDeck_Dpad_Left.png",
    right: "SteamDeck_Dpad_Right.png",
    leftBumper: "SteamDeck_L1.png",
    rightBumper: "SteamDeck_R1.png",
    previousCollection: "SteamDeck_L1.png",
    nextCollection: "SteamDeck_R1.png"
}

function physicalControl(profile, action) {
    var mapping = profiles[String(profile || "xbox")] || profiles.xbox
    return mapping[String(action || "confirm")] || mapping.confirm
}

function glyphFile(profile, action) {
    return fallbackGlyphs[String(action || "confirm")] || fallbackGlyphs.confirm
}

function glyph(profile, action) {
    return controllerGlyphs[physicalControl(profile, action)] || controllerGlyphs.a
}
