import QtQuick

Image {
    property string action: "confirm"
    property real glyphSize: 22
    readonly property var glyphFiles: ({
        confirm: "SteamDeck_A.png",
        back: "SteamDeck_B.png",
        previousCollection: "SteamDeck_L1.png",
        nextCollection: "SteamDeck_R1.png",
        navigation: "SteamDeck_Dpad.png",
        up: "SteamDeck_Dpad_Up.png",
        down: "SteamDeck_Dpad_Down.png",
        left: "SteamDeck_Dpad_Left.png",
        right: "SteamDeck_Dpad_Right.png"
    })
    source: "controllerglyphs/" + (glyphFiles[action] || glyphFiles.confirm)
    sourceSize: Qt.size(glyphSize, glyphSize)
    width: glyphSize
    height: glyphSize
    fillMode: Image.PreserveAspectFit
    smooth: true
}
