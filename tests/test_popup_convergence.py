from pathlib import Path
import unittest


ROOT = Path(__file__).parents[1]


class PopupConvergenceTests(unittest.TestCase):
    def test_lutris_uses_downloads_geometry_and_keeps_search_row_in_flow(self) -> None:
        lutris = (ROOT / "ui" / "LutrisRecipeInstall.qml").read_text()
        shell = (ROOT / "ui" / "ConsoleShell.qml").read_text()
        for token in (
            'objectName: "lutrisPopupPanel"',
            'materialRole: "overlay"',
            'decorationRole: "overlay"',
            'Math.min(expandedContentWidth, 780 * uiScale)',
            'Math.min(Math.max(1, expandedContentBottom - expandedContentY), 610 * uiScale)',
            'objectName: "lutrisSearchRow"',
            'objectName: "lutrisResultRows"',
            'role: "row"',
            'if (selectedIndex === 0) searchEditRequested()',
        ):
            self.assertIn(token, lutris)
        self.assertIn("lutrisRecipeInstall.openSearch()", shell)
        self.assertIn('target.kind === "lutris-search"', shell)
        self.assertIn('get("/lutris/search?query=" + encodeURIComponent(query)', lutris)
        self.assertIn('xhr.open("POST", root.apiUrl + "/lutris/install-recipe")', lutris)
        for geometry in ("canonicalTexture", "canonicalCoordinateRoot", "canonicalSize",
                         "expandedContentX", "expandedContentY", "expandedContentWidth",
                         "expandedContentBottom"):
            self.assertIn(geometry + ":", shell)

    def test_game_options_uses_centered_popup_and_preserves_existing_views(self) -> None:
        options = (ROOT / "ui" / "GameOptions.qml").read_text()
        shell = (ROOT / "ui" / "ConsoleShell.qml").read_text()
        for token in (
            'objectName: "gameOptionsPopupPanel"',
            "x: options.panelX",
            "y: options.panelY",
            'materialRole: "overlay"',
            'decorationRole: "overlay"',
            'role: "row"',
            '"menu"',
            '"mapping"',
            '"artworkRole"',
            '"artwork"',
            '"title"',
            '"confirm"',
            "preserveCandidateIdentity()",
            "textEntryRequested()",
        ):
            self.assertIn(token, options)
        self.assertIn("expandedContentX: root.expandedContentX", shell)
        self.assertIn("root.showGameOptionsKeyboard()", shell)
        self.assertNotIn("anchors.right: parent.right\n        anchors.top: parent.top", options)


if __name__ == "__main__":
    unittest.main()
