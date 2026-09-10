"""Provider capability vocabulary kept independent of provider implementations."""

from dataclasses import dataclass
from enum import StrEnum


class Capability(StrEnum):
    DISCOVER = "discover"
    SEARCH = "search"
    OWNERSHIP = "ownership"
    INSTALL = "install"
    UNINSTALL = "uninstall"
    UPDATE = "update"
    LAUNCH = "launch"
    ARTWORK = "artwork"
    METADATA = "metadata"
    DOWNLOAD_PROGRESS = "download_progress"
    CHECKOUT_HANDOFF = "checkout_handoff"


@dataclass(frozen=True, slots=True)
class ProviderCapabilities:
    provider: str
    capabilities: frozenset[Capability]

    def supports(self, capability: Capability) -> bool:
        return capability in self.capabilities


STEAM_CAPABILITIES = ProviderCapabilities(
    "steam",
    frozenset({Capability.DISCOVER, Capability.OWNERSHIP, Capability.LAUNCH, Capability.ARTWORK, Capability.METADATA}),
)
LOCAL_EMULATION_CAPABILITIES = ProviderCapabilities(
    "local",
    frozenset({Capability.DISCOVER, Capability.LAUNCH, Capability.METADATA}),
)
