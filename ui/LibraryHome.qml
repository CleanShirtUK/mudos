import QtQuick

Item {
    property real cardHeight: 0
    readonly property real libraryGameCardAspectRatio: 1 / 1.55
    signal openRequested()

    Rectangle {
        id: libraryHomeCard
        x: 0
        y: 0
        width: cardHeight * libraryGameCardAspectRatio
        height: cardHeight
        radius: 18
        color: "#1b2a4a"
        border.color: "#6675ac"
        border.width: 1

        Column {
            anchors.centerIn: parent
            spacing: 18

            Text {
                anchors.horizontalCenter: parent.horizontalCenter
                text: "[ ]"
                color: "#f1f3fb"
                font.pixelSize: Math.min(100, libraryHomeCard.width * 0.45)
            }

            Text {
                anchors.horizontalCenter: parent.horizontalCenter
                text: "All Games"
                color: "#f1f3fb"
                font.pixelSize: 22
            }
        }

        MouseArea {
            anchors.fill: parent
            onClicked: openRequested()
        }
    }
}
