import QtQuick

Column {
    id: root
    ThemeText { id: themeText }
    property string iconName: "info"
    property string title: "Nothing here"
    property string detail: ""
    property real uiScale: 1
    property var typography
    property var luluPalette
    property real maximumTextWidth: 520 * uiScale
    spacing: 10 * uiScale

    MudosIcon {
        anchors.horizontalCenter: parent.horizontalCenter
        width: implicitWidth
        height: implicitHeight
        name: root.iconName
        typography: root.typography
        semanticColor: root.luluPalette.headingAccent
        iconSize: 34 * root.uiScale
    }
    Text {
        width: root.maximumTextWidth
        anchors.horizontalCenter: parent.horizontalCenter
        text: themeText.formatRole(root.title, "heading")
        color: root.luluPalette.primaryText
        font.family: themeText.fontFamily("heading", root.typography, "interface")
        font.weight: themeText.weight("heading", Font.Normal)
        font.pixelSize: root.typography.size("heading", 22)
        font.letterSpacing: themeText.spacing("heading", root.uiScale)
        horizontalAlignment: Text.AlignHCenter
        wrapMode: Text.Wrap
    }
    Text {
        visible: root.detail !== ""
        width: root.maximumTextWidth
        anchors.horizontalCenter: parent.horizontalCenter
        text: themeText.formatRole(root.detail, "annotation")
        color: root.luluPalette.secondaryText
        font.family: themeText.fontFamily("annotation", root.typography, "interface")
        font.weight: themeText.weight("annotation", Font.Normal)
        font.pixelSize: root.typography.size("body", 15)
        font.letterSpacing: themeText.spacing("annotation", root.uiScale)
        horizontalAlignment: Text.AlignHCenter
        wrapMode: Text.Wrap
    }
}
