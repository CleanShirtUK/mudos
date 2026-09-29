import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from lulu import questarr_paths
from lulu.paths import MudosPaths
from lulu.questarr_paths import (QUESTARR_AUTO_IMPORT_SOURCE_SUPPORTED,
                                 questarr_completed_download_path, questarr_library_mounts,
                                 questarr_post_processing_readiness)


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

    def test_questarr_platform_projection_follows_alternate_configured_storage(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config_home = root / "config"
            config_root = config_home / "lulu"
            config_root.mkdir(parents=True)
            (config_root / "storage-targets.json").write_text(
                '{"emulation_path":"/mnt/games-volume"}', encoding="utf-8"
            )
            paths = MudosPaths(root, config_home, root / "data", root / "cache", root / "runtime")

            wii = next(mount for mount in questarr_library_mounts(paths)
                       if mount.platform_id == "wii")

        self.assertEqual(wii.host_path, Path("/mnt/games-volume/Mudos/ROMs/wii"))
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

    def test_questarr_post_processing_stays_degraded_until_patched_runtime_is_verified(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = MudosPaths(root, root / "config", root / "data", root / "cache", root / "runtime")
            storage = paths.config_root / "storage-targets.json"
            storage.parent.mkdir(parents=True)
            storage.write_text('{"emulation_path":"' + str(root / "external") + '"}')
            (root / "external/Mudos/ROMs/wii").mkdir(parents=True)
            paths.usenet_complete_root.mkdir(parents=True)

            ready, reason = questarr_post_processing_readiness(paths)

        self.assertFalse(ready)
        self.assertTrue(QUESTARR_AUTO_IMPORT_SOURCE_SUPPORTED)
        self.assertIn("runtime path verification", reason)

    def test_questarr_post_processing_requires_matching_verified_runtime_image(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = MudosPaths(root, root / "config", root / "data", root / "cache", root / "runtime")
            storage = paths.config_root / "storage-targets.json"
            storage.parent.mkdir(parents=True)
            storage.write_text('{"emulation_path":"' + str(root / "external") + '"}')
            (root / "external/Mudos/ROMs/wii").mkdir(parents=True)
            paths.usenet_complete_root.mkdir(parents=True)
            ref = root / "image-ref"
            attestation = root / "running-image"
            ref.write_text("localhost/mudos-questarr@sha256:" + "a" * 64)
            attestation.write_text("sha256:" + "a" * 64)

            with patch.object(questarr_paths, "QUESTARR_AUTO_IMPORT_SOURCE_SUPPORTED", True), \
                    patch.object(questarr_paths, "QUESTARR_IMAGE_REF_PATH", ref), \
                    patch.object(questarr_paths, "QUESTARR_RUNTIME_IMAGE_ATTESTATION", attestation):
                ready, reason = questarr_post_processing_readiness(paths)
                attestation.write_text("sha256:" + "b" * 64)
                mismatched, mismatch_reason = questarr_post_processing_readiness(paths)

        self.assertTrue(ready, reason)
        self.assertFalse(mismatched)
        self.assertIn("does not match", mismatch_reason)


if __name__ == "__main__":
    unittest.main()
