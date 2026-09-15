import QtQuick

Item {
    property string action: "confirm"
    property real glyphSize: 22
    property var luluPalette
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
    width: glyphSize
    height: glyphSize

    Image {
        anchors.fill: parent
        visible: parent.action !== "options"
        source: "controllerglyphs/" + (glyphFiles[parent.action] || glyphFiles.confirm)
        sourceSize: Qt.size(parent.glyphSize, parent.glyphSize)
        fillMode: Image.PreserveAspectFit
        smooth: true
    }

    Text {
        anchors.fill: parent
        visible: parent.action === "options"
        text: "X"
        color: parent.luluPalette.primaryText
        font.family: "JetBrains Mono"
        font.bold: true
        font.pixelSize: parent.glyphSize * 0.8
        horizontalAlignment: Text.AlignHCenter
        verticalAlignment: Text.AlignVCenter
    }
}
