import QtQuick

Item {
    property string title: ""
    property string description: ""

    Column {
        x: 0
        y: 0
        spacing: 14

        Text {
            anchors.horizontalCenter: parent.horizontalCenter
            text: title.toUpperCase()
            color: "#eadcff"
            font.pixelSize: 26
            font.letterSpacing: 4
        }

        Text {
            anchors.horizontalCenter: parent.horizontalCenter
            text: description
            color: "#9aa8c2"
            font.pixelSize: 22
        }
    }
}
