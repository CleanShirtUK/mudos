import QtQuick
import "ControllerProfiles.js" as ControllerProfiles

Item {
    property string action: "confirm"
    property string controllerProfile: "xbox"
    property real glyphSize: 22
    property var luluPalette
    property var typography
    property FontLoader controllerFont: FontLoader {
        source: "fonts/Config-Glyphs.otf"
    }
    readonly property string glyphText: ControllerProfiles.glyph(
        controllerProfile, action)
    readonly property string glyphFile: ControllerProfiles.glyphFile(
        controllerProfile, action)
    width: glyphSize
    height: glyphSize

    Image {
        anchors.fill: parent
        visible: parent.controllerFont.status !== FontLoader.Ready
            && parent.action !== "options"
        source: "controllerglyphs/" + parent.glyphFile
        sourceSize: Qt.size(parent.glyphSize, parent.glyphSize)
        fillMode: Image.PreserveAspectFit
        smooth: true
    }

    Text {
        anchors.fill: parent
        visible: parent.controllerFont.status === FontLoader.Ready
            && parent.action !== "options"
        text: parent.glyphText
        color: parent.luluPalette.primaryText
        font.family: parent.controllerFont.name
        font.pixelSize: parent.glyphSize
        horizontalAlignment: Text.AlignHCenter
        verticalAlignment: Text.AlignVCenter
        renderType: Text.NativeRendering
    }

    MudosIcon {
        anchors.fill: parent
        visible: parent.action === "options"
        name: "settings"
        typography: parent.typography
        semanticColor: parent.luluPalette.primaryText
        iconSize: parent.glyphSize * 0.8
    }
}
