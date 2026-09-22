"""Authoritative configuration boundary for optional external services.

Ordinary provider configuration is layered from safe defaults, host config,
user config, and an explicit development override file. Secret values are
never accepted from TOML; providers refer to names in :class:`SecretStore`.
"""

from __future__ import annotations

from dataclasses import dataclass
import copy
import logging
import os
from pathlib import Path
import tomllib
from typing import Any, Mapping

from .credential import SecretStore
from .paths import PATHS


LOGGER = logging.getLogger("lulu.provider-config")
SYSTEM_CONFIG = Path("/etc/lulu/provider-services.toml")
USER_FILENAME = "provider-services.toml"

# No optional service is enabled by default. The structure is intentionally
# generic so new namespaces do not require a second configuration mechanism.
DEFAULT_CONFIG: dict[str, object] = {}
_SECRET_KEYS = {"api_key", "api-key", "password", "secret", "token", "client_secret", "client-secret"}


def _merge(base: dict[str, Any], overlay: Mapping[str, Any]) -> None:
    for key, value in overlay.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            _merge(base[key], value)
        else:
            base[key] = copy.deepcopy(value)


def _ordinary(value: object, path: str = "") -> object:
    """Copy TOML data while dropping plaintext secret-shaped settings."""
    if isinstance(value, dict):
        result: dict[str, object] = {}
        for key, child in value.items():
            normalized = str(key).casefold().replace("-", "_")
            # Keys inside `secrets` are references, never secret values.
            if normalized in {item.replace("-", "_") for item in _SECRET_KEYS} and not path.endswith(".secrets"):
                LOGGER.warning("ignored plaintext secret-shaped provider setting path=%s", f"{path}.{key}".lstrip("."))
                continue
            result[str(key)] = _ordinary(child, f"{path}.{key}".lstrip("."))
        return result
    if isinstance(value, list):
        return [_ordinary(item, path) for item in value]
    return value


def _read_layer(path: Path) -> dict[str, object]:
    try:
        with path.open("rb") as stream:
            value = tomllib.load(stream)
        if not isinstance(value, dict):
            raise ValueError("configuration root must be a table")
        return _ordinary(value)  # type: ignore[return-value]
    except FileNotFoundError:
        return {}
    except (OSError, tomllib.TOMLDecodeError, TypeError, ValueError) as error:
        LOGGER.warning("provider configuration ignored path=%s reason=%s", path, type(error).__name__)
        return {}


