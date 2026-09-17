import QtQuick

Item {
    id: root
    property var storageData: ({available: false, devices: [], targets: {game: null, emulation: null}, error: ""})
    property int selectedIndex: 0
    property real uiScale: 1
    property var typography
    property var luluPalette
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
        var result = [{label: "Game Install Storage", value: targetName("game"), action: "heading"},
                      {label: "Emulation Storage", value: targetName("emulation"), action: "heading"}]
        for (var device of (storageData.devices || [])) {
            var state = device.mounted ? size(device.free) + " free · Mounted" : "Not mounted"
            result.push({label: device.name, value: device.filesystem + " · " + size(device.capacity) + " · " + state,
                         action: "device", device: device})
            if (device.mounted && !device.system && !device.read_only) {
                result.push({label: "Use for Game Install", value: device.game_target ? "Selected" : "Select",
                             action: "target", kind: "game", device: device})
                result.push({label: "Use for Emulation", value: device.emulation_target ? "Selected" : "Select",
                             action: "target", kind: "emulation", device: device})
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
        if (row.action === "device") {
            if (row.device.mounted) operationRequested("unmount", row.device.id, "")
            else operationRequested("mount", row.device.id, "")
        } else if (row.action === "target") operationRequested("target", row.device.id, row.kind)
        else if (row.action === "eject") operationRequested("eject", row.device.id, "")
        else if (row.action === "back") backRequested()
    }
    function move(delta) { selectedIndex = Math.max(0, Math.min(rows().length - 1, selectedIndex + delta)) }

    Text { x: 76 * root.uiScale; y: 76 * root.uiScale; text: "STORAGE"
        color: luluPalette.headingAccent; font.family: typography.majorHeadingFamily
        font.weight: typography.majorHeadingWeight; font.pixelSize: typography.size("section", 30)
        font.letterSpacing: 5 * root.uiScale }
    Column {
        x: 76 * root.uiScale; y: 142 * root.uiScale; width: parent.width - 152 * root.uiScale; spacing: 10 * root.uiScale
        Repeater {
            model: root.rows()
            delegate: Rectangle {
                required property int index; required property var modelData
                width: parent.width; height: 58 * root.uiScale; radius: 10 * root.uiScale
                color: index === root.selectedIndex ? luluPalette.focusedCardSurface : luluPalette.cardSurface
                border.color: index === root.selectedIndex ? luluPalette.focusIndicator : luluPalette.glassBorder
                border.width: index === root.selectedIndex ? 2 * root.uiScale : root.uiScale
                Text { x: 18 * root.uiScale; anchors.verticalCenter: parent.verticalCenter; text: modelData.label
                    color: luluPalette.primaryText; font.family: typography.interfaceFamily; font.pixelSize: typography.size("body", 18) }
                Text { anchors.right: parent.right; anchors.rightMargin: 18 * root.uiScale; anchors.verticalCenter: parent.verticalCenter
                    text: modelData.value; color: luluPalette.secondaryText; font.family: typography.interfaceFamily
                    font.pixelSize: typography.size("body", 16) }
            }
        }
    }
    Text { x: 76 * root.uiScale; y: 650 * root.uiScale; text: root.storageData.available ? (root.storageData.error || "A: Select · mounted devices are safe targets") : "UDisks2 unavailable"
        color: luluPalette.secondaryText; font.family: typography.interfaceFamily; font.pixelSize: typography.size("body", 16) }
}
