"""Validated provider registry loaded from TOML."""

from pathlib import Path
import tomllib

from ..paths import PATHS
import shlex

from .model import ConfigStrategy, LaunchDefinition, ProviderCapabilities, ProviderDefinition


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

    def standalone(self) -> tuple[ProviderDefinition, ...]:
        """Declared providers with a content-independent standalone frontend."""
        return tuple(definition for definition in self._definitions.values()
                     if definition.standalone_launch is not None)

    def for_platform(self, platform_id: str) -> ProviderDefinition:
        """Resolve a launch-capable provider from the declared relationship."""
        for definition in self._definitions.values():
            if (platform_id.casefold() in definition.supported_platforms
                    and definition.capabilities.launch):
                return definition
        raise KeyError(f"no launch provider registered for platform: {platform_id}")


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
        launch = raw.get("launch", {})
        if not provider_id or not isinstance(caps, dict) or not isinstance(platforms, dict):
            raise ValueError(f"invalid provider definition: {path}")
        try:
            strategy = ConfigStrategy(str(config.get("strategy", "generated")).casefold())
        except ValueError as error:
            raise ValueError(f"invalid provider config strategy: {path}") from error
        def launch_definition(value: object) -> LaunchDefinition | None:
            if not isinstance(value, dict) or "command" not in value:
                return None
            command = value["command"]
            parts = tuple(command) if isinstance(command, list) else tuple(shlex.split(str(command)))
            return LaunchDefinition(parts, str(value.get("controller_mode", "game"))) if parts else None

        definitions[provider_id] = ProviderDefinition(
            provider_id, str(raw.get("name", provider_id)),
            ProviderCapabilities(*(bool(caps.get(name, False)) for name in ("launch", "settings", "library", "acquire", "health"))),
            tuple(str(item).casefold() for item in platforms.get("supported", ())), strategy,
            str(config.get("directory", "config")), raw.get("assets", {}).get("icon"),
            launch_definition(launch.get("standalone")) if isinstance(launch, dict) else None,
            launch_definition(launch.get("game")) if isinstance(launch, dict) else None,
        )
    return ProviderRegistry(definitions)
