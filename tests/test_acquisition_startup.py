import asyncio
import unittest
from unittest.mock import patch

from lulu import acquisitiond


class AcquisitionStartupTests(unittest.TestCase):
    def test_bus_disconnect_is_logged_and_fails_fast(self):
        class BrokenBus:
            async def wait_for_disconnect(self):
                raise ConnectionError("bus reader failed")

        with self.assertLogs("lulu.acquisitiond", level="ERROR") as captured:
            with self.assertRaisesRegex(ConnectionError, "bus reader failed"):
                asyncio.run(acquisitiond._wait_for_bus_disconnect(BrokenBus()))
        self.assertIn("event=connection-lost", " ".join(captured.output))

    def test_clean_bus_close_is_unexpected(self):
        class ClosedBus:
            async def wait_for_disconnect(self):
                return None

        with self.assertRaisesRegex(RuntimeError, "closed unexpectedly"):
            asyncio.run(acquisitiond._wait_for_bus_disconnect(ClosedBus()))

    def test_service_starts_with_no_optional_plugins_or_external_gateway(self):
        class Bus:
            def __init__(self, **_kwargs):
                self.exports = []

            async def connect(self):
                return self

            def export(self, path, interface):
                self.exports.append((path, interface))

            async def request_name(self, _name):
                return None

            async def wait_for_disconnect(self):
                raise asyncio.CancelledError

        class Store:
            def __init__(self, _path):
                pass

            def close(self):
                pass

            def load(self):
                return []

        class Plugins:
            def __init__(self, _root):
                pass

            def discover(self):
                pass

            def with_capability(self, _capability):
                return []

        class Interface:
            def __init__(self, *_args, **_kwargs):
                pass

            def _snapshot(self):
                return "{}"

            def StateChanged(self, _value):
                pass

        bus = Bus()

        def create_task(coroutine):
            coroutine.close()
            return object()

        with patch.object(acquisitiond, "MessageBus", return_value=bus), \
                patch.object(acquisitiond, "AcquisitionStore", Store), \
                patch.object(acquisitiond, "CatalogueStore", lambda _path: object()), \
                patch.object(acquisitiond, "PluginRegistry", Plugins), \
                patch.object(acquisitiond, "AcquisitionInterface", Interface), \
                patch.object(acquisitiond.asyncio, "create_task", create_task):
            with self.assertRaises(asyncio.CancelledError):
                asyncio.run(acquisitiond.serve())

        self.assertEqual(bus.exports[0][0], acquisitiond.OBJECT_PATH)


if __name__ == "__main__":
    unittest.main()
