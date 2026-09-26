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
}
