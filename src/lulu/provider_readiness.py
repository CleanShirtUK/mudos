"""Small persistent record of the last successful provider reconciliation.

Installation and account credentials are discovered at runtime by their
owners. This store records only validation/reconciliation outcomes and counts;
it never contains credentials or transient in-flight jobs.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
import threading
import time
from typing import Any

from .paths import PATHS


class ProviderReadinessStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or PATHS.data_root / "provider-readiness.json"
        self._lock = threading.RLock()
        # Reconciliation cannot survive process death as if still running.
        # Auth attempts, unlike reconciliation, may have a live GUI process;
        # keep a persisted approval-wait state until the auth owner observes it.
        for provider_id, value in self._load().items():
            if isinstance(value, dict) and value.get("status") == "syncing":
                try:
                    count = max(0, int(value.get("catalogue_count", 0)))
                except (TypeError, ValueError):
                    count = 0
                self.set(provider_id, "sync_failed",
                         message="Provider reconciliation was interrupted by a service restart.",
                         catalogue_count=count)

    def _load(self) -> dict[str, Any]:
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(value, dict):
                return value
        except (OSError, ValueError, json.JSONDecodeError):
            pass
        return {}

    def get(self, provider_id: str) -> dict[str, Any]:
        with self._lock:
            value = self._load().get(provider_id, {})
            return dict(value) if isinstance(value, dict) else {}

    def remove(self, provider_id: str) -> None:
        """Forget one provider's derived readiness during an explicit reset."""
        with self._lock:
            state = self._load()
            if provider_id not in state:
                return
            state.pop(provider_id, None)
            self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            os.chmod(self.path.parent, 0o700)
            fd, temporary = tempfile.mkstemp(prefix=".provider-readiness-", dir=self.path.parent)
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as stream:
                    json.dump(state, stream, sort_keys=True)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.chmod(temporary, 0o600)
                os.replace(temporary, self.path)
            finally:
                try:
                    os.unlink(temporary)
                except FileNotFoundError:
                    pass

    def set(self, provider_id: str, status: str, *, message: str = "",
            catalogue_count: int = 0, updated_at: int | None = None) -> dict[str, Any]:
        if status not in {"installing", "install_failed", "installed",
                          "authentication_required", "authenticating", "authorization_pending",
                          "auth_failed", "authenticated", "configuration_required",
                          "reconciling", "syncing", "sync_failed", "ready", "unavailable"}:
            raise ValueError("invalid provider readiness status")
        record = {"status": status, "message": message[:240],
                  "catalogue_count": max(0, int(catalogue_count)),
                  "updated_at": int(time.time()) if updated_at is None else int(updated_at)}
        with self._lock:
            state = self._load()
            state[provider_id] = record
            self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            os.chmod(self.path.parent, 0o700)
            fd, temporary = tempfile.mkstemp(prefix=".provider-readiness-", dir=self.path.parent)
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as stream:
                    json.dump(state, stream, sort_keys=True)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.chmod(temporary, 0o600)
                os.replace(temporary, self.path)
            finally:
                try:
                    os.unlink(temporary)
                except FileNotFoundError:
                    pass
        return record
