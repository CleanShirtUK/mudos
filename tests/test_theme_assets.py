import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
THEME = ROOT / "themes" / "mudos-default"


class DefaultThemeInventoryTests(unittest.TestCase):
    def test_default_theme_declares_current_theme_owned_assets(self):
        config = json.loads((THEME / "theme.json").read_text())
        self.assertEqual(config["schema_version"], 1)
        self.assertEqual(config["id"], "mudos-default")
        self.assertTrue(config["glass"]["enabled"])
        self.assertTrue((THEME / config["wallpaper"]["shader"]).is_file())
        for face in config["fonts"]["faces"].values():
            path = Path(face["file"])
            self.assertFalse(path.is_absolute())
            self.assertNotIn("..", path.parts)
            self.assertTrue((THEME / path).is_file(), str(path))
        for path in config["icons"].values():
            self.assertTrue((THEME / path).is_file())
        for value in config["colors"].values():
            self.assertTrue(value.startswith("#"))
        for value in config["opacity"].values():
            self.assertGreaterEqual(value, 0)
            self.assertLessEqual(value, 1)
        for value in config["radii"].values():
            self.assertGreaterEqual(value, 0)
            self.assertLessEqual(value, 128)

    def test_font_and_wallpaper_no_longer_need_runtime_ui_asset_paths(self):
        typography = (ROOT / "ui/Typography.qml").read_text()
        controller = (ROOT / "ui/ControllerGlyph.qml").read_text()
        wallpaper = (ROOT / "ui/OrbitRenderSource.qml").read_text()
        self.assertNotIn('source: "fonts/', typography)
        self.assertNotIn('source: "fonts/', controller)
        self.assertIn("mudosTheme.wallpaperShader", wallpaper)


if __name__ == "__main__":
    unittest.main()
