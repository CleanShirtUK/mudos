import QtQuick

Item {
    id: root
    property var categories: []
    property int selectedIndex: 0
    property real uiScale: 1
    property var typography
    property var luluPalette
    signal openRequested(int index)

    Grid {
        x: 76 * root.uiScale
        y: 150 * root.uiScale
        columns: 4
        rowSpacing: 18 * root.uiScale
        columnSpacing: 18 * root.uiScale

        Repeater {
            model: root.categories
            delegate: Rectangle {
                required property int index
                required property string modelData
                width: 248 * root.uiScale
                height: 170 * root.uiScale
                radius: 16 * root.uiScale
                color: index === root.selectedIndex ? luluPalette.focusedCardSurface : luluPalette.cardSurface
                border.color: index === root.selectedIndex ? luluPalette.focusIndicator : luluPalette.glassBorder
                border.width: index === root.selectedIndex ? 3 * root.uiScale : root.uiScale

                Text {
                    anchors.centerIn: parent
                    text: modelData
                    color: luluPalette.primaryText
                    font.family: typography.displayFamily
                    font.weight: typography.displayWeight
                    font.pixelSize: typography.size("section", 24)
                }

                MouseArea {
                    anchors.fill: parent
                    onClicked: root.openRequested(index)
                }
            }
        }
    }
}
