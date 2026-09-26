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
}
