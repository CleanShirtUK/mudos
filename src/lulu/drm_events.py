"""Small unprivileged listener for DRM connector hotplug uevents."""

import os
import socket


NETLINK_KOBJECT_UEVENT = 15
KERNEL_UEVENT_GROUP = 1


def is_drm_hotplug_uevent(payload: bytes) -> bool:
    """Return true for a kernel DRM hotplug/change event."""
    fields: dict[bytes, bytes] = {}
    for item in payload.split(b"\0"):
        key, separator, value = item.partition(b"=")
        if separator:
            fields[key] = value
    return fields.get(b"SUBSYSTEM") == b"drm" and fields.get(b"HOTPLUG") == b"1"


def open_drm_uevent_socket() -> socket.socket:
    """Subscribe to kernel hotplug uevents without requiring root."""
    event_socket = socket.socket(socket.AF_NETLINK, socket.SOCK_DGRAM, NETLINK_KOBJECT_UEVENT)
    try:
        event_socket.bind((os.getpid(), KERNEL_UEVENT_GROUP))
        event_socket.setblocking(False)
    except BaseException:
        event_socket.close()
        raise
    return event_socket
