"""Bounded readiness checks for Lulu's service dependencies."""

import asyncio

from dbus_next.errors import DBusError


TRANSIENT_DBUS_ERRORS = frozenset({
    "org.freedesktop.DBus.Error.ServiceUnknown",
    "org.freedesktop.DBus.Error.NameHasNoOwner",
})


async def wait_for_dbus_service(
    bus: object,
    name: str,
    path: str,
    *,
    timeout: float = 5.0,
    interval: float = 0.1,
) -> object:
    """Return introspection only after the service and object are available."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while True:
        try:
            return await bus.introspect(name, path)
        except DBusError as error:
            if error.type not in TRANSIENT_DBUS_ERRORS:
                raise
            remaining = deadline - loop.time()
            if remaining <= 0:
                raise RuntimeError(
                    f"D-Bus service unavailable after {timeout:.1f}s: {name}{path}"
                ) from error
            await asyncio.sleep(min(interval, remaining))
