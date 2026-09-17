import QtQuick

Item {
    id: root
    property var displayData: ({available: false, displays: [], requested: {}, known_good: {}, selected: null, error: ""})
    property string view: "main"
    property int selectedIndex: 0
    property real uiScale: 1
    property var typography
    property var luluPalette
    property string message: ""
    property var requested: ({})
    signal applyRequested(string output, int width, int height, real refresh)
    signal backRequested()

    function selectedDisplay() {
        var requested = root.requested
        return (displayData.displays || []).find(function(item) { return item.id === requested.output })
            || displayData.selected || (displayData.displays || [])[0] || null
    }
    function selectedMode() {
        var display = selectedDisplay(), requested = root.requested
        if (!display) return null
        return (display.modes || []).find(function(item) {
            return item.width === Number(requested.width) && item.height === Number(requested.height)
                && Math.abs(Number(item.refresh) - Number(requested.refresh)) < 0.02
        }) || display.preferred || (display.modes || [])[0] || null
    }
    function rows() {
        var display = selectedDisplay(), mode = selectedMode(), result = []
        if (root.view === "outputs") {
            for (var output of (displayData.displays || []))
                result.push({label: output.name, value: output.active ? "Selected" : "Connected", action: "output", output: output})
            result.push({label: "Back", value: "", action: "back"})
            return result
        }
        if (root.view === "resolution") {
            if (display) for (var candidate of (display.modes || []))
                if (!result.some(function(item) { return item.width === candidate.width && item.height === candidate.height }))
                    result.push({label: candidate.width + " × " + candidate.height,
                                 value: candidate.width === mode.width && candidate.height === mode.height ? "Selected" : "",
                                 action: "resolution", width: candidate.width, height: candidate.height})
            result.push({label: "Back", value: "", action: "back"})
            return result
        }
        if (root.view === "refresh") {
            if (display && mode) for (var rate of (display.modes || []))
                if (rate.width === mode.width && rate.height === mode.height)
                    result.push({label: Number(rate.refresh).toFixed(2) + " Hz", value: Math.abs(Number(rate.refresh) - Number(root.requested.refresh)) < 0.02 ? "Selected" : "", action: "refresh", refresh: rate.refresh})
            result.push({label: "Back", value: "", action: "back"})
            return result
        }
        result = [
            {label: "Gameplay Display", value: display ? display.name : "Unavailable", action: "outputs"},
            {label: "Resolution", value: mode ? mode.width + " × " + mode.height : "Unavailable", action: "open-resolution"},
            {label: "Refresh Rate", value: mode ? Number(mode.refresh).toFixed(2) + " Hz" : "Unavailable", action: "open-refresh"},
            {label: "Apply", value: "Restart session", action: "apply"},
            {label: "Back", value: "", action: "back"}
        ]
        return result
    }
    function activate() {
        var row = rows()[selectedIndex], display = selectedDisplay(), mode = selectedMode(), requested = root.requested
        if (!row) return
        if (row.action === "outputs") { view = "outputs"; selectedIndex = 0 }
        else if (row.action === "output") { root.requested = {output: row.output.id}; view = "main"; selectedIndex = 0 }
        else if (row.action === "open-resolution") { view = "resolution"; selectedIndex = 0 }
        else if (row.action === "open-refresh") { view = "refresh"; selectedIndex = 0 }
        else if (row.action === "resolution") {
            var firstMode = (display.modes || []).find(function(item) { return item.width === row.width && item.height === row.height })
            root.requested = {output: display.id, width: row.width, height: row.height,
                               refresh: firstMode ? firstMode.refresh : requested.refresh}
            view = "main"; selectedIndex = 1
        }
        else if (row.action === "refresh") { root.requested = {output: display.id, width: mode.width, height: mode.height, refresh: row.refresh}; view = "main"; selectedIndex = 2 }
        else if (row.action === "apply" && display && mode) applyRequested(display.id, mode.width, mode.height, Number(mode.refresh))
        else if (row.action === "back") backRequested()
    }
    function move(delta) { selectedIndex = Math.max(0, Math.min(rows().length - 1, selectedIndex + delta)) }
    function back() { if (view !== "main") { view = "main"; selectedIndex = 0; return true } return false }
    onDisplayDataChanged: {
        if (root.view === "main" && Object.keys(root.requested).length === 0)
            root.requested = Object.assign({}, displayData.requested || {})
    }

    Text { x: 76 * root.uiScale; y: 76 * root.uiScale; text: "DISPLAY"; color: luluPalette.headingAccent
        font.family: typography.majorHeadingFamily; font.weight: typography.majorHeadingWeight
        font.pixelSize: typography.size("section", 30); font.letterSpacing: 5 * root.uiScale }
    Column { x: 76 * root.uiScale; y: 142 * root.uiScale; width: parent.width - 152 * root.uiScale; spacing: 10 * root.uiScale
        Repeater { model: root.rows(); delegate: Rectangle {
            required property int index; required property var modelData
            width: parent.width; height: 58 * root.uiScale; radius: 10 * root.uiScale
            color: index === root.selectedIndex ? luluPalette.focusedCardSurface : luluPalette.cardSurface
            border.color: index === root.selectedIndex ? luluPalette.focusIndicator : luluPalette.glassBorder
            border.width: index === root.selectedIndex ? 2 * root.uiScale : root.uiScale
            Text { x: 18 * root.uiScale; anchors.verticalCenter: parent.verticalCenter; text: modelData.label; color: luluPalette.primaryText
                font.family: typography.interfaceFamily; font.pixelSize: typography.size("body", 18) }
            Text { anchors.right: parent.right; anchors.rightMargin: 18 * root.uiScale; anchors.verticalCenter: parent.verticalCenter; text: modelData.value
                color: luluPalette.secondaryText; font.family: typography.interfaceFamily; font.pixelSize: typography.size("body", 16) }
        }}
    }
    Text { x: 76 * root.uiScale; y: 650 * root.uiScale; text: root.displayData.available ? (root.message || root.displayData.error || "A: Apply · changes restart the session") : "No connected display"
        color: luluPalette.secondaryText; font.family: typography.interfaceFamily; font.pixelSize: typography.size("body", 16) }
}
