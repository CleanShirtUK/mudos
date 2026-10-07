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
    function severityColor(severity) {
        if (severity === "success") return luluPalette.notificationSuccess
        if (severity === "warning") return luluPalette.notificationWarning
        if (severity === "error") return luluPalette.notificationError
        return luluPalette.notificationInfo
    }
    function severityGlyph(severity) {
        if (severity === "success") return "✓"
        if (severity === "warning") return "!"
        if (severity === "error") return "×"
        return "i"
    }

    Rectangle {
        x: root.width - width - 56
        y: 54
        width: 620
        height: 132
        radius: luluPalette.radius("overlay", 12)
        visible: notificationModel.visible
        opacity: 1
        color: luluPalette.material("overlay").style === "linearGradient"
            ? "transparent" : luluPalette.overlaySurface
        border.color: luluPalette.glassBorder
        border.width: 1

        MudosMaterialLayer {
            anchors.fill: parent
            luluPalette: luluPalette
            role: "overlay"
            cornerRadius: parent.radius
        }
        MudosDecorationLayer {
            anchors.fill: parent
            luluPalette: luluPalette
            role: "overlay"
            cornerRadius: parent.radius
        }

        MudosChromeFrame {
            anchors.fill: parent
            luluPalette: luluPalette
            cornerRadius: parent.radius
        }

        Row {
            anchors.fill: parent
            anchors.margins: 20
            spacing: 16

            MudosIcon {
                visible: notificationModel.iconName !== ""
                width: 42
                height: 42
                name: notificationModel.iconName || ""
                typography: typography
                semanticColor: root.severityColor(notificationModel.severity)
                iconSize: 30
            }
            Text {
                visible: notificationModel.iconName === ""
                width: 42
                text: notificationModel.glyph || root.severityGlyph(notificationModel.severity)
                color: root.severityColor(notificationModel.severity)
                font.family: typography.iconFamily
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
