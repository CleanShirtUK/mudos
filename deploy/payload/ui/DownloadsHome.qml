import QtQuick

// Provider-neutral acquisition history. The snapshot is authoritative; this
// component never talks to acquisitiond or infers state from the filesystem.
Item {
    id: root

    property string snapshot: "{\"jobs\":[],\"activeDownloadCount\":0}"
    property int selectedIndex: 0
    property real uiScale: 1
    property var typography
    property var luluPalette
    property var canonicalTexture
    property var canonicalCoordinateRoot
    property size canonicalSize: Qt.size(1280, 720)
    property var jobs: []
    property var rows: []
    signal backRequested()
    signal retryRequested(string jobId)

    readonly property var activeStates: ["starting", "transferring", "finalizing"]
    readonly property var queuedStates: ["queued", "paused"]
    readonly property var historyStates: ["completed", "failed", "cancelled"]

    function parseSnapshot() {
        var parsed
        try {
            parsed = JSON.parse(snapshot || "{\"jobs\":[]}")
        } catch (error) {
            parsed = {jobs: []}
        }
        var incoming = parsed.jobs || []
        var ordered = []
        for (var i = 0; i < incoming.length; i++)
            ordered.push(incoming[i])
        ordered.sort(function(a, b) {
            var left = String(a.completed_at || a.updated_at || a.created_at || "")
            var right = String(b.completed_at || b.updated_at || b.created_at || "")
            return right.localeCompare(left)
        })
        jobs = ordered
        rebuildRows()
    }

    function addSection(result, label, states) {
        var section = []
        for (var i = 0; i < jobs.length; i++) {
            if (states.indexOf(String(jobs[i].state || "")) >= 0)
                section.push(jobs[i])
        }
        if (!section.length)
            return
        result.push({heading: true, label: label})
        for (var j = 0; j < section.length; j++)
            result.push({heading: false, job: section[j]})
    }

    function rebuildRows() {
        var result = []
        addSection(result, "ACTIVE", activeStates)
        addSection(result, "QUEUED", queuedStates)
        addSection(result, "HISTORY", historyStates)
        rows = result
        selectedIndex = Math.min(selectedIndex, Math.max(0, selectableCount() - 1))
    }

    function selectableCount() {
        var count = 0
        for (var i = 0; i < rows.length; i++)
            if (!rows[i].heading)
                count++
        return count
    }

    function rowForSelection(selection) {
        var count = 0
        for (var i = 0; i < rows.length; i++) {
            if (rows[i].heading)
                continue
            if (count === selection)
                return i
            count++
        }
        return -1
    }

    function moveSelection(delta) {
        if (!selectableCount())
            return
        selectedIndex = Math.max(0, Math.min(selectableCount() - 1, selectedIndex + delta))
    }

    function selectedJob() {
        var row = rowForSelection(selectedIndex)
        return row >= 0 && rows[row] ? rows[row].job : null
    }

    function activateSelected() {
        var job = selectedJob()
        if (job && String(job.state) === "failed" && job.retryable === true)
            retryRequested(String(job.job_id || ""))
    }

    function formatBytes(value) {
        if (value === null || value === undefined || Number(value) <= 0)
            return ""
        var number = Number(value)
        var units = ["B", "KB", "MB", "GB", "TB"]
        var unit = 0
        while (number >= 1024 && unit < units.length - 1) {
            number /= 1024
            unit++
        }
        return number.toFixed(unit === 0 ? 0 : 1) + " " + units[unit]
    }

    function formatTime(job) {
        var value = String(job.completed_at || job.updated_at || "")
        return value ? value.replace("T", " ").replace("Z", " UTC") : ""
    }

    function progressText(job) {
        if (String(job.state) === "transferring" && job.progress !== null
                && job.progress !== undefined)
            return Math.round(Number(job.progress) * 100) + "%"
        if (String(job.state) === "completed")
            return "100%"
        return ""
    }

    onSnapshotChanged: parseSnapshot()
    Component.onCompleted: parseSnapshot()

    Rectangle {
        anchors.fill: parent
        color: "transparent"

        Text {
            x: 52 * root.uiScale
            y: 35 * root.uiScale
            text: "DOWNLOADS"
            color: root.luluPalette ? root.luluPalette.headingAccent : "white"
            font.family: root.typography ? root.typography.displayFamily : "sans-serif"
            font.weight: root.typography ? root.typography.displayWeight : Font.Black
            font.pixelSize: 42 * root.uiScale
            font.letterSpacing: 4 * root.uiScale
        }

        Flickable {
            id: list
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.top: parent.top
            anchors.bottom: parent.bottom
            anchors.topMargin: 105 * root.uiScale
            anchors.bottomMargin: 80 * root.uiScale
            contentWidth: width
            contentHeight: contentColumn.height
            clip: true

            Column {
                id: contentColumn
                x: 52 * root.uiScale
                width: parent.width - 104 * root.uiScale
                spacing: 10 * root.uiScale

                Repeater {
                    model: root.rows
                    delegate: Item {
                        required property var modelData
                        width: contentColumn.width
                        height: modelData.heading ? 40 * root.uiScale : 78 * root.uiScale

                        Text {
                            visible: modelData.heading
                            anchors.left: parent.left
                            anchors.verticalCenter: parent.verticalCenter
                            text: modelData.label
                            color: root.luluPalette ? root.luluPalette.secondaryText : "#b8c0cc"
                            font.family: root.typography ? root.typography.displayFamily : "sans-serif"
                            font.weight: root.typography ? root.typography.displayWeight : Font.Bold
                            font.pixelSize: 18 * root.uiScale
                            font.letterSpacing: 2 * root.uiScale
                        }

                        Rectangle {
                            visible: !modelData.heading
                            anchors.fill: parent
                            radius: 8 * root.uiScale
                            color: {
                                var ordinal = 0
                                for (var n = 0; n < index; n++)
                                    if (!root.rows[n].heading) ordinal++
                                return ordinal === root.selectedIndex
                                    ? (root.luluPalette ? root.luluPalette.focusedCardSurface : "#263449")
                                    : (root.luluPalette ? root.luluPalette.glassTint : "#151c28")
                            }
                            border.width: 1
                            border.color: root.luluPalette ? root.luluPalette.glassBorder : "#445064"

                            Text {
                                x: 20 * root.uiScale
                                y: 12 * root.uiScale
                                text: modelData.job.title || "Untitled acquisition"
                                color: root.luluPalette ? root.luluPalette.primaryText : "white"
                                font.family: root.typography ? root.typography.displayFamily : "sans-serif"
                                font.weight: root.typography ? root.typography.displayWeight : Font.Bold
                                font.pixelSize: 20 * root.uiScale
                                elide: Text.ElideRight
                                width: parent.width * 0.52
                            }
                            Text {
                                x: 20 * root.uiScale
                                y: 45 * root.uiScale
                                text: String(modelData.job.provider || "provider").toUpperCase()
                                    + "  ·  " + String(modelData.job.operation || "acquire").toUpperCase()
                                color: root.luluPalette ? root.luluPalette.secondaryText : "#b8c0cc"
                                font.family: root.typography ? root.typography.displayFamily : "sans-serif"
                                font.pixelSize: 13 * root.uiScale
                            }
                            Text {
                                anchors.right: parent.right
                                anchors.rightMargin: 20 * root.uiScale
                                y: 12 * root.uiScale
                                text: String(modelData.job.stage || modelData.job.state || "").toUpperCase()
                                color: root.luluPalette ? root.luluPalette.accent : "#8fd3ff"
                                font.family: root.typography ? root.typography.displayFamily : "sans-serif"
                                font.pixelSize: 14 * root.uiScale
                            }
                            Text {
                                anchors.right: parent.right
                                anchors.rightMargin: 20 * root.uiScale
                                y: 39 * root.uiScale
                                text: {
                                    var progress = root.progressText(modelData.job)
                                    var bytes = root.formatBytes(modelData.job.downloaded_bytes)
                                    var total = root.formatBytes(modelData.job.total_bytes)
                                    if (progress) return progress + (bytes && total ? "  " + bytes + " / " + total : "")
                                    if (String(modelData.job.state) === "failed")
                                        return modelData.job.error ? String(modelData.job.error.message || "Failed") : "Failed"
                                    if (String(modelData.job.state) === "completed")
                                        return root.formatTime(modelData.job)
                                    return "Working…"
                                }
                                color: root.luluPalette ? root.luluPalette.primaryText : "white"
                                font.family: root.typography ? root.typography.displayFamily : "sans-serif"
                                font.pixelSize: 14 * root.uiScale
                                elide: Text.ElideLeft
                                width: parent.width * 0.42
                            }
                            Text {
                                visible: String(modelData.job.state) === "failed"
                                    && modelData.job.retryable === true
                                anchors.right: parent.right
                                anchors.rightMargin: 20 * root.uiScale
                                y: 58 * root.uiScale
                                text: "RETRY"
                                color: root.luluPalette ? root.luluPalette.warning : "#ffd166"
                                font.family: root.typography ? root.typography.displayFamily : "sans-serif"
                                font.pixelSize: 12 * root.uiScale
                            }
                        }
                    }
                }

                Text {
                    visible: root.rows.length === 0
                    width: parent.width
                    text: "No downloads"
                    color: root.luluPalette ? root.luluPalette.secondaryText : "#b8c0cc"
                    font.family: root.typography ? root.typography.displayFamily : "sans-serif"
                    font.pixelSize: 22 * root.uiScale
                    horizontalAlignment: Text.AlignHCenter
                    topPadding: 70 * root.uiScale
                }
            }
        }

        Text {
            anchors.left: parent.left
            anchors.leftMargin: 52 * root.uiScale
            anchors.bottom: parent.bottom
            anchors.bottomMargin: 24 * root.uiScale
            text: {
                var job = root.selectedJob()
                return job && String(job.state) === "failed" && job.retryable === true
                    ? "A  RETRY    B  BACK" : "B  BACK"
            }
            color: root.luluPalette ? root.luluPalette.secondaryText : "#b8c0cc"
            font.family: root.typography ? root.typography.displayFamily : "sans-serif"
            font.pixelSize: 15 * root.uiScale
        }
    }
}
