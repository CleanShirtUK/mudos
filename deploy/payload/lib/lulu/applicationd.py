"""Generic application and managed-runtime package boundary."""

from .contracts import ServiceDescriptor, ServiceName


DESCRIPTOR = ServiceDescriptor(
    name=ServiceName.APPLICATIOND,
    authority="generic applications and managed runtime packages",
    owned_state=(
        "application catalogue",
        "package transactions",
        "permissions",
        "launch metadata",
        "progress and error state",
    ),
    notes=("The UI does not invoke package commands or privilege escalation directly.",),
)


class ApplicationCatalog:
    """Boundary placeholder with no package backend or persistence implementation."""

    descriptor = DESCRIPTOR
