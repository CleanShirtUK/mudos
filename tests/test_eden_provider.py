from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from lulu.emulation import PLATFORMS
from lulu.emulator_runtime import EmulatorRuntimeAdapter
from lulu.paths import PATHS
from lulu.switch_provider import (
    SwitchProvider,
    eden_flatpak_config_root,
    eden_flatpak_data_root,
)


class EdenManagedProvisioningTests(unittest.TestCase):
    def test_game_runtime_uses_release_wrapper_and_actual_flatpak_roots(self) -> None:
        wrapper = PATHS.install_root / "packaging" / "eden-flatpak"
        self.assertEqual(PLATFORMS["switch"].executable, wrapper)
        with tempfile.TemporaryDirectory() as directory:
            runtime = EmulatorRuntimeAdapter({"switch": wrapper}, config_root=Path(directory) / "providers")
            self.assertEqual(runtime.switch_provider.config_root, Path(directory) / "providers/eden/config")
            self.assertEqual(runtime.switch_provider.active_config_root, eden_flatpak_config_root())
            self.assertEqual(runtime.switch_provider.data_root, eden_flatpak_data_root())

    def test_production_defaults_target_system_flatpak_config_and_data_roots(self) -> None:
        home = Path("/fixture/home")
        self.assertEqual(
            eden_flatpak_config_root(home),
            home / ".var/app/dev.eden_emu.eden/config/eden",
        )
        self.assertEqual(
            eden_flatpak_data_root(home),
            home / ".var/app/dev.eden_emu.eden/data/eden",
        )
        wrapper = (Path(__file__).parents[1] / "packaging/eden-flatpak").read_text()
        self.assertIn('"--filesystem=$MUDOS_EDEN_KEYS_DIR:ro"', wrapper)
        self.assertNotIn('"--filesystem=$MUDOS_EDEN_FIRMWARE_DIR:ro"', wrapper)
        self.assertIn('"--filesystem=$MUDOS_EDEN_GAME_DIR:ro"', wrapper)
        self.assertIn('"--nosocket=wayland"', wrapper)
        self.assertIn('"--env=QT_QPA_PLATFORM=xcb"', wrapper)

    def test_eden_config_is_the_consumed_flatpak_file_and_preserves_unowned_settings(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            provider_config = root / "provider-config"
            active_config = root / "flatpak/config/eden"
            active_config.mkdir(parents=True)
            qt_config = active_config / "qt-config.ini"
            qt_config.write_text(
                "[UI]\nfirstStart=true\nfullscreen=false\ntheme=keep-me\n"
                "[Renderer]\nbackend=1\n"
                "[Controls]\nplayer_0_button_a=old-keyboard-binding\n\n"
            )
            provider = SwitchProvider(
                root / "eden", provider_config, active_config,
            )
            with patch.dict("os.environ", {"LULU_SWITCH_SDL_GUID": "030081b85e0400008e02000001000000"}):
                first = provider.ensure_controller_config(1, {1: 0})
                content = qt_config.read_text()
                second = provider.ensure_controller_config(1, {1: 0})
                second_content = second.read_text()
                source_exists = (provider_config / "lulu-switch.ini").is_file()

        self.assertEqual(first, qt_config)
        self.assertEqual(second_content, content)
        self.assertIn("firstStart=false", content)
        self.assertIn("fullscreen=false", content)
        self.assertIn("theme=keep-me", content)
        self.assertIn("[Renderer]\nbackend=1", content)
        self.assertIn('player_0_button_a\\default=false', content)
        self.assertIn('player_0_button_a="engine:sdl,port:0,guid:030000005e0400008e02000001000000,button:0"', content)
        for name, button in (("b", 1), ("x", 2), ("y", 3)):
            self.assertIn(
                f'player_0_button_{name}="engine:sdl,port:0,guid:030000005e0400008e02000001000000,button:{button}"',
                content,
            )
        self.assertNotIn("old-keyboard-binding", content)
        self.assertTrue(source_exists)

    def test_keys_projected_and_firmware_installed_to_writable_nand(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bios_root = root / "Mudos" / "BIOS"
            keys = bios_root / "switch/keys"
            firmware = bios_root / "switch/firmware"
            keys.mkdir(parents=True)
            firmware.mkdir(parents=True)
            prod = keys / "prod.keys"
            title = keys / "title.keys"
            nca = firmware / "0123456789abcdef.nca"
            prod.write_bytes(b"user-provided prod key")
            title.write_bytes(b"user-provided title key")
            nca.write_bytes(b"firmware material")
            data_root = root / "flatpak/data/eden"
            nand = data_root / "nand"
            active_config = root / "flatpak/config/eden"
            active_config.mkdir(parents=True)
            (active_config / "qt-config.ini").write_text(
                "[Data%20Storage]\nnand_directory=" + str(nand) + "\n"
            )
            provider = SwitchProvider(
                root / "eden", root / "provider-config", active_config, data_root,
            )
            with patch("lulu.switch_provider.PATHS", type("Paths", (), {"bios_root": bios_root})()):
                projected = provider.ensure_managed_system_files()
                again = provider.ensure_managed_system_files()

            key_link = data_root / "keys/prod.keys"
            firmware_link = nand / "system/Contents/registered/0123456789abcdef.nca"
            self.assertTrue(key_link.is_symlink())
            self.assertEqual(key_link.resolve(), prod)
            self.assertTrue((data_root / "keys/title.keys").is_symlink())
            self.assertTrue(firmware_link.is_file())
            self.assertFalse(firmware_link.is_symlink())
            self.assertEqual(firmware_link.read_bytes(), nca.read_bytes())
            self.assertEqual(prod.read_bytes(), b"user-provided prod key")
            self.assertEqual(nca.read_bytes(), b"firmware material")
            self.assertEqual(projected, again)

    def test_legacy_firmware_links_migrate_without_touching_canonical_source(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bios = root / "bios"
            keys = bios / "switch/keys"
            firmware = bios / "switch/firmware"
            keys.mkdir(parents=True)
            firmware.mkdir(parents=True)
            (keys / "prod.keys").write_text("key")
            source = firmware / "abc.nca"
            source.write_bytes(b"firmware")
            data = root / "data"
            target = data / "nand/system/Contents/registered/abc.nca"
            target.parent.mkdir(parents=True)
            target.symlink_to(source)
            config = root / "config"
            config.mkdir()
            (config / ".mudos-eden-file-projection.json").write_text(
                __import__("json").dumps({"firmware/abc.nca": str(source.resolve())})
            )
            provider = SwitchProvider(config_root=config, active_config_root=root / "active", data_root=data)
            with patch("lulu.switch_provider.PATHS", type("Paths", (), {"bios_root": bios})()):
                provider.ensure_managed_system_files()
                provider.ensure_managed_system_files()
            self.assertFalse(target.is_symlink())
            self.assertEqual(target.read_bytes(), source.read_bytes())

    def test_unowned_firmware_entry_is_not_replaced(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bios = root / "bios"
            (bios / "switch/keys").mkdir(parents=True)
            (bios / "switch/firmware").mkdir(parents=True)
            (bios / "switch/keys/prod.keys").write_text("key")
            (bios / "switch/firmware/abc.nca").write_bytes(b"canonical")
            data = root / "data"
            target = data / "nand/system/Contents/registered/abc.nca"
            target.parent.mkdir(parents=True)
            target.write_bytes(b"unowned")
            provider = SwitchProvider(config_root=root / "config", active_config_root=root / "active", data_root=data)
            with patch("lulu.switch_provider.PATHS", type("Paths", (), {"bios_root": bios})()):
                with self.assertRaises(FileExistsError):
                    provider.ensure_managed_system_files()
            self.assertEqual(target.read_bytes(), b"unowned")

    def test_changed_firmware_updates_only_managed_nand_without_repeating_unchanged_install(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bios = root / "bios"
            (bios / "switch/keys").mkdir(parents=True)
            firmware = bios / "switch/firmware"
            firmware.mkdir(parents=True)
            (bios / "switch/keys/prod.keys").write_text("key")
            source = firmware / "abc.nca"
            source.write_bytes(b"version-one")
            provider = SwitchProvider(config_root=root / "config", active_config_root=root / "active",
                                      data_root=root / "data")
            target = root / "data/nand/system/Contents/registered/abc.nca"
            with patch("lulu.switch_provider.PATHS", type("Paths", (), {"bios_root": bios})()):
                provider.ensure_managed_system_files()
                original_inode = target.stat().st_ino
                provider.ensure_managed_system_files()
                self.assertEqual(target.stat().st_ino, original_inode)
                source.write_bytes(b"version-two")
                provider.ensure_managed_system_files()
            self.assertEqual(target.read_bytes(), b"version-two")
            self.assertEqual(source.read_bytes(), b"version-two")
            self.assertNotEqual(target.stat().st_ino, original_inode)

    def test_storage_target_change_repoints_only_eden_projection_links(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            data_root = root / "flatpak/data/eden"
            provider = SwitchProvider(root / "eden", root / "provider-config",
                                      root / "flatpak/config/eden", data_root)
            first_bios = root / "disk-a/Mudos/BIOS"
            second_bios = root / "disk-b/Mudos/BIOS"
            for bios, payload in ((first_bios, b"a"), (second_bios, b"b")):
                (bios / "switch/keys").mkdir(parents=True)
                (bios / "switch/keys/prod.keys").write_bytes(payload)
                (bios / "switch/firmware").mkdir()
                (bios / "switch/firmware/abc.nca").write_bytes(b"firmware")
            with patch("lulu.switch_provider.PATHS", type("Paths", (), {"bios_root": first_bios})()):
                provider.ensure_managed_system_files()
            key_link = data_root / "keys/prod.keys"
            self.assertEqual(key_link.resolve(), first_bios / "switch/keys/prod.keys")
            with patch("lulu.switch_provider.PATHS", type("Paths", (), {"bios_root": second_bios})()):
                provider.ensure_managed_system_files()
            self.assertEqual(key_link.resolve(), second_bios / "switch/keys/prod.keys")
            self.assertEqual((second_bios / "switch/keys/prod.keys").read_bytes(), b"b")

    def test_missing_required_mudos_key_fails_with_authoritative_path(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bios_root = root / "Mudos/BIOS"
            (bios_root / "switch/keys").mkdir(parents=True)
            provider = SwitchProvider(root / "eden", root / "provider-config",
                                      root / "config/eden", root / "data/eden")
            with patch("lulu.switch_provider.PATHS", type("Paths", (), {"bios_root": bios_root})()):
                with self.assertRaisesRegex(FileNotFoundError, str(bios_root / "switch/keys/prod.keys")):
                    provider.ensure_managed_system_files()


if __name__ == "__main__":
    unittest.main()
