"""Validated provider registry loaded from TOML."""

from pathlib import Path
import tomllib

from ..paths import PATHS
from ..plugins import PluginRegistry
import shlex

from .model import ConfigStrategy, GuideAction, LaunchDefinition, ProviderCapabilities, ProviderDefinition

VALID_GUIDE_ROLES = {"system", "provider", "quit"}
VALID_GUIDE_CONTEXTS = {"shell", "game", "standalone", "store", "downloads", "install"}


def _guide_actions(raw: object, path: Path) -> tuple[GuideAction, ...]:
    if raw is None:
        return ()
    if not isinstance(raw, dict) or not isinstance(raw.get("actions", []), list):
        raise ValueError(f"invalid guide actions: {path}")
    actions: list[GuideAction] = []
    seen: set[str] = set()
    for index, value in enumerate(raw["actions"]):
        if not isinstance(value, dict):
            raise ValueError(f"invalid guide action {index}: {path}")
        action_id = str(value.get("id", "")).strip()
        label = str(value.get("label", "")).strip()
        role = str(value.get("role", "provider")).strip().casefold()
        target = str(value.get("target", "")).strip()
        contexts = tuple(str(item).strip().casefold() for item in value.get("contexts", ("game", "standalone")))
        if not action_id or action_id in seen or not label or not target:
            raise ValueError(f"invalid or duplicate Guide action {action_id!r}: {path}")
        if role not in VALID_GUIDE_ROLES or not contexts or any(item not in VALID_GUIDE_CONTEXTS for item in contexts):
            raise ValueError(f"invalid Guide action contract {action_id!r}: {path}")
        seen.add(action_id)
        actions.append(GuideAction(action_id, label, role, target, contexts,
                                   bool(value.get("confirm", False)), int(value.get("order", index))))
    actions.sort(key=lambda action: (action.order, action.action_id))
    if any(action.role == "quit" for action in actions) and sum(action.role == "quit" for action in actions) != 1:
        raise ValueError(f"provider must define exactly one Guide Quit action: {path}")
    return tuple(actions)


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

    def guide_actions(self, provider_id: str | None, context: str | None) -> tuple[GuideAction, ...]:
        if not provider_id:
            return ()
        provider = self.get(provider_id)
        context = context or "game"
        return tuple(action for action in provider.guide_actions if context in action.contexts)


def load_base_guide(path: Path | None = None) -> tuple[GuideAction, ...]:
    path = path or (Path(__file__).resolve().parents[3] / "config" / "guide" / "base.toml")
    with path.open("rb") as stream:
        return _guide_actions(tomllib.load(stream).get("guide"), path)


def load_mudos_guide(path: Path | None = None) -> tuple[GuideAction, ...]:
    path = path or (Path(__file__).resolve().parents[3] / "config" / "guide" / "mudos.toml")
    with path.open("rb") as stream:
        return _guide_actions(tomllib.load(stream).get("guide"), path)


def load_providers(directory: Path | None = None) -> ProviderRegistry:
    directory = directory or PATHS.providers_root
    directories = [directory]
    if directory == PATHS.providers_root:
        installed = Path(__file__).resolve().parents[3] / "config" / "providers"
        if installed.is_dir() and installed != directory:
            directories.insert(0, installed)
    if directory == PATHS.providers_root:
        plugin_root = PATHS.plugins_root
        installed_plugins = Path(__file__).resolve().parents[3] / "config" / "plugins"
        if installed_plugins.is_dir() and installed_plugins != plugin_root:
            plugin_root = installed_plugins
        for plugin in PluginRegistry(plugin_root).discover():
            if plugin.health == "available":
                provider_root = plugin.manifest.root / "providers"
                if provider_root.is_dir():
                    directories.append(provider_root)
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
            return LaunchDefinition(parts, str(value.get("controller_mode", "game")),
                                    str(value["window_class"]) if value.get("window_class") else None) if parts else None

        definitions[provider_id] = ProviderDefinition(
            provider_id, str(raw.get("name", provider_id)),
            ProviderCapabilities(*(bool(caps.get(name, False)) for name in ("launch", "settings", "library", "acquire", "health"))),
            tuple(str(item).casefold() for item in platforms.get("supported", ())), strategy,
            str(config.get("directory", "config")), raw.get("assets", {}).get("icon"),
            launch_definition(launch.get("standalone")) if isinstance(launch, dict) else None,
            launch_definition(launch.get("game")) if isinstance(launch, dict) else None,
            _guide_actions(raw.get("guide"), path),
        )
        if definitions[provider_id].capabilities.launch and not any(
                action.role == "quit" for action in definitions[provider_id].guide_actions):
            raise ValueError(f"executable provider has no usable Guide Quit action: {path}")
    return ProviderRegistry(definitions)
