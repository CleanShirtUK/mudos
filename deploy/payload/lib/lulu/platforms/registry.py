"""Validated platform registry loaded from user-overridable TOML."""

from pathlib import Path
import tomllib

from ..paths import PATHS
from .model import BiosDefinition, ContentDefinition, PlatformDefinition


class PlatformRegistry:
    def __init__(self, definitions: dict[str, PlatformDefinition]):
        self._definitions = dict(definitions)

    def get(self, platform_id: str) -> PlatformDefinition:
        try:
            return self._definitions[platform_id.casefold()]
        except KeyError as error:
            raise KeyError(f"unknown platform: {platform_id}") from error

    def __getitem__(self, platform_id: str) -> PlatformDefinition:
        return self.get(platform_id)

    def __iter__(self):
        return iter(self._definitions)

    def items(self):
        return self._definitions.items()

    def __len__(self) -> int:
        return len(self._definitions)


def load_platforms(directory: Path | None = None) -> PlatformRegistry:
    directory = directory or PATHS.platforms_root
    directories = [directory]
    if directory == PATHS.platforms_root:
        # Installed definitions are defaults; user definitions override by ID.
        installed = Path(__file__).resolve().parents[3] / "config" / "platforms"
        if installed.is_dir() and installed != directory:
            directories.insert(0, installed)
    definitions = {}
    paths = {path.name: path for root in directories if root.is_dir() for path in root.glob("*.toml")}
    for path in sorted(paths.values(), key=lambda item: item.name):
        with path.open("rb") as stream:
            raw = tomllib.load(stream)
        platform_id = str(raw.get("id", path.stem)).strip().casefold()
        content = raw.get("content", {})
        bios = raw.get("bios", {})
        providers = raw.get("providers", {})
        if not platform_id or not isinstance(content, dict) or not isinstance(providers, dict):
            raise ValueError(f"invalid platform definition: {path}")
        subdir = str(content.get("subdir", platform_id)).strip()
        extensions = tuple(str(item).lower() for item in content.get("extensions", ()))
        supported = tuple(str(item).casefold() for item in providers.get("supported", ()))
        if not subdir or not extensions or not supported:
            raise ValueError(f"incomplete platform definition: {path}")
        definitions[platform_id] = PlatformDefinition(
            platform_id, str(raw.get("name", platform_id)),
            ContentDefinition(subdir, extensions),
            BiosDefinition(bool(bios.get("required", False)), bios.get("subdir")),
            supported, providers.get("default"), raw.get("assets", {}).get("icon"),
        )
    return PlatformRegistry(definitions)
