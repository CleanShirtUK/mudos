"""Lulu service-boundary foundation.

Transport, persistence, and external integrations are intentionally not part of
this initial substrate.
"""

from .contracts import (
    InputMode,
    Lifecycle,
    Overlay,
    Presentation,
    Role,
    ServiceDescriptor,
)

__all__ = [
    "InputMode",
    "Lifecycle",
    "Overlay",
    "Presentation",
    "Role",
    "ServiceDescriptor",
]
