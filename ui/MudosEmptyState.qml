import QtQuick

Column {
    id: root
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
        text: root.title
        color: root.luluPalette.primaryText
        font.family: root.typography.interfaceFamily
        font.pixelSize: root.typography.size("heading", 22)
        horizontalAlignment: Text.AlignHCenter
        wrapMode: Text.Wrap
    }
    Text {
        visible: root.detail !== ""
        width: root.maximumTextWidth
        anchors.horizontalCenter: parent.horizontalCenter
        text: root.detail
        color: root.luluPalette.secondaryText
        font.family: root.typography.interfaceFamily
        font.pixelSize: root.typography.size("body", 15)
        horizontalAlignment: Text.AlignHCenter
        wrapMode: Text.Wrap
    }
}
