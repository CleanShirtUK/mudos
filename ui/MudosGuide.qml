import QtQuick
import QtQuick.Window

Window {
    id: root
    objectName: "mudosGuide"
    visible: false
    title: "Mudos Guide"
    flags: Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
    color: "transparent"
    width: 1920
    height: 1080

    property bool confirmationPending: guideModel.confirmationPending
    property string confirmationAction: guideModel.confirmationAction

    LuluPalette {
        id: luluPalette
    }

    Rectangle {
        anchors.centerIn: parent
        width: 520
        height: confirmationPending ? 250 : Math.max(250, 110 + (guideModel.actions.length * 60))
        color: luluPalette.guideSurface
        border.color: luluPalette.guideBorder
        border.width: 2

        Text {
            x: 24
            y: 18
            text: confirmationPending ? "Confirm" : "Guide"
            color: luluPalette.primaryText
            font.pixelSize: 28
        }

        Column {
            x: 24
            y: 62
            spacing: 12
            Repeater {
                model: confirmationPending ? [{label: "Cancel"}, {label: confirmationAction}] : guideModel.actions
                delegate: Rectangle {
                    width: 472
                    height: 48
                    color: index === guideModel.selection ? luluPalette.guideBorder : luluPalette.guideItemSurface
                    Text {
                        anchors.fill: parent
                        anchors.leftMargin: 14
                        text: modelData.label
                        color: index === guideModel.selection ? luluPalette.guideSelectedText : luluPalette.primaryText
                        font.pixelSize: 18
                        verticalAlignment: Text.AlignVCenter
                    }
                }
            }
        }
    }
}
