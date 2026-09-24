import QtQuick

Row {
    property string action: "confirm"
    property string label: ""
    property real uiScale: 1
    property var typography
    property var luluPalette
    property string fontFamily: typography ? typography.interfaceFamily : "JetBrains Mono"
    readonly property color hintColor: luluPalette.navigationText
    spacing: 5 * uiScale

    ControllerGlyph {
        action: parent.action
        glyphSize: 20 * parent.uiScale
        luluPalette: parent.luluPalette
        typography: parent.typography
        semanticColor: parent.hintColor
        anchors.verticalCenter: parent.verticalCenter
    }

    Text {
        text: parent.label
        color: parent.hintColor
        font.family: parent.fontFamily
        font.pixelSize: parent.typography.size("hint", 14)
        anchors.verticalCenter: parent.verticalCenter
    }
}
