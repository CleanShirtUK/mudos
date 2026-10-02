from pathlib import Path
import unittest


ROOT = Path(__file__).parents[1]


class StoreAcquisitionStabilityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.store = (ROOT / "ui" / "StoreHome.qml").read_text()
        self.card = (ROOT / "ui" / "StoreCardState.qml").read_text()
        self.shell = (ROOT / "ui" / "ConsoleShell.qml").read_text()
        self.library = (ROOT / "ui" / "LibrarySpace.qml").read_text()
        self.game_card = (ROOT / "ui" / "GameCard.qml").read_text()

    def test_store_uses_stable_records_and_visible_job_lookup(self) -> None:
        self.assertIn("readonly property var displayGames: displayCards", self.store)
        self.assertIn("function applyAcquisitionJobs()", self.store)
        self.assertNotIn("displayCards[index].setAcquisition", self.store)
        self.assertNotIn("cardStateComponent.createObject", self.store)
        self.assertIn("onLaunchRequested: root.activateGame(game, acquisitionJob)", self.store)
        self.assertIn("function acquisitionJobFor(game)", self.library)
        self.assertIn("acquisitionJobs[String(game.game_id)]", self.library)
        self.assertIn("function setAcquisition(job)", self.card)
        self.assertIn("if (signature === acquisition_signature)", self.card)
        self.assertNotIn("Object.keys(acquisitionJobs)", self.store)
        self.assertIn("property var acquisitionJobs", self.library)

    def test_transient_stages_do_not_use_stale_transfer_progress(self) -> None:
        self.assertIn('card.acquisitionState === "transferring"', self.game_card)
        self.assertIn("acquisitionProgressKnown", self.game_card)
        self.assertIn('card.acquisitionState === "starting"', self.game_card)
        self.assertIn('card.acquisitionState === "finalizing"', self.game_card)
        self.assertIn('if (state === "queued")', self.game_card)
        self.assertIn("function acquisitionStatusLabel(state)", self.game_card)
        self.assertIn('return "Download failed"', self.game_card)
        self.assertIn('text: "00000000000"', self.game_card)
        self.assertIn("width: acquisitionStatusMetrics.advanceWidth", self.game_card)
        self.assertIn("wrapMode: Text.WordWrap", self.game_card)
        self.assertIn("maximumLineCount: 2", self.game_card)
        self.assertIn("radius: artworkFrame.artworkRadius", self.game_card)
        self.assertIn("font.pixelSize: card.typography.size(\"control\", 16 * card.focalScale)", self.game_card)
        self.assertIn("font.pixelSize: card.typography.size(\"secondary\", 13 * card.focalScale)", self.game_card)

    def test_completion_is_the_only_acquisition_catalogue_refresh(self) -> None:
        completion_block = self.shell.split('if (String(job.state || "") === "completed"', 1)[1]
        completion_block = completion_block.split("acquisitionJobs = jobs", 1)[0]
        self.assertIn("refreshStore()", completion_block)
        self.assertIn("refreshCatalogue()", completion_block)
        self.assertIn("acquisitionJobs = jobs", self.shell)
        self.assertIn("onAcquisitionJobsChanged: applyAcquisitionJobs()", self.store)

    def test_selection_and_viewport_are_preserved_when_catalogue_rebuilds(self) -> None:
        self.assertIn("selectedIdentity", self.store)
        self.assertIn("previousFirstVisibleRow", self.store)
        self.assertIn("preservedIndex", self.store)
        self.assertIn("firstVisibleRow = Math.min(previousFirstVisibleRow", self.store)

    def test_concurrent_provider_decoration_is_identity_keyed(self) -> None:
        self.assertIn('acquisitionJobs[String(game.game_id)]', self.store)
        self.assertIn('"steam-aurelia:"', self.store)
        self.assertIn('"steam:"', self.store)
        self.assertIn('provider === "romm"', self.store)


if __name__ == "__main__":
    unittest.main()
