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
    onControllersChanged: syncControllers()
    property bool bluetoothAvailable: false
    property string bluetoothState: "unavailable"
    property bool networkAvailable: false
    property string networkConnectionType: ""
    property string currentTime: Qt.formatTime(new Date(), "HH:mm")

    readonly property real presentationScale: compact ? 0.72 : 1.35
    readonly property real glyphSize: (compact ? 15 : 19) * uiScale * presentationScale
    readonly property real valueSize: (compact ? 12 : 16) * uiScale * presentationScale
    readonly property real groupSpacing: (compact ? 8 : 16) * uiScale * presentationScale
    readonly property real innerSpacing: (compact ? 4 : 5) * uiScale * presentationScale
    readonly property real backingPadding: 10 * uiScale * presentationScale
    readonly property color statusColor: luluPalette ? luluPalette.primaryText : "white"
    readonly property int presentedControllerCount: controllerPresentation.count

    function controllerKey(controller) {
        return String(controller.identity || "player:" + controller.index)
    }

    function syncControllers() {
        var incoming = controllers || []
        var seen = ({})
        for (var item of incoming) {
            var key = controllerKey(item)
            if (seen[key]) continue
            seen[key] = true
            var row = -1
            for (var index = 0; index < controllerPresentation.count; index++) {
                if (controllerPresentation.get(index).key === key) { row = index; break }
            }
            var values = {
                key: key,
                player: item.index === undefined ? "?" : String(item.index),
                batteryKind: String(item.batteryKind || "unknown"),
                batteryPercentage: item.batteryPercentage === undefined ? -1 : item.batteryPercentage,
                battery: String(item.battery || "Unknown"),
                present: true,
                retireAt: 0
            }
            if (row < 0)
                controllerPresentation.append(values)
            else {
                controllerPresentation.setProperty(row, "player", values.player)
                controllerPresentation.setProperty(row, "batteryKind", values.batteryKind)
                controllerPresentation.setProperty(row, "batteryPercentage", values.batteryPercentage)
                controllerPresentation.setProperty(row, "battery", values.battery)
                controllerPresentation.setProperty(row, "present", true)
            }
        }
        for (var index = 0; index < controllerPresentation.count; index++) {
            if (!seen[controllerPresentation.get(index).key]
                    && controllerPresentation.get(index).present) {
                controllerPresentation.setProperty(index, "present", false)
                controllerPresentation.setProperty(index, "retireAt", Date.now() + 260)
                if (!controllerRetire.running)
                    controllerRetire.start()
            }
        }
    }

    Component.onCompleted: syncControllers()

    ListModel { id: controllerPresentation }
    Timer {
        id: controllerRetire
        interval: 30
        repeat: true
        onTriggered: {
            var pending = false
            var now = Date.now()
            for (var index = controllerPresentation.count - 1; index >= 0; index--)
                if (!controllerPresentation.get(index).present) {
                    if (controllerPresentation.get(index).retireAt <= now)
                        controllerPresentation.remove(index)
                    else
                        pending = true
                }
            if (!pending)
                stop()
        }
    }

    width: statusRow.implicitWidth + 2 * backingPadding
    height: statusRow.implicitHeight + 2 * backingPadding

    Rectangle {
        id: statusBacking
        objectName: "statusBacking"
        anchors.fill: parent
        radius: 10 * root.uiScale
        color: root.luluPalette ? root.luluPalette.glassTint : "#1d2a49"
        opacity: 0.76
        border.color: root.luluPalette ? root.luluPalette.glassBorder : "#455274"
        border.width: root.uiScale
    }

    Timer {
        interval: 1000
        repeat: true
        running: true
        onTriggered: root.currentTime = Qt.formatTime(new Date(), "HH:mm")
    }

    Row {
        id: statusRow
        anchors.right: parent.right
        anchors.rightMargin: root.backingPadding
        anchors.verticalCenter: parent.verticalCenter
        spacing: 0
        height: root.glyphSize

        Item {
            id: downloadGroup
            height: root.glyphSize
            width: root.activeDownloadCount > 0
                ? downloadContent.implicitWidth + root.groupSpacing : 0
            opacity: root.activeDownloadCount > 0 ? 1 : 0
            clip: true
            Behavior on width { NumberAnimation { duration: 220; easing.type: Easing.OutCubic } }
            Behavior on opacity { NumberAnimation { duration: 180 } }

            Row {
                id: downloadContent
                x: root.groupSpacing
                height: root.glyphSize
                spacing: root.innerSpacing

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
        }

        Repeater {
            model: controllerPresentation
            delegate: Item {
                objectName: "controllerSlot"
                required property string player
                required property string batteryKind
                required property int batteryPercentage
                required property string battery
                required property bool present
                property bool appeared: false
                height: root.glyphSize
                width: present ? controllerContent.implicitWidth + root.groupSpacing : 0
                opacity: appeared && present ? 1 : 0
                clip: true
                Component.onCompleted: appeared = true
                Behavior on width { NumberAnimation { duration: 220; easing.type: Easing.OutCubic } }
                Behavior on opacity { NumberAnimation { duration: 180 } }

                Row {
                    id: controllerContent
                    x: root.groupSpacing
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
                        text: player
                        color: root.statusColor
                        font.family: root.typography ? root.typography.displayFamily : "JetBrains Mono"
                        font.weight: root.typography ? root.typography.displayWeight : Font.Black
                        font.pixelSize: root.valueSize
                        height: root.glyphSize
                        verticalAlignment: Text.AlignVCenter
                    }
                    Text {
                        visible: batteryKind === "percent" && batteryPercentage >= 0
                        text: ": " + battery
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

        Item {
            width: root.groupSpacing + bluetoothIcon.width
            height: root.glyphSize
            StatusGlyph {
                id: bluetoothIcon
                x: root.groupSpacing
                objectName: "bluetoothStatusIcon"
                glyph: root.bluetoothState === "off" || root.bluetoothState === "unavailable"
                    ? String.fromCodePoint(0xF00B0) : String.fromCodePoint(0xF00AF)
                glyphSize: root.glyphSize
                targetPaintedHeight: root.glyphSize * 0.72
                fontFamily: root.typography ? root.typography.iconFamily : "JetBrains Mono"
                glyphColor: root.bluetoothState === "connected" ? root.luluPalette.headingAccent
                    : root.bluetoothState === "off" ? root.luluPalette.warning
                    : root.bluetoothState === "unavailable" ? root.luluPalette.secondaryText
                    : root.statusColor
            }
        }

        Item {
            width: root.groupSpacing + networkIcon.width
            height: root.glyphSize
            StatusGlyph {
                id: networkIcon
                objectName: "networkIcon"
                x: root.groupSpacing
                glyph: !root.networkAvailable ? "\uf6a9"
                    : root.networkConnectionType === "ethernet"
                        ? String.fromCodePoint(0xF0201) : "\uf1eb"
                glyphSize: root.glyphSize
                targetPaintedHeight: root.glyphSize * 0.72
                fontFamily: root.typography ? root.typography.iconFamily : "JetBrains Mono"
                glyphColor: root.networkAvailable ? root.statusColor
                    : (root.luluPalette ? root.luluPalette.warning : "#ffd17d")
            }
        }

        Item {
            width: root.groupSpacing + clockContent.implicitWidth
            height: root.glyphSize
            Row {
                id: clockContent
                x: root.groupSpacing
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
}
