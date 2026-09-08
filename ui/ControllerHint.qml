import QtQuick

Row {
    property string action: "confirm"
    property string label: ""
    property real uiScale: 1
    property var typography
    property var luluPalette
    spacing: 5 * uiScale

    ControllerGlyph {
        action: parent.action
        glyphSize: 20 * parent.uiScale
        anchors.verticalCenter: parent.verticalCenter
    }

    Text {
        text: parent.label
        color: parent.luluPalette.navigationText
        font.family: parent.typography.interfaceFamily
        font.pixelSize: parent.typography.size("hint", 14)
        anchors.verticalCenter: parent.verticalCenter
    }
}
