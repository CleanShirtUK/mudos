import QtQuick

Item {
    id: root
    property var audioData: ({available: false, outputs: [], inputs: [], current_output: null,
                              current_input: null, error: ""})
    property int selectedIndex: 0
    property bool embedded: false
    property real uiScale: 1
    property var typography
    property var luluPalette
    property var canonicalTexture
    property var canonicalCoordinateRoot
    property size canonicalSize: Qt.size(1280, 720)
    property real expandedShellX: 0
    property real expandedShellY: 0
    property real expandedShellWidth: 0
    property real expandedShellHeight: 0
    property real expandedShellBottom: 0
    signal operationRequested(string action, string deviceId, int volume, bool inputDevice, bool muted)
    signal interactionRequested()
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
        if (!root.embedded)
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

    MudosSettingsPage {
        anchors.fill: parent
        title: "AUDIO"
        rows: root.rows()
        selectedIndex: root.selectedIndex
        embedded: root.embedded
        uiScale: root.uiScale
        typography: root.typography
        luluPalette: root.luluPalette
        canonicalTexture: root.canonicalTexture
        canonicalCoordinateRoot: root.canonicalCoordinateRoot
        canonicalSize: root.canonicalSize
        expandedShellX: root.expandedShellX
        expandedShellY: root.expandedShellY
        expandedShellWidth: root.expandedShellWidth
        expandedShellHeight: root.expandedShellHeight
        expandedShellBottom: root.expandedShellBottom
        footerText: root.audioData.available
            ? (root.audioData.error || "A: Select · Left/Right: Volume")
            : "Audio service unavailable"
        onRowActivated: {
            root.selectedIndex = index
            root.interactionRequested()
            root.activate()
        }
    }
}
