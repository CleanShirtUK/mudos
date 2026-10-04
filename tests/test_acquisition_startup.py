import asyncio
import unittest
from unittest.mock import patch

from lulu import acquisitiond


class AcquisitionStartupTests(unittest.TestCase):
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

        class Store:
            def __init__(self, _path):
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

        class StopLoop:
            async def wait(self):
                raise asyncio.CancelledError

        bus = Bus()

        def create_task(coroutine):
            coroutine.close()
            return object()

        with patch.object(acquisitiond, "MessageBus", return_value=bus), \
                patch.object(acquisitiond, "AcquisitionStore", Store), \
                patch.object(acquisitiond, "CatalogueStore", lambda _path: object()), \
                patch.object(acquisitiond, "PluginRegistry", Plugins), \
                patch.object(acquisitiond, "AcquisitionInterface", Interface), \
                patch.object(acquisitiond.asyncio, "create_task", create_task), \
                patch.object(acquisitiond.asyncio, "Event", StopLoop):
            with self.assertRaises(asyncio.CancelledError):
                asyncio.run(acquisitiond.serve())

        self.assertEqual(bus.exports[0][0], acquisitiond.OBJECT_PATH)


if __name__ == "__main__":
    unittest.main()
