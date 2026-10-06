import QtQuick
import QtQuick.Effects
import "ControllerProfiles.js" as ControllerProfiles

Item {
    property string action: "confirm"
    property string controllerProfile: "xbox"
    property real glyphSize: 22
    property var luluPalette
    property var typography
    property color semanticColor: luluPalette ? luluPalette.primaryText : "white"
    property FontLoader controllerFont: FontLoader {
        source: typeof mudosTheme !== "undefined" ? mudosTheme.fonts.controller : ""
    }
    readonly property string glyphText: ControllerProfiles.glyph(
        controllerProfile, action)
    readonly property string glyphFile: ControllerProfiles.glyphFile(
        controllerProfile, action)
    width: glyphSize
    height: glyphSize

    Image {
        id: fallbackImage
        anchors.fill: parent
        visible: parent.controllerFont.status !== FontLoader.Ready
        source: "controllerglyphs/" + parent.glyphFile
        sourceSize: Qt.size(parent.glyphSize, parent.glyphSize)
        fillMode: Image.PreserveAspectFit
        smooth: true
    }

    MultiEffect {
        anchors.fill: fallbackImage
        source: fallbackImage
        visible: fallbackImage.visible
        colorization: 1.0
        colorizationColor: parent.semanticColor
    }

    Text {
        anchors.fill: parent
        visible: parent.controllerFont.status === FontLoader.Ready
        text: parent.glyphText
        color: parent.semanticColor
        font.family: parent.controllerFont.name
        font.pixelSize: parent.glyphSize
        horizontalAlignment: Text.AlignHCenter
        verticalAlignment: Text.AlignVCenter
        renderType: Text.NativeRendering
    }

}
