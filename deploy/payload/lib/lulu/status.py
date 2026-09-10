"""Normalized read-only system status models."""

from dataclasses import dataclass
from enum import StrEnum


class Readiness(StrEnum):
    READY = "ready"
    MISSING = "missing"
    DEGRADED = "degraded"
    UNKNOWN = "unknown"


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
