import QtQuick

Item {
    id: root
    property var audioData: ({available: false, outputs: [], inputs: [], current_output: null,
                              current_input: null, error: ""})
    property int selectedIndex: 0
    property real uiScale: 1
    property var typography
    property var luluPalette
    signal operationRequested(string action, string deviceId, int volume, bool inputDevice, bool muted)
    signal backRequested()

    function rows() {
        var result = []
        var outputs = audioData.outputs || []
        for (var output of outputs)
            result.push({label: output.name, value: output.type + " · " + output.volume + "%"
                         + (output.active ? " · Current" : ""), action: "output", device: output})
        if (outputs.length) {
            var current = audioData.current_output || outputs[0]
            result.push({label: "Volume", value: current.volume + "%", action: "volume", device: current})
            result.push({label: current.mute ? "Unmute output" : "Mute output", value: "A", action: "mute", device: current})
        }
        for (var input of (audioData.inputs || []))
            result.push({label: "Input: " + input.name, value: input.type + " · " + input.volume + "%"
                         + (input.active ? " · Current" : ""), action: "input", device: input})
        result.push({label: "Back", value: "", action: "back"})
        return result
    }

    function currentDevice(row) {
        return row && row.device ? row.device : audioData.current_output
    }

    function adjust(delta) {
        var row = rows()[selectedIndex]
        var device = currentDevice(row)
        if (!device) return
        var next = Math.max(0, Math.min(100, Number(device.volume) + delta))
        operationRequested("volume", device.id, next, row.action === "input", false)
    }

    function activate() {
        var row = rows()[selectedIndex]
        if (!row) return
        if (row.action === "output") operationRequested("output", row.device.id, 0, false, false)
        else if (row.action === "input") operationRequested("input", row.device.id, 0, true, false)
        else if (row.action === "volume") adjust(5)
        else if (row.action === "mute") operationRequested("mute", row.device.id, 0, false, !row.device.mute)
        else if (row.action === "back") backRequested()
    }

    function move(delta) {
        selectedIndex = Math.max(0, Math.min(rows().length - 1, selectedIndex + delta))
    }

    Text { x: 76 * root.uiScale; y: 76 * root.uiScale; text: "AUDIO"
        color: luluPalette.headingAccent; font.family: typography.majorHeadingFamily
        font.weight: typography.majorHeadingWeight; font.pixelSize: typography.size("section", 30)
        font.letterSpacing: 5 * root.uiScale }
    Column {
        x: 76 * root.uiScale; y: 142 * root.uiScale
        width: parent.width - 152 * root.uiScale; spacing: 10 * root.uiScale
        Repeater {
            model: root.rows()
            delegate: Rectangle {
                required property int index
                required property var modelData
                width: parent.width; height: 58 * root.uiScale; radius: 10 * root.uiScale
                color: index === root.selectedIndex ? luluPalette.focusedCardSurface : luluPalette.cardSurface
                border.color: index === root.selectedIndex ? luluPalette.focusIndicator : luluPalette.glassBorder
                border.width: index === root.selectedIndex ? 2 * root.uiScale : root.uiScale
                Text { x: 18 * root.uiScale; anchors.verticalCenter: parent.verticalCenter
                    text: modelData.label; color: luluPalette.primaryText; font.family: typography.interfaceFamily
                    font.pixelSize: typography.size("body", 18) }
                Text { anchors.right: parent.right; anchors.rightMargin: 18 * root.uiScale
                    anchors.verticalCenter: parent.verticalCenter; text: modelData.value
                    color: luluPalette.secondaryText; font.family: typography.interfaceFamily
                    font.pixelSize: typography.size("body", 16) }
            }
        }
    }
    Text { x: 76 * root.uiScale; y: 650 * root.uiScale
        text: root.audioData.available ? (root.audioData.error || "A: Select · Left/Right: Volume") : "Audio service unavailable"
        color: luluPalette.secondaryText; font.family: typography.interfaceFamily
        font.pixelSize: typography.size("body", 16) }
}
