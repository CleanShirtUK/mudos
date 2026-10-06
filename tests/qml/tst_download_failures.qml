import QtQuick
import QtQuick.Window
import QtTest
import "../../ui" as UI

TestCase {
    name: "DownloadFailures"
    width: 1280
    height: 720
    when: windowShown
    UI.LuluPalette { id: palette }
    UI.Typography { id: fonts }
    Window {
        width: 1280
        height: 720
        visible: true
        UI.DownloadsHome {
            id: downloads
            anchors.fill: parent
            luluPalette: palette
            typography: fonts
        }
    }
    SignalSpy { id: retries; target: downloads; signalName: "retryRequested" }

    function test_reason_state_and_capability() {
        var failure = {job_id: "failure", state: "failed", retryable: true,
            error: {code: "unsupported-platform", message: "No emulator maps this platform", retryable: false}}
        downloads.snapshot = JSON.stringify({jobs: [failure]})
        compare(downloads.stateLabel(failure), "FAILED")
        verify(downloads.failureReason(failure).indexOf("No emulator maps this platform") >= 0)
        verify(downloads.failureReason(failure).indexOf("unsupported-platform") >= 0)
        compare(downloads.actionText(failure), "")
        downloads.activateSelected()
        compare(retries.count, 0)
        failure.retryable = false
        failure.error.retryable = true
        downloads.snapshot = JSON.stringify({jobs: [failure]})
        downloads.activateSelected()
        compare(retries.count, 0)
        failure.retryable = true
        downloads.snapshot = JSON.stringify({jobs: [failure]})
        compare(downloads.actionText(failure), "Retry")
        downloads.activateSelected()
        compare(retries.count, 1)
    }

    function test_selected_row_stays_inside_clipping_viewport() {
        downloads.snapshot = JSON.stringify({jobs: [
            {job_id: "first", state: "failed", title: "Long failure", retryable: false,
             error: {code: "unsupported-platform", message: "A long failure reason that must wrap across the row instead of being cut off or hidden behind the clipped left edge of Downloads.", retryable: false}},
            {job_id: "second", state: "transferring", title: "Second", retryable: true}
        ]})
        wait(10)
        var list = findChild(downloads, "downloadJobRows")
        verify(list !== null)
        list.forceLayout()
        wait(20)
        var row = null
        for (var childIndex = 0; childIndex < list.contentItem.children.length; ++childIndex) {
            var child = list.contentItem.children[childIndex]
            if (child.job_id === "first") {
                for (var nested = 0; nested < child.children.length; ++nested) {
                    if (child.children[nested].objectName === "downloadJobRow")
                        row = child.children[nested]
                }
            }
        }
        verify(row !== null, "selected first delegate should be instantiated")
        function contained() {
            var left = row.mapToItem(list, 0, 0).x
            var right = row.mapToItem(list, row.width, 0).x
            verify(left >= 0, "selected row should not clip on left: " + left)
            verify(right <= list.width, "selected row should not clip on right: " + right)
        }
        compare(downloads.selectedIndex, 0)
        verify(row.height > 88)
        contained()
        downloads.moveSelection(1)
        wait(1)
        compare(downloads.selectedIndex, 1)
        var selected = null
        // ListView delegates are recycled; select the one representing the
        // second job rather than assuming findChild returns it first.
        for (var i = 0; i < list.contentItem.children.length; ++i) {
            var candidate = list.contentItem.children[i]
            if (candidate.job_id === "second") {
                for (var k = 0; k < candidate.children.length; ++k)
                    if (candidate.children[k].objectName === "downloadJobRow")
                        selected = candidate.children[k]
            }
        }
        verify(selected !== null)
        row = selected
        contained()
    }

    function test_selection_tracks_job_identity_across_snapshot_replacement() {
        var rows = [
            {job_id: "job-a", state: "transferring", title: "A", created_at: "1"},
            {job_id: "job-b", state: "queued", title: "B", created_at: "2"},
            {job_id: "job-c", state: "queued", title: "C", created_at: "3"}
        ]
        downloads.selectedIndex = 0
        downloads.selectedJobId = ""
        downloads.snapshot = JSON.stringify({jobs: rows})
        downloads.moveSelection(1)
        compare(downloads.selectedJobId, "job-b")

        rows[0].progress = 0.5
        rows[1].state = "starting"
        downloads.snapshot = JSON.stringify({jobs: rows})
        compare(downloads.selectedJobId, "job-b")
        compare(downloads.selectedIndex, 1)

        downloads.snapshot = JSON.stringify({jobs: [rows[0], rows[2]]})
        compare(downloads.selectedIndex, 1)
        compare(downloads.selectedJobId, "job-c")
    }

    function test_selection_survives_production_model_churn_and_reordering() {
        downloads.selectedIndex = 0
        downloads.selectedJobId = ""
        var rows = [
            {job_id: "active-a", state: "transferring", title: "A", provider: "fixture",
             created_at: "2026-01-01", progress: 0.1, downloaded_bytes: 10, total_bytes: 100},
            {job_id: "selected-b", state: "queued", title: "B", provider: "fixture",
             created_at: "2026-01-02", progress: null, downloaded_bytes: null, total_bytes: null,
             pause_supported: true},
            {job_id: "active-c", state: "transferring", title: "C", provider: "fixture",
             created_at: "2026-01-03", progress: 0.2, downloaded_bytes: 20, total_bytes: 100}
        ]
        downloads.snapshot = JSON.stringify({jobs: rows})
        downloads.moveSelection(1)
        compare(downloads.selectedJobId, "selected-b")
        var list = findChild(downloads, "downloadJobRows")
        verify(list !== null)
        compare(list.currentIndex, 1)
        compare(list.model.count, 3)

        // Realistic burst of progress/speed/ETA snapshots while another row
        // moves from transfer into finalization. Selection stays by ID.
        for (var tick = 1; tick <= 12; tick++) {
            rows[0].progress = tick / 20
            rows[0].downloaded_bytes = tick * 5
            rows[0].speed_bytes_per_second = tick * 100
            rows[0].eta_seconds = 60 - tick
            rows[2].progress = tick / 15
            rows[2].downloaded_bytes = tick * 7
            if (tick === 4)
                rows[2].state = "finalizing"
            downloads.snapshot = JSON.stringify({jobs: rows})
            wait(1)
            compare(downloads.selectedJobId, "selected-b", "progress churn changed selected job")
            compare(list.currentIndex, 1, "progress churn changed visual row")
        }

        // Exercise the actual normalized pause/resume state vocabulary. These
        // transient states must remain actionable/visible instead of dropping
        // and re-inserting the selected entry.
        var selectedStates = ["starting", "transferring", "pausing", "paused",
                              "resuming", "queued", "finalizing"]
        for (var stateIndex = 0; stateIndex < selectedStates.length; stateIndex++) {
            rows[1].state = selectedStates[stateIndex]
            downloads.snapshot = JSON.stringify({jobs: rows})
            wait(1)
            compare(downloads.selectedJobId, "selected-b",
                    "selected job disappeared during " + selectedStates[stateIndex])
            compare(list.currentIndex, 1)
        }

        // A newly discovered earlier job changes the selected visual row;
        // selection must follow the original job, not freeze the row number.
        rows.push({job_id: "inserted", state: "starting", title: "New", provider: "fixture",
                   created_at: "2025-12-31", progress: 0})
        downloads.snapshot = JSON.stringify({jobs: rows})
        wait(1)
        compare(downloads.selectedJobId, "selected-b")
        compare(downloads.selectedIndex, 2)
        compare(list.currentIndex, 2)

        // Removing an unrelated completing/retired row keeps the selected ID.
        rows[0].state = "completed"
        downloads.snapshot = JSON.stringify({jobs: rows})
        wait(1)
        compare(downloads.selectedJobId, "selected-b")
        compare(downloads.selectedIndex, 1)
        compare(list.currentIndex, 1)

        // Removing the selected row selects the row now occupying its old
        // position (the deterministic next neighbour), or the previous last.
        rows[1].state = "cancelled"
        rows[1].retired = true
        downloads.snapshot = JSON.stringify({jobs: rows})
        wait(1)
        compare(downloads.selectedJobId, "active-c")
        compare(downloads.selectedIndex, 1)
        compare(list.currentIndex, 1)
    }

    function test_six_normal_rows_scroll_in_bounded_centered_panel() {
        var rows = []
        for (var i = 0; i < 6; ++i)
            rows.push({job_id: "row-" + i, state: "queued", title: "Download " + i})
        downloads.snapshot = JSON.stringify({jobs: rows})
        wait(10)
        var list = findChild(downloads, "downloadJobRows")
        verify(list !== null)
        list.forceLayout()
        wait(20)
        verify(list.height < list.contentHeight,
               "bounded centered panel should scroll longer job lists")
        verify(list.contentHeight >= 6 * 88,
               "six complete row delegates should be laid out: content="
               + list.contentHeight + " count=" + list.model.count)
        compare(downloads.controllerHints[downloads.controllerHints.length - 1].label, "Back")
        verify(downloads.panelWidth <= downloads.expandedContentWidth)
        verify(downloads.panelHeight <= downloads.expandedContentBottom - downloads.expandedContentY)
        verify(Math.abs(downloads.panelX + downloads.panelWidth / 2
                        - downloads.expandedContentX - downloads.expandedContentWidth / 2) < 1)
        verify(findChild(downloads, "downloadControllerHints") === null)
    }
}
