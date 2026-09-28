"""Validated platform registry loaded from user-overridable TOML."""

from pathlib import Path
import tomllib

from ..paths import PATHS
from .model import BiosDefinition, ContentDefinition, PlatformDefinition, SetupFileRequirement


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
        setup = raw.get("setup", {})
        questarr = raw.get("questarr", {})
        if not platform_id or not isinstance(content, dict) or not isinstance(providers, dict):
            raise ValueError(f"invalid platform definition: {path}")
        subdir = str(content.get("subdir", platform_id)).strip()
        extensions = tuple(str(item).lower() for item in content.get("extensions", ()))
        supported = tuple(str(item).casefold() for item in providers.get("supported", ()))
        if not subdir or not extensions or not supported:
            raise ValueError(f"incomplete platform definition: {path}")
        if not isinstance(questarr, dict):
            raise ValueError(f"invalid Questarr platform mapping: {path}")
        questarr_library_dir = questarr.get("library_dir")
        if questarr_library_dir is not None:
            questarr_library_dir = str(questarr_library_dir).strip()
            if (not questarr_library_dir or Path(questarr_library_dir).is_absolute()
                    or len(Path(questarr_library_dir).parts) != 1
                    or questarr_library_dir in {".", ".."}):
                raise ValueError(f"invalid Questarr library directory: {path}")
        setup_files = []
        if not isinstance(setup, dict) or not isinstance(setup.get("files", []), list):
            raise ValueError(f"invalid setup file requirements: {path}")
        for item in setup.get("files", []):
            if not isinstance(item, dict):
                raise ValueError(f"invalid setup file requirement: {path}")
            requirement_id = str(item.get("id", "")).strip().casefold()
            destination = str(item.get("destination", "")).strip()
            if (not requirement_id or not destination or Path(destination).is_absolute()
                    or ".." in Path(destination).parts):
                raise ValueError(f"unsafe setup file destination: {path}")
            setup_files.append(SetupFileRequirement(
                requirement_id, str(item.get("label", requirement_id)), destination,
                str(item.get("description", "")),
                tuple(str(ext).casefold() for ext in item.get("extensions", [])),
                bool(item.get("multiple", False)), bool(item.get("archive", False)),
                bool(item.get("required", False)),
                tuple(str(name).casefold() for name in item.get("required_names", [])),
            ))
        definitions[platform_id] = PlatformDefinition(
            platform_id, str(raw.get("name", platform_id)),
            ContentDefinition(subdir, extensions),
            BiosDefinition(bool(bios.get("required", False)), bios.get("subdir")),
            supported, providers.get("default"), raw.get("assets", {}).get("icon"),
            tuple(setup_files), questarr_library_dir,
        )
    return PlatformRegistry(definitions)
