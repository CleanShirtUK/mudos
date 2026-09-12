"""Typed settings ownership and persistence boundary."""

from dataclasses import dataclass
import json
from pathlib import Path
import sqlite3
from typing import Any


@dataclass(frozen=True, slots=True)
class SettingSpec:
    key: str
    category: str
    value_type: type
    default: Any
    writable: bool = True
    label: str = ""
    kind: str = "value"
    options: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.kind not in {"value", "toggle", "select"}:
            raise ValueError(f"unsupported setting kind: {self.kind}")
        if self.kind == "toggle" and self.value_type is not bool:
            raise TypeError("toggle settings must use bool values")
        if self.kind == "select" and (self.value_type is not str or not self.options):
            raise TypeError("select settings must use non-empty string options")

    @property
    def display_label(self) -> str:
        return self.label or self.key.rsplit(".", 1)[-1].replace("_", " ").title()


SETTING_SPECS = (
    SettingSpec("display.output", "Display", str, "auto", label="Presentation output", kind="select", options=("auto",)),
    SettingSpec("display.mode", "Display", str, "auto", label="Display mode", kind="select", options=("auto", "deployment")),
    SettingSpec("audio.output", "Audio", str, "auto", label="Audio output", kind="select", options=("auto",)),
    SettingSpec("controllers.navigation_owner", "Controllers", str, "auto", label="Navigation owner", kind="select", options=("auto",)),
    SettingSpec("storage.library_root", "Storage", str, "managed", label="Game storage", kind="select", options=("managed",)),
    SettingSpec("network.enabled", "Network", bool, True, label="Network", kind="toggle"),
    SettingSpec("applications.auto_update", "Applications", bool, False, label="Automatic updates", kind="toggle"),
    SettingSpec("runtime.retroarch_ready", "Applications", bool, False, writable=False),
    SettingSpec("runtime.pcsx2_ready", "Applications", bool, False, writable=False),
    SettingSpec("runtime.dolphin_ready", "Applications", bool, False, writable=False),
    SettingSpec("power.confirm_shutdown", "Power", bool, True, label="Confirm shutdown", kind="toggle"),
)


class SettingsStore:
    """Persist only Lulu-owned values; read-only readiness is not user-writable."""

    def __init__(self, path: Path, specs: tuple[SettingSpec, ...] = SETTING_SPECS) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(path)
        self.connection.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        self.connection.commit()
        self.specs: dict[str, SettingSpec] = {}
        for spec in specs:
            self.register(spec)

    def register(self, spec: SettingSpec) -> None:
        """Register a setting without changing the persistence schema."""
        if spec.key in self.specs:
            raise ValueError(f"setting already registered: {spec.key}")
        self.specs[spec.key] = spec

    def specs_for(self, category: str) -> tuple[SettingSpec, ...]:
        return tuple(spec for spec in self.specs.values() if spec.category == category)

    def get(self, key: str) -> Any:
        spec = self._spec(key)
        row = self.connection.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return spec.default if row is None else self._decode(spec, row[0])

    def set(self, key: str, value: Any) -> None:
        spec = self._spec(key)
        if not spec.writable:
            raise ValueError(f"setting is read-only: {key}")
        if type(value) is not spec.value_type:
            raise TypeError(f"invalid type for {key}: expected {spec.value_type.__name__}")
        if spec.options and value not in spec.options:
            raise ValueError(f"invalid option for {key}: {value}")
        self.connection.execute(
            "INSERT INTO settings(key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, json.dumps(value)),
        )
        self.connection.commit()

    def _spec(self, key: str) -> SettingSpec:
        try:
            return self.specs[key]
        except KeyError as error:
            raise KeyError(f"unknown setting: {key}") from error

    @staticmethod
    def _decode(spec: SettingSpec, value: str) -> Any:
        decoded = json.loads(value)
        if type(decoded) is not spec.value_type:
            raise ValueError(f"persisted setting has invalid type: {spec.key}")
        return decoded
