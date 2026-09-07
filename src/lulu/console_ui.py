"""Frontend boundary; owns ephemeral presentation and navigation state only."""

from .contracts import ServiceDescriptor, ServiceName


DESCRIPTOR = ServiceDescriptor(
    name=ServiceName.CONSOLE_UI,
    authority="ephemeral frontend and navigation state",
    owned_state=("current view", "focus", "transient navigation state"),
    notes=("Platform authority remains in the services consumed by the frontend.",),
)


class ConsoleUi:
    descriptor = DESCRIPTOR
