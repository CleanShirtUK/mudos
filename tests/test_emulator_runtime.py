import tempfile
import unittest
from pathlib import Path

from lulu.emulator_runtime import EmulatorRuntimeAdapter
from lulu.controller_provisioning import ensure_provider_controller_config
from lulu.consoled import _retroarch_child_config
from lulu.local_content import LocalContentGame
from lulu.switch_provider import SwitchProvider
from lulu.paths import PATHS


class EmulatorRuntimeTests(unittest.TestCase):
    def test_retroarch_child_config_does_not_emit_invalid_negative_joypad_index(self) -> None:
        config_path = Path(_retroarch_child_config({1: 0, 2: 1, 3: 2}))
        try:
            content = config_path.read_text()
        finally:
            config_path.unlink()

        self.assertIn('input_player1_joypad_index = "0"', content)
        self.assertIn('input_player2_joypad_index = "1"', content)
        self.assertIn('input_player3_joypad_index = "2"', content)
        self.assertNotIn("-1", content)
        self.assertNotIn("input_player4_joypad_index", content)

    def test_retroarch_provider_menu_capability_and_command(self) -> None:
        self.assertTrue(EmulatorRuntimeAdapter.supports_provider_menu("nes"))
        self.assertEqual(
            EmulatorRuntimeAdapter.open_provider_menu("nes"),
            ("/usr/bin/retroarch", "--command", "MENU_TOGGLE"),
        )

    def test_other_provider_menus_are_not_advertised(self) -> None:
        for platform in ("ps2", "wii", "switch"):
            self.assertFalse(EmulatorRuntimeAdapter.supports_provider_menu(platform))
            with self.assertRaises(ValueError):
                EmulatorRuntimeAdapter.open_provider_menu(platform)

    def test_retroarch_intent_contains_core_and_content_only(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            executable = root / "retroarch"
            core = root / "nestopia_libretro.so"
            content = root / "game.nes"
            for path in (executable, core, content):
                path.write_bytes(b"fixture")
            game = LocalContentGame("local:nes:id", "Game", "nes", str(content), True, "installed", "ready")

            intent = EmulatorRuntimeAdapter({"nes": executable}, {"nes": core}).launch_intent(game)

        self.assertEqual(intent.executable, str(executable))
        self.assertEqual(intent.arguments, ("-L", str(core), str(content)))

    def test_unlaunchable_content_is_rejected_before_runtime_invocation(self) -> None:
        game = LocalContentGame("local:switch:id", "Switch", "switch", "/fixture/game.nsp", False, "installed", "runtime-missing")

        with self.assertRaisesRegex(ValueError, "runtime-missing"):
            EmulatorRuntimeAdapter({}).launch_intent(game)

    def test_missing_core_is_a_distinct_runtime_failure(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            executable = Path(directory) / "retroarch"
            executable.write_bytes(b"fixture")
            game = LocalContentGame("local:nes:id", "Game", "nes", "/fixture/game.nes", True, "installed", "ready")

            with self.assertRaisesRegex(ValueError, "runtime-core-missing"):
                EmulatorRuntimeAdapter({"nes": executable}).launch_intent(game)

    def test_dolphin_intent_is_platform_driven(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            executable = Path(directory) / "dolphin-emu"
            executable.write_bytes(b"fixture")
            game = LocalContentGame("local:wii:id", "Wii", "wii", "/fixture/game.rvz", True, "installed", "ready")

            intent = EmulatorRuntimeAdapter({"wii": executable}).launch_intent(game)

        self.assertEqual(intent.arguments, ("-e", "/fixture/game.rvz"))

    def test_switch_intent_uses_eden_direct_launch_and_deterministic_profile(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            executable = root / "eden-cli"
            executable.write_bytes(b"fixture")
            provider = SwitchProvider(executable, root / "eden")
            game = LocalContentGame("local:switch:id", "Game", "switch", "/fixture/game.nsp", True, "installed", "ready")

            intent = EmulatorRuntimeAdapter({"switch": executable}, switch_provider=provider).launch_intent(game)
            config_path = root / "eden" / "lulu-switch.ini"
            config = config_path.read_text()
            second = provider.ensure_controller_config()
            second_content = second.read_text()

        self.assertEqual(intent.arguments, ("--appimage-extract-and-run", "--config", str(second), "--fullscreen", "--game", "/fixture/game.nsp"))
        self.assertIn('player_1_button_a="engine:sdl,guid:030081b85e0400008e02000001000000,port:0,button:1"', config)
        self.assertIn('player_1_button_zl="engine:sdl,guid:030081b85e0400008e02000001000000,port:0,axis:4,threshold:0.5,invert:+"', config)
        self.assertEqual(config, second_content)

    def test_pcsx2_intent_uses_controller_first_direct_boot(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            executable = Path(directory) / "pcsx2-qt"
            executable.write_bytes(b"fixture")
            game = LocalContentGame("local:ps2:id", "Game", "ps2", "/fixture/game.cue", True, "installed", "ready")

            intent = EmulatorRuntimeAdapter({"ps2": executable}).launch_intent(game)

        self.assertEqual(
            intent.arguments,
            ("-batch", "-fullscreen", "-bigpicture", "--", "/fixture/game.cue"),
        )

    def test_pcsx2_controller_profile_is_native_and_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = ensure_provider_controller_config("pcsx2", root)
            first = path.read_text()
            ensure_provider_controller_config("pcsx2", root)

            self.assertEqual(path.read_text(), first)
            self.assertIn("[Pad1]", first)
            self.assertIn(f"Bios = {PATHS.bios_root / 'ps2'}", first)
            self.assertIn("Cross = SDL-0/FaceSouth", first)
            pad1 = first.split("[Pad2]", 1)[0]
            self.assertNotIn("SDL-1/", pad1)
            self.assertIn("Up = SDL-0/DPadDown", first)
            self.assertIn("L2 = SDL-0/+LeftTrigger", first)
            self.assertNotIn("Keyboard/", first)
            self.assertIn("[Pad2]", first)
            self.assertIn("Cross = SDL-1/FaceSouth", first)

    def test_dolphin_controller_profile_uses_inputplumber_virtual_name(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = ensure_provider_controller_config("dolphin", Path(directory))
            content = path.read_text()

            self.assertIn("Device = SDL/0/Xbox 360 Controller", content)
            self.assertIn("Buttons/A = `Button A`", content)
            self.assertIn("Main Stick/Up = `Left Y+`", content)
            self.assertIn("Triggers/L-Analog = `Trigger L`", content)
            self.assertIn("Main Stick/Calibration = 100.00", content)
            self.assertIn("[GCPad2]", content)
            self.assertIn("Device = SDL/1/Xbox 360 Controller", content)

            dolphin = Path(directory) / "dolphin-emu" / "Dolphin.ini"
            dolphin_content = dolphin.read_text()
            self.assertIn("SIDevice0 = 6", dolphin_content)
            self.assertIn("WiimoteSource0 = 0", dolphin_content)

            wiimote = Path(directory) / "dolphin-emu" / "WiimoteNew.ini"
            wiimote_content = wiimote.read_text()
            self.assertNotIn("[Wiimote1]", wiimote_content)

    def test_provider_profiles_follow_logical_player_device_indices(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            pcsx2 = ensure_provider_controller_config(
                "pcsx2", root, 3, {1: 0, 2: 2, 3: 1}
            ).read_text()
            dolphin = ensure_provider_controller_config(
                "dolphin", root, 3, {1: 0, 2: 2, 3: 1}
            ).read_text()

        self.assertIn("[Pad2]", pcsx2)
        self.assertIn("Cross = SDL-2/FaceSouth", pcsx2)
        self.assertIn("[GCPad2]", dolphin)
        self.assertIn("Device = SDL/2/Xbox 360 Controller", dolphin)
        self.assertIn("[GCPad3]", dolphin)
        self.assertIn("Device = SDL/1/Xbox 360 Controller", dolphin)


if __name__ == "__main__":
    unittest.main()
