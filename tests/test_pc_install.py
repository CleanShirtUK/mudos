import tempfile
from pathlib import Path
import unittest

from lulu.pc_install import (
    PcInstallSource, PcSourceFile, PcSourceType, RecipeFileRequirement, canonical_lutris_root,
    inspect_pc_source, match_required_files, recipe_requirements,
)
from lulu.pc_install_store import PcInstallSourceStore


class PcInstallTests(unittest.TestCase):
    def test_inspection_classifies_sources_without_executing_them(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            exe = root / "setup.exe"
            exe.write_bytes(b"not executed")
            source = inspect_pc_source(exe, canonical_game_id="pc:test", title="Test", provenance="manual")
            self.assertEqual(source.source_type, PcSourceType.WINDOWS_INSTALLER)
            self.assertTrue(source.ready_to_install)
            self.assertEqual(exe.read_bytes(), b"not executed")

            iso = root / "disc.iso"
            iso.write_bytes(b"iso")
            self.assertEqual(inspect_pc_source(iso, canonical_game_id="pc:test", title="Test").source_type,
                             PcSourceType.DISC_IMAGE)

    def test_directory_and_unknown_payload_are_safe(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "game"
            root.mkdir()
            (root / "game.exe").write_bytes(b"exe")
            source = inspect_pc_source(root, canonical_game_id="pc:test", title="Test")
            self.assertEqual(source.source_type, PcSourceType.DIRECTORY)
            self.assertTrue(source.ready_to_install)

            unknown = root.parent / "payload.dat"
            unknown.write_bytes(b"data")
            self.assertFalse(inspect_pc_source(unknown, canonical_game_id="pc:test", title="Test").ready_to_install)

    def test_local_recipe_file_mapping_is_deterministic(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "setup.exe").write_bytes(b"exe")
            source = inspect_pc_source(root / "setup.exe", canonical_game_id="pc:test", title="Test")
            mapping = match_required_files(source, (RecipeFileRequirement("installer", "setup.exe", "N/A"),))
            self.assertEqual(mapping["installer"], str(root / "setup.exe"))

    def test_ambiguous_local_file_requires_choice(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "one").mkdir(); (root / "two").mkdir()
            (root / "one/setup.exe").write_bytes(b"1")
            (root / "two/setup.exe").write_bytes(b"2")
            source = inspect_pc_source(root, canonical_game_id="pc:test", title="Test")
            with self.assertRaisesRegex(ValueError, "ambiguous"):
                match_required_files(source, (RecipeFileRequirement("installer", "setup.exe", "N/A"),))

    def test_recipe_requirements_keep_file_identity_and_optional_status(self):
        requirements = recipe_requirements({"script": {"files": [
            {"rom": {"filename": "Sonic.bin", "url": "N/A: select ROM"}},
            {"optional_patch": {"filename": "patch.zip", "url": "https://example.invalid/patch.zip",
                                "optional": True}},
        ]}})
        self.assertEqual([(item.file_id, item.filename, item.required) for item in requirements], [
            ("rom", "Sonic.bin", True), ("optional_patch", "patch.zip", False),
        ])
        with tempfile.TemporaryDirectory() as directory:
            rom = Path(directory) / "Sonic.bin"
            rom.write_bytes(b"rom")
            source = inspect_pc_source(rom, canonical_game_id="pc:sonic", title="Sonic")
            self.assertEqual(match_required_files(source, requirements), {"rom": str(rom)})

    def test_lutris_string_n_a_file_entries_are_exposed_and_mapped_by_id(self):
        requirements = recipe_requirements({"script": {"files": [
            {"bin": "N/A:Please select the .bin file from Steam"},
        ]}})
        self.assertEqual(len(requirements), 1)
        self.assertEqual(requirements[0].file_id, "bin")
        self.assertEqual(requirements[0].filename, "bin")
        self.assertTrue(requirements[0].local)
        self.assertEqual(requirements[0].label, "Please select the .bin file from Steam")

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "user-provided.bin"
            path.write_bytes(b"user-provided content")
            # CreateLutrisInstallSource binds a specifically selected path to
            # the recipe's file ID; the remote interpreter consumes that ID.
            source = PcInstallSource(
                canonical_game_id="lutris:sonic-3-air", title="Sonic 3 A.I.R",
                provenance="lutris-recipe", source_type=PcSourceType.UNKNOWN,
                completed_path=directory,
                files=(PcSourceFile(str(path), "bin", path.stat().st_size, "file"),),
                ready_to_install=True,
            )
            self.assertEqual(match_required_files(source, requirements), {"bin": str(path)})

    def test_lutris_root_is_canonical_and_slug_safe(self):
        root = canonical_lutris_root("My Game!")
        self.assertEqual(root.parts[-3:], ("Executables", "lutris", "My-Game"))

    def test_legacy_acquired_source_record_migrates_to_generic_identity(self):
        source = PcInstallSourceStore.from_dict({
            "canonical_game_id": "pc:test", "title": "Test", "provenance": "questarr",
            "source_type": "directory", "completed_path": "/games/test",
            "questarr_game_id": "game-1", "questarr_download_id": "download-1",
            "ready_to_install": True,
        })
        self.assertEqual(source.provenance, "acquisition")
        self.assertEqual(source.acquisition_id, "download-1")
        self.assertEqual(source.source_id, "acquisition:download-1")
        self.assertTrue(source.ready_to_install)


if __name__ == "__main__":
    unittest.main()
