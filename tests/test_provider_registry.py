import tempfile
import unittest
from pathlib import Path

from lulu.providers import load_providers


class ProviderLaunchContractTests(unittest.TestCase):
    def test_launch_contract_is_separate_and_menu_order_is_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for provider_id, name, standalone in (
                ("zeta", "Zeta", "zeta --menu"),
                ("alpha", "Alpha", "alpha"),
                ("catalogue", "Catalogue", None),
            ):
                path = root / provider_id
                path.mkdir()
                launch = f'\n[launch.standalone]\ncommand = "{standalone}"' if standalone else ""
                (path / "provider.toml").write_text(
                    f'id = "{provider_id}"\nname = "{name}"\n'
                    '[capabilities]\nlaunch = true\n[platforms]\nsupported = []\n'
                    '[config]\nstrategy = "direct"\n' + launch
                )
            registry = load_providers(root)
            self.assertEqual([item.provider_id for item in registry.standalone()], ["alpha", "zeta"])
            self.assertEqual(registry["zeta"].standalone_launch.command, ("zeta", "--menu"))
            self.assertIsNone(registry["catalogue"].standalone_launch)

    def test_game_and_standalone_can_share_executable_but_arguments_differ(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "retroarch"
            path.mkdir()
            (path / "provider.toml").write_text(
                'id = "retroarch"\nname = "RetroArch"\n'
                '[capabilities]\nlaunch = true\n[platforms]\nsupported = ["nes"]\n'
                '[config]\nstrategy = "direct"\n'
                '[launch.standalone]\ncommand = "/usr/bin/retroarch"\n'
                '[launch.game]\ncommand = "/usr/bin/retroarch --game"\n'
            )
            provider = load_providers(Path(directory))["retroarch"]
            self.assertEqual(provider.standalone_launch.command, ("/usr/bin/retroarch",))
            self.assertEqual(provider.game_launch.command, ("/usr/bin/retroarch", "--game"))

    def test_steam_is_a_declared_standalone_provider(self) -> None:
        provider = load_providers()["steam"]
        self.assertEqual(provider.standalone_launch.command,
                         ("/usr/bin/steam", "steam://open/main"))
        self.assertEqual(provider.standalone_launch.controller_mode, "compat")
        self.assertEqual(provider.standalone_launch.window_class, "steam")



if __name__ == "__main__":
    unittest.main()