def _toml_string(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    if isinstance(value, float):
        return str(value)
    if isinstance(value, str):
        return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'
    raise ValueError(f"unsupported provider configuration value: {type(value).__name__}")


def _toml_dump(value: Mapping[str, object], prefix: str = "") -> str:
    lines: list[str] = []
    scalars = {key: child for key, child in value.items() if not isinstance(child, dict)}
    for key, child in scalars.items():
        if isinstance(child, (str, int, float, bool)):
            lines.append(f"{key} = {_toml_string(child)}")
    tables = [(key, child) for key, child in value.items() if isinstance(child, dict)]
    for key, child in tables:
        name = f"{prefix}.{key}" if prefix else key
        if lines:
            lines.append("")
        lines.append(f"[{name}]")
        lines.extend(_toml_dump(child, name).splitlines())
    return "\n".join(lines) + ("\n" if lines else "")
@dataclass(frozen=True, slots=True)
class ProviderConfiguration:
    """Safe view of one provider/service namespace."""

    provider_id: str
    values: Mapping[str, object]
    source: str
    secrets: SecretStore

    @property
    def enabled(self) -> bool:
        return bool(self.values.get("enabled", False))

    @property
    def secret_refs(self) -> Mapping[str, str]:
        value = self.values.get("secrets", {})
        return value if isinstance(value, dict) else {}

    @property
    def configured(self) -> bool:
        if not self.enabled:
            return False
        return all(self.secret_available(name) for name in self.secret_refs)

    @property
    def status(self) -> str:
        if not self.enabled:
            return "disabled"
        return "configured" if self.configured else "unconfigured"

    def get(self, name: str, default: object = None) -> object:
        return self.values.get(name, default)

    def secret_available(self, name: str) -> bool:
        reference = self.secret_refs.get(name)
        if not isinstance(reference, str) or not reference:
            return False
        namespace, separator, secret_name = reference.partition("/")
        if not separator or not namespace or not secret_name:
            return False
        return self.secrets.configured(namespace, secret_name)

    def secret(self, name: str) -> str | None:
        reference = self.secret_refs.get(name)
        if not isinstance(reference, str):
            return None
        namespace, separator, secret_name = reference.partition("/")
        if not separator or not namespace or not secret_name:
            return None
        return self.secrets.get(namespace, secret_name)

    def diagnostics(self) -> dict[str, object]:
        return {
            "provider": self.provider_id,
            "status": self.status,
            "source": self.source,
            "endpoint": self.get("endpoint", ""),
            "client_id_present": bool(self.get("client_id", "")),
            "secrets": {name: self.secret_available(name) for name in self.secret_refs},
        }


class ProviderConfigurationService:
    """Load all provider configuration through one deterministic boundary."""

    def __init__(self, *, system_path: Path = SYSTEM_CONFIG,
                 user_path: Path | None = None, override_path: Path | None = None,
                 secrets: SecretStore | None = None) -> None:
        self.system_path = system_path
        self.user_path = user_path or (PATHS.config_root / USER_FILENAME)
        self.override_path = override_path
        self.secrets = secrets or SecretStore()
        self._config, self._sources = self._load()

    @classmethod
    def from_environment(cls, *, system_path: Path = SYSTEM_CONFIG,
                         user_path: Path | None = None,
                         secrets: SecretStore | None = None) -> "ProviderConfigurationService":
        override = os.environ.get("LULU_PROVIDER_CONFIG")
        return cls(system_path=system_path, user_path=user_path,
                   override_path=Path(override).expanduser() if override else None,
                   secrets=secrets)

    def _load(self) -> tuple[dict[str, object], dict[str, str]]:
        result = copy.deepcopy(DEFAULT_CONFIG)
        sources: dict[str, str] = {}
        for path, label in ((self.system_path, "system"), (self.user_path, "user"),
                            (self.override_path, "environment")):
            if path is None:
                continue
            layer = _read_layer(path)
            _merge(result, layer)
            if layer:
                for namespace in layer:
                    sources[str(namespace)] = label
        return result, sources

    def provider(self, provider_id: str) -> ProviderConfiguration:
        value: object = self._config
        for part in provider_id.split("."):
            value = value.get(part, {}) if isinstance(value, dict) else {}
        return ProviderConfiguration(provider_id, value if isinstance(value, dict) else {},
                                     self._sources.get(provider_id.split(".")[0], "default"), self.secrets)

    def diagnostics(self, provider_id: str) -> dict[str, object]:
        return self.provider(provider_id).diagnostics()

    def update_provider(self, provider_id: str, values: Mapping[str, object],
                        secrets: Mapping[str, str] | None = None,
                        clear_secrets: set[str] | None = None) -> ProviderConfiguration:
        """Update the user layer without exposing or writing secret values.

        This is the shared mutation boundary for OOBE, controller tooling and
        the admin frontend. Secret values go directly to SecretStore; the TOML
        layer contains references only.
        """
        try:
            raw = tomllib.loads(self.user_path.read_text()) if self.user_path.exists() else {}
        except (OSError, tomllib.TOMLDecodeError):
            raw = {}
        merged_refs = dict(self.provider(provider_id).secret_refs)
        node: dict[str, object] = raw
        parts = provider_id.split(".")
        for part in parts[:-1]:
            child = node.get(part)
            if not isinstance(child, dict):
                child = {}
                node[part] = child
            node = child
        current = node.get(parts[-1])
        provider = current if isinstance(current, dict) else {}
        node[parts[-1]] = provider
        for key, value in values.items():
            if key not in {"password", "secret", "api_key", "token"}:
                provider[key] = value
        secret_refs = provider.setdefault("secrets", {})
        if not isinstance(secret_refs, dict):
            secret_refs = {}
            provider["secrets"] = secret_refs
        for name, value in (secrets or {}).items():
            if value:
                reference = secret_refs.get(name)
                if not isinstance(reference, str) or "/" not in reference:
                    reference = merged_refs.get(name)
                if not isinstance(reference, str) or "/" not in reference:
                    reference = f"{parts[0]}/{parts[0]}-{name.replace('_', '-')}"
                secret_refs[name] = reference
                namespace, _, secret_name = reference.partition("/")
                self.secrets.put(namespace, secret_name, value)
        for name in clear_secrets or set():
            reference = secret_refs.get(name)
            if isinstance(reference, str) and "/" in reference:
                namespace, _, secret_name = reference.partition("/")
                self.secrets.clear(namespace, secret_name)
        self.user_path.parent.mkdir(parents=True, exist_ok=True)
        self.user_path.write_text(_toml_dump(raw))
        os.chmod(self.user_path, 0o640)
        self._config, self._sources = self._load()
        return self.provider(provider_id)
