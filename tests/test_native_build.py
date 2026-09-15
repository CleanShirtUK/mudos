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
        self.assertIn("x: recentHome.presentationX", recent)
        self.assertNotIn("cardOffset(index)", recent)
        self.assertIn("function recentRowStartupX", coordinator)
        self.assertIn("function recentRowPresentationX", coordinator)
        self.assertNotIn("recentRowFastPhase", coordinator)
        self.assertNotIn("recentRowFastProgress", coordinator)
        self.assertNotIn("recentRowSettlePower", coordinator)

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
