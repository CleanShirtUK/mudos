import QtQuick
import QtQuick.Effects

Item {
    id: root
    property var guideModel
    property var luluPalette
    property var typography
    property real uiScale: 1

    readonly property var actions: guideModel
        ? (guideModel.guideActions !== undefined
            ? guideModel.guideActions : guideModel.actions) : []
    readonly property int selection: guideModel
        ? (guideModel.guideSelection !== undefined
            ? guideModel.guideSelection : guideModel.selection) : 0
    readonly property bool confirmationPending: guideModel
        ? (guideModel.guideConfirmationPending !== undefined
            ? guideModel.guideConfirmationPending : guideModel.confirmationPending) : false
    readonly property string confirmationAction: guideModel
        ? (guideModel.guideConfirmationAction !== undefined
            ? guideModel.guideConfirmationAction : guideModel.confirmationAction) : ""

    readonly property real rowHeight: 58 * uiScale
    readonly property real rowGap: 10 * uiScale
    readonly property real rowWidth: 472 * uiScale

    Rectangle {
        id: panel
        anchors.centerIn: parent
        width: 520 * root.uiScale
        height: Math.max(250 * root.uiScale,
            110 * root.uiScale + root.actions.length
                * (root.rowHeight + root.rowGap))
        radius: 10 * root.uiScale
        color: root.luluPalette.overlaySurface
        border.color: root.luluPalette.glassBorder
        border.width: root.uiScale

        Column {
            anchors.fill: parent
            anchors.margins: 24 * root.uiScale
            spacing: 18 * root.uiScale

            Text {
                text: root.confirmationPending ? "CONFIRM" : "GUIDE"
                color: root.luluPalette.headingAccent
                font.family: root.typography.majorHeadingFamily
                font.weight: root.typography.majorHeadingWeight
                font.pixelSize: root.typography.size("section", 30)
                font.letterSpacing: 5 * root.uiScale
                layer.enabled: true
                layer.effect: MultiEffect {
                    shadowEnabled: true
                    shadowColor: "#000000"
                    shadowOpacity: 0.35
                    shadowBlur: 0.2
                    shadowVerticalOffset: 1 * root.uiScale
                }
            }

            Column {
                width: root.rowWidth
                spacing: root.rowGap
                Repeater {
                    model: root.confirmationPending
                        ? [{label: "Cancel"},
                           {label: root.confirmationAction}]
                        : root.actions
                    delegate: Item {
                        required property int index
                        required property var modelData
                        width: root.rowWidth
                        height: root.rowHeight
                        z: index === root.selection ? 1 : 0
                        property real selectionProgress:
                            index === root.selection ? 1 : 0
                        Behavior on selectionProgress {
                            NumberAnimation {
                                duration: 180
                                easing.type: Easing.OutQuint
                            }
                        }

                        Rectangle {
                            anchors.fill: parent
                            scale: 1 + 0.01 * parent.selectionProgress
                            transformOrigin: Item.Center
                            radius: 8 * root.uiScale
                            color: parent.selectionProgress > 0
                                ? root.luluPalette.focusedCardSurface
                                : root.luluPalette.cardSurface
                            border.color: parent.selectionProgress > 0
                                ? root.luluPalette.focusIndicator
                                : root.luluPalette.glassBorder
                            border.width: root.uiScale

                            Text {
                                anchors.fill: parent
                                anchors.leftMargin: 18 * root.uiScale
                                anchors.rightMargin: 18 * root.uiScale
                                text: parent.parent.modelData.label
                                color: parent.parent.selectionProgress > 0
                                    ? root.luluPalette.primaryText
                                    : root.luluPalette.navigationText
                                font.family: root.typography.interfaceFamily
                                font.pixelSize: root.typography.size("body", 18)
                                verticalAlignment: Text.AlignVCenter
                                elide: Text.ElideRight
                                layer.enabled: true
                                layer.effect: MultiEffect {
                                    shadowEnabled: true
                                    shadowColor: "#000000"
                                    shadowOpacity: 0.35
                                    shadowBlur: 0.2
                                    shadowVerticalOffset: 1 * root.uiScale
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}
