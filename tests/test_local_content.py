import tempfile
import unittest
from pathlib import Path

from lulu.local_content import LocalContentProvider


class LocalContentTests(unittest.TestCase):
    def test_explicit_root_groups_cue_and_reports_missing_runtime(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "ps2").mkdir()
            (root / "ps2" / "Crazy Taxi (USA).bin").write_bytes(b"disc")
            (root / "ps2" / "Crazy Taxi (USA).cue").write_text('FILE "Crazy Taxi (USA).bin" BINARY\n')

            games = LocalContentProvider().list_installed(root)

        self.assertEqual(len(games), 1)
        self.assertEqual(games[0].install_state, "installed")
        self.assertFalse(games[0].launchable)
        self.assertEqual(games[0].reason, "runtime-missing")

    def test_invalid_cue_is_visible_but_not_launchable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "ps2").mkdir()
            cue = root / "ps2" / "Broken.cue"
            cue.write_text("FILE missing.bin BINARY\n")

            games = LocalContentProvider({"ps2": Path("/runtime/pcsx2")}).list_installed(root)

        self.assertEqual(games[0].install_state, "invalid")
        self.assertFalse(games[0].launchable)
        self.assertEqual(games[0].reason, "malformed-cue")

    def test_stable_ids_do_not_depend_on_file_enumeration_order(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "nes").mkdir()
            (root / "nes" / "Zelda.nes").write_bytes(b"z")
            (root / "nes" / "Mario.nes").write_bytes(b"m")
            first = {game.title: game.content_id for game in LocalContentProvider().list_installed(root)}
            second = {game.title: game.content_id for game in LocalContentProvider().list_installed(root)}

        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
