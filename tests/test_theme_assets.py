import json
from pathlib import Path
import subprocess
import tempfile
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
        for icon in config["icons"].values():
            path = icon["file"] if isinstance(icon, dict) else icon
            self.assertTrue((theme / path).is_file())
        for value in config["colors"].values():
            self.assertTrue(value.startswith("#"))

    def test_frutiger_aero_full_colour_assets_and_presentation_contract(self):
        theme = THEMES / "frutiger-aero"
        config = json.loads((theme / "theme.json").read_text())
        self.assertEqual((config["id"], config["name"]), ("frutiger-aero", "Frutiger Aero"))
        self.assertTrue(config["glass"]["enabled"])
        self.assertEqual(config["radii"],
                         {"panel": 22, "card": 16, "row": 12,
                          "media": 16, "status": 18, "overlay": 22})
        self.assertEqual(config["radiusPolicy"], "exact")
        self.assertEqual(config["chrome"]["style"], "flat")
        self.assertEqual(set(config["textStyles"]) ,
                         {"homeTitle", "viewTitle", "heading", "body", "metadata",
                          "annotation", "status"})
        self.assertNotIn("pixelSize", json.dumps(config["textStyles"]))
        self.assertEqual(set(config["materials"]),
                         {"panel", "card", "navigation", "status", "overlay", "row"})
        self.assertTrue((theme / "wallpaper/wallpaper.frag").is_file())
        self.assertTrue((theme / config["wallpaper"]["shader"]).is_file())
        self.assertTrue((theme / "ASSET_PROVENANCE.md").is_file())
        required = {"settings", "applications", "controller", "wifi", "bluetooth",
                    "volume", "storage", "display", "download", "refresh", "platform",
                    "provider", "gameMode", "genre", "play", "warning", "info"}
        self.assertTrue(required.issubset(config["icons"]))
        for name, descriptor in config["icons"].items():
            self.assertEqual(descriptor["render"], "original", name)
            self.assertTrue(descriptor["file"].endswith(".png"), name)
            self.assertTrue((theme / descriptor["file"]).is_file(), name)
        for key in ("regular", "bold", "heavy"):
            self.assertTrue((theme / config["fonts"]["faces"][key]["file"]).is_file())

    def test_metalheart_wallpaper_contract_and_qsb_are_reproducible(self):
        theme = THEMES / "metalheart"
        config = json.loads((theme / "theme.json").read_text())
        self.assertEqual(config["wallpaper"]["shader"], "wallpaper/wallpaper.frag.qsb")
        self.assertEqual(config["motion"]["roles"]["wallpaper"],
                         {"enabled": True, "speed": 1.0})
        source = (theme / "wallpaper/wallpaper.frag").read_text()
        self.assertIn("#define MAX_STEPS 24", source)
        self.assertIn("qt_TexCoord0.x, 1.0 - qt_TexCoord0.y", source)
        self.assertIn("vec2 fragCoord = shaderUv * u_resolution", source)
        self.assertIn("intersectSceneBounds(ro,rd,tNear,tFar)", source)
        self.assertIn("float pixelFootprint = max(", source)
        self.assertIn("closestDistance < pixelFootprint*3.0", source)
        self.assertIn("if(edgeCandidate)", source)
        self.assertIn("vec2 sampleOffsets[2]", source)
        self.assertIn("vec2 primaryUv = uv + vec2(-quarterPixel,-quarterPixel)", source)
        self.assertIn("colorSum += renderSceneRay", source)
        self.assertIn("for(int i=0;i<4;i++)", source)
        self.assertIn("for(int i=0;i<4;i++)", source)
        self.assertIn("const vec3 halfExtent = vec3(5.25,2.78,1.50)", source)
        self.assertNotIn("calcAO(", source)
        self.assertIn("fwidth(d)", source)

        qsb = Path("/usr/lib/qt6/bin/qsb")
        if not qsb.is_file():
            self.skipTest("Qt Shader Baker is unavailable")
        with tempfile.TemporaryDirectory() as directory:
            rebuilt = Path(directory) / "wallpaper.frag.qsb"
            subprocess.run([
                str(qsb), "--qt6", "--batchable", "-o", str(rebuilt),
                str(theme / "wallpaper/wallpaper.frag")
            ], check=True, capture_output=True, text=True)
            self.assertEqual(rebuilt.read_bytes(),
                             (theme / "wallpaper/wallpaper.frag.qsb").read_bytes())
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
        self.assertEqual(set(config["materials"]),
                         {"panel", "card", "navigation", "status", "overlay", "row"})
        for material in config["materials"].values():
            self.assertEqual(material["style"], "linearGradient")
            self.assertIn(material["orientation"], {"vertical", "horizontal"})
            self.assertGreaterEqual(len(material["stops"]), 2)
            self.assertLessEqual(len(material["stops"]), 8)
        self.assertIn("panel", config["decorations"])
        self.assertIn("overlay", config["decorations"])
        for profile in config["decorations"].values():
            for slot in profile.values():
                self.assertTrue((theme / slot["asset"]).is_file())
                self.assertIn(slot["tint"], {"accent", "secondaryText", "border", "focusIndicator"})
        for face in config["fonts"]["faces"].values():
            path = Path(face["file"])
            self.assertFalse(path.is_absolute())
            self.assertNotIn("..", path.parts)
            self.assertTrue((theme / path).is_file(), str(path))
        for icon in config["icons"].values():
            path = Path(icon["file"] if isinstance(icon, dict) else icon)
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
