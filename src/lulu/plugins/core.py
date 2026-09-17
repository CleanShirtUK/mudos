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

PLUGIN_API_VERSION = 1
LOGGER = logging.getLogger("lulu.plugins")


@dataclass(frozen=True, slots=True)
class PluginManifest:
    plugin_id: str
    name: str
    version: str
    api_version: int
    capabilities: frozenset[str]
    root: Path
    enabled: bool = True


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
            manifest = PluginManifest(plugin_id, str(raw["name"]), str(raw.get("version", "1")),
                                      api_version, frozenset(key for key, value in capabilities.items() if value),
                                      path.parent, enabled)
            return PluginRecord(manifest, "disabled" if not enabled else "unavailable")
        except (OSError, tomllib.TOMLDecodeError, KeyError, TypeError, ValueError) as error:
            plugin_id = path.parent.name.casefold()
            manifest = PluginManifest(plugin_id, plugin_id, "invalid", 0, frozenset(), path.parent, False)
            return PluginRecord(manifest, "unavailable", str(error))

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

    def status(self) -> list[dict[str, object]]:
        return [{"id": record.manifest.plugin_id, "name": record.manifest.name,
                 "version": record.manifest.version, "health": record.health,
                 "capabilities": sorted(record.manifest.capabilities), "error": record.error}
                for record in self.records.values()]
