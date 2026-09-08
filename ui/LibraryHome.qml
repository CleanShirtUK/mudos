import QtQuick

Item {
    property real cardHeight: 0
    property var typography
    property var luluPalette
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
        color: luluPalette.libraryCardSurface
        border.color: luluPalette.libraryBorder
        border.width: uiScale

        Column {
            anchors.centerIn: parent
            spacing: 18 * uiScale

            Text {
                anchors.horizontalCenter: parent.horizontalCenter
                text: "[ ]"
                color: luluPalette.primaryText
                font.family: typography ? typography.displayFamily : "Zalando Sans Condensed Black"
                font.weight: typography ? typography.displayWeight : Font.Black
                font.pixelSize: Math.min(typography ? typography.size("display", 100) : 100 * uiScale,
                                          libraryHomeCard.width * 0.45)
            }

            Text {
                anchors.horizontalCenter: parent.horizontalCenter
                text: "All Games"
                color: luluPalette.primaryText
                font.family: typography ? typography.interfaceFamily : "JetBrains Mono"
                font.pixelSize: typography ? typography.size("body", 22) : 22 * uiScale
            }
        }

        MouseArea {
            anchors.fill: parent
            onClicked: openRequested()
        }
    }
}
