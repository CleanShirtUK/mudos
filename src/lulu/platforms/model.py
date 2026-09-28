"""Provider-independent descriptions of content platforms."""

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class ContentDefinition:
    subdir: str
    extensions: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class BiosDefinition:
    required: bool = False
    subdir: str | None = None


@dataclass(frozen=True, slots=True)
class SetupFileRequirement:
    requirement_id: str
    label: str
    destination: str
    description: str
    extensions: tuple[str, ...]
    multiple: bool = False
    archive: bool = False
    required: bool = False
    required_names: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class PlatformDefinition:
    platform_id: str
    name: str
    content: ContentDefinition
    bios: BiosDefinition
    supported_providers: tuple[str, ...]
    default_provider: str | None = None
    icon: str | None = None
    setup_files: tuple[SetupFileRequirement, ...] = ()
    questarr_library_dir: str | None = None

    @property
    def label(self) -> str:
        """Compatibility spelling used by catalogue models."""
        return self.name

    def content_root(self, rom_root: Path) -> Path:
        return rom_root / self.content.subdir

    def bios_root(self, bios_root: Path) -> Path:
        return bios_root / (self.bios.subdir or self.platform_id)
