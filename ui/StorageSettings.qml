import QtQuick

Item {
    id: root
    property var storageData: ({available: false, devices: [], targets: {game: null, emulation: null}, error: ""})
    property int selectedIndex: 0
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
    property string message: ""
    property string targetView: ""
    signal operationRequested(string action, string deviceId, string kind)
    signal backRequested()

    function size(value) {
        if (value === null || value === undefined) return "Unknown"
        var units = ["B", "KiB", "MiB", "GiB", "TiB"]
        var amount = Number(value), index = 0
        while (amount >= 1024 && index < units.length - 1) { amount /= 1024; index++ }
        return amount.toFixed(index ? 1 : 0) + " " + units[index]
    }
    function targetName(kind) {
        var target = (storageData.targets || {})[kind]
        return target && target.name ? target.name : target && target.available === false ? "Unavailable" : "Internal default"
    }
    function rows() {
        if (root.targetView) {
            var choices = [{label: "Internal Storage (default)", value: "Default", action: "target-default", kind: root.targetView}]
            for (var candidate of (storageData.devices || []))
                if (candidate.mounted && !candidate.system && !candidate.read_only)
                    choices.push({label: candidate.name, value: candidate.filesystem + " · " + size(candidate.free) + " free",
                                  action: "target", kind: root.targetView, device: candidate})
            choices.push({label: "Back", value: "", action: "target-back"})
            return choices
        }
        var result = [{label: "Game Install Storage", value: targetName("game"), action: "heading"},
                      {label: "Emulation Storage", value: targetName("emulation"), action: "heading"}]
        for (var device of (storageData.devices || [])) {
            var state = device.mounted ? size(device.free) + " free · Mounted" : "Not mounted"
            result.push({label: device.name, value: device.filesystem + " · " + size(device.capacity) + " · " + state,
                         action: "device", device: device})
            if (device.mounted && !device.system && !device.read_only) {
                if (device.removable)
                    result.push({label: "Eject " + device.name, value: "A", action: "eject", device: device})
            }
        }
        result.push({label: "Back", value: "", action: "back"})
        return result
    }
    function activate() {
        var row = rows()[selectedIndex]
        if (!row) return
        if (row.action === "heading") {
            root.targetView = row.label.indexOf("Game") === 0 ? "game" : "emulation"
            root.selectedIndex = 0
        } else if (row.action === "device") {
            if (row.device.mounted) operationRequested("unmount", row.device.id, "")
            else operationRequested("mount", row.device.id, "")
        } else if (row.action === "target") {
            operationRequested("target", row.device.id, row.kind)
            root.targetView = ""
            root.selectedIndex = 0
        } else if (row.action === "target-default") {
            operationRequested("target-default", "", row.kind)
            root.targetView = ""
            root.selectedIndex = 0
        } else if (row.action === "target-back") {
            root.targetView = ""
            root.selectedIndex = 0
        } else if (row.action === "eject") operationRequested("eject", row.device.id, "")
        else if (row.action === "back") backRequested()
    }
    function move(delta) { selectedIndex = Math.max(0, Math.min(rows().length - 1, selectedIndex + delta)) }
    function back() {
        if (root.targetView) { root.targetView = ""; root.selectedIndex = 0; return true }
        return false
    }

    MudosSettingsPage {
        anchors.fill: parent
        title: "STORAGE"
        rows: root.rows()
        selectedIndex: root.selectedIndex
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
        footerText: root.storageData.available
            ? (root.message || root.storageData.error
                || "A: Select · mounted devices are safe targets")
            : "UDisks2 unavailable"
        onRowActivated: {
            root.selectedIndex = index
            root.activate()
        }
    }
}
