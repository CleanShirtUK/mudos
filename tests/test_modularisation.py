import tempfile
from pathlib import Path
import unittest

from lulu.assets import AssetRegistry
from lulu.platforms import load_platforms
from lulu.providers import ConfigStrategy, load_providers
from lulu.providers import NativeConfigAdapter
from lulu.providers.runtime import launch_arguments


class ModularisationTests(unittest.TestCase):
    def test_shipped_platforms_are_content_only_and_provider_neutral(self):
        registry = load_platforms(Path(__file__).parents[1] / "config/platforms")
        gamecube = registry["gamecube"]
        self.assertEqual(gamecube.content.subdir, "gamecube")
        self.assertEqual(gamecube.supported_providers, ("dolphin",))
        self.assertFalse(hasattr(gamecube, "executable"))

    def test_provider_capabilities_and_strategy_are_explicit(self):
        registry = load_providers()
        self.assertTrue(registry["steam"].capabilities.library)
        self.assertEqual(registry["romm"].config_strategy, ConfigStrategy.DIRECT)
        for provider in ("retroarch", "dolphin", "pcsx2", "eden"):
            self.assertEqual(registry[provider].config_strategy, ConfigStrategy.DIRECT)
        self.assertEqual(registry["dolphin"].config_root(Path("/tmp/providers")),
                         Path("/tmp/providers/dolphin/config"))
        self.assertEqual(registry.for_platform("wii").provider_id, "dolphin")

    def test_provider_launch_adapter_uses_centralized_config(self):
        registry = load_providers()
        provider = registry["retroarch"]
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            executable, core = root / "retroarch", root / "core.so"
            executable.write_bytes(b"")
            core.write_bytes(b"")
            game = type("Game", (), {"platform": "nes", "content_path": "/tmp/game.nes"})()
            args = launch_arguments(provider, game, executable, core,
                                    root / "lulu/retroarch/config", None)
        self.assertEqual(args[0], "--config")
        self.assertEqual(Path(args[1]).parts[-4:-1], ("lulu", "retroarch", "config"))
        self.assertEqual(Path(args[1]).name, "retroarch.cfg")

    def test_native_setting_round_trip_preserves_unowned_values(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "Dolphin.ini"
            path.write_text("[Core]\nCPUThread= true\nOther=keep\n")
            adapter = NativeConfigAdapter(path)
            adapter.set("Core", "CPUThread", "false")
            self.assertEqual(adapter.get("Core", "CPUThread"), "false")
            self.assertEqual(adapter.get("Core", "Other"), "keep")

    def test_native_sectionless_setting_round_trip(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "retroarch.cfg"
            path.write_text('video_driver = "gl"\nfps_show = "false"\n')
            adapter = NativeConfigAdapter(path)
            self.assertEqual(adapter.get("", "fps_show"), '"false"')
            adapter.set("", "fps_show", '"true"')
            self.assertEqual(adapter.get("", "fps_show"), '"true"')

    def test_dolphin_central_user_directory_is_flat(self):
        from lulu.controller_provisioning import ensure_provider_controller_config
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = ensure_provider_controller_config(
                "dolphin", root / "xdg", native_user_root=root / "lulu-dolphin"
            )
            self.assertEqual(path, root / "lulu-dolphin/GCPadNew.ini")
            self.assertTrue((root / "lulu-dolphin/Dolphin.ini").is_file())
            self.assertTrue((root / "lulu-dolphin/Hotkeys.ini").is_file())
            self.assertTrue((root / "lulu-dolphin/WiimoteNew.ini").is_file())

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
