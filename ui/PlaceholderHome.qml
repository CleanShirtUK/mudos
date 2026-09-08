import QtQuick

Item {
    property string title: ""
    property string description: ""
    property real uiScale: 1

    Column {
        x: 0
        y: 0
        spacing: 14 * uiScale

        Text {
            anchors.horizontalCenter: parent.horizontalCenter
            text: title.toUpperCase()
            color: "#eadcff"
            font.pixelSize: 26 * uiScale
            font.letterSpacing: 4 * uiScale
        }

        Text {
            anchors.horizontalCenter: parent.horizontalCenter
            text: description
            color: "#9aa8c2"
            font.pixelSize: 22 * uiScale
        }
    }
}
