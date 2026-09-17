"""Provider metadata: capabilities, supported content, and config ownership."""

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path


class ConfigStrategy(StrEnum):
    DIRECT = "direct"
    REDIRECTED = "redirected"
    SYNCHRONISED = "synchronised"
    GENERATED = "generated"


@dataclass(frozen=True, slots=True)
class ProviderCapabilities:
    launch: bool = False
    settings: bool = False
    library: bool = False
    acquire: bool = False
    health: bool = False


@dataclass(frozen=True, slots=True)
class LaunchDefinition:
    """One explicit provider launch contract (never inferred from the other)."""
    command: tuple[str, ...]
    controller_mode: str = "game"


@dataclass(frozen=True, slots=True)
class ProviderDefinition:
    provider_id: str
    name: str
    capabilities: ProviderCapabilities
    supported_platforms: tuple[str, ...]
    config_strategy: ConfigStrategy
    config_directory: str = "config"
    icon: str | None = None
    standalone_launch: LaunchDefinition | None = None
    game_launch: LaunchDefinition | None = None

    @property
    def standalone_capable(self) -> bool:
        return self.standalone_launch is not None

    def config_root(self, providers_root: Path) -> Path:
        return providers_root / self.provider_id / self.config_directory
