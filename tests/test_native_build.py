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
        self.assertIn("model: recentModel", recent)
        self.assertIn("recentRepeater.count > 0", recent)
        self.assertNotIn("recentModel.count", recent)
        self.assertTrue((root / "tests" / "qml" / "tst_recent_model_boundary.qml").exists())

    def test_recent_delegate_maps_native_roles_to_game_card_contract(self) -> None:
        root = Path(__file__).parents[1]
        recent = (root / "ui" / "RecentHome.qml").read_text()
        self.assertIn("property var gameRecord: ({", recent)
        for field in ("game_id", "title", "artwork_url", "platform", "provider",
                      "last_played", "genres", "local_multiplayer",
                      "online_multiplayer", "game_mode"):
            self.assertIn(f"{field}: {field}", recent)
            self.assertIn(f"required property", recent)
        self.assertIn("game: gameRecord", recent)
        self.assertIn("recentHome.itemCount - 1", (root / "ui" / "ConsoleShell.qml").read_text())

    def test_startup_recent_motion_is_one_rigid_row(self) -> None:
        root = Path(__file__).parents[1]
        recent = (root / "ui" / "RecentHome.qml").read_text()
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
        self.assertIn("focused: index === recentHome.selectedIndex", source_section)
        self.assertIn("presentationProgress: blend", source_section)
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
        self.assertIn("hideSource: true", effect)
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
        self.assertIn("hideSource: true", effect)
        self.assertIn("live: true", effect)

    def test_title_animation_viewport_is_separate_from_final_rail(self) -> None:
        root = Path(__file__).parents[1]
        shell = (root / "ui" / "ConsoleShell.qml").read_text()
        self.assertIn("id: titlePresentationViewport", shell)
        self.assertIn("x: 0\n            y: 0\n            width: root.width", shell)
        self.assertIn("width: root.width\n            height: parent.height\n            z: 20\n            clip: true", shell)
        self.assertIn("x: root.homeCategoryRailX", shell)
        self.assertIn("presentationCoordinator.titleOffset(index,", shell)


if __name__ == "__main__":
    unittest.main()
