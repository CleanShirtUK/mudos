import tempfile
import unittest
from pathlib import Path

from lulu.providers import load_base_guide, load_mudos_guide, load_providers


class ProviderLaunchContractTests(unittest.TestCase):
    def test_base_guide_is_ordered_and_provider_quit_is_declared(self) -> None:
        actions = load_base_guide()
        self.assertEqual([action.label for action in actions], [
            "Switch Input Mode", "Restart Mudos", "Reboot System", "Shutdown System",
        ])
        self.assertEqual([action.label for action in load_mudos_guide()], ["Open Downloads"])
        providers = load_providers()
        for provider_id in ("retroarch", "steam", "dolphin", "pcsx2", "eden"):
            self.assertEqual(sum(action.role == "quit" for action in providers[provider_id].guide_actions), 1)

    def test_provider_context_filtering_and_standalone_actions(self) -> None:
        providers = load_providers()
        game_actions = providers.guide_actions("steam", "game")
        self.assertEqual([action.action_id for action in game_actions],
                         ["steam-overlay", "steam-quit"])
        self.assertEqual(game_actions[0].target, "key:Shift+Tab")
        self.assertEqual([a.action_id for a in providers.guide_actions("steam", "store")],
                         ["steam-quit"])
        self.assertEqual([a.action_id for a in providers.guide_actions("steam", "standalone")],
                         ["steam-quit"])
        self.assertEqual(providers.guide_actions("romm", "game"), ())

    def test_pcsx2_quit_targets_sessiond_owned_process(self) -> None:
        providers = load_providers()
        for context in ("game", "standalone"):
            actions = providers.guide_actions("pcsx2", context)
            menu_action, = (action for action in actions if action.action_id == "pcsx2-menu")
            quit_action, = (action for action in actions if action.role == "quit")
            self.assertEqual(menu_action.target, "key:F12")
            self.assertEqual(quit_action.action_id, "pcsx2-quit")
            self.assertEqual(quit_action.target, "process-group-terminate")

    def test_dolphin_wiimote_sync_is_guide_only_and_provider_scoped(self) -> None:
        providers = load_providers()
        for context in ("game", "standalone"):
            action, = tuple(
                item for item in providers.guide_actions("dolphin", context)
                if item.action_id == "dolphin-wiimote-sync"
            )
            self.assertEqual(action.target, "key:bracketright")
        self.assertNotIn(
            "dolphin-wiimote-sync",
            [item.action_id for item in providers.guide_actions("retroarch", "game")],
        )
        source = (Path(__file__).parents[1] / "native/mudos-guide.cpp").read_text()
        key_handler = source.split("bool sendKey(", 1)[1].split("bool runCommand(", 1)[0]
        self.assertIn('key == QStringLiteral("bracketright")', key_handler)
        self.assertIn("XK_bracketright", key_handler)

    def test_guide_keys_are_allowlisted_and_steam_overlay_releases_modifier(self) -> None:
        source = (Path(__file__).parents[1] / "native/mudos-guide.cpp").read_text()
        key_handler = source.split("bool sendKey(", 1)[1].split("bool runCommand(", 1)[0]
        self.assertIn('key == QStringLiteral("Shift+Tab")', key_handler)
        self.assertIn('key == QStringLiteral("bracketright")', key_handler)
        self.assertIn('key == QStringLiteral("F12")', key_handler)
        self.assertIn('steamOverlay ? XK_Tab : dolphinSync ? XK_bracketright : XK_F12', key_handler)
        self.assertIn('connection, XCB_INPUT_FOCUS_NONE, targetXid_, XCB_CURRENT_TIME', key_handler)
        self.assertIn('xcb_key_symbols_get_keycode(keySymbols, keySymbol)', key_handler)
        self.assertIn('sendFakeInput(XCB_KEY_PRESS, keycodes[0])', key_handler)
        self.assertIn('sendFakeInput(XCB_KEY_RELEASE, keycodes[0])', key_handler)
        self.assertIn('xcb_flush(connection);', key_handler)
        self.assertIn('xcb_key_symbols_get_keycode(keySymbols, XK_Shift_L)', key_handler)
        self.assertIn('if (steamOverlay)\n            sendFakeInput(XCB_KEY_PRESS, shiftCodes[0])', key_handler)
        self.assertIn("xcb_flush(connection);\n        if (dolphinSync)\n            usleep(100 * 1000);", key_handler)
        self.assertIn('sendFakeInput(XCB_KEY_RELEASE, shiftCodes[0])', key_handler)
        self.assertIn("xcb_request_check(connection, cookie)", key_handler)
        self.assertIn('"input_focus="', key_handler)
        self.assertNotIn("sendUInputKey", source)
        self.assertNotIn('"/dev/uinput"', source)
        self.assertNotIn('"Guide uinput key complete"', source)
        self.assertIn('targetXid_', key_handler)
        action_handler = source.split("bool executeAction(", 1)[1].split("bool setProperty(", 1)[0]
        self.assertIn('id == QStringLiteral("pcsx2-menu") && key == QStringLiteral("F12")',
                      action_handler)
        self.assertIn("window_->hide();\n                QTimer::singleShot(100", action_handler)
        self.assertIn("const bool sent = sendKey(key);", action_handler)

    def test_dolphin_and_eden_can_reveal_ui_without_quitting_or_toggling_fullscreen(self) -> None:
        providers = load_providers()
        for provider_id in ("dolphin", "eden"):
            for context in ("game", "standalone"):
                actions = providers.guide_actions(provider_id, context)
                self.assertEqual(actions[0].action_id, f"{provider_id}-show-ui")
                self.assertEqual(actions[0].target, "window-unfullscreen")
                self.assertFalse(actions[0].confirm)
                self.assertEqual(actions[-1].role, "quit")
        source = (Path(__file__).parents[1] / "native/mudos-guide.cpp").read_text()
        reveal = source.split("bool removeFullscreen()", 1)[1].split("bool sendKey(", 1)[0]
        self.assertIn('target == "window-unfullscreen"', source)
        self.assertIn('"_NET_WM_STATE_FULLSCREEN"', reveal)
        self.assertIn("message.data.data32[0] = 0", reveal)
        self.assertIn("message.window = targetXid_", reveal)
        self.assertNotIn("kill(", reveal)

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
                    '[config]\nstrategy = "direct"\n' + launch +
                    '\n[[guide.actions]]\nid = "quit"\nlabel = "Quit"\nrole = "quit"\ntarget = "window-delete"\n'
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
                '[[guide.actions]]\nid = "quit"\nlabel = "Quit"\nrole = "quit"\ntarget = "window-delete"\n'
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
