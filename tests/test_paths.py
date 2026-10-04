import os
import tempfile
import unittest
from pathlib import Path

from lulu.paths import MudosPaths


class MudosPathsTests(unittest.TestCase):
    def test_canonical_home_layout(self) -> None:
        paths = MudosPaths.current()
        self.assertEqual(paths.home, Path.home())
        self.assertEqual(paths.config_root, paths.config_home / "lulu")
        self.assertEqual(paths.data_root, paths.data_home / "lulu")
        self.assertEqual(paths.rom_root, paths.home / "Games/ROMs")
        self.assertEqual(paths.bios_root, paths.home / "Games/BIOS")
        self.assertEqual(paths.runtime_root, Path(os.environ.get("LULU_RUNTIME_ROOT", "/run/lulu")))

if __name__ == "__main__":
    unittest.main()
