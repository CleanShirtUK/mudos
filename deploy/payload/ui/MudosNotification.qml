import QtQuick
import QtQuick.Window

Window {
    id: root
    visible: true
    color: "transparent"
    flags: Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnTopHint | Qt.WindowTransparentForInput
    width: 1920
    height: 1080

    LuluPalette { id: luluPalette }
    Typography { id: typography }

    Rectangle {
        x: root.width - width - 56
        y: 54
        width: 620
        height: 132
        radius: 12
        visible: notificationModel.visible
        opacity: 1
        color: luluPalette.overlaySurface
        border.color: luluPalette.glassBorder
        border.width: 1

        Row {
            anchors.fill: parent
            anchors.margins: 20
            spacing: 16

            Text {
                visible: notificationModel.glyph !== ""
                width: 42
                text: notificationModel.glyph
                color: luluPalette.headingAccent
                font.family: typography.interfaceFamily
                font.pixelSize: 30
                verticalAlignment: Text.AlignVCenter
            }
            Column {
                width: parent.width - (notificationModel.glyph !== "" ? 58 : 0)
                spacing: 5
                Text {
                    width: parent.width
                    text: notificationModel.title
                    color: luluPalette.headingAccent
                    font.family: typography.majorHeadingFamily
                    font.pixelSize: 20
                    font.weight: typography.majorHeadingWeight
                    elide: Text.ElideRight
                }
                Text {
                    width: parent.width
                    text: notificationModel.body
                    color: luluPalette.primaryText
                    font.family: typography.interfaceFamily
                    font.pixelSize: 18
                    wrapMode: Text.WordWrap
                    maximumLineCount: 2
                    elide: Text.ElideRight
                }
            }
        }
    }
}
