import QtQuick

Item {
    id: root
    property string category: "System"
    property var settings: []
    property int selectedIndex: 0
    property real uiScale: 1
    property var typography
    property var luluPalette
    signal actionRequested(string key)

    Text {
        x: 76 * root.uiScale
        y: 76 * root.uiScale
        text: root.category.toUpperCase()
        color: luluPalette.headingAccent
        font.family: typography.majorHeadingFamily
        font.weight: typography.majorHeadingWeight
        font.pixelSize: typography.size("section", 30)
        font.letterSpacing: 5 * root.uiScale
    }

    Column {
        x: 76 * root.uiScale
        y: 142 * root.uiScale
        width: parent.width - 152 * root.uiScale
        spacing: 10 * root.uiScale

        Repeater {
            model: root.settings
            delegate: Rectangle {
                required property int index
                required property var modelData
                width: parent.width
                height: 58 * root.uiScale
                radius: 10 * root.uiScale
                color: index === root.selectedIndex ? luluPalette.focusedCardSurface : luluPalette.cardSurface
                border.color: index === root.selectedIndex ? luluPalette.focusIndicator : luluPalette.glassBorder
                border.width: index === root.selectedIndex ? 2 * root.uiScale : root.uiScale

                Text {
                    x: 18 * root.uiScale
                    anchors.verticalCenter: parent.verticalCenter
                    text: modelData.label
                    color: luluPalette.primaryText
                    font.family: typography.interfaceFamily
                    font.pixelSize: typography.size("body", 18)
                }
                Text {
                    anchors.right: parent.right
                    anchors.rightMargin: 18 * root.uiScale
                    anchors.verticalCenter: parent.verticalCenter
                    text: String(modelData.value)
                    color: luluPalette.secondaryText
                    font.family: typography.interfaceFamily
                    font.pixelSize: typography.size("body", 16)
                }
                MouseArea {
                    anchors.fill: parent
                    enabled: modelData.writable === true && modelData.kind === "action"
                    onClicked: root.actionRequested(modelData.key)
                }
            }
        }
    }
}
