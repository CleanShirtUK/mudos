"""Unified game catalogue and game/content intent boundary."""

from .contracts import ServiceDescriptor, ServiceName


DESCRIPTOR = ServiceDescriptor(
    name=ServiceName.CONSOLED,
    authority="unified game catalogue and game/platform intent",
    owned_state=(
        "normalized provider records",
        "content installation metadata",
        "game profiles",
        "compatibility intent",
        "emulator configuration intent",
    ),
    notes=("External runtime configuration is generated output, not authority.",),
)


class ConsoleCatalog:
    """Boundary placeholder with no provider or persistence implementation."""

    descriptor = DESCRIPTOR
