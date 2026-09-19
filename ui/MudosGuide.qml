import QtQuick
import QtQuick.Effects
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

    Typography {
        id: typography
    }

    Rectangle {
        id: panel
        anchors.centerIn: parent
        width: 520
        height: Math.max(250, 110 + guideModel.actions.length * 68)
        radius: 10
        color: luluPalette.overlaySurface
        border.color: luluPalette.glassBorder
        border.width: 1

        Column {
            anchors.fill: parent
            anchors.margins: 24
            spacing: 18

            Text {
                text: confirmationPending ? "CONFIRM" : "GUIDE"
                color: luluPalette.headingAccent
                font.family: typography.majorHeadingFamily
                font.weight: typography.majorHeadingWeight
                font.pixelSize: typography.size("section", 30)
                font.letterSpacing: 5
                layer.enabled: true
                layer.effect: MultiEffect {
                    shadowEnabled: true
                    shadowColor: "#000000"
                    shadowOpacity: 0.35
                    shadowBlur: 0.2
                    shadowVerticalOffset: 1
                }
            }

            Column {
                width: 472
                spacing: 10
            Repeater {
                model: confirmationPending ? [{label: "Cancel"}, {label: confirmationAction}] : guideModel.actions
                delegate: Item {
                    required property int index
                    required property var modelData
                    width: 472
                    height: 58
                    z: index === guideModel.selection ? 1 : 0
                    property real selectionProgress: index === guideModel.selection ? 1 : 0
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
                        radius: 8
                        color: parent.selectionProgress > 0
                            ? luluPalette.focusedCardSurface : luluPalette.cardSurface
                        border.color: parent.selectionProgress > 0
                            ? luluPalette.focusIndicator : luluPalette.glassBorder
                        border.width: 1

                        Text {
                            anchors.fill: parent
                            anchors.leftMargin: 18
                            anchors.rightMargin: 18
                            text: parent.parent.modelData.label
                            color: parent.parent.selectionProgress > 0
                                ? luluPalette.primaryText : luluPalette.navigationText
                            font.family: typography.interfaceFamily
                            font.pixelSize: typography.size("body", 18)
                            verticalAlignment: Text.AlignVCenter
                            elide: Text.ElideRight
                            layer.enabled: true
                            layer.effect: MultiEffect {
                                shadowEnabled: true
                                shadowColor: "#000000"
                                shadowOpacity: 0.35
                                shadowBlur: 0.2
                                shadowVerticalOffset: 1
                            }
                        }
                    }
                }
            }
            }
        }
    }
}
