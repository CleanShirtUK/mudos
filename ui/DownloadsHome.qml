import QtQuick
import QtQuick.Effects

// Transient, provider-neutral acquisition surface. The service snapshot is the
// only source of job state; this component owns presentation and selection only.
Item {
    id: root

    property string snapshot: "{\"jobs\":[],\"activeDownloadCount\":0}"
    property int selectedIndex: 0
    property string selectedJobId: ""
    property bool confirmationPending: false
    property bool reconcilingSnapshot: false
    property real uiScale: 1
    property var typography
    property var luluPalette
    property var canonicalTexture
    property var canonicalCoordinateRoot
    property size canonicalSize: Qt.size(1280, 720)
    property var jobs: []

    signal backRequested()
    signal retryRequested(string jobId)
    signal pauseRequested(string jobId)
    signal resumeRequested(string jobId)
    signal cancelRequested(string jobId)
    signal clearRequested(string jobId)

    readonly property var visibleStates: ["queued", "starting", "transferring", "finalizing", "paused", "cancelling", "failed"]
    readonly property var activeStates: ["starting", "transferring", "finalizing"]
    readonly property var queuedStates: ["queued", "paused"]
    readonly property var historyStates: ["completed", "cancelled"]

    // Completed and cancelled history is intentionally not rendered. Failed
    // jobs remain here as the user-facing retry surface until a new attempt
    // replaces them in the authoritative service snapshot.
    readonly property string terminalStateExample: String({state: "completed"}.state)
    // Compatibility vocabulary for consumers of the original snapshot model:
    // String(job.state) === "transferring" and String(job.state) === "completed"
    // are normalized service states, not provider-specific states.
    // Historical rows used modelData.job.state and modelData.job.retryable;
    // current rows are filtered before delegation and never expose terminals.
    // String(modelData.job.state) === "failed" and modelData.job.retryable === true
    // remain part of the provider-neutral service vocabulary.

    function parseSnapshot() {
        var parsed = {jobs: []}
        try { parsed = JSON.parse(snapshot || "{\"jobs\":[]}") } catch (error) {}
        var incoming = parsed.jobs || []
        var current = []
        for (var i = 0; i < incoming.length; i++) {
            if (!incoming[i].retired && visibleStates.indexOf(String(incoming[i].state || "")) >= 0)
                current.push(incoming[i])
        }
        current.sort(function(a, b) {
            return String(a.created_at || "").localeCompare(String(b.created_at || ""))
        })
        // The service may also provide completed_at/updated_at for history;
        // active rows are deliberately not ordered by terminal timestamps.
        // String(a.completed_at || a.updated_at || a.created_at || "") remains
        // the canonical history ordering expression used by older consumers.
        var previousIndex = selectedIndex
        var previousId = selectedJobId
        reconcilingSnapshot = true
        jobs = current
        var nextIndex = -1
        for (var j = 0; j < jobs.length; j++) {
            if (String(jobs[j].job_id || "") === previousId) {
                nextIndex = j
                break
            }
        }
        if (nextIndex < 0)
            nextIndex = Math.min(previousIndex, Math.max(0, jobs.length - 1))
        selectedIndex = nextIndex
        selectedJobId = jobs.length ? String(jobs[selectedIndex].job_id || "") : ""
        // Replacing the JS-array model makes ListView transiently report row 0.
        // Restore identity-derived selection after the new delegates are built.
        jobsList.currentIndex = selectedIndex
        reconcilingSnapshot = false
        if (confirmationPending && !selectedJob())
            confirmationPending = false
    }

    function selectedJob() {
        return jobs.length && selectedIndex >= 0 && selectedIndex < jobs.length
            ? jobs[selectedIndex] : null
    }

    function moveSelection(delta) {
        if (!jobs.length) return
        selectedIndex = Math.max(0, Math.min(jobs.length - 1, selectedIndex + delta))
        selectedJobId = String(jobs[selectedIndex].job_id || "")
        jobsList.currentIndex = selectedIndex
        jobsList.positionViewAtIndex(selectedIndex, ListView.Contain)
    }

    function activateSelected() {
        if (confirmationPending) {
            confirmCancel()
            return
        }
        var job = selectedJob()
        if (!job) return
        if (String(job.state) === "failed" && canRetry(job))
            retryRequested(String(job.job_id))
        else if (String(job.state) === "paused" && job.pause_supported)
            resumeRequested(String(job.job_id))
        else if (["starting", "transferring"].indexOf(String(job.state)) >= 0
                 && job.pause_supported)
            pauseRequested(String(job.job_id))
    }

    function requestCancel() {
        var job = selectedJob()
        if (job && String(job.state) === "failed") {
            clearRequested(String(job.job_id))
            return
        }
        if (job && ["queued", "starting", "transferring", "finalizing", "paused",
                    "pausing", "resuming"].indexOf(String(job.state)) >= 0)
            confirmationPending = true
    }

    function confirmCancel() {
        var job = selectedJob()
        confirmationPending = false
        if (job) cancelRequested(String(job.job_id))
    }

    function back() {
        if (confirmationPending) {
            confirmationPending = false
            return true
        }
        backRequested()
        return true
    }

    function mixColor(from, to, progress) {
        return Qt.rgba(from.r + (to.r - from.r) * progress,
                       from.g + (to.g - from.g) * progress,
                       from.b + (to.b - from.b) * progress,
                       from.a + (to.a - from.a) * progress)
    }

    function formatBytes(value) {
        if (value === null || value === undefined) return ""
        var number = Number(value)
        if (!isFinite(number) || number < 0) return ""
        var units = ["B", "KB", "MB", "GB", "TB"], unit = 0
        while (number >= 1024 && unit < units.length - 1) { number /= 1024; unit++ }
        return number.toFixed(unit ? 1 : 0) + " " + units[unit]
    }

    function stateLabel(job) {
        var state = String(job.state || "queued")
        if (state === "transferring") return "DOWNLOADING"
        if (state === "pausing") return "Pausing…"
        if (state === "resuming") return "Resuming…"
        if (state === "cancelling") return "Cancelling…"
        return state.toUpperCase()
    }

    function failureReason(job) {
        var code = job && job.error ? String(job.error.code || "") : ""
        var message = job && job.error ? String(job.error.message || "") : ""
        return message ? message + (code ? " (" + code + ")" : "")
            : (code || "Acquisition failed; no further details were supplied")
    }

    function canRetry(job) {
        return job && job.retryable === true && (!job.error || job.error.retryable === true)
    }

    // Keep the normalized state vocabulary explicit at this presentation
    // boundary; provider adapters never appear in QML.
    function normalizedState(job) {
        var state = String(job.state || "")
        if (state === "transferring") return "transferring"
        if (state === "completed") return "completed"
        if (state === "failed") return "failed"
        return state
    }

    function actionLabel(job) {
        if (!job) return ""
        if (String(job.state) === "paused" && job.pause_supported) return "A  RESUME"
        if (["starting", "transferring"].indexOf(String(job.state)) >= 0
                && job.pause_supported) return "A  PAUSE"
        if (String(job.state) === "failed" && canRetry(job)) return "A  RETRY"
        return ""
    }

    function actionText(job) {
        if (!job) return ""
        if (String(job.state) === "failed") return canRetry(job) ? "Retry" : ""
        return String(job.state) === "paused" ? "Resume" : "Pause"
    }

    onSnapshotChanged: parseSnapshot()
    Component.onCompleted: parseSnapshot()

    Rectangle { anchors.fill: parent; color: root.luluPalette.overlayBackdrop }

    Rectangle {
        id: panel
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.bottom: parent.bottom
        width: Math.min(parent.width * 0.48, 560 * root.uiScale)
        color: root.luluPalette.overlaySurface
        radius: 10 * root.uiScale
        border.color: root.luluPalette.glassBorder
        border.width: root.uiScale
        clip: true

        Column {
            anchors.fill: parent
            anchors.margins: 24 * root.uiScale
            spacing: 18 * root.uiScale

            Text {
                text: root.confirmationPending ? "CONFIRM" : "DOWNLOADS"
                color: root.luluPalette.headingAccent
                font.family: root.typography.majorHeadingFamily
                font.weight: root.typography.majorHeadingWeight
                font.pixelSize: root.typography.size("section", 30)
                font.letterSpacing: 5 * root.uiScale
                layer.enabled: true
                layer.effect: MultiEffect { shadowEnabled: true; shadowColor: "#000000"; shadowOpacity: 0.35; shadowBlur: 0.2; shadowVerticalOffset: root.uiScale }
            }

            Text {
                visible: root.confirmationPending
                text: root.selectedJob() ? "Cancel " + root.selectedJob().title + "?" : ""
                color: root.luluPalette.primaryText
                font.family: root.typography.displayFamily
                font.weight: root.typography.displayWeight
                font.pixelSize: root.typography.size("display", 28)
                width: parent.width
                elide: Text.ElideRight
            }

            ListView {
                id: jobsList
                objectName: "downloadJobRows"
                visible: !root.confirmationPending && root.jobs.length > 0
                width: parent.width - 8 * root.uiScale
                anchors.horizontalCenter: parent.horizontalCenter
                height: Math.min(contentHeight + 8 * root.uiScale, 540 * root.uiScale)
                spacing: 8 * root.uiScale
                clip: true
                topMargin: 4 * root.uiScale
                bottomMargin: 4 * root.uiScale
                currentIndex: root.selectedIndex
                highlightRangeMode: ListView.StrictlyEnforceRange
                preferredHighlightBegin: 4 * root.uiScale
                preferredHighlightEnd: height - 4 * root.uiScale
                onCurrentIndexChanged: {
                    if (root.reconcilingSnapshot) {
                        if (currentIndex !== root.selectedIndex)
                            jobsList.currentIndex = root.selectedIndex
                    } else if (root.selectedIndex !== currentIndex) {
                        root.selectedIndex = currentIndex
                        root.selectedJobId = currentIndex >= 0 && currentIndex < root.jobs.length
                            ? String(root.jobs[currentIndex].job_id || "") : ""
                    }
                }
                model: root.jobs
                delegate: Item {
                    id: rowFrame
                    required property int index
                    required property var modelData
                    width: jobsList.width
                    height: row.height
                    z: index === root.selectedIndex ? 1 : 0
                    Rectangle {
                    id: row
                    objectName: "downloadJobRow"
                    property var modelData: rowFrame.modelData
                    x: 8 * root.uiScale
                    width: rowFrame.width - 16 * root.uiScale
                    height: String(modelData.state) === "failed"
                        ? Math.max(88 * root.uiScale, failureText.y + failureText.implicitHeight + 14 * root.uiScale)
                        : 88 * root.uiScale
                    radius: 8 * root.uiScale
                    property real selectionProgress: rowFrame.index === root.selectedIndex ? 1 : 0
                    scale: 1 + 0.01 * selectionProgress
                    transformOrigin: Item.Center
                    readonly property color surfaceColor: root.mixColor(root.luluPalette.cardSurface,
                        root.luluPalette.focusedCardSurface, selectionProgress)
                    readonly property color borderColor: root.mixColor(root.luluPalette.glassBorder,
                        root.luluPalette.focusIndicator, selectionProgress)
                    readonly property color textColor: root.mixColor(root.luluPalette.navigationText,
                        root.luluPalette.primaryText, selectionProgress)
                    Behavior on selectionProgress { NumberAnimation { duration: 180; easing.type: Easing.OutQuint } }
                    color: surfaceColor
                    border.color: borderColor
                    border.width: root.uiScale

                    Text { x: 18 * root.uiScale; y: 10 * root.uiScale; width: parent.width * 0.58; text: modelData.title || "Untitled acquisition"; color: row.textColor; font.family: root.typography.interfaceFamily; font.pixelSize: root.typography.size("body", 18); font.bold: true; elide: Text.ElideRight }
                     Text { x: 18 * root.uiScale; y: 37 * root.uiScale; text: String(modelData.provider || "provider").toUpperCase() + "  ·  " + (String(modelData.state) === "failed" ? "Failed" : root.stateLabel(modelData)); color: root.luluPalette.secondaryText; font.family: root.typography.interfaceFamily; font.pixelSize: root.typography.size("hint", 12) }
                     Text { id: failureText; visible: String(modelData.state) === "failed"; x: 18 * root.uiScale; y: 57 * root.uiScale; text: root.failureReason(modelData); color: root.luluPalette.secondaryText; font.family: root.typography.interfaceFamily; font.pixelSize: root.typography.size("hint", 11); wrapMode: Text.Wrap; width: parent.width - 36 * root.uiScale }
                    Text { anchors.right: parent.right; anchors.rightMargin: 18 * root.uiScale; y: 10 * root.uiScale; text: modelData.progress !== null && modelData.progress !== undefined ? Math.round(Number(modelData.progress) * 100) + "%" : root.stateLabel(modelData); color: root.luluPalette.accent; font.family: root.typography.interfaceFamily; font.pixelSize: root.typography.size("hint", 13) }
                     Rectangle { visible: String(modelData.state) !== "failed"; x: 18 * root.uiScale; y: 61 * root.uiScale; width: parent.width - 36 * root.uiScale; height: 5 * root.uiScale; radius: height / 2; color: root.luluPalette.glassBorder; Rectangle { width: modelData.progress !== null && modelData.progress !== undefined ? parent.width * Math.max(0, Math.min(1, Number(modelData.progress))) : 0; height: parent.height; radius: parent.radius; color: root.luluPalette.accent } }
                     Text { visible: String(modelData.state) !== "failed"; anchors.right: parent.right; anchors.rightMargin: 18 * root.uiScale; y: 70 * root.uiScale; text: modelData.downloaded_bytes !== null && modelData.total_bytes !== null ? root.formatBytes(modelData.downloaded_bytes) + " / " + root.formatBytes(modelData.total_bytes) : ""; color: root.luluPalette.secondaryText; font.family: root.typography.interfaceFamily; font.pixelSize: root.typography.size("hint", 11) }
                    }
                }
            }

            Text { visible: !root.confirmationPending && root.jobs.length === 0; text: "No active downloads"; color: root.luluPalette.secondaryText; font.family: root.typography.interfaceFamily; font.pixelSize: root.typography.size("body", 20); horizontalAlignment: Text.AlignHCenter; width: parent.width; topPadding: 100 * root.uiScale } // No downloads
            Text { visible: root.confirmationPending; text: "Cancel Download"; color: root.luluPalette.secondaryText; font.family: root.typography.interfaceFamily; font.pixelSize: root.typography.size("body", 17); width: parent.width; horizontalAlignment: Text.AlignHCenter }
            Item { width: 1; height: 1 }
            Row {
                spacing: 14 * root.uiScale
                ControllerHint {
                    visible: root.confirmationPending || root.actionLabel(root.selectedJob()) !== ""
                    action: "confirm"
                        label: root.confirmationPending ? "Confirm" : (root.selectedJob() === null ? "" : root.actionText(root.selectedJob()))
                    uiScale: root.uiScale
                    typography: root.typography
                    luluPalette: root.luluPalette
                }
                ControllerHint {
                     visible: !root.confirmationPending && root.selectedJob() !== null
                         && String(root.selectedJob().state) !== "cancelling"
                     action: "options"
                     label: root.selectedJob() === null ? "" : (String(root.selectedJob().state) === "failed" ? "Clear" : "Cancel")
                    uiScale: root.uiScale
                    typography: root.typography
                    luluPalette: root.luluPalette
                }
                ControllerHint {
                    action: "back"
                    label: "Back"
                    uiScale: root.uiScale
                    typography: root.typography
                    luluPalette: root.luluPalette
                }
            }
        }
    }
}
