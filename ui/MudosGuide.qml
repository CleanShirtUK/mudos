import QtQuick
import QtQuick.Effects
import QtQuick.Window

Window {
    id: root
    ThemeMotion { id: themeMotion }
    ThemeText { id: themeText }
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

    function mixColor(from, to, progress) {
        return Qt.rgba(
            from.r + (to.r - from.r) * progress,
            from.g + (to.g - from.g) * progress,
            from.b + (to.b - from.b) * progress,
            from.a + (to.a - from.a) * progress)
    }

    Rectangle {
        id: panel
        objectName: "guidePanel"
        anchors.centerIn: parent
        width: 520
        height: Math.max(250, 110 + guideModel.actions.length * 68)
        radius: luluPalette.radius("panel", 14)
        color: luluPalette.material("overlay").style === "linearGradient"
            ? "transparent" : luluPalette.guideSurface
        border.color: luluPalette.guideBorder
        border.width: 1

        MudosMaterialLayer {
            anchors.fill: parent
            luluPalette: luluPalette
            role: "overlay"
            cornerRadius: panel.radius
            selectionProgress: 0
        }
        MudosDecorationLayer {
            anchors.fill: parent
            luluPalette: luluPalette
            role: "overlay"
            cornerRadius: panel.radius
        }

        MudosChromeFrame {
            anchors.fill: parent
            luluPalette: luluPalette
            cornerRadius: panel.radius
        }

        Column {
            anchors.fill: parent
            anchors.margins: 24
            spacing: 18

            Text {
                text: themeText.formatRole(confirmationPending ? "CONFIRM"
                      : guideModel.sessionClassification !== ""
                        ? guideModel.sessionClassification
                          + (guideModel.sessionTitle !== "" ? " · " + guideModel.sessionTitle : "")
                        : "GUIDE", "heading")
                color: luluPalette.headingAccent
                font.family: themeText.fontFamily("heading", typography, "majorHeading")
                font.weight: themeText.weight("heading", typography.majorHeadingWeight)
                font.pixelSize: typography.size("section", 30)
                font.letterSpacing: themeText.spacing("heading", 1,
                    themeText.letterSpacing("viewTitle", 1))
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
                    id: rowDelegate
                    required property int index
                    required property var modelData
                    width: 472
                    height: 58
                    z: index === guideModel.selection ? 1 : 0
                    property real selectionProgress: index === guideModel.selection ? 1 : 0
                    readonly property color surfaceColor: root.mixColor(
                        luluPalette.cardSurface, luluPalette.focusedCardSurface,
                        selectionProgress)
                    readonly property color borderColor: root.mixColor(
                        luluPalette.glassBorder, luluPalette.focusIndicator,
                        selectionProgress)
                    readonly property color textColor: root.mixColor(
                        luluPalette.navigationText, luluPalette.primaryText,
                        selectionProgress)
                    Behavior on selectionProgress {
                        enabled: themeMotion.enabled("focus")
                        NumberAnimation {
                            duration: themeMotion.duration("focus", 180)
                            easing.type: themeMotion.easing("focus", "outQuint")
                        }
                    }

                    Rectangle {
                        anchors.fill: parent
                        scale: 1 + 0.01 * parent.selectionProgress
                        transformOrigin: Item.Center
                        radius: luluPalette.radius("row", 8)
                        color: parent.surfaceColor
                        border.color: parent.borderColor
                        border.width: 1

                        MudosMaterialLayer {
                            anchors.fill: parent
                            luluPalette: luluPalette
                            role: "row"
                            cornerRadius: parent.radius
                            selectionProgress: rowDelegate.selectionProgress
                        }

                        MudosChromeFrame {
                            anchors.fill: parent
                            luluPalette: luluPalette
                            raised: rowDelegate.selectionProgress < 0.5
                            cornerRadius: parent.radius
                        }

                        Text {
                            anchors.fill: parent
                            anchors.leftMargin: 18
                            anchors.rightMargin: 18
                            text: themeText.formatRole(rowDelegate.modelData.label, "body")
                            color: rowDelegate.textColor
                            font.family: themeText.fontFamily("body", typography, "interface")
                            font.weight: themeText.weight("body", Font.Normal)
                            font.pixelSize: typography.size("body", 18)
                            font.letterSpacing: themeText.spacing("body", 1)
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
