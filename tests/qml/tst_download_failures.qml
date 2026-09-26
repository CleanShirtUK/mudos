import QtQuick
import QtTest
import "../../ui" as UI

TestCase {
    name: "DownloadFailures"
    width: 1280
    height: 720
    UI.LuluPalette { id: palette }
    UI.Typography { id: fonts }
    UI.DownloadsHome {
        id: downloads
        anchors.fill: parent
        luluPalette: palette
        typography: fonts
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
        compare(downloads.actionLabel(failure), "")
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
        wait(1)
        var list = findChild(downloads, "downloadJobRows")
        var row = findChild(downloads, "downloadJobRow")
        verify(list !== null && row !== null)
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
            if (candidate.modelData && candidate.modelData.job_id === "second") {
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

    function test_six_normal_rows_fit_without_clipping_the_last_row() {
        var rows = []
        for (var i = 0; i < 6; ++i)
            rows.push({job_id: "row-" + i, state: "queued", title: "Download " + i})
        downloads.snapshot = JSON.stringify({jobs: rows})
        wait(1)
        var list = findChild(downloads, "downloadJobRows")
        verify(list !== null)
        verify(list.height >= list.contentHeight,
               "the visible viewport should contain all six normal rows")
        verify(list.contentHeight >= 6 * 88,
               "six complete row delegates should be laid out")
        var hints = findChild(downloads, "downloadControllerHints")
        verify(hints !== null)
        var listBottom = list.mapToItem(downloads, 0, list.height).y
        var hintsTop = hints.mapToItem(downloads, 0, 0).y
        verify(hintsTop >= listBottom,
               "controller hints must not overlap the last visible row: hints="
               + hintsTop + " listBottom=" + listBottom)
        verify(hintsTop + hints.height <= downloads.height,
               "controller hints must remain inside the Downloads surface")
    }
}
