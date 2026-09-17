import QtQuick

Item {
    id: root
    property var controllerData: ({controllers: {}, navigation_controller_id: ""})
    property int selectedIndex: 0
    property string view: "main"
    property string targetControllerId: ""
    property real uiScale: 1
    property var typography
    property var luluPalette
    signal operationRequested(string action, string controllerId, int player)
    signal backRequested()

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
            for (var navigation of list) {
                result.push({label: "Player " + (navigation.data.player || "Unassigned"), value: navigation.id === controllerData.navigation_controller_id ? "Selected" : "", action: "set-navigation", id: navigation.id})
            }
            result.push({label: "Automatic fallback", value: "First connected", action: "set-navigation", id: ""})
            result.push({label: "Back", value: "", action: "back"})
            return result
        }
        for (var entry of list) {
            var identity = entry.data.physical_identity || "unknown"
            var name = identity === "045e_0291" ? "Xbox 360 Wireless Controller" : identity
            result.push({label: name, value: "Player " + (entry.data.player || "Unassigned")
                         + (entry.id === controllerData.navigation_controller_id ? " · Navigation" : ""),
                         action: "open-player", id: entry.id})
        }
        if (list.length === 0) result.push({label: "No controller connected", value: "", action: "none"})
        result.push({label: "Navigation Controller", value: controllerData.navigation_controller_id ? "Assigned" : "Automatic fallback", action: "open-navigation"})
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
        else if (row.action === "back") back()
    }
    function move(delta) { selectedIndex = Math.max(0, Math.min(rows().length - 1, selectedIndex + delta)) }
    function back() { if (view !== "main") { view = "main"; selectedIndex = 0; return true } backRequested(); return true }

    Text { x: 76 * root.uiScale; y: 76 * root.uiScale; text: "CONTROLLERS"; color: luluPalette.headingAccent
        font.family: typography.majorHeadingFamily; font.weight: typography.majorHeadingWeight
        font.pixelSize: typography.size("section", 30); font.letterSpacing: 5 * root.uiScale }
    Column { x: 76 * root.uiScale; y: 142 * root.uiScale; width: parent.width - 152 * root.uiScale; spacing: 10 * root.uiScale
        Repeater { model: root.rows(); delegate: Rectangle {
            required property int index; required property var modelData
            width: parent.width; height: 58 * root.uiScale; radius: 10 * root.uiScale
            color: index === root.selectedIndex ? luluPalette.focusedCardSurface : luluPalette.cardSurface
            border.color: index === root.selectedIndex ? luluPalette.focusIndicator : luluPalette.glassBorder
            border.width: index === root.selectedIndex ? 2 * root.uiScale : root.uiScale
            Text { x: 18 * root.uiScale; anchors.verticalCenter: parent.verticalCenter; text: modelData.label
                color: luluPalette.primaryText; font.family: typography.interfaceFamily; font.pixelSize: typography.size("body", 18) }
            Text { anchors.right: parent.right; anchors.rightMargin: 18 * root.uiScale; anchors.verticalCenter: parent.verticalCenter; text: modelData.value
                color: luluPalette.secondaryText; font.family: typography.interfaceFamily; font.pixelSize: typography.size("body", 16) }
        }}
    }
    Text { x: 76 * root.uiScale; y: 650 * root.uiScale; text: root.view === "main" ? "A: choose assignment · provider mappings remain provider-owned" : "A: select · B: back"
        color: luluPalette.secondaryText; font.family: typography.interfaceFamily; font.pixelSize: typography.size("body", 16) }
}
