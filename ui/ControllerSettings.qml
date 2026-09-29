import QtQuick

Item {
    id: root
    property var controllerData: ({controllers: {}, navigation_controller_id: "", dolphin_wii_remote_mode: "standard"})
    property int selectedIndex: 0
    property string view: "main"
    property string targetControllerId: ""
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
    signal operationRequested(string action, string controllerId, int player)
    signal backRequested()
    signal refreshRequested()

    Timer {
        interval: 1000
        repeat: true
        running: root.visible
        onTriggered: root.refreshRequested()
    }

    onControllerDataChanged: selectedIndex = Math.max(0, Math.min(rows().length - 1, selectedIndex))

    function items() {
        var result = [], controllers = controllerData.controllers || {}
        for (var id in controllers) {
            var item = controllers[id]
            if (item.connected) result.push({id: id, data: item})
        }
        result.sort(function(a, b) { return (a.data.player || 99) - (b.data.player || 99) })
        return result
    }
    function rows() {
        var result = [], list = items()
        if (root.view === "player") {
            var target = controllerData.controllers[targetControllerId] || {}
            for (var player = 1; player <= list.length; player++)
                result.push({label: "Player " + player, value: player === target.player ? "Selected" : "", action: "set-player", player: player})
            result.push({label: "Back", value: "", action: "back"})
            return result
        }
        if (root.view === "navigation") {
            result.push({label: "All", value: controllerData.navigation_mode === "all" ? "Selected" : "Any connected controller", action: "set-navigation", id: "all"})
            for (var navigation of list) {
                result.push({label: "Player " + (navigation.data.player || "Unassigned"), value: navigation.id === controllerData.navigation_controller_id ? "Selected" : "", action: "set-navigation", id: navigation.id})
            }
            result.push({label: "Automatic fallback", value: "First connected", action: "set-navigation", id: ""})
            result.push({label: "Back", value: "", action: "back"})
            return result
        }
        for (var entry of list) {
            var identity = entry.data.physical_identity || "unknown"
            var name = entry.data.sdl_name || identity
            result.push({label: name, value: "Player " + (entry.data.player || "Unassigned")
                         + (entry.id === controllerData.navigation_controller_id ? " · Navigation" : ""),
                         action: "open-player", id: entry.id})
        }
        if (list.length === 0) result.push({label: "No controller connected", value: "", action: "none"})
        result.push({label: "Dolphin Wii Remote", value: controllerData.dolphin_wii_remote_mode === "passthrough" ? "Real · Bluetooth adapter" : "Standard gamepad", action: "toggle-dolphin-wii-mode"})
        result.push({label: "Navigation Controller", value: controllerData.navigation_mode === "all" ? "All" : (controllerData.navigation_controller_id ? "Assigned" : "Automatic fallback"), action: "open-navigation"})
        result.push({label: "Provider profiles", value: "Owned by providers", action: "info"})
        result.push({label: "Back", value: "", action: "back"})
        return result
    }
    function activate() {
        var row = rows()[selectedIndex]
        if (!row) return
        if (row.action === "open-player") { targetControllerId = row.id; view = "player"; selectedIndex = 0 }
        else if (row.action === "open-navigation") { view = "navigation"; selectedIndex = 0 }
        else if (row.action === "set-player") { operationRequested("player", targetControllerId, row.player); view = "main"; selectedIndex = 0 }
        else if (row.action === "set-navigation") { operationRequested("navigation", row.id, 0); view = "main"; selectedIndex = 0 }
        else if (row.action === "toggle-dolphin-wii-mode") operationRequested(
            "dolphin-wii-mode", controllerData.dolphin_wii_remote_mode === "passthrough" ? "standard" : "passthrough", 0)
        else if (row.action === "back") back()
    }
    function move(delta) { selectedIndex = Math.max(0, Math.min(rows().length - 1, selectedIndex + delta)) }
    function back() { if (view !== "main") { view = "main"; selectedIndex = 0; return true } backRequested(); return true }

    MudosSettingsPage {
        anchors.fill: parent
        title: "CONTROLLERS"
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
        footerText: root.view === "main"
            ? "A: confirm · B: back"
            : "A: select · B: back"
        onRowActivated: {
            root.selectedIndex = index
            root.activate()
        }
    }
}
