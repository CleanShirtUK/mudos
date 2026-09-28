import os
import tempfile
import unittest
from pathlib import Path

from lulu.paths import MudosPaths
from lulu.questarr_paths import questarr_completed_download_path, questarr_library_mounts


class MudosPathsTests(unittest.TestCase):
    def test_canonical_home_layout(self) -> None:
        paths = MudosPaths.current()
        self.assertEqual(paths.home, Path.home())
        self.assertEqual(paths.config_root, paths.config_home / "lulu")
        self.assertEqual(paths.data_root, paths.data_home / "lulu")
        self.assertEqual(paths.rom_root, paths.home / "Games/ROMs")
        self.assertEqual(paths.bios_root, paths.home / "Games/BIOS")
        self.assertEqual(paths.runtime_root, Path(os.environ.get("LULU_RUNTIME_ROOT", "/run/lulu")))

    def test_questarr_platform_projection_uses_normalized_mudos_platform_roots(self) -> None:
        mounts = questarr_library_mounts()
        wii = next(mount for mount in mounts if mount.platform_id == "wii")
        self.assertEqual(wii.host_path, MudosPaths.current().rom_root / "wii")
        self.assertEqual(wii.container_path, Path("/data/Wii"))

    def test_questarr_completed_source_is_mapped_only_from_real_completed_output(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = MudosPaths(root, root / "config", root / "data", root / "cache", root / "runtime")
            completed = paths.usenet_complete_root / "one-job"
            completed.mkdir(parents=True)
            self.assertEqual(
                questarr_completed_download_path(completed, paths=paths),
                "/home/lulu/Games/.acquisition/usenet/complete/one-job",
            )
            self.assertIsNone(questarr_completed_download_path(paths.usenet_incomplete_root, paths=paths))
            outside = root / "outside"
            outside.mkdir()
            self.assertIsNone(questarr_completed_download_path(outside, paths=paths))


if __name__ == "__main__":
    unittest.main()
