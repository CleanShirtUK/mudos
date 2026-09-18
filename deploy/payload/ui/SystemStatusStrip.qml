import QtQuick

// Shell-owned persistent status presentation. Data is intentionally supplied
// through provider-neutral properties so controller/download services can bind
// in without moving this component into Home or Library.
Item {
    id: root

    property bool compact: false
    property real uiScale: 1
    property var typography
    property var luluPalette
    property int activeDownloadCount: 0
    property var controllers: []
    property bool bluetoothAvailable: false
    property bool networkAvailable: false
    property string networkConnectionType: ""
    property string currentTime: Qt.formatTime(new Date(), "HH:mm")

    readonly property real presentationScale: compact ? 0.72 : 1.35
    readonly property real glyphSize: (compact ? 15 : 19) * uiScale * presentationScale
    readonly property real valueSize: (compact ? 12 : 16) * uiScale * presentationScale
    readonly property real groupSpacing: (compact ? 8 : 16) * uiScale * presentationScale
    readonly property real innerSpacing: (compact ? 4 : 5) * uiScale * presentationScale
    readonly property color statusColor: luluPalette ? luluPalette.primaryText : "white"

    width: statusRow.implicitWidth
    height: statusRow.implicitHeight

    Timer {
        interval: 1000
        repeat: true
        running: true
        onTriggered: root.currentTime = Qt.formatTime(new Date(), "HH:mm")
    }

    Row {
        id: statusRow
        anchors.right: parent.right
        spacing: root.groupSpacing
        height: root.glyphSize

        Row {
            height: root.glyphSize
            spacing: root.innerSpacing
            visible: root.activeDownloadCount > 0

            StatusGlyph {
                glyph: "\uf019" // fa-download
                glyphSize: root.glyphSize
                targetPaintedHeight: root.glyphSize * 0.72
                fontFamily: root.typography ? root.typography.iconFamily : "JetBrains Mono"
                glyphColor: root.statusColor
            }
            Text {
                text: String(root.activeDownloadCount)
                color: root.statusColor
                font.family: root.typography ? root.typography.displayFamily : "JetBrains Mono"
                font.weight: root.typography ? root.typography.displayWeight : Font.Black
                font.pixelSize: root.valueSize
                height: root.glyphSize
                verticalAlignment: Text.AlignVCenter
            }
        }

        Repeater {
            model: root.controllers
            delegate: Row {
                required property var modelData
                height: root.glyphSize
                spacing: root.innerSpacing

                StatusGlyph {
                    glyph: "\uf11b" // fa-gamepad
                    glyphSize: root.glyphSize
                    targetPaintedHeight: root.glyphSize * 0.72
                    fontFamily: root.typography ? root.typography.iconFamily : "JetBrains Mono"
                    glyphColor: root.statusColor
                }
                Text {
                    text: String(modelData.index === undefined ? "?" : modelData.index)
                    color: root.statusColor
                    font.family: root.typography ? root.typography.displayFamily : "JetBrains Mono"
                    font.weight: root.typography ? root.typography.displayWeight : Font.Black
                    font.pixelSize: root.valueSize
                    height: root.glyphSize
                    verticalAlignment: Text.AlignVCenter
                }
                Text {
                    visible: modelData.batteryKind === "percent"
                        && modelData.batteryPercentage !== undefined
                        && modelData.batteryPercentage >= 0
                    text: ": " + String(modelData.battery)
                    color: root.statusColor
                    font.family: root.typography ? root.typography.displayFamily : "JetBrains Mono"
                    font.weight: root.typography ? root.typography.displayWeight : Font.Black
                    font.pixelSize: root.valueSize
                    height: root.glyphSize
                    verticalAlignment: Text.AlignVCenter
                }
            }
        }

        StatusGlyph {
            glyph: String.fromCodePoint(0xF00AF) // nf-md-bluetooth
            glyphSize: root.glyphSize
            targetPaintedHeight: root.glyphSize * 0.72
            fontFamily: root.typography ? root.typography.iconFamily : "JetBrains Mono"
            glyphColor: root.statusColor
        }

        StatusGlyph {
            glyph: !root.networkAvailable ? "\uf6a9"
                : root.networkConnectionType === "ethernet"
                    ? String.fromCodePoint(0xF0201) : "\uf1eb"
            glyphSize: root.glyphSize
            targetPaintedHeight: root.glyphSize * 0.72
            fontFamily: root.typography ? root.typography.iconFamily : "JetBrains Mono"
            glyphColor: root.statusColor
        }

        Row {
            height: root.glyphSize
            spacing: root.innerSpacing

            StatusGlyph {
                glyph: "\uf017" // fa-clock-o
                glyphSize: root.glyphSize
                targetPaintedHeight: root.glyphSize * 0.72
                fontFamily: root.typography ? root.typography.iconFamily : "JetBrains Mono"
                glyphColor: root.statusColor
            }
            Text {
                text: root.currentTime
                color: root.statusColor
                font.family: root.typography ? root.typography.displayFamily : "JetBrains Mono"
                font.weight: root.typography ? root.typography.displayWeight : Font.Black
                font.pixelSize: root.valueSize
                height: root.glyphSize
                verticalAlignment: Text.AlignVCenter
            }
        }
    }
}
