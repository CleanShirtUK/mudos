"""Small, transport-neutral contracts shared by Lulu services."""

from dataclasses import dataclass
from enum import StrEnum


class ServiceName(StrEnum):
    CONTROLLERD = "controllerd"
    CONSOLE_SESSIOND = "console-sessiond"
    CONSOLED = "consoled"
    APPLICATIOND = "applicationd"
    CONSOLE_UI = "console-ui"


class Role(StrEnum):
    NAVIGATION = "navigation"
    PLAYER = "player"


class Lifecycle(StrEnum):
    SHELL = "shell"
    LAUNCHING = "launching"
    RUNNING = "running"
    RETURNING = "returning"


class Presentation(StrEnum):
    SHELL = "shell"
    GAME = "game"
    FOREIGN_UI = "foreign-ui"


class Overlay(StrEnum):
    CLOSED = "closed"
    OPEN = "open"


class InputMode(StrEnum):
    SHELL = "shell"
    GAME = "game"
    COMPAT = "compat"


@dataclass(frozen=True, slots=True)
class ServiceDescriptor:
    """The inspectable boundary of a service, not an IPC registration."""

    name: ServiceName
    authority: str
    owned_state: tuple[str, ...]
    notes: tuple[str, ...] = ()
