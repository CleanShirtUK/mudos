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


SETTING_SPECS = (
    SettingSpec("display.output", "Display", str, "auto"),
    SettingSpec("display.mode", "Display", str, "auto"),
    SettingSpec("audio.output", "Audio", str, "auto"),
    SettingSpec("controllers.navigation_owner", "Controllers", str, "auto"),
    SettingSpec("dolphin.wii_remote_mode", "Controllers", str, "standard"),
    SettingSpec("storage.library_root", "Storage", str, "managed"),
    SettingSpec("network.enabled", "Network", bool, True),
    SettingSpec("applications.auto_update", "Applications", bool, False),
    SettingSpec("runtime.retroarch_ready", "Applications", bool, False, writable=False),
    SettingSpec("runtime.pcsx2_ready", "Applications", bool, False, writable=False),
    SettingSpec("runtime.dolphin_ready", "Applications", bool, False, writable=False),
    SettingSpec("power.confirm_shutdown", "Power", bool, True),
    SettingSpec("launch_overlay_enabled", "Lulu", bool, True),
)


class SettingsStore:
    """Persist only Lulu-owned values; read-only readiness is not user-writable."""

    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(path)
        self.connection.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        self.connection.commit()
        self.specs = {spec.key: spec for spec in SETTING_SPECS}

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
