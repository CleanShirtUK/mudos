"""Validated provider registry loaded from TOML."""

from pathlib import Path
import tomllib

from ..paths import PATHS
from .model import ConfigStrategy, ProviderCapabilities, ProviderDefinition


class ProviderRegistry:
    def __init__(self, definitions: dict[str, ProviderDefinition]):
        self._definitions = dict(definitions)

    def get(self, provider_id: str) -> ProviderDefinition:
        try:
            return self._definitions[provider_id.casefold()]
        except KeyError as error:
            raise KeyError(f"unknown provider: {provider_id}") from error

    def __getitem__(self, provider_id: str) -> ProviderDefinition:
        return self.get(provider_id)

    def items(self):
        return self._definitions.items()


def load_providers(directory: Path | None = None) -> ProviderRegistry:
    directory = directory or PATHS.providers_root
    directories = [directory]
    if directory == PATHS.providers_root:
        installed = Path(__file__).resolve().parents[3] / "config" / "providers"
        if installed.is_dir() and installed != directory:
            directories.insert(0, installed)
    definitions = {}
    paths = {path.parent.name: path for root in directories if root.is_dir() for path in root.glob("*/provider.toml")}
    for path in sorted(paths.values(), key=lambda item: item.parent.name):
        with path.open("rb") as stream:
            raw = tomllib.load(stream)
        provider_id = str(raw.get("id", path.parent.name)).strip().casefold()
        caps = raw.get("capabilities", {})
        platforms = raw.get("platforms", {})
        config = raw.get("config", {})
        if not provider_id or not isinstance(caps, dict) or not isinstance(platforms, dict):
            raise ValueError(f"invalid provider definition: {path}")
        try:
            strategy = ConfigStrategy(str(config.get("strategy", "generated")).casefold())
        except ValueError as error:
            raise ValueError(f"invalid provider config strategy: {path}") from error
        definitions[provider_id] = ProviderDefinition(
            provider_id, str(raw.get("name", provider_id)),
            ProviderCapabilities(*(bool(caps.get(name, False)) for name in ("launch", "settings", "library", "acquire", "health"))),
            tuple(str(item).casefold() for item in platforms.get("supported", ())), strategy,
            str(config.get("directory", "config")), raw.get("assets", {}).get("icon"),
        )
    return ProviderRegistry(definitions)
