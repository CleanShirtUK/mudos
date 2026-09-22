import QtQuick
import QtQuick.Effects

Item {
    id: root
    property var store: null
    property int selectedIndex: 0
    property real uiScale: 1
    property var typography
    property var luluPalette
    signal activated(string action)
    signal backed()

    readonly property var entries: ["Change Name", "Update URL", "Remove Store"]

    function move(delta) {
        selectedIndex = Math.max(0, Math.min(entries.length - 1, selectedIndex + delta))
    }
    function activate() { activated(entries[selectedIndex]) }

    anchors.fill: parent
    visible: store !== null
    z: 400

    Rectangle { anchors.fill: parent; color: luluPalette.overlayBackdrop }
    Rectangle {
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.bottom: parent.bottom
        width: Math.min(parent.width * 0.48, 560 * root.uiScale)
        color: luluPalette.overlaySurface
        radius: 10 * root.uiScale
        border.color: luluPalette.glassBorder
        border.width: root.uiScale

        Column {
            anchors.fill: parent
            anchors.margins: 24 * root.uiScale
            spacing: 18 * root.uiScale
            Text {
                text: "STORE OPTIONS"
                color: root.luluPalette.headingAccent
                font.family: root.typography.majorHeadingFamily
                font.weight: root.typography.majorHeadingWeight
                font.pixelSize: root.typography.size("section", 30)
                font.letterSpacing: 5 * root.uiScale
            }
            Text {
                text: root.store ? root.store.title : ""
                color: root.luluPalette.primaryText
                font.family: root.typography.displayFamily
                font.weight: root.typography.displayWeight
                font.pixelSize: root.typography.size("display", 34)
                width: parent.width
                elide: Text.ElideRight
            }
            ListView {
                id: list
                width: parent.width
                height: contentHeight
                spacing: 8 * root.uiScale
                model: root.entries
                interactive: false
                delegate: Rectangle {
                    required property int index
                    required property string modelData
                    width: list.width
                    height: 58 * root.uiScale
                    radius: 8 * root.uiScale
                    property real selectionProgress: index === root.selectedIndex ? 1 : 0
                    color: Qt.rgba(
                        root.luluPalette.cardSurface.r
                            + (root.luluPalette.focusedCardSurface.r - root.luluPalette.cardSurface.r) * selectionProgress,
                        root.luluPalette.cardSurface.g
                            + (root.luluPalette.focusedCardSurface.g - root.luluPalette.cardSurface.g) * selectionProgress,
                        root.luluPalette.cardSurface.b
                            + (root.luluPalette.focusedCardSurface.b - root.luluPalette.cardSurface.b) * selectionProgress,
                        1)
                    border.color: index === root.selectedIndex
                        ? root.luluPalette.focusIndicator : root.luluPalette.glassBorder
                    border.width: root.uiScale
                    Behavior on selectionProgress { NumberAnimation { duration: 180; easing.type: Easing.OutQuint } }
                    Text {
                        anchors.fill: parent
                        anchors.leftMargin: 18 * root.uiScale
                        text: parent.modelData
                        color: root.luluPalette.primaryText
                        font.family: root.typography.interfaceFamily
                        font.pixelSize: root.typography.size("body", 18)
                        verticalAlignment: Text.AlignVCenter
                    }
                }
            }
            Text {
                text: "A Select    B Back"
                color: root.luluPalette.secondaryText
                font.family: root.typography.interfaceFamily
                font.pixelSize: root.typography.size("body", 15)
            }
        }
    }
}
