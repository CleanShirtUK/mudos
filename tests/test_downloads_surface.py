from pathlib import Path
import unittest


ROOT = Path(__file__).parents[1]


class DownloadsSurfaceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.qml = (ROOT / "ui" / "DownloadsHome.qml").read_text()
        self.shell = (ROOT / "ui" / "ConsoleShell.qml").read_text()
        self.store = (ROOT / "ui" / "StoreHome.qml").read_text()
        self.bridge = (ROOT / "scripts" / "console-ui-bridge.py").read_text()
        self.guide = (ROOT / "native" / "mudos-guide.cpp").read_text()

    def test_surface_is_snapshot_driven_and_provider_neutral(self) -> None:
        for token in ("systemStatus.acquisitionSnapshot", "acquisitionSnapshotChanged",
                      "activeStates", "queuedStates", "historyStates", "No active downloads",
                      "retryRequested"):
            self.assertIn(token, self.qml + self.shell)
        self.assertNotIn("SteamCmd", self.qml)
        self.assertNotIn("Romm", self.qml)

    def test_stage_and_history_semantics_are_explicit(self) -> None:
        self.assertIn('String(job.state) === "transferring"', self.qml)
        self.assertIn('String(job.state) === "completed"', self.qml)
        self.assertIn('String(modelData.job.state) === "failed"', self.qml)
        self.assertIn('modelData.job.retryable === true', self.qml)
        self.assertIn('String(a.completed_at || a.updated_at || a.created_at', self.qml)

    def test_navigation_retry_and_store_active_routing(self) -> None:
        self.assertIn('root.space === "downloads"', self.shell)
        self.assertIn('root.openDownloads(root.space)', self.shell)
        self.assertIn('root.retryAcquisition(jobId)', self.shell)
        self.assertIn('/acquisition/retry/', self.shell)
        self.assertIn('downloadsRequested()', self.store)
        self.assertIn('call_retry_job', self.bridge)
        self.assertIn('target = "mudos:downloads"', (ROOT / "config/guide/mudos.toml").read_text())
        self.assertIn('label = "Open Downloads"', (ROOT / "config/guide/mudos.toml").read_text())

    def test_failed_rows_are_visible_and_retry_only(self) -> None:
        self.assertIn('"failed"]', self.qml)
        self.assertIn('String(job.state) === "failed"', self.qml)
        self.assertIn('retryRequested(String(job.job_id))', self.qml)
        self.assertIn('return canRetry(job) ? "Retry" : ""', self.qml)
        self.assertIn('text: root.failureReason(row.modelData)', self.qml)
        self.assertIn('hints.push({action: "options", label: "Clear"})', self.qml)
        self.assertIn('hints.push({action: "options", label: "Cancel"})', self.qml)

    def test_snapshot_churn_keeps_a_stable_list_model_and_identity_authority(self) -> None:
        self.assertIn("model: jobsModel", self.qml)
        self.assertIn("jobsModel.set(targetIndex, modelJob)", self.qml)
        self.assertIn("jobsModel.move(existingIndex, targetIndex, 1)", self.qml)
        self.assertNotIn("onCurrentIndexChanged", self.qml)
        self.assertNotIn("forceActiveFocus", self.qml)
        self.assertIn('else if (root.space === "downloads") root.moveDownloads(1)', self.shell)
        self.assertIn('else if (root.space === "downloads") root.moveDownloads(-1)', self.shell)

    def test_failed_rows_can_be_cleared_without_active_job_clear_path(self) -> None:
        for token in ('clearRequested', 'String(job.state) === "failed"',
                      'clearAcquisition(jobId)', '/acquisition/clear/'):
            self.assertIn(token, self.qml + self.shell + self.bridge)
        self.assertIn('def clear_acquisition', self.bridge)

    def test_list_view_follows_selection_and_accounts_for_scale(self) -> None:
        for token in ('positionViewAtIndex', 'currentIndex: root.selectedIndex',
                      'ListView.StrictlyEnforceRange', 'preferredHighlightBegin',
                      'preferredHighlightEnd', 'scale: 1 + 0.01 * selectionProgress',
                      'topMargin:', 'bottomMargin:'):
            self.assertIn(token, self.qml)

    def test_pending_mutations_and_stable_identity_selection_are_explicit(self) -> None:
        for token in ('"pausing"', '"resuming"', '"cancelling"', 'Pausing…',
                      'Resuming…', 'Cancelling…', 'selectedJobId',
                      'pause_supported', 'currentIndex: root.selectedIndex'):
            self.assertIn(token, self.qml)

    def test_pause_is_capability_gated_and_cancelled_rows_are_not_visible(self) -> None:
        self.assertIn('!incoming[i].retired', self.qml)
        self.assertIn('job.pause_supported', self.qml)
        self.assertNotIn('"cancelled"', self.qml.split('readonly property var visibleStates', 1)[1].split('\n', 1)[0])

    def test_centered_glass_surface_exposes_shell_owned_hints(self) -> None:
        self.assertIn('objectName: "downloadsGlassPanel"', self.qml)
        self.assertIn('readonly property real panelX', self.qml)
        self.assertIn('readonly property real panelY', self.qml)
        self.assertIn('readonly property var controllerHints', self.qml)
        self.assertNotIn('downloadControllerHints', self.qml)
        self.assertIn('objectName: "activeSurfaceControllerHints"', self.shell)
        self.assertIn('root.activeSurfaceHints', self.shell)
        self.assertIn('MudosPanelSurface {', self.qml)
        self.assertIn('MudosEmptyState {', self.qml)

    def test_old_steam_download_delegation_is_absent(self) -> None:
        for path in (ROOT / "src", ROOT / "native", ROOT / "scripts", ROOT / "ui"):
            for file in path.rglob("*"):
                if file.suffix in {".py", ".cpp", ".qml"}:
                    text = file.read_text()
                    for obsolete in ("RequestSteamDownloads", "open_steam_downloads",
                                     "steam://open/downloads", "View Download Queue"):
                        self.assertNotIn(obsolete, text, str(file))


if __name__ == "__main__":
    unittest.main()
