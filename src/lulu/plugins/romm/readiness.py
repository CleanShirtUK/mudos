"""Persistent RomM setup and initial-catalogue readiness state.

The encrypted API token never enters this file. A one-way configuration
fingerprint ties readiness to the current URL/token pair so replacing either
credential invalidates an old Ready result.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import tempfile
import time
from typing import Any

from ...paths import PATHS
from .client import RommConfig


_STATUSES = frozenset({
    "not_selected", "selected", "installed", "missing_configuration",
    "configuration_invalid", "authenticated", "syncing", "sync_failed", "ready",
})


class RommReadinessStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or PATHS.data_root / "romm" / "readiness.json"
        current = self._read()
        if current.get("status") == "syncing":
            config = RommConfig.from_file()
            fingerprint = str(current.get("config_fingerprint", ""))
            if self.fingerprint(config) == fingerprint:
                self.set("sync_failed", config,
                         message="RomM catalogue reconciliation was interrupted by a service restart.",
                         record_count=int(current.get("record_count", 0)),
                         installable_count=int(current.get("installable_count", 0)))
            elif config is None:
                self.set("missing_configuration", None,
                         message="RomM configuration changed while reconciliation was interrupted.")
            else:
                self.set("installed", config,
                         message="RomM configuration changed while reconciliation was interrupted.")

    @staticmethod
    def fingerprint(config: RommConfig | None, token: str | None = None) -> str:
        if config is None:
            return ""
        secret = token if token is not None else config.client_token
        material = f"{config.server_url.rstrip('/')}\0{secret}".encode("utf-8")
        return hashlib.sha256(material).hexdigest()

    def _read(self) -> dict[str, Any]:
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(value, dict) and value.get("status") in _STATUSES:
                return value
        except (OSError, ValueError, json.JSONDecodeError):
            pass
        return {}

    def snapshot(self, *, selected: bool, installed: bool,
                 config: RommConfig | None = None) -> dict[str, Any]:
        fingerprint = self.fingerprint(config)
        if not selected:
            return {"status": "not_selected", "message": "RomM was not selected.",
                    "record_count": 0, "installable_count": 0}
        if not installed:
            return {"status": "selected", "message": "RomM component is unavailable.",
                    "record_count": 0, "installable_count": 0}
        if config is None or not config.client_token:
            return {"status": "missing_configuration",
                    "message": "RomM server URL and Client API Token are required.",
                    "record_count": 0, "installable_count": 0}
        current = self._read()
        if current.get("config_fingerprint") != fingerprint:
            return {"status": "installed", "message": "RomM is installed but not validated.",
                    "record_count": 0, "installable_count": 0}
        return {key: value for key, value in current.items() if key != "config_fingerprint"}

    def set(self, status: str, config: RommConfig | None, *, message: str = "",
            record_count: int | None = None, installable_count: int | None = None,
            token: str | None = None) -> dict[str, Any]:
        if status not in _STATUSES:
            raise ValueError(f"unsupported RomM readiness status: {status}")
        value: dict[str, Any] = {
            "status": status,
            "config_fingerprint": self.fingerprint(config, token),
            "message": message[:240],
            "updated_at": int(time.time()),
        }
        previous = self._read()
        if record_count is not None:
            value["record_count"] = max(0, int(record_count))
        elif previous.get("config_fingerprint") == value["config_fingerprint"]:
            value["record_count"] = max(0, int(previous.get("record_count", 0)))
        else:
            value["record_count"] = 0
        if installable_count is not None:
            value["installable_count"] = max(0, int(installable_count))
        elif previous.get("config_fingerprint") == value["config_fingerprint"]:
            value["installable_count"] = max(0, int(previous.get("installable_count", 0)))
        else:
            value["installable_count"] = 0
        if status in {"authenticated", "syncing", "ready"}:
            value["authenticated_at"] = previous.get("authenticated_at", int(time.time()))
        if status == "ready":
            value["synced_at"] = int(time.time())
        elif status == "sync_failed":
            if previous.get("config_fingerprint") == value["config_fingerprint"]:
                for key in ("authenticated_at", "synced_at"):
                    if key in previous:
                        value[key] = previous[key]

        self.path.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
        os.chmod(self.path.parent, 0o700)
        descriptor, temporary = tempfile.mkstemp(prefix=".romm-readiness-", dir=self.path.parent)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                json.dump(value, stream, sort_keys=True)
                stream.flush()
                os.fsync(stream.fileno())
            os.chmod(temporary, 0o600)
            os.replace(temporary, self.path)
        finally:
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass
        return {key: item for key, item in value.items() if key != "config_fingerprint"}
