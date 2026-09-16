"""Normalized read-only system status models."""

from dataclasses import dataclass
from enum import StrEnum


class Readiness(StrEnum):
    READY = "ready"
    MISSING = "missing"
    DEGRADED = "degraded"
    UNKNOWN = "unknown"


class BluetoothState(StrEnum):
    POWERED = "powered"
    OFF = "off"
    UNAVAILABLE = "unavailable"


def network_manager_state_is_connected(state: int | None) -> bool:
    """Return whether NetworkManager reports a usable connected state."""
    return state in {50, 60, 70}  # local, site, or global connectivity


def normalize_bluetooth_state(
    service_available: bool, adapter_powered: tuple[bool, ...]
) -> BluetoothState:
    """Normalize BlueZ service/adapter observations for consumers."""
    if not service_available or not adapter_powered:
        return BluetoothState.UNAVAILABLE
    return BluetoothState.POWERED if any(adapter_powered) else BluetoothState.OFF


@dataclass(frozen=True, slots=True)
class RuntimeStatus:
    name: str
    readiness: Readiness
    detail: str = ""


@dataclass(frozen=True, slots=True)
class SystemStatus:
    controller_connected: bool
    navigation_owner: str | None
    input_mode: str
    storage_free_bytes: int | None
    network_connected: bool | None
    display_output: str | None
    display_mode: str | None
    runtimes: tuple[RuntimeStatus, ...]
