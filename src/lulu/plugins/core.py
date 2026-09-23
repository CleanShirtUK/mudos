"""Versioned, failure-isolated Mudos plugin registry.

Plugins are deliberately small in v1: an in-process ``register(context)``
entrypoint receives explicit registries rather than the application object.
Declarative provider resources remain authoritative and are discovered through
the normal provider registry.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import importlib.util
import logging
from pathlib import Path
import tomllib
from typing import Any, Callable
from urllib.parse import urlsplit

from ..credential import SecretStore

PLUGIN_API_VERSION = 1
LOGGER = logging.getLogger("lulu.plugins")


@dataclass(frozen=True, slots=True)
class ConfigurationField:
    """Provider-neutral configuration field metadata; never contains values."""

    key: str
    kind: str
    label: str
    description: str = ""
    required: bool = False
    secret: bool = False
    validation: str = ""
    default: object | None = None
    choices: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class SecretRequirement:
    slot: str
    label: str
    description: str = ""
    required: bool = False
    reference: str = ""


@dataclass(frozen=True, slots=True)
class DependencySpec:
    requires_all: tuple[str, ...] = ()
    requires_any: tuple[tuple[str, ...], ...] = ()


@dataclass(frozen=True, slots=True)
class StoreCardContribution:
    card_id: str
    label: str
    url: str
    glyph: str = ""
    artwork: str = ""
    browser_profile: str = ""
    removable: bool = False


@dataclass(frozen=True, slots=True)
class BrowserHandoffContribution:
    handoff_id: str
    schemes: tuple[str, ...]
    handler: str
    trusted_origins: tuple[str, ...] = ()
    artifact_types: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ServiceContribution:
    service_id: str
    name: str
    description: str
    url: str = ""
    health: str = ""
    configurable: bool = False


@dataclass(frozen=True, slots=True)
class ProvisioningRequirement:
    package: str
    service: str = ""
    reason: str = ""


@dataclass(frozen=True, slots=True)
class ComponentDescriptor:
    """Unified onboarding descriptor for built-ins, services, and plugins."""

    component_id: str
    name: str
    description: str
    kind: str
    enabled: bool = True
    installed: bool = True
    capabilities: frozenset[str] = frozenset()
    dependencies: DependencySpec = DependencySpec()
    configuration: tuple[ConfigurationField, ...] = ()
    secrets: tuple[SecretRequirement, ...] = ()
    store_cards: tuple[StoreCardContribution, ...] = ()
    services: tuple[ServiceContribution, ...] = ()
    browser_handoffs: tuple[BrowserHandoffContribution, ...] = ()
    provisioning: tuple[ProvisioningRequirement, ...] = ()
    provider_ids: tuple[str, ...] = ()
    source_plugin: str = ""
    authentication_methods: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class DependencyPlan:
    selected: tuple[str, ...]
    ordered: tuple[str, ...]
    missing_any: tuple[tuple[str, tuple[str, ...]], ...] = ()
    unknown: tuple[str, ...] = ()


class PluginSecretBoundary:
    """Generic plugin-owned SecretStore namespace boundary."""

    def __init__(self, plugin_id: str, store: SecretStore | None = None):
        self.plugin_id = plugin_id
        self.store = store or SecretStore()

    def reference(self, slot: str) -> str:
        if not slot or "/" in slot:
            raise ValueError("secret slot must be a local name")
        return f"{self.plugin_id}/{slot}"

    def configured(self, slot: str) -> bool:
        return self.store.configured(self.plugin_id, slot)

    def get(self, slot: str) -> str | None:
        return self.store.get(self.plugin_id, slot)

    def put(self, slot: str, value: str) -> None:
        self.store.put(self.plugin_id, slot, value)

    def clear(self, slot: str) -> None:
        self.store.clear(self.plugin_id, slot)


@dataclass(frozen=True, slots=True)
class PluginManifest:
    plugin_id: str
    name: str
    version: str
    api_version: int
    capabilities: frozenset[str]
    root: Path
    enabled: bool = True
    description: str = ""
    plugin_types: tuple[str, ...] = ()
    dependencies: DependencySpec = DependencySpec()
    configuration: tuple[ConfigurationField, ...] = ()
    secrets: tuple[SecretRequirement, ...] = ()
    store_cards: tuple[StoreCardContribution, ...] = ()
    services: tuple[ServiceContribution, ...] = ()
    browser_handoffs: tuple[BrowserHandoffContribution, ...] = ()
    provisioning: tuple[ProvisioningRequirement, ...] = ()
    kind: str = "plugin"
    installed: bool = True
    provider_ids: tuple[str, ...] = ()
    authentication_methods: tuple[str, ...] = ()


@dataclass(slots=True)
class PluginRecord:
    manifest: PluginManifest
    health: str = "unavailable"
    error: str | None = None
    registrations: dict[str, list[Any]] = field(default_factory=dict)


class PluginContext:
    """Minimal registration context exposed to plugin entrypoints."""

    def __init__(self, record: PluginRecord, logger: logging.Logger):
        self.manifest = record.manifest
        self.logger = logger
        self._record = record
        self.secrets = PluginSecretBoundary(record.manifest.plugin_id)

    def register(self, capability: str, contribution: Any) -> None:
        if capability not in self.manifest.capabilities:
            raise ValueError(f"plugin {self.manifest.plugin_id} registered undeclared capability {capability}")
        self._record.registrations.setdefault(capability, []).append(contribution)


class PluginRegistry:
    """Discover, validate, and initialize plugins in deterministic order."""

    def __init__(self, root: Path, *, enabled: dict[str, bool] | None = None,
                 api_version: int = PLUGIN_API_VERSION):
        self.root = root
        self.enabled = enabled or {}
        self.api_version = api_version
        self.records: dict[str, PluginRecord] = {}

    def discover(self) -> tuple[PluginRecord, ...]:
        self.records.clear()
        if not self.root.is_dir():
            return ()
        for manifest_path in sorted(self.root.glob("*/plugin.toml"), key=lambda path: path.parent.name.casefold()):
            record = self._load_manifest(manifest_path)
            if record is not None:
                if record.manifest.plugin_id in self.records:
                    self.records[record.manifest.plugin_id].health = "degraded"
                    self.records[record.manifest.plugin_id].error = "duplicate plugin id"
                    LOGGER.error("duplicate plugin id=%s path=%s", record.manifest.plugin_id, manifest_path)
                    continue
                self.records[record.manifest.plugin_id] = record
        for record in self.records.values():
            if record.manifest.enabled:
                self._initialize(record)
        return tuple(self.records.values())

    def _load_manifest(self, path: Path) -> PluginRecord | None:
        try:
            with path.open("rb") as stream:
                raw = tomllib.load(stream)
            plugin_id = str(raw.get("id", "")).strip().casefold()
            if not plugin_id or not str(raw.get("name", "")).strip():
                raise ValueError("id and name are required")
            if plugin_id in self.records:
                raise ValueError(f"duplicate plugin id: {plugin_id}")
            api_version = int(raw.get("api_version", 0))
            if api_version != self.api_version:
                raise ValueError(f"unsupported plugin API version {api_version}")
            capabilities = raw.get("capabilities", {})
            if not isinstance(capabilities, dict):
                raise ValueError("capabilities must be a table")
            enabled = self.enabled.get(plugin_id, bool(raw.get("enabled", True)))
            dependencies = self._dependencies(raw.get("dependencies", {}), path)
            configuration = self._configuration(raw.get("configuration", {}), path)
            secrets = self._secrets(raw.get("secrets", {}), path)
            store_cards = self._store_cards(raw.get("store_cards", []), path)
            services = self._services(raw.get("services", []), path)
            browser_handoffs = self._browser_handoffs(raw.get("browser_handoffs", []), path)
            provisioning = self._provisioning(raw.get("provisioning", []), path)
            manifest = PluginManifest(
                plugin_id=plugin_id, name=str(raw["name"]), version=str(raw.get("version", "1")),
                api_version=api_version,
                capabilities=frozenset(key for key, value in capabilities.items() if value),
                root=path.parent, enabled=enabled, description=str(raw.get("description", "")),
                plugin_types=tuple(str(item) for item in raw.get("types", ())), dependencies=dependencies,
                configuration=configuration, secrets=secrets, store_cards=store_cards,
                services=services, browser_handoffs=browser_handoffs,
                provisioning=provisioning, kind=str(raw.get("kind", "plugin")),
                installed=bool(raw.get("installed", True)),
                provider_ids=tuple(str(item) for item in raw.get("providers", ())),
                authentication_methods=tuple(str(item).strip().casefold()
                                             for item in raw.get("authentication_methods", ())),
            )
            return PluginRecord(manifest, "disabled" if not enabled else "unavailable")
        except (OSError, tomllib.TOMLDecodeError, KeyError, TypeError, ValueError) as error:
            plugin_id = path.parent.name.casefold()
            manifest = PluginManifest(plugin_id, plugin_id, "invalid", 0, frozenset(), path.parent, False)
            return PluginRecord(manifest, "unavailable", str(error))

    @staticmethod
    def _dependencies(raw: object, path: Path) -> DependencySpec:
        if raw is None:
            return DependencySpec()
        if not isinstance(raw, dict):
            raise ValueError(f"invalid dependencies: {path}")
        all_items = tuple(str(item).strip().casefold() for item in raw.get("requires_all", ()))
        groups: list[tuple[str, ...]] = []
        for group in raw.get("requires_any", ()):
            if isinstance(group, str):
                group = [group]
            if not isinstance(group, list) or not group:
                raise ValueError(f"invalid dependency alternative: {path}")
            groups.append(tuple(str(item).strip().casefold() for item in group))
        return DependencySpec(tuple(item for item in all_items if item), tuple(groups))

    @staticmethod
    def _configuration(raw: object, path: Path) -> tuple[ConfigurationField, ...]:
        if not raw:
            return ()
        if not isinstance(raw, dict):
            raise ValueError(f"invalid configuration schema: {path}")
        fields_raw = raw.get("fields", {})
        if not isinstance(fields_raw, dict):
            raise ValueError(f"invalid configuration fields: {path}")
        fields: list[ConfigurationField] = []
        for key, value in fields_raw.items():
            if not isinstance(value, dict):
                raise ValueError(f"invalid configuration field: {path}")
            kind = str(value.get("type", "text"))
            if kind not in {"text", "url", "username", "password", "secret", "api_key", "integer", "boolean", "choice"}:
                raise ValueError(f"invalid configuration field type {kind}: {path}")
            choices = tuple(str(item) for item in value.get("choices", ()))
            fields.append(ConfigurationField(str(key), kind, str(value.get("label", key)),
                                             str(value.get("description", "")), bool(value.get("required", False)),
                                             bool(value.get("secret", kind in {"password", "secret", "api_key"})),
                                             str(value.get("validation", "")), value.get("default"), choices))
        return tuple(fields)

    @staticmethod
    def _secrets(raw: object, path: Path) -> tuple[SecretRequirement, ...]:
        if not raw:
            return ()
        if not isinstance(raw, list):
            raise ValueError(f"invalid secret requirements: {path}")
        return tuple(SecretRequirement(str(item.get("slot", "")), str(item.get("label", "")),
                                       str(item.get("description", "")), bool(item.get("required", False)),
                                       str(item.get("reference", "")))
                     for item in raw if isinstance(item, dict) and item.get("slot"))

    @staticmethod
    def _store_cards(raw: object, path: Path) -> tuple[StoreCardContribution, ...]:
        if not raw:
            return ()
        if not isinstance(raw, list):
            raise ValueError(f"invalid store cards: {path}")
        return tuple(StoreCardContribution(str(item["id"]), str(item["label"]), str(item["url"]),
                                           str(item.get("glyph", "")), str(item.get("artwork", "")),
                                           str(item.get("browser_profile", "")), bool(item.get("removable", False)))
                     for item in raw if isinstance(item, dict) and item.get("id") and item.get("label") and item.get("url"))

    @staticmethod
    def _services(raw: object, path: Path) -> tuple[ServiceContribution, ...]:
        if not raw:
            return ()
        if not isinstance(raw, list):
            raise ValueError(f"invalid services: {path}")
        return tuple(ServiceContribution(str(item["id"]), str(item["name"]), str(item.get("description", "")),
                                         str(item.get("url", "")), str(item.get("health", "")), bool(item.get("configurable", False)))
                     for item in raw if isinstance(item, dict) and item.get("id") and item.get("name"))

    @staticmethod
    def _browser_handoffs(raw: object, path: Path) -> tuple[BrowserHandoffContribution, ...]:
        if not raw:
            return ()
        if not isinstance(raw, list):
            raise ValueError(f"invalid browser handoffs: {path}")
        return tuple(BrowserHandoffContribution(
            str(item.get("id", "")),
            tuple(str(value).casefold() for value in item.get("schemes", ())),
            str(item.get("handler", "")),
            tuple(str(value).rstrip("/").casefold() for value in item.get("trusted_origins", ())),
            tuple(str(value).casefold() for value in item.get("artifact_types", ())),
        ) for item in raw if isinstance(item, dict) and item.get("id") and item.get("schemes") and item.get("handler"))

    @staticmethod
    def _provisioning(raw: object, path: Path) -> tuple[ProvisioningRequirement, ...]:
        if not raw:
            return ()
        if not isinstance(raw, list):
            raise ValueError(f"invalid provisioning requirements: {path}")
        return tuple(ProvisioningRequirement(str(item.get("package", "")), str(item.get("service", "")), str(item.get("reason", "")))
                     for item in raw if isinstance(item, dict) and item.get("package"))

    def _initialize(self, record: PluginRecord) -> None:
        try:
            entrypoint = record.manifest.root / "plugin.py"
            if not entrypoint.is_file():
                raise FileNotFoundError(entrypoint)
            spec = importlib.util.spec_from_file_location(f"lulu_plugin_{record.manifest.plugin_id}", entrypoint)
            if spec is None or spec.loader is None:
                raise ImportError(f"cannot load {entrypoint}")
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            register: Callable[[PluginContext], object] = getattr(module, "register")
            register(PluginContext(record, logging.getLogger(f"lulu.plugin.{record.manifest.plugin_id}")))
            record.health = "available"
        except Exception as error:  # plugin isolation boundary
            record.health = "degraded"
            record.error = str(error)
            LOGGER.exception("plugin initialization failed id=%s", record.manifest.plugin_id)

    def enabled_records(self) -> tuple[PluginRecord, ...]:
        return tuple(record for record in self.records.values() if record.health == "available")

    def with_capability(self, capability: str) -> tuple[Any, ...]:
        return tuple(contribution for record in self.enabled_records()
                     for contribution in record.registrations.get(capability, ()))

    def for_plugin(self, plugin_id: str, capability: str) -> tuple[Any, ...]:
        record = self.records.get(plugin_id.casefold())
        if record is None or record.health != "available":
            return ()
        return tuple(record.registrations.get(capability, ()))

    def store_cards(self) -> tuple[StoreCardContribution, ...]:
        return tuple(card for record in self.enabled_records() for card in record.manifest.store_cards)

    def services(self) -> tuple[ServiceContribution, ...]:
        return tuple(service for record in self.enabled_records() for service in record.manifest.services)

    def browser_handoffs(self) -> tuple[BrowserHandoffContribution, ...]:
        return tuple(item for record in self.enabled_records() for item in record.manifest.browser_handoffs)

    def claim_browser_handoff(self, uri: str, source_origin: str):
        """Return (component, declaration, backend, trusted) for an external URI."""
        parsed = urlsplit(uri)
        origin = source_origin.rstrip("/").casefold()
        for record in self.enabled_records():
            for declaration in record.manifest.browser_handoffs:
                if parsed.scheme.casefold() not in declaration.schemes:
                    continue
                backends = record.registrations.get("browser_handoff", ())
                if backends:
                    return (record.manifest.plugin_id, declaration, backends[0],
                            origin in declaration.trusted_origins)
        return None

    def status(self) -> list[dict[str, object]]:
        return [{"id": record.manifest.plugin_id, "name": record.manifest.name,
                 "version": record.manifest.version, "health": record.health,
                 "capabilities": sorted(record.manifest.capabilities), "error": record.error}
                for record in self.records.values()]

    def components(self) -> tuple[ComponentDescriptor, ...]:
        return tuple(ComponentDescriptor(
            component_id=record.manifest.plugin_id,
            name=record.manifest.name,
            description=record.manifest.description,
            kind=record.manifest.kind,
            enabled=record.manifest.enabled and record.health == "available",
            installed=record.manifest.installed,
            capabilities=record.manifest.capabilities,
            dependencies=record.manifest.dependencies,
            configuration=record.manifest.configuration,
            secrets=record.manifest.secrets,
            store_cards=record.manifest.store_cards,
            services=record.manifest.services,
            browser_handoffs=record.manifest.browser_handoffs,
             provisioning=record.manifest.provisioning,
             provider_ids=record.manifest.provider_ids,
             source_plugin=record.manifest.plugin_id,
             authentication_methods=record.manifest.authentication_methods,
         ) for record in self.records.values())

    def resolve_selection(self, selected: set[str] | tuple[str, ...] | list[str]) -> DependencyPlan:
        """Resolve only outgoing dependencies of selected plugins."""
        requested = {str(item).casefold() for item in selected}
        unknown = sorted(item for item in requested if item not in self.records)
        selected_ids = set(requested) - set(unknown)
        missing: list[tuple[str, tuple[str, ...]]] = []
        visiting: set[str] = set()
        ordered: list[str] = []

        def visit(plugin_id: str) -> None:
            if plugin_id in visiting or plugin_id in ordered:
                return
            visiting.add(plugin_id)
            manifest = self.records[plugin_id].manifest
            for dependency in manifest.dependencies.requires_all:
                if dependency not in self.records:
                    unknown.append(dependency)
                else:
                    selected_ids.add(dependency)
                    visit(dependency)
            for alternatives in manifest.dependencies.requires_any:
                available = tuple(item for item in alternatives if item in self.records)
                if not available:
                    missing.append((plugin_id, alternatives))
                else:
                    selected_ids.add(available[0])
                    visit(available[0])
            visiting.remove(plugin_id)
            ordered.append(plugin_id)

        for plugin_id in sorted(tuple(selected_ids)):
            visit(plugin_id)
        return DependencyPlan(tuple(sorted(selected_ids)), tuple(ordered), tuple(missing), tuple(sorted(set(unknown))))


BUILTIN_COMPONENTS: tuple[ComponentDescriptor, ...] = (
    ComponentDescriptor(
        "metadata.igdb", "IGDB", "Canonical game metadata and artwork.", "builtin_metadata",
        capabilities=frozenset({"metadata"}), provider_ids=("metadata.igdb",),
        configuration=(
            ConfigurationField("enabled", "boolean", "Enable IGDB metadata",
                               "Allow Mudos to query IGDB for canonical identity and presentation metadata."),
            ConfigurationField("client_id", "text", "Client ID", "Your Twitch application client ID.", required=True),
        ),
        secrets=(SecretRequirement("client_secret", "Client Secret",
                                   "Write-only Twitch application client secret.", required=True,
                                   reference="metadata/igdb-client-secret"),),
    ),
    ComponentDescriptor(
        "metadata.steamgriddb", "SteamGridDB", "Preferred automatic cover artwork.", "builtin_metadata",
        capabilities=frozenset({"artwork"}), provider_ids=("metadata.steamgriddb",),
        configuration=(ConfigurationField("enabled", "boolean", "Enable SteamGridDB artwork",
                                          "Allow Mudos to use validated SteamGridDB covers after canonical identity resolution."),),
        secrets=(SecretRequirement("api_key", "API Key", "Write-only SteamGridDB API key.", required=True,
                                   reference="metadata/steamgriddb-api-key"),),
    ),
    ComponentDescriptor("retroarch", "RetroArch", "Classic console emulation.", "builtin_provider",
                        capabilities=frozenset({"catalogue", "launch", "settings"}), provider_ids=("retroarch",)),
    ComponentDescriptor("dolphin", "Dolphin", "GameCube and Wii emulation.", "builtin_provider",
                        capabilities=frozenset({"catalogue", "launch", "settings"}), provider_ids=("dolphin",)),
    ComponentDescriptor("pcsx2", "PCSX2", "PlayStation 2 emulation.", "builtin_provider",
                        capabilities=frozenset({"catalogue", "launch", "settings"}), provider_ids=("pcsx2",)),
    ComponentDescriptor("eden", "Eden", "Switch emulation and content components.", "builtin_provider",
                        capabilities=frozenset({"catalogue", "launch", "settings", "content_components"}), provider_ids=("eden",)),
)


class ComponentRegistry:
    """Single descriptor surface for OOBE/Admin and future setup flows."""

    def __init__(self, plugin_registry: PluginRegistry | None = None,
                 builtins: tuple[ComponentDescriptor, ...] = BUILTIN_COMPONENTS):
        self.plugins = plugin_registry
        self.builtins = builtins
        self._components: dict[str, ComponentDescriptor] = {}

    def discover(self) -> tuple[ComponentDescriptor, ...]:
        components = {item.component_id: item for item in self.builtins}
        if self.plugins is not None:
            for item in self.plugins.components():
                components[item.component_id] = item
        self._components = components
        return tuple(components.values())

    def get(self, component_id: str) -> ComponentDescriptor:
        return self._components[component_id.casefold()]

    def all(self) -> tuple[ComponentDescriptor, ...]:
        return tuple(self._components.values())

    def store_cards(self) -> tuple[StoreCardContribution, ...]:
        return tuple(card for component in self._components.values() if component.enabled
                     for card in component.store_cards)

    def services(self) -> tuple[ServiceContribution, ...]:
        return tuple(service for component in self._components.values() if component.enabled
                     for service in component.services)

    def setup_records(self, secrets: SecretStore | None = None) -> list[dict[str, object]]:
        """Return safe OOBE/Admin metadata; secret values are never included."""
        records: list[dict[str, object]] = []
        for component in self._components.values():
            store = PluginSecretBoundary(component.component_id, secrets)
            records.append({
                "id": component.component_id,
                "name": component.name,
                "description": component.description,
                "kind": component.kind,
                "enabled": component.enabled,
                "installed": component.installed,
                "capabilities": sorted(component.capabilities),
                "requires_all": list(component.dependencies.requires_all),
                "requires_any": [list(group) for group in component.dependencies.requires_any],
                "configuration": [{"key": field.key, "type": field.kind, "label": field.label,
                                   "description": field.description, "required": field.required,
                                   "secret": field.secret, "validation": field.validation,
                                   "default": field.default, "choices": list(field.choices)}
                                  for field in component.configuration],
                 "secrets": [{"slot": requirement.slot, "label": requirement.label,
                             "description": requirement.description, "required": requirement.required,
                             "configured": store.configured(requirement.slot)}
                             for requirement in component.secrets],
                 "authentication_methods": list(component.authentication_methods),
                "store_cards": [{"id": card.card_id, "label": card.label, "url": card.url,
                                 "glyph": card.glyph, "artwork": card.artwork,
                                 "browser_profile": card.browser_profile, "removable": card.removable}
                                for card in component.store_cards],
                "services": [{"id": service.service_id, "name": service.name,
                              "description": service.description, "url": service.url,
                              "health": service.health, "configurable": service.configurable}
                              for service in component.services],
                "browser_handoffs": [{"id": handoff.handoff_id, "schemes": list(handoff.schemes),
                                       "handler": handoff.handler,
                                       "trusted_origins": list(handoff.trusted_origins),
                                       "artifact_types": list(handoff.artifact_types)}
                                      for handoff in component.browser_handoffs],
                "providers": list(component.provider_ids),
            })
        return records

    def resolve_selection(self, selected: set[str] | tuple[str, ...] | list[str]) -> DependencyPlan:
        requested = {str(item).casefold() for item in selected}
        unknown = sorted(item for item in requested if item not in self._components)
        selected_ids = set(requested) - set(unknown)
        missing: list[tuple[str, tuple[str, ...]]] = []
        visiting: set[str] = set()
        ordered: list[str] = []

        def visit(component_id: str) -> None:
            if component_id in visiting or component_id in ordered:
                return
            visiting.add(component_id)
            descriptor = self._components[component_id]
            for dependency in descriptor.dependencies.requires_all:
                if dependency not in self._components:
                    unknown.append(dependency)
                else:
                    selected_ids.add(dependency)
                    visit(dependency)
            for alternatives in descriptor.dependencies.requires_any:
                available = tuple(item for item in alternatives if item in self._components)
                if not available:
                    missing.append((component_id, alternatives))
                else:
                    selected_ids.add(available[0])
                    visit(available[0])
            visiting.remove(component_id)
            ordered.append(component_id)

        for component_id in sorted(tuple(selected_ids)):
            visit(component_id)
        return DependencyPlan(tuple(sorted(selected_ids)), tuple(ordered), tuple(missing), tuple(sorted(set(unknown))))
