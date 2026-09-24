import asyncio
import unittest

from dbus_next.errors import DBusError

from lulu.service_readiness import LULU_DBUS_OBJECTS, wait_for_lulu_services
from lulu.sessiond import bootstrap_after_services_ready


class ServiceReadinessTests(unittest.TestCase):
    def test_waits_until_every_required_object_introspects(self) -> None:
        class DelayedBus:
            def __init__(self) -> None:
                self.ready = False
                self.calls: list[tuple[str, str]] = []

            async def introspect(self, name: str, path: str) -> object:
                self.calls.append((name, path))
                if not self.ready:
                    self.ready = True
                    raise DBusError(
                        "org.freedesktop.DBus.Error.NameHasNoOwner", "not ready yet"
                    )
                return (name, path)

        bus = DelayedBus()
        result = asyncio.run(wait_for_lulu_services(bus, timeout=0.1, interval=0))
        self.assertEqual(set(result), set(LULU_DBUS_OBJECTS))
        self.assertEqual(len(bus.calls), 4)

    def test_missing_prerequisite_times_out_with_object_identity(self) -> None:
        class UnavailableBus:
            async def introspect(self, _name: str, _path: str) -> object:
                raise DBusError(
                    "org.freedesktop.DBus.Error.ServiceUnknown", "not activatable"
                )

        with self.assertRaisesRegex(RuntimeError, "org.lulu.ConsoleSessiond"):
            asyncio.run(wait_for_lulu_services(UnavailableBus(), timeout=0, interval=0))

    def test_graphical_bootstrap_runs_only_after_prerequisites_are_ready(self) -> None:
        class ReadyBus:
            async def introspect(self, name: str, path: str) -> object:
                return (name, path)

        class Interface:
            def __init__(self) -> None:
                self.started = False

            async def bootstrap_shell(self) -> None:
                self.started = True

        interface = Interface()
        asyncio.run(bootstrap_after_services_ready(interface, ReadyBus(), timeout=0.1))
        self.assertTrue(interface.started)

    def test_graphical_bootstrap_is_not_run_when_a_prerequisite_fails(self) -> None:
        class UnavailableBus:
            async def introspect(self, _name: str, _path: str) -> object:
                raise DBusError(
                    "org.freedesktop.DBus.Error.ServiceUnknown", "not activatable"
                )

        class Interface:
            started = False

            async def bootstrap_shell(self) -> None:
                self.started = True

        interface = Interface()
        with self.assertRaisesRegex(RuntimeError, "prerequisites unavailable"):
            asyncio.run(bootstrap_after_services_ready(interface, UnavailableBus(), timeout=0))
        self.assertFalse(interface.started)
