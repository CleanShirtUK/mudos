import QtQuick
import Mudos.Poc 1.0

Item {
    id: root
    property var guideModel
    property var luluPalette
    property var displayUnderlay
    property real uiScale: 1

    Rectangle {
        id: panel
        anchors.centerIn: parent
        width: 520 * root.uiScale
        height: root.guideModel.guideConfirmationPending
            ? 250 * root.uiScale
                : Math.max(250 * root.uiScale,
                110 * root.uiScale + root.guideModel.guideActions.length * 60 * root.uiScale)
        color: root.luluPalette.guideSurface
        border.color: root.luluPalette.guideBorder
        border.width: 2 * root.uiScale

        MudosGlassItem {
            anchors.fill: parent
            anchors.margins: 1 * root.uiScale
            backdrop: root.displayUnderlay
            canonicalSize: root.displayUnderlay.frameSize
            canonicalRect: Qt.rect(panel.x, panel.y, panel.width, panel.height)
            cornerRadius: 10 * root.uiScale
            refractionPixels: 24 * root.uiScale
            diffusionPixels: 7 * root.uiScale
            transmission: 0.8
            bevelWidthPx: 3 * root.uiScale
        }

        Text {
            x: 24 * root.uiScale
            y: 18 * root.uiScale
            text: root.guideModel.guideConfirmationPending ? "Confirm" : "Guide"
            color: root.luluPalette.primaryText
            font.pixelSize: 28 * root.uiScale
        }

        Column {
            x: 24 * root.uiScale
            y: 62 * root.uiScale
            spacing: 12 * root.uiScale
            Repeater {
                model: root.guideModel.guideConfirmationPending
                    ? [{label: "Cancel"}, {label: root.guideModel.guideConfirmationAction}]
                    : root.guideModel.guideActions
                delegate: Rectangle {
                    width: 472 * root.uiScale
                    height: 48 * root.uiScale
                    color: index === root.guideModel.selection
                        ? root.luluPalette.guideBorder : root.luluPalette.guideItemSurface
                    Text {
                        anchors.fill: parent
                        anchors.leftMargin: 14 * root.uiScale
                        text: modelData.label
                        color: index === root.guideModel.selection
                            ? root.luluPalette.guideSelectedText : root.luluPalette.primaryText
                        font.pixelSize: 18 * root.uiScale
                        verticalAlignment: Text.AlignVCenter
                    }
                }
            }
        }
    }
}
