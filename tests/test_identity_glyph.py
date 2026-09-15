import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]


class IdentityGlyphTests(unittest.TestCase):
    def setUp(self):
        self.resolver = (ROOT / "ui/IdentityGlyphResolver.js").read_text()
        self.component = (ROOT / "ui/IdentityGlyph.qml").read_text()

    def test_namespaces_and_canonical_paths(self):
        for namespace, identity in (("provider", "steam"), ("runtime", "dolphin"),
                                    ("platform", "gamecube"), ("metadata", "genres")):
            self.assertIn(f'{identity}: "{identity}"', self.resolver)
            self.assertIn('"artwork/glyphs/" + namespace', self.resolver)
        self.assertIn('".svg"', self.resolver)

    def test_real_platform_aliases_and_namespace_separation(self):
        for alias in ("game-cube", "playstation 2", "nintendo switch"):
            self.assertIn(f'"{alias}"', self.resolver)
        self.assertIn('"last_played": "last-played"', self.resolver)
        self.assertIn('if (!mappings[namespace] || !value)', self.resolver)
        self.assertIn('assetPath: known ?', self.resolver)

    def test_missing_assets_have_no_placeholder_or_fallback(self):
        self.assertIn('assetPath: known ?', self.resolver)
        self.assertIn('.svg" : ""', self.resolver)
        self.assertNotIn("[ ]", self.component)
        self.assertIn("image.status === Image.Ready", self.component)
        self.assertIn("width: resolved ? size : 0", self.component)
        self.assertIn("height: resolved ? size : 0", self.component)

    def test_shared_component_uses_palette_colour_and_multieffect(self):
        self.assertIn("property color semanticColor", self.component)
        self.assertIn("colorization: 1.0", self.component)
        self.assertIn("colorizationColor: root.semanticColor", self.component)
        self.assertIn("fillMode: Image.PreserveAspectFit", self.component)

    def test_payload_copies_future_glyph_directories(self):
        release = (ROOT / "scripts/release.py").read_text()
        self.assertIn('PAYLOAD_DIRS = ("ui",', release)
        self.assertTrue((ROOT / "ui").is_dir())

    def test_supplied_metadata_assets_are_normalized(self):
        metadata = ROOT / "ui/artwork/glyphs/metadata"
        for name in ("genres.svg", "last-played.svg", "local-multiplayer.svg",
                     "online-multiplayer.svg", "protondb.svg"):
            self.assertTrue((metadata / name).is_file())


if __name__ == "__main__":
    unittest.main()
