"""Readiness checks for Lulu's shared user-session D-Bus services."""

import asyncio
from typing import Any

from dbus_next.errors import DBusError


LULU_DBUS_OBJECTS = {
    "sessiond": ("org.lulu.ConsoleSessiond", "/org/lulu/ConsoleSession"),
    "consoled": ("org.lulu.Consoled", "/org/lulu/Console"),
    "acquisitiond": ("org.lulu.Acquisitiond", "/org/lulu/Acquisition"),
}
_RETRYABLE_DBUS_ERRORS = {
    "org.freedesktop.DBus.Error.ServiceUnknown",
    "org.freedesktop.DBus.Error.NameHasNoOwner",
}


async def introspect_lulu_services(bus: Any) -> dict[str, Any]:
    """Prove all required Lulu services own and export their expected objects."""
    result: dict[str, Any] = {}
    for key, (name, path) in LULU_DBUS_OBJECTS.items():
        result[key] = await bus.introspect(name, path)
    return result


async def wait_for_lulu_services(bus: Any, *, timeout: float = 30.0,
                                 interval: float = 0.1) -> dict[str, Any]:
    """Wait for all required user-bus objects, failing clearly at the deadline."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    last_error: DBusError | None = None
    last_missing = "unknown"
    while True:
        try:
            result: dict[str, Any] = {}
            last_missing = "unknown"
            for key, (name, path) in LULU_DBUS_OBJECTS.items():
                last_missing = f"{name}{path}"
                result[key] = await bus.introspect(name, path)
            return result
        except DBusError as error:
            if error.type not in _RETRYABLE_DBUS_ERRORS:
                raise
            last_error = error
        remaining = deadline - loop.time()
        if remaining <= 0:
            raise RuntimeError(
                f"Lulu D-Bus prerequisites unavailable after {timeout:.1f}s "
                f"(last missing object: {last_missing}): {last_error}"
            ) from last_error
        await asyncio.sleep(min(interval, remaining))
