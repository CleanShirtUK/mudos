import tempfile
from pathlib import Path
import unittest

from lulu.assets import AssetRegistry
from lulu.platforms import load_platforms
from lulu.providers import ConfigStrategy, load_providers


class ModularisationTests(unittest.TestCase):
    def test_shipped_platforms_are_content_only_and_provider_neutral(self):
        registry = load_platforms(Path(__file__).parents[1] / "config/platforms")
        gamecube = registry["gamecube"]
        self.assertEqual(gamecube.content.subdir, "gamecube")
        self.assertEqual(gamecube.supported_providers, ("dolphin",))
        self.assertFalse(hasattr(gamecube, "executable"))

    def test_provider_capabilities_and_strategy_are_explicit(self):
        registry = load_providers(Path(__file__).parents[1] / "config/providers")
        self.assertTrue(registry["steam"].capabilities.library)
        self.assertEqual(registry["romm"].config_strategy, ConfigStrategy.DIRECT)
        self.assertEqual(registry["dolphin"].config_root(Path("/tmp/providers")),
                         Path("/tmp/providers/dolphin/config"))

    def test_user_registry_override_is_deterministic(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "nes.toml").write_text(
                'id="nes"\nname="Test NES"\n[content]\nsubdir="custom"\nextensions=[".foo"]\n'
                '[providers]\nsupported=["retroarch"]\n')
            loaded = load_platforms(root)
            self.assertEqual(loaded["nes"].name, "Test NES")
            self.assertEqual(loaded["nes"].content.extensions, (".foo",))

    def test_asset_ids_cannot_escape_namespace(self):
        registry = AssetRegistry(Path("/tmp/lulu-assets"))
        self.assertEqual(registry.resolve("platforms/icon.svg"), Path("/tmp/lulu-assets/platforms/icon.svg"))
        with self.assertRaises(ValueError):
            registry.resolve("../secrets")
