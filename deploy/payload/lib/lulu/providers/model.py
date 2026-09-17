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
    window_class: str | None = None


@dataclass(frozen=True, slots=True)
class GuideAction:
    """A registry-normalized action available from Guide."""
    action_id: str
    label: str
    role: str
    target: str
    contexts: tuple[str, ...] = ("game", "standalone")
    confirm: bool = False
    order: int = 0


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
    guide_actions: tuple[GuideAction, ...] = ()

    @property
    def standalone_capable(self) -> bool:
        return self.standalone_launch is not None

    def config_root(self, providers_root: Path) -> Path:
        return providers_root / self.provider_id / self.config_directory
