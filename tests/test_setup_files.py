from io import BytesIO
from pathlib import Path
import tempfile
import unittest
import zipfile
from unittest.mock import patch

from lulu.setup_files import (
    UploadedPart,
    _extract_firmware_zip,
    read_multipart,
    save_platform_files,
)
from lulu.platforms import load_platforms


class SetupFileTests(unittest.TestCase):
    def test_platform_registry_declares_ps2_bios_and_switch_key_uploads(self) -> None:
        platforms = load_platforms(Path(__file__).parents[1] / "config/platforms")
        ps2 = platforms["ps2"].setup_files[0]
        switch = platforms["switch"].setup_files
        self.assertEqual((ps2.requirement_id, ps2.destination, ps2.required),
                         ("bios", "ps2", True))
        self.assertEqual(switch[0].required_names, ("prod.keys",))
        self.assertTrue(switch[1].archive)

    def test_multipart_reader_streams_fields_and_binary_upload(self) -> None:
        boundary = "fixture-boundary"
        body = (
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"csrf\"\r\n\r\ntoken\r\n"
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"prod.keys\"\r\n"
            "Content-Type: application/octet-stream\r\n\r\n"
        ).encode() + b"\x00key-data\xff\r\n" + f"--{boundary}--\r\n".encode()
        fields, uploads = read_multipart(
            BytesIO(body), f"multipart/form-data; boundary={boundary}", len(body))
        try:
            self.assertEqual(fields["csrf"], "token")
            self.assertEqual(uploads[0].filename, "prod.keys")
            self.assertEqual(uploads[0].path.read_bytes(), b"\x00key-data\xff")
        finally:
            for upload in uploads:
                upload.path.unlink(missing_ok=True)

    def test_registry_driven_switch_keys_save_under_bios_folder(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            upload_path = root / "incoming"
            upload_path.write_bytes(b"test key")
            upload = UploadedPart("file", "prod.keys", upload_path)
            platforms = Path(__file__).parents[1] / "config/platforms"
            paths = type("Paths", (), {"bios_root": root / "BIOS", "platforms_root": platforms})()
            with patch("lulu.setup_files.PATHS", paths), \
                    patch("lulu.platforms.registry.PATHS", paths):
                saved = save_platform_files("switch", "keys", [upload])
            self.assertEqual(saved, ["prod.keys"])
            self.assertEqual((root / "BIOS/switch/keys/prod.keys").read_bytes(), b"test key")
            self.assertFalse(upload_path.exists())

    def test_setup_manifest_detects_required_files_in_nested_upload_directories(self) -> None:
        from lulu.setup_files import file_setup_manifest
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "switch/keys/nested").mkdir(parents=True)
            (root / "switch/keys/nested/prod.keys").write_text("key")
            paths = type("Paths", (), {"bios_root": root,
                                        "platforms_root": Path(__file__).parents[1] / "config/platforms"})()
            with patch("lulu.setup_files.PATHS", paths), \
                    patch("lulu.platforms.registry.PATHS", paths):
                row = next(item for item in file_setup_manifest({"eden"})
                           if item["platform"] == "switch")
            keys = next(item for item in row["requirements"] if item["id"] == "keys")
            self.assertTrue(keys["ready"])
            self.assertIn("nested/prod.keys", keys["present"])

    def test_firmware_archive_rejects_path_traversal(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = root / "firmware.zip"
            with zipfile.ZipFile(archive, "w") as bundle:
                bundle.writestr("../outside.nca", b"unsafe")
            with self.assertRaisesRegex(ValueError, "unsafe path"):
                _extract_firmware_zip(archive, root / "firmware")


if __name__ == "__main__":
    unittest.main()
