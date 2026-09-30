import tempfile
import unittest
import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from lulu.emulator_runtime import EmulatorRuntimeAdapter
from lulu.controller_provisioning import ensure_provider_controller_config, ensure_retroarch_autoconfig
from lulu.consoled import (
    _mudos_provider_device_indices,
    _parse_busctl_json_string,
    _retroarch_child_config,
)
from lulu.local_content import LocalContentGame
from lulu.switch_provider import SwitchProvider
from lulu.paths import PATHS


class EmulatorRuntimeTests(unittest.TestCase):
    def setUp(self) -> None:
        # Unit profiles use an explicit synthetic live identity. Production
        # callers always supply this from the controller inventory.
        self._old_guid = os.environ.get("LULU_SWITCH_SDL_GUID")
        os.environ["LULU_SWITCH_SDL_GUID"] = "synthetic-live-guid"

    def tearDown(self) -> None:
        if self._old_guid is None:
            os.environ.pop("LULU_SWITCH_SDL_GUID", None)
        else:
            os.environ["LULU_SWITCH_SDL_GUID"] = self._old_guid
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

    def test_provider_indices_use_normalized_sdl_identity_not_composite_path(self) -> None:
        from unittest.mock import patch

        controllers = {
            1: {
                "connected": True,
                "controller_type": "standard_gamepad",
                "physical_identity": "source:event8",
                "sdl_index": 0,
                "sdl_guid": "unknown-guid",
                "sdl_name": "Unbranded USB Gamepad",
            }
        }
        with patch("lulu.consoled._mudos_provider_controller_identities", return_value=controllers):
            self.assertEqual(_mudos_provider_device_indices(), {1: 0})

    def test_retroarch_provider_menu_capability_and_command(self) -> None:
        self.assertTrue(EmulatorRuntimeAdapter.supports_provider_menu("nes"))
        self.assertEqual(
            EmulatorRuntimeAdapter.open_provider_menu("nes"),
            ("/usr/bin/retroarch", "--command", "MENU_TOGGLE"),
        )

    def test_installed_retroarch_platform_registry_includes_added_core_systems(self) -> None:
        from lulu.emulation import PLATFORMS
        from lulu.providers import load_providers

        supported = set(load_providers()["retroarch"].supported_platforms)
        for platform in ("gba", "gb", "gbc", "snes", "nds", "n64", "psx",
                         "psp", "arcade", "dreamcast"):
            self.assertIn(platform, PLATFORMS)
            self.assertIsNotNone(PLATFORMS[platform].core)
            self.assertIn(platform, supported)

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

    def test_retroarch_launches_the_generated_multi_disc_playlist_descriptor(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            executable = root / "retroarch"
            core = root / "pcsx_rearmed_libretro.so"
            playlist = root / "Final Fantasy [fixture].m3u"
            for path in (executable, core):
                path.write_bytes(b"fixture")
            playlist.write_text("disc1.cue\ndisc2.cue\n")
            game = LocalContentGame("local:psx:playlist", "Final Fantasy", "psx", str(playlist),
                                    True, "installed", "ready")

            intent = EmulatorRuntimeAdapter({"psx": executable}, {"psx": core}).launch_intent(game)

        self.assertEqual(intent.arguments, ("-L", str(core), str(playlist)))

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

        self.assertEqual(intent.arguments, ("--batch", "-e", "/fixture/game.rvz"))

    def test_switch_intent_uses_eden_direct_launch_and_deterministic_profile(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            executable = root / "eden-cli"
            executable.write_bytes(b"fixture")
            provider = SwitchProvider(executable, root / "eden")
            game = LocalContentGame("local:switch:id", "Game", "switch", "/fixture/game.nsp", True, "installed", "ready")

            intent = EmulatorRuntimeAdapter({"switch": executable}, switch_provider=provider).launch_intent(game)
            config_path = root / "eden" / "qt-config.ini"
            config = config_path.read_text()
            second = provider.ensure_controller_config()
            second_content = second.read_text()

        self.assertEqual(intent.arguments, ("--appimage-extract-and-run", "--config", str(second), "-f", "--fullscreen", "--game", "/fixture/game.nsp"))
        self.assertIn('player_0_button_a="engine:sdl,port:0,guid:synthetic-live-guid,button:0"', config)
        self.assertIn('player_0_button_b="engine:sdl,port:0,guid:synthetic-live-guid,button:1"', config)
        self.assertIn('player_0_button_x="engine:sdl,port:0,guid:synthetic-live-guid,button:2"', config)
        self.assertIn('player_0_button_y="engine:sdl,port:0,guid:synthetic-live-guid,button:3"', config)
        self.assertIn("player_0_type=0", config)
        self.assertIn("player_0_connected=true", config)
        self.assertIn("player_0_connected\\default=false", config)
        self.assertNotIn("player_0_connect=", config)
        self.assertEqual(config, second_content)
        self.assertIn('player_0_lstick="engine:sdl,port:0,guid:synthetic-live-guid,axis_x:0,axis_y:1,invert_x:+,invert_y:+"', config)

    def test_switch_profile_follows_assigned_controller_indices(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            provider = SwitchProvider(root / "eden-cli", root / "eden")
            config = provider.ensure_controller_config(device_indices={1: 0, 2: 2, 3: 1})
            content = config.read_text()

        self.assertIn("player_0_button_a=\"engine:sdl,port:0,guid:synthetic-live-guid,button:0\"", content)
        self.assertIn("player_1_button_a=\"engine:sdl,port:2,guid:synthetic-live-guid,button:0\"", content)
        self.assertIn("player_2_button_a=\"engine:sdl,port:1,guid:synthetic-live-guid,button:0\"", content)
        self.assertNotIn("player_3_", content)

    def test_switch_three_player_profile_has_unique_gamepads_and_native_mapping(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            provider = SwitchProvider(Path(directory) / "eden-cli", Path(directory) / "eden")
            path = provider.ensure_controller_config(3, {1: 0, 2: 1, 3: 2})
            content = path.read_text()

        for player, port in enumerate((0, 1, 2)):
            for name, button in (("a", 0), ("b", 1), ("x", 2), ("y", 3)):
                self.assertIn(
                    f'player_{player}_button_{name}="engine:sdl,port:{port},guid:synthetic-live-guid,button:{button}"',
                    content,
                )
            self.assertIn(f"player_{player}_type=0", content)
            self.assertIn(f"player_{player}_connected=true", content)
            self.assertNotIn(f"player_{player}_button_a=\"engine:keyboard", content)
        self.assertNotIn("player_3_", content)

    def test_switch_reload_removes_stale_keyboard_and_unpopulated_slots(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            provider = SwitchProvider(Path(directory) / "eden-cli", Path(directory) / "eden")
            provider.ensure_controller_config(3, {1: 0, 2: 1, 3: 2})
            path = provider.ensure_controller_config(1, {1: 0})
            content = path.read_text()

        self.assertIn("player_0_type=0", content)
        self.assertNotIn("player_1_", content)
        self.assertNotIn("player_2_", content)
        self.assertNotIn("engine:keyboard", content)

    def test_switch_writes_current_eden_native_config_root(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            provider = SwitchProvider(
                root / "eden-cli",
                root / "provider-config",
                root / "native-eden",
            )
            active = provider.ensure_controller_config(1, {1: 0})
            content = active.read_text()
            source_exists = (root / "provider-config" / "lulu-switch.ini").is_file()

        self.assertEqual(active, root / "native-eden" / "qt-config.ini")
        self.assertTrue(source_exists)
        self.assertIn("player_0_button_dup=", content)
        self.assertIn("engine:sdl,port:0,guid:", content)
        self.assertIn("player_0_button_dup=\"engine:sdl,port:0,guid:", content)
        self.assertIn("hat:0,direction:up\"", content)

    def test_pcsx2_intent_uses_controller_first_direct_boot(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            executable = Path(directory) / "pcsx2-qt"
            executable.write_bytes(b"fixture")
            game = LocalContentGame("local:ps2:id", "Game", "ps2", "/fixture/game.cue", True, "installed", "ready")

            intent = EmulatorRuntimeAdapter({"ps2": executable}).launch_intent(game)

        self.assertEqual(
            intent.arguments,
            ("-batch", "-fullscreen", "--", "/fixture/game.cue"),
        )
        provider = (Path(__file__).parents[1] / "config/providers/pcsx2/provider.toml").read_text()
        self.assertEqual(provider.count('command = "/usr/local/bin/pcsx2-qt"'), 2)

    def test_pcsx2_default_runtime_uses_release_owned_flatpak_wrapper(self) -> None:
        from lulu.emulation import PLATFORMS

        expected = PATHS.install_root / "packaging" / "pcsx2-qt-flatpak"
        self.assertEqual(PLATFORMS["ps2"].executable, expected)
        self.assertTrue(expected.is_file())

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
            self.assertIn("Circle = SDL-0/FaceEast", first)
            pad1 = first.split("[Pad2]", 1)[0]
            self.assertNotIn("SDL-1/", pad1)
            self.assertIn("Up = SDL-0/DPadDown", first)
            self.assertIn("L2 = SDL-0/+LeftTrigger", first)
            self.assertIn("ConfirmShutdown = false", first)
            self.assertIn("StartFullscreen = true", first)
            self.assertIn("StartBigPictureMode = false", first)
            self.assertIn("SettingsVersion = 1", first)
            self.assertIn("SetupWizardIncomplete = false", first)
            self.assertIn("[Hotkeys]\nOpenPauseMenu = Keyboard/F12", first)
            self.assertIn("[InputSources]\nKeyboard = true", first)
            ui = first.split("[UI]", 1)[1].split("[", 1)[0]
            self.assertNotIn("OpenPauseMenu", ui)
            self.assertIn("[EmuCore/GS]\nRenderer = -1", first)
            self.assertIn("[Pad2]", first)
            self.assertIn("Cross = SDL-1/FaceSouth", first)

    def test_pcsx2_migrates_open_pause_menu_to_hotkeys_section(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            ini = root / "PCSX2" / "inis" / "PCSX2.ini"
            ini.parent.mkdir(parents=True)
            ini.write_text(
                "[UI]\nOpenPauseMenu = Keyboard/Escape\nTheme = dark\n\n"
                "[Hotkeys]\nToggleFullscreen = Keyboard/Alt & Keyboard/Return\n"
            )
            result = ensure_provider_controller_config("pcsx2", root).read_text()
        ui = result.split("[UI]", 1)[1].split("[", 1)[0]
        hotkeys = result.split("[Hotkeys]", 1)[1].split("[", 1)[0]
        self.assertNotIn("OpenPauseMenu", ui)
        self.assertIn("Theme = dark", ui)
        self.assertIn("OpenPauseMenu = Keyboard/F12", hotkeys)
        self.assertIn("ToggleFullscreen = Keyboard/Alt & Keyboard/Return", hotkeys)

    def test_pcsx2_default_storage_bios_path_is_provisioned_into_native_config(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bios_root = root / "Games" / "BIOS"
            with patch(
                "lulu.controller_provisioning.PATHS",
                SimpleNamespace(bios_root=bios_root),
            ):
                config = ensure_provider_controller_config("pcsx2", root)
            self.assertEqual(config, root / "PCSX2" / "inis" / "PCSX2.ini")
            content = config.read_text()
        self.assertIn(f"Bios = {bios_root / 'ps2'}", content)
        self.assertIn("SetupWizardIncomplete = false", content)

    def test_pcsx2_alternate_storage_target_is_provisioned_without_bios_copy(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            alternate_bios_root = root / "mounted" / "library with spaces" / "Mudos" / "BIOS"
            alternate_bios_dir = alternate_bios_root / "ps2"
            alternate_bios_dir.mkdir(parents=True)
            bios_file = alternate_bios_dir / "bios.bin"
            bios_file.write_bytes(b"fixture")
            with patch(
                "lulu.controller_provisioning.PATHS",
                SimpleNamespace(bios_root=alternate_bios_root),
            ):
                config = ensure_provider_controller_config("pcsx2", root)
            content = config.read_text()
            self.assertIn(f"Bios = {alternate_bios_dir}", content)
            self.assertTrue(bios_file.is_file())
            self.assertEqual(bios_file.read_bytes(), b"fixture")

    def test_pcsx2_flatpak_wrapper_exposes_dynamic_mudos_config_and_bios(self) -> None:
        wrapper = (Path(__file__).parents[1] / "packaging/pcsx2-qt-flatpak").read_text()
        self.assertIn('"--filesystem=$config_home:rw"', wrapper)
        self.assertIn('pcsx2_args+=("-datapath" "$config_home")', wrapper)
        self.assertIn('"--filesystem=$bios_dir:ro"', wrapper)
        self.assertIn('"$@"', wrapper)
        self.assertIn('"${pcsx2_args[@]}"', wrapper)

    def test_dolphin_controller_profile_uses_inputplumber_virtual_name(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = ensure_provider_controller_config("dolphin", Path(directory))
            content = path.read_text()

            self.assertIn("Device = SDL/0/SDL Gamepad", content)
            self.assertIn("Buttons/A = `Button A`", content)
            self.assertIn("Main Stick/Up = `Left Y+`", content)
            self.assertIn("Triggers/L-Analog = `Trigger L`", content)
            self.assertIn("Main Stick/Calibration = 100.00", content)
            self.assertIn("[GCPad2]", content)
            self.assertIn("[GCPad3]", content)
            self.assertIn("[GCPad4]", content)
            self.assertIn("Device = SDL/3/SDL Gamepad", content)

            dolphin = Path(directory) / "Config" / "Dolphin.ini"
            dolphin_content = dolphin.read_text()
            self.assertIn("SIDevice0 = 6", dolphin_content)
            self.assertIn("SIDevice1 = 6", dolphin_content)
            self.assertIn("SIDevice2 = 6", dolphin_content)
            self.assertIn("SIDevice3 = 6", dolphin_content)
            self.assertIn("WiimoteSource0 = 1", dolphin_content)
            self.assertIn("WiimoteContinuousScanning = True", dolphin_content)
            self.assertIn("[Interface]", dolphin_content)
            self.assertIn("ConfirmStop = false", dolphin_content)

            wiimote = Path(directory) / "Config" / "WiimoteNew.ini"
            wiimote_content = wiimote.read_text()
            self.assertIn("[Wiimote1]", wiimote_content)
            self.assertIn("Extension = Classic Controller", wiimote_content)
            self.assertIn("Classic/Buttons/A = `Button A`", wiimote_content)
            hotkeys = path.parent / "Hotkeys.ini"
            self.assertIn("Wii/Press Sync Button = bracketright", hotkeys.read_text())
            graphics = path.parent / "GFX.ini"
            self.assertIn("InternalResolution = 3", graphics.read_text())

    def test_dolphin_three_times_internal_resolution_preserves_other_graphics_settings(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            graphics = root / "Config" / "GFX.ini"
            graphics.parent.mkdir(parents=True)
            graphics.write_text(
                "[Settings]\nInternalResolution = 2\nVSync = True\n\n[Other]\nValue = keep\n",
            )
            ensure_provider_controller_config("dolphin", root, 1, {1: 0})
            updated = graphics.read_text()
            ensure_provider_controller_config("dolphin", root, 1, {1: 0})
            self.assertEqual(updated, graphics.read_text())
        self.assertIn("InternalResolution = 3", updated)
        self.assertIn("VSync = True", updated)
        self.assertIn("[Other]\nValue = keep", updated)

    def test_dolphin_sync_hotkey_update_preserves_unrelated_hotkeys(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config_root = root / "Config"
            config_root.mkdir(parents=True)
            hotkeys = config_root / "Hotkeys.ini"
            hotkeys.write_text(
                "[Hotkeys]\nGeneral/Stop = Escape\nWii/Press Sync Button = Tab\n\n"
                "[Other]\nPreference = keep\n",
            )
            ensure_provider_controller_config("dolphin", root, 1, {1: 0})
            updated = hotkeys.read_text()
            ensure_provider_controller_config("dolphin", root, 1, {1: 0})
            repeated = hotkeys.read_text()
        self.assertEqual(updated, repeated)
        self.assertIn("General/Stop = Escape", updated)
        self.assertIn("Wii/Press Sync Button = bracketright", updated)
        self.assertIn("[Other]\nPreference = keep", updated)

    def test_dolphin_continuous_wiimote_scan_preserves_other_core_options(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            dolphin_ini = root / "Config" / "Dolphin.ini"
            dolphin_ini.parent.mkdir(parents=True)
            dolphin_ini.write_text("[Core]\nCustomPreference = keep\nWiimoteContinuousScanning = False\n")
            ensure_provider_controller_config("dolphin", root, 1, {1: 0})
            updated = dolphin_ini.read_text()
        self.assertIn("WiimoteContinuousScanning = True", updated)
        self.assertIn("CustomPreference = keep", updated)

    def test_dolphin_stop_confirmation_update_preserves_other_preferences(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = root / "Config" / "Dolphin.ini"
            config.parent.mkdir(parents=True)
            config.write_text("[Interface]\nConfirmStop = true\nLanguageCode = en\n\n"
                              "[Core]\nCustomPreference = keep\n")
            ensure_provider_controller_config("dolphin", root)
            changed = config.read_text()
            ensure_provider_controller_config("dolphin", root)
            self.assertEqual(changed, config.read_text())
            self.assertIn("ConfirmStop = false", changed)
            self.assertIn("LanguageCode = en", changed)
            self.assertIn("CustomPreference = keep", changed)

    def test_retroarch_state_parser_survives_apostrophes_for_repeat_launches(self) -> None:
        state = {
            "controller": {"controllers": {}},
            "last_result": {"argv": ["/usr/bin/pcsx2-qt", "Tony Hawk's Underground.iso"]},
        }
        import json

        encoded = json.dumps(state).replace("'", "\\u0027")
        decoded = _parse_busctl_json_string("s " + repr(encoded))
        self.assertEqual(decoded, state)

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
        self.assertIn("Device = SDL/2/SDL Gamepad", dolphin)
        self.assertIn("[GCPad3]", dolphin)
        self.assertIn("Device = SDL/1/SDL Gamepad", dolphin)

    def test_standard_face_layout_is_always_identity(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            pcsx2 = ensure_provider_controller_config(
                "pcsx2", root, 1, {1: 0},
            ).read_text()
            dolphin = ensure_provider_controller_config(
                "dolphin", root, 1, {1: 0},
            ).read_text()
        self.assertIn("Cross = SDL-0/FaceSouth", pcsx2)
        self.assertIn("Circle = SDL-0/FaceEast", pcsx2)
        self.assertIn("Buttons/A = `Button A`", dolphin)
        self.assertIn("Buttons/B = `Button B`", dolphin)

    def test_dolphin_real_remote_mode_selects_passthrough_source(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            standard = ensure_provider_controller_config(
                "dolphin", root, 1, {1: 0}, real_wiimote_passthrough=False,
            )
            dolphin_ini = standard.parent / "Dolphin.ini"
            self.assertIn("WiimoteSource0 = 1", dolphin_ini.read_text())
            passthrough = ensure_provider_controller_config(
                "dolphin", root, 1, {1: 0}, real_wiimote_passthrough=True,
            )
            self.assertIn("WiimoteSource0 = 2", dolphin_ini.read_text())
            self.assertIn("Source = 2", passthrough.with_name("WiimoteNew.ini").read_text())
            self.assertIn("Buttons/A = `Button A`", passthrough.with_name("GCPadNew.ini").read_text())

    def test_passthrough_keeps_native_wiimote_mapping_untouched(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            dolphin_root = root / "Config"
            dolphin_root.mkdir(parents=True)
            native_remote = dolphin_root / "WiimoteNew.ini"
            original = "[Wiimote1]\nDevice = Bluetooth passthrough\nButtons/A = `A`\n"
            native_remote.write_text(original)
            generated = ensure_provider_controller_config(
                "dolphin", root, 2, {1: 0, 2: 2},
                real_wiimote_passthrough=True,
            )
            gc_pads = generated.read_text()
            native_remote_content = native_remote.read_text()
        self.assertIn("Buttons/A = `A`", native_remote_content)
        self.assertIn("Buttons/A = `Button A`", gc_pads)
        self.assertIn("[GCPad2]", gc_pads)
        self.assertIn("Device = SDL/2/SDL Gamepad", gc_pads)

    def test_dolphin_profiles_disambiguate_two_identical_gamepads_by_live_index(self) -> None:
        pads = {
            1: {"sdl_index": 0, "sdl_name": "Xbox 360 Wireless Controller"},
            2: {"sdl_index": 2, "sdl_name": "Xbox 360 Wireless Controller"},
        }
        with tempfile.TemporaryDirectory() as directory:
            generated = ensure_provider_controller_config(
                "dolphin", Path(directory), 2, {1: 0, 2: 2},
                controller_identities=pads,
            )
            content = generated.read_text()
        self.assertIn("[GCPad1]\nDevice = SDL/0/Xbox 360 Wireless Controller", content)
        self.assertIn("[GCPad2]\nDevice = SDL/2/Xbox 360 Wireless Controller", content)

    def test_dolphin_reserves_unique_sdl_slots_for_unconnected_gamecube_ports(self) -> None:
        pads = {1: {"sdl_index": 0, "sdl_name": "Xbox 360 Controller"}}
        with tempfile.TemporaryDirectory() as directory:
            content = ensure_provider_controller_config(
                "dolphin", Path(directory), 1, {1: 0}, controller_identities=pads,
            ).read_text()
        for player, index in enumerate(range(4), 1):
            self.assertIn(f"[GCPad{player}]\nDevice = SDL/{index}/Xbox 360 Controller", content)

    def test_runtime_dolphin_profiles_target_the_active_xdg_native_config_tree(self) -> None:
        from lulu.paths import PATHS
        from lulu.dolphin_passthrough import dolphin_config_path

        root = PATHS.provider_config_root("dolphin")
        self.assertEqual(
            dolphin_config_path(), root / "Config" / "Dolphin.ini",
        )
        with tempfile.TemporaryDirectory() as directory:
            provider_root = Path(directory)
            generated = ensure_provider_controller_config(
                "dolphin", provider_root, 1, {1: 0},
                provider_root / "Config",
            )
            self.assertEqual(
                generated, provider_root / "Config" / "GCPadNew.ini",
            )
            self.assertTrue((provider_root / "Config" / "Hotkeys.ini").is_file())

    def test_retroarch_generated_autoconfig_translates_xbox_to_retropad_face_buttons(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            enabled = ensure_retroarch_autoconfig(root)
            enabled_content = next(enabled.glob("*.cfg")).read_text()
            ensure_retroarch_autoconfig(root)
            disabled_content = next(enabled.glob("*.cfg")).read_text()
        self.assertIn('input_device = "Microsoft X-Box 360 pad"', enabled_content)
        self.assertIn('input_a_btn = "1"', enabled_content)
        self.assertIn('input_b_btn = "0"', enabled_content)
        self.assertIn('input_x_btn = "3"', enabled_content)
        self.assertIn('input_y_btn = "2"', enabled_content)
        self.assertIn('input_l2_axis = "+2"', enabled_content)
        self.assertEqual(enabled_content, disabled_content)

    def test_retroarch_two_identical_pads_use_distinct_indices_and_shared_layout(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            autoconfig = ensure_retroarch_autoconfig(root)
            child_path = Path(_retroarch_child_config({1: 0, 2: 2}, autoconfig))
            try:
                child = child_path.read_text()
                profile = next(autoconfig.glob("*.cfg")).read_text()
            finally:
                child_path.unlink(missing_ok=True)
        self.assertIn('input_player1_joypad_index = "0"', child)
        self.assertIn('input_player2_joypad_index = "2"', child)
        self.assertIn('input_a_btn = "1"', profile)
        self.assertIn('input_b_btn = "0"', profile)

    def test_retroarch_profile_is_generic_to_normalized_pads_and_players(self) -> None:
        fixtures = (
            {"name": "Xbox-style Generic Pad", "guid": "fixture-xbox", "index": 0},
            {"name": "Second Identical Pad", "guid": "fixture-xbox", "index": 1},
            {"name": "Generic Non-Xbox SDL Pad", "guid": "fixture-generic", "index": 2},
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            autoconfig = ensure_retroarch_autoconfig(root)
            profile = next(autoconfig.glob("*.cfg")).read_text()
            child_path = Path(_retroarch_child_config(
                {player + 1: fixture["index"] for player, fixture in enumerate(fixtures)},
                autoconfig,
            ))
            try:
                child = child_path.read_text()
            finally:
                child_path.unlink(missing_ok=True)
        self.assertNotIn("input_device_guid", profile)
        self.assertIn('input_device = "Microsoft X-Box 360 pad"', profile)
        self.assertIn(f'joypad_autoconfig_dir = "{autoconfig}"', child)
        self.assertIn('input_player1_joypad_index = "0"', child)
        self.assertIn('input_player2_joypad_index = "1"', child)
        self.assertIn('input_player3_joypad_index = "2"', child)


if __name__ == "__main__":
    unittest.main()
