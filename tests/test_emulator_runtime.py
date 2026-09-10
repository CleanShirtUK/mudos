import tempfile
import unittest
from pathlib import Path

from lulu.emulator_runtime import EmulatorRuntimeAdapter
from lulu.local_content import LocalContentGame


class EmulatorRuntimeTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
