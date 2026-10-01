import unittest
from pathlib import Path


class NativeBuildTests(unittest.TestCase):
    def test_repo_shell_script_lists_all_lulu_shell_sources(self) -> None:
        root = Path(__file__).parents[1]
        script = (root / "scripts" / "build-lulu-shell.sh").read_text()
        cmake = (root / "native" / "CMakeLists.txt").read_text()
        for source in ("lulu-shell.cpp", "catalogue-model.cpp", "recent-model.cpp"):
            self.assertIn(f'"$repo_root/native/{source}"', script)
            self.assertIn(source, cmake)

    def test_recent_qml_uses_repeater_count_for_native_model_visibility(self) -> None:
        root = Path(__file__).parents[1]
        recent = (root / "ui" / "RecentHome.qml").read_text()
        self.assertIn("property var renderedRecentModel", recent)
        self.assertIn("model: recentHome.renderedRecentModel", recent)
        self.assertIn("recentModel", recent)
        self.assertIn("recentRepeater.count > 0", recent)
        self.assertNotIn("recentModel.count", recent)
        self.assertTrue((root / "tests" / "qml" / "tst_recent_model_boundary.qml").exists())

    def test_recent_delegate_maps_native_roles_to_game_card_contract(self) -> None:
        root = Path(__file__).parents[1]
        recent = (root / "ui" / "RecentHome.qml").read_text()
        card_presentation = (root / "ui" / "RecentCardPresentation.qml").read_text()
        catalogue_model = (root / "native" / "catalogue-model.cpp").read_text()
        self.assertIn('{"game_modes", "game_modes"}', catalogue_model)
        self.assertIn("property var gameRecord: ({", card_presentation)
        for field in ("game_id", "title", "artwork_url", "platform", "provider",
                      "last_played", "genres", "game_modes", "game_mode"):
            self.assertIn(f"{field}: {field}", card_presentation)
            self.assertIn(f"required property", card_presentation)
        for field in ("release_date", "release_year", "developer", "publisher",
                      "local_multiplayer", "online_multiplayer"):
            self.assertIn(f"{field}: {field}", card_presentation)
        self.assertIn("required property var game_modes", card_presentation)
        self.assertIn("game: root.gameRecord", card_presentation)
        self.assertIn("recentHome.itemCount - 1", (root / "ui" / "ConsoleShell.qml").read_text())

    def test_recent_reconciliation_preserves_index_binding_and_uses_authority_signal(self) -> None:
        root = Path(__file__).parents[1]
        recent = (root / "ui" / "RecentHome.qml").read_text()
        shell = (root / "ui" / "ConsoleShell.qml").read_text()
        reconcile = recent.split("function reconcilePresentation()", 1)[1].split(
            "function selectionCardVelocityAt", 1)[0]
        self.assertIn("var reconciledIndex", reconcile)
        self.assertIn("selectionIndexRequested(reconciledIndex)", reconcile)
        self.assertIn("var fallbackIndex", reconcile)
        self.assertNotIn("selectedIndex =", reconcile)
        self.assertIn("selectedIndex: root.recentIndex", shell)
        self.assertIn('"selectionIndexRequested"', shell)
        self.assertIn('"resultingRootIndex"', shell)
        self.assertIn('"resultingSelectedIndex"', shell)
        self.assertIn('"retargetTarget"', shell)

    def test_startup_recent_motion_is_one_rigid_row(self) -> None:
        root = Path(__file__).parents[1]
        recent = (root / "ui" / "RecentHome.qml").read_text()
        card_presentation = (root / "ui" / "RecentCardPresentation.qml").read_text()
        coordinator = (root / "ui" / "PresentationCoordinator.qml").read_text()
        self.assertIn("readonly property real rowRightEdge", recent)
        self.assertIn("readonly property real recentRowStartupX", recent)
        self.assertIn("readonly property real presentationX", recent)
        self.assertIn("id: recentRow", recent)
        self.assertIn("id: recentMotionBlur", recent)
        self.assertIn("x: recentHome.presentationX", recent)
        self.assertIn("sourceItem: recentRow", recent)
        self.assertIn("x: startX + (recentHome.railX(toRelativeIndex) - startX) * railProgress", recent)
        source_section = recent.split("id: recentRow", 1)[1].split("DirectionalMotionBlur", 1)[0]
        self.assertNotIn("+ recentHome.motionBlurPadding", source_section)
        self.assertIn("focused: index === recentHome.selectedIndex", recent)
        self.assertIn("presentationProgress", card_presentation)
        self.assertIn("selectionProgress", (root / "ui" / "GameCard.qml").read_text())
        self.assertNotIn("cardOffset(index)", recent)
        self.assertIn("function recentRowStartupX", coordinator)
        self.assertIn("function recentRowPresentationX", coordinator)
        self.assertNotIn("recentRowFastPhase", coordinator)
        self.assertNotIn("recentRowFastProgress", coordinator)
        self.assertNotIn("recentRowSettlePower", coordinator)

    def test_recent_motion_blur_is_bounded_and_qsb_backed(self) -> None:
        root = Path(__file__).parents[1]
        recent = (root / "ui" / "RecentHome.qml").read_text()
        effect = (root / "ui" / "DirectionalMotionBlur.qml").read_text()
        shader = (root / "ui" / "shaders" / "presentation-motion-blur.frag").read_text()
        self.assertIn("motionBlurPadding", recent)
        self.assertIn("hideSource: root.active", effect)
        self.assertIn('fragmentShader: "shaders/presentation-motion-blur.frag.qsb"', effect)
        self.assertIn("sourceTextureSize", shader)
        self.assertEqual(shader.count("texture(source"), 7)
        self.assertTrue((root / "ui" / "shaders" / "presentation-motion-blur.frag.qsb").exists())

    def test_motion_blur_padding_is_effect_space_only(self) -> None:
        root = Path(__file__).parents[1]
        recent = (root / "ui" / "RecentHome.qml").read_text()
        effect = (root / "ui" / "DirectionalMotionBlur.qml").read_text()
        self.assertIn("sourceRect: Qt.rect(recentHome.rowLeftEdge - recentHome.motionBlurPadding", recent)
        self.assertIn("property rect sourceRect", effect)
        self.assertIn("sourceRect: root.sourceRect", effect)
        self.assertIn("hideSource: root.active", effect)
        self.assertIn("live: root.active", effect)
        self.assertIn("selectionCardVelocityAt", recent)
        self.assertIn("selectionBlurSurfaceCount", recent)
        self.assertIn("selectionMotionActive", recent)

    def test_title_animation_viewport_is_separate_from_final_rail(self) -> None:
        root = Path(__file__).parents[1]
        shell = (root / "ui" / "ConsoleShell.qml").read_text()
        self.assertIn("id: titlePresentationViewport", shell)
        self.assertIn("x: 0\n            y: 0\n            width: root.width", shell)
        self.assertIn("width: root.width\n            height: parent.height\n            z: 20\n            clip: true", shell)
        self.assertIn("x: root.homeCategoryRailX", shell)
        self.assertIn("presentationCoordinator.titleOffset(index,", shell)

    def test_titles_use_independent_live_motion_blur_surfaces(self) -> None:
        root = Path(__file__).parents[1]
        shell = (root / "ui" / "ConsoleShell.qml").read_text()
        coordinator = (root / "ui" / "PresentationCoordinator.qml").read_text()
        self.assertIn("delegate: Item", shell)
        self.assertIn("id: titleText", shell)
        self.assertIn("sourceItem: titleText", shell)
        self.assertIn("sourceRect: Qt.rect(-titleBlurPadding", shell)
        self.assertIn("titleSignedBlurPixels(index,", shell)
        self.assertIn("titlePresentationVelocityPxPerMs", coordinator)
        self.assertIn("function titleTravelVelocityAt(index)", coordinator)
        self.assertIn("motionBlurMaxPixels", shell)
        self.assertNotIn("sourceItem: titleRail", shell)

    def test_library_and_system_share_coordinate_transparent_selection_blur(self) -> None:
        root = Path(__file__).parents[1]
        navigation = (root / "ui" / "NavigationCard.qml").read_text()
        library = (root / "ui" / "LibraryHome.qml").read_text()
        system = (root / "ui" / "SystemHome.qml").read_text()
        store = (root / "ui" / "StoreHome.qml").read_text()
        shell = (root / "ui" / "ConsoleShell.qml").read_text()
        self.assertIn("id: logicalCard", navigation)
        self.assertIn("sourceItem: logicalCard", navigation)
        self.assertIn("motionStartX", navigation)
        self.assertIn("motionTargetX", navigation)
        self.assertIn("motionBlurActive", navigation)
        self.assertIn("motionBlurPixels", navigation)
        for domain in (library, system):
            self.assertIn("selectionMotionActive", domain)
            self.assertIn("motionStartX: startX", domain)
            self.assertIn("motionTargetX: targetX", domain)
            self.assertIn("Easing.OutQuint", domain)
            self.assertIn("duration: 500", domain)
        self.assertIn("presentationCoordinator: presentationCoordinator", shell)
        self.assertIn("LibrarySpace {", store)
        self.assertNotIn("selectionMotionActive", store)


if __name__ == "__main__":
    unittest.main()
