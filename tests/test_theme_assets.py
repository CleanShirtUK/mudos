import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
THEMES = ROOT / "themes"


class DefaultThemeInventoryTests(unittest.TestCase):
    def test_default_theme_declares_current_theme_owned_assets(self):
        theme = THEMES / "modern"
        config = json.loads((theme / "theme.json").read_text())
        self.assertEqual(config["schema_version"], 1)
        self.assertEqual(config["id"], "modern")
        self.assertEqual(config["name"], "Modern")
        self.assertTrue(config["glass"]["enabled"])
        self.assertEqual(config["radiusPolicy"], "componentBaseline")
        self.assertEqual(config["chrome"]["style"], "flat")
        self.assertEqual(config["motion"]["roles"]["wallpaper"],
                         {"enabled": True, "speed": 1.0})
        self.assertTrue((theme / config["wallpaper"]["shader"]).is_file())
        for face in config["fonts"]["faces"].values():
            path = Path(face["file"])
            self.assertFalse(path.is_absolute())
            self.assertNotIn("..", path.parts)
            self.assertTrue((theme / path).is_file(), str(path))
        for path in config["icons"].values():
            self.assertTrue((theme / path).is_file())
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

    def test_95_is_a_self_contained_flat_square_theme(self):
        theme = THEMES / "95"
        config = json.loads((theme / "theme.json").read_text())
        self.assertEqual((config["id"], config["name"]), ("95", "95"))
        self.assertFalse(config["glass"]["enabled"])
        self.assertEqual(set(config["radii"].values()), {0})
        self.assertEqual(config["radiusPolicy"], "exact")
        self.assertEqual(config["chrome"]["style"], "bevel")
        self.assertFalse(config["motion"]["roles"]["wallpaper"]["enabled"])
        self.assertTrue((theme / config["wallpaper"]["shader"]).is_file())
        self.assertTrue((theme / "wallpaper/wallpaper.frag").is_file())
        self.assertEqual(len(config["icons"]), 12)
        self.assertEqual(set(config["fonts"]["faces"]),
                         {"regular", "bold", "heavy", "icons", "controller"})
        self.assertTrue((theme / "fonts/LIBERATION-FONTS-LICENSE.txt").is_file())
        for face in config["fonts"]["faces"].values():
            self.assertTrue((theme / face["file"]).is_file())
        for icon in config["icons"].values():
            self.assertTrue((theme / icon).is_file())

    def test_metalheart_is_a_self_contained_glass_theme(self):
        theme = THEMES / "metalheart"
        config = json.loads((theme / "theme.json").read_text())
        self.assertEqual((config["id"], config["name"]), ("metalheart", "Metalheart"))
        self.assertTrue(config["glass"]["enabled"])
        self.assertEqual(config["radii"],
                         {role: 0 for role in ("panel", "card", "row", "media", "status", "overlay")})
        self.assertEqual(config["radiusPolicy"], "exact")
        self.assertEqual(config["chrome"]["style"], "flat")
        self.assertEqual(config["motion"]["roles"]["wallpaper"],
                         {"enabled": True, "speed": 1.0})
        self.assertEqual(config["labels"]["home"]["store"], "ACQUIRE")
        self.assertEqual(config["textStyles"]["homeTitle"],
                         {"case": "preserve", "letterSpacing": 1.25})
        self.assertEqual(config["motion"]["durationScale"], 0.72)
        self.assertEqual(config["fonts"]["roles"]["interface"], "regular")
        self.assertEqual(config["fonts"]["roles"]["display"], "heavy")
        self.assertNotEqual(config["fonts"]["faces"]["regular"]["file"],
                            config["fonts"]["faces"]["heavy"]["file"])
        self.assertTrue((theme / config["wallpaper"]["shader"]).is_file())
        self.assertTrue((theme / "wallpaper/wallpaper.frag").is_file())
        self.assertGreaterEqual(len(config["icons"]), 30)
        for face in config["fonts"]["faces"].values():
            path = Path(face["file"])
            self.assertFalse(path.is_absolute())
            self.assertNotIn("..", path.parts)
            self.assertTrue((theme / path).is_file(), str(path))
        for icon in config["icons"].values():
            path = Path(icon)
            self.assertFalse(path.is_absolute())
            self.assertNotIn("..", path.parts)
            self.assertTrue((theme / path).is_file(), str(path))
        for license_name in ("OXANIUM-OFL.txt", "SHARE-TECH-MONO-OFL.txt",
                             "NERD-FONTS-LICENSE.txt", "PROVENANCE.md"):
            self.assertTrue((theme / "fonts" / license_name).is_file())
        for value in config["colors"].values():
            self.assertTrue(value.startswith("#"))
        for value in config["glass"].values():
            if isinstance(value, dict):
                for metric in ("ior", "depth", "refractionPixels", "dispersionIor",
                               "diffusionPixels", "transmission", "bevelWidth",
                               "bulgeStrength", "sceneLightStrength", "sceneLightPixels",
                               "edgeLightStrength"):
                    self.assertIn(metric, value)
                    self.assertGreaterEqual(value[metric], 0)


if __name__ == "__main__":
    unittest.main()
