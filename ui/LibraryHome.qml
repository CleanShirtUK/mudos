import QtQuick

Item {
    property real cardHeight: 0
    property string transitionState: "RESTING"
    property real uiScale: 1
    readonly property string navigationObject: "library"
    readonly property real libraryGameCardAspectRatio: 1 / 1.55
    signal openRequested()

    Rectangle {
        id: libraryHomeCard
        x: 0
        y: 0
        width: cardHeight * libraryGameCardAspectRatio
        height: cardHeight
        radius: 18 * uiScale
        color: "#1b2a4a"
        border.color: "#6675ac"
        border.width: uiScale

        Column {
            anchors.centerIn: parent
            spacing: 18 * uiScale

            Text {
                anchors.horizontalCenter: parent.horizontalCenter
                text: "[ ]"
                color: "#f1f3fb"
                font.pixelSize: Math.min(100 * uiScale, libraryHomeCard.width * 0.45)
            }

            Text {
                anchors.horizontalCenter: parent.horizontalCenter
                text: "All Games"
                color: "#f1f3fb"
                font.pixelSize: 22 * uiScale
            }
        }

        MouseArea {
            anchors.fill: parent
            onClicked: openRequested()
        }
    }
}
