"""Small, transport-neutral contracts shared by Lulu services."""

from dataclasses import dataclass
from enum import StrEnum


class ServiceName(StrEnum):
    CONTROLLERD = "controllerd"
    CONSOLE_SESSIOND = "console-sessiond"
    CONSOLED = "consoled"
    APPLICATIOND = "applicationd"
    ACQUISITIOND = "acquisitiond"
    CONSOLE_UI = "console-ui"


class Role(StrEnum):
    NAVIGATION = "navigation"
    PLAYER = "player"


class Lifecycle(StrEnum):
    SHELL = "shell"
    LAUNCH_REQUESTED = "launch_requested"
    STARTING = "starting"
    PRESENTATION_PENDING = "presentation_pending"
    GAME = "game"
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
    GAME = "gamepad"
    COMPAT = "compat"


class SessionClassification(StrEnum):
    GAME = "game"
    UTILITY = "utility"


@dataclass(frozen=True, slots=True)
class LaunchDescriptor:
    """Session-owned description of a launched surface and input policy."""

    primary_id: str
    classification: SessionClassification = SessionClassification.GAME
    title: str = ""
    presentation: Presentation = Presentation.GAME
    input_mode: InputMode | None = None

    def __post_init__(self) -> None:
        if self.input_mode is None:
            default_mode = (InputMode.COMPAT
                            if self.classification is SessionClassification.UTILITY
                            else InputMode.GAME)
            object.__setattr__(self, "input_mode", default_mode)


@dataclass(frozen=True, slots=True)
class ServiceDescriptor:
    """The inspectable boundary of a service, not an IPC registration."""

    name: ServiceName
    authority: str
    owned_state: tuple[str, ...]
    notes: tuple[str, ...] = ()
