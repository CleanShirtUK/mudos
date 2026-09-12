import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from lulu.paths import MudosPaths


class MudosPathsTests(unittest.TestCase):
    def test_defaults_preserve_current_appliance_locations(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            paths = MudosPaths.from_environment()

        data = Path("/var/lib/lulu")
        self.assertEqual(paths.roms, data / "roms")
        self.assertEqual(paths.bios, data / "bios")
        self.assertEqual(paths.artwork, data / ".cache/lulu/steamgriddb")
        self.assertEqual(paths.catalogue_db, data / ".local/share/lulu/catalogue.sqlite3")
        self.assertEqual(paths.metadata_cache, data / ".cache/lulu/steamgriddb/metadata")
        self.assertEqual(paths.steam, data / ".local/share/Steam")

    def test_custom_data_root_derives_supported_paths(self) -> None:
        with patch.dict(os.environ, {"LULU_DATA_ROOT": "/tmp/mudos-data"}, clear=True):
            paths = MudosPaths.from_environment()

        data = Path("/tmp/mudos-data")
        self.assertEqual(paths.roms, data / "roms")
        self.assertEqual(paths.artwork, data / ".cache/lulu/steamgriddb")
        self.assertEqual(paths.catalogue_db, data / ".local/share/lulu/catalogue.sqlite3")
        self.assertEqual(paths.metadata_cache, data / ".cache/lulu/steamgriddb/metadata")
        self.assertEqual(paths.steam, data / ".local/share/Steam")

    def test_artwork_follows_an_explicit_assets_root(self) -> None:
        with patch.dict(os.environ, {"LULU_ASSETS_ROOT": "/tmp/mudos-assets"}, clear=True):
            paths = MudosPaths.from_environment()
            self.assertEqual(paths.assets, Path("/tmp/mudos-assets"))
            self.assertEqual(paths.artwork, Path("/var/lib/lulu/.cache/lulu/steamgriddb"))

    def test_legacy_path_overrides_remain_independent(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch.dict(os.environ, {
                "LULU_DATA_ROOT": str(root / "data"),
                "LULU_ROM_ROOT": str(root / "roms"),
                "LULU_CATALOGUE_DB": str(root / "catalogue.sqlite3"),
            }, clear=True):
                paths = MudosPaths.from_environment()
                self.assertEqual(paths.roms, root / "roms")
                self.assertEqual(paths.catalogue_db, root / "catalogue.sqlite3")
                self.assertEqual(paths.bios, root / "data" / "bios")


if __name__ == "__main__":
    unittest.main()
