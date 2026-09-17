import asyncio
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from lulu.storage_manager import StorageManagerAdapter


class StorageManagerTests(unittest.TestCase):
    def test_mount_points_decode_and_irrelevant_objects_are_not_ui_data(self):
        self.assertEqual(StorageManagerAdapter._mount_points([[ord("/"), ord("m"), 0], b"/usb\0"]), ["/m", "/usb"])

    def test_unavailable_target_is_explicit_and_not_fallback(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "targets.json"
            path.write_text(json.dumps({"game": "uuid-missing", "game_path": "/gone"}))
            adapter = StorageManagerAdapter(state_path=path)
            async def devices(): return []
            adapter._devices = devices
            state = asyncio.run(adapter.snapshot())
            self.assertFalse(state["available"] is False)
            self.assertFalse(state["targets"]["game"]["available"])
            self.assertEqual(state["targets"]["game"]["id"], "uuid-missing")

    def test_system_and_read_only_storage_are_protected(self):
        with TemporaryDirectory() as directory:
            adapter = StorageManagerAdapter(state_path=Path(directory) / "targets.json")
            async def devices():
                return [{"id": "root", "system": True, "read_only": False, "mounted": True,
                         "object_path": "/root", "mount_point": "/", "removable": False}]
            adapter._devices = devices
            state = asyncio.run(adapter.select_target("game", "root"))
            self.assertIn("writable", state["error"])


if __name__ == "__main__":
    unittest.main()
