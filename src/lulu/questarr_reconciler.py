"""Idempotently reconcile Mudos-owned services into Questarr's HTTP API."""

from __future__ import annotations

from dataclasses import dataclass
import json
import logging
import base64
import errno
import fcntl
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen
from email.utils import parsedate_to_datetime

from .credential import SecretStore
from .provider_config import ProviderConfigurationService
from .questarr_paths import questarr_post_processing_readiness

LOGGER = logging.getLogger("lulu.questarr-reconciler")
QUESTARR_URL = "http://127.0.0.1:5002"
MANAGED_MARKER = "mudos.questarr"


def _jwt_expiry(token: str) -> int:
    """Read exp locally; signature verification remains Questarr's job."""
    try:
        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        value = json.loads(base64.urlsafe_b64decode(payload).decode("utf-8"))
        return int(value.get("exp", 0) or 0)
    except (IndexError, ValueError, TypeError, KeyError, UnicodeError):
        return 0


def _retry_after(error: HTTPError) -> int | None:
    value = error.headers.get("Retry-After") if error.headers else None
    if not value:
        return None
    try:
        return max(1, int(value))
    except ValueError:
        try:
            date = parsedate_to_datetime(value)
            if date.tzinfo is None:
                date = date.replace(tzinfo=timezone.utc)
            return max(1, int(date.timestamp() - time.time()))
        except (TypeError, ValueError, OverflowError):
            return None


class QuestarrApiError(RuntimeError):
    pass


class QuestarrUnauthorized(QuestarrApiError):
    pass


class QuestarrRateLimited(QuestarrApiError):
    def __init__(self, retry_after: int | None = None) -> None:
        self.retry_after = retry_after
        super().__init__("Questarr reconciliation deferred: authentication rate limited")


class QuestarrApi:
    def __init__(self, base_url: str = QUESTARR_URL,
                 opener: Callable[..., Any] | None = None,
                 cache_path: Path | None = None) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = ""
        self.token_expiry = 0
        self._username = ""
        self._password = ""
        self.cache_path = cache_path or Path(os.environ.get(
            "XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")) / "lulu/questarr-session.json"
        self._opener = opener or urlopen

    def _request(self, method: str, path: str, body: object | None = None) -> Any:
        headers = {"Accept": "application/json"}
        payload = None
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        if body is not None:
            payload = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"
        request = Request(self.base_url + path, data=payload, headers=headers, method=method)
        try:
            with self._opener(request, timeout=15) as response:
                raw = response.read()
        except HTTPError as error:
            if error.code in (401, 403):
                raise QuestarrUnauthorized("Questarr session expired") from error
            if error.code == 429:
                retry_after = _retry_after(error)
                self._defer(retry_after)
                raise QuestarrRateLimited(retry_after) from error
            raise QuestarrApiError(f"Questarr request failed: HTTP {error.code}") from error
        except (URLError, TimeoutError, OSError) as error:
            raise QuestarrApiError(f"Questarr request failed: {type(error).__name__}") from error
        try:
            return json.loads(raw) if raw else {}
        except (ValueError, TypeError) as error:
            raise QuestarrApiError("Questarr returned invalid JSON") from error

    def login(self, username: str, password: str) -> None:
        self._username, self._password = username, password
        result = self._request("POST", "/api/auth/login", {"username": username, "password": password})
        token = result.get("token") if isinstance(result, dict) else None
        if not isinstance(token, str) or not token:
            raise QuestarrApiError("Questarr authentication failed")
        self.token = token
        self.token_expiry = _jwt_expiry(token)
        self._save_cache()
        try:
            self.cache_path.with_suffix(".deferred").unlink(missing_ok=True)
        except OSError:
            pass

    def ensure_authenticated(self, username: str, password: str) -> None:
        self._username, self._password = username, password
        if self._valid_token():
            return
        lock_path = self.cache_path.with_suffix(".auth.lock")
        lock_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        with lock_path.open("a+", encoding="ascii") as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            try:
                # Another backend process may have authenticated while this
                # process was waiting for the single-flight lock.
                self._load_cache()
                if self._valid_token():
                    return
                self._check_deferred()
                self.login(username, password)
            finally:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)

    def invalidate(self) -> None:
        self.token = ""
        self.token_expiry = 0
        self._save_cache()

    def get(self, path: str) -> Any:
        return self._authenticated_request("GET", path)

    def post(self, path: str, body: object) -> Any:
        return self._authenticated_request("POST", path, body)

    def patch(self, path: str, body: object) -> Any:
        return self._authenticated_request("PATCH", path, body)

    def _authenticated_request(self, method: str, path: str, body: object | None = None) -> Any:
        try:
            return self._request(method, path, body)
        except QuestarrUnauthorized:
            if not self._username or not self._password:
                raise
            self.invalidate()
            self._check_deferred()
            self.login(self._username, self._password)
            return self._request(method, path, body)

    def _valid_token(self) -> bool:
        return bool(self.token) and (not self.token_expiry or self.token_expiry > int(time.time()) + 30)

    def _load_cache(self) -> None:
        try:
            value = json.loads(self.cache_path.read_text(encoding="utf-8"))
            self.token = str(value.get("token", ""))
            self.token_expiry = int(value.get("exp", 0) or 0)
        except (OSError, ValueError, TypeError):
            self.token, self.token_expiry = "", 0

    def _save_cache(self) -> None:
        try:
            self.cache_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            temporary = self.cache_path.with_suffix(".tmp")
            temporary.write_text(json.dumps({"token": self.token, "exp": self.token_expiry},
                                             separators=(",", ":")), encoding="utf-8")
            temporary.chmod(0o600)
            temporary.replace(self.cache_path)
        except OSError:
            LOGGER.warning("Questarr runtime session cache unavailable")

    def _defer(self, retry_after: int | None) -> None:
        marker = self.cache_path.with_suffix(".deferred")
        attempts = 0
        try:
            previous = json.loads(marker.read_text(encoding="utf-8"))
            attempts = int(previous.get("attempts", 0))
        except (OSError, ValueError, TypeError):
            pass
        delay = max(1, min(retry_after or (30 * (2 ** min(attempts, 3))), 300))
        try:
            self.cache_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            marker.write_text(json.dumps({"until": int(time.time()) + delay,
                                          "attempts": attempts + 1}, separators=(",", ":")), encoding="ascii")
            marker.chmod(0o600)
        except OSError:
            pass

    def _check_deferred(self) -> None:
        marker = self.cache_path.with_suffix(".deferred")
        try:
            value = json.loads(marker.read_text(encoding="ascii"))
            until = int(value.get("until", 0))
            if until > int(time.time()):
                raise QuestarrRateLimited(until - int(time.time()))
            marker.unlink(missing_ok=True)
        except FileNotFoundError:
            return
        except ValueError:
            marker.unlink(missing_ok=True)


@dataclass(frozen=True, slots=True)
class ReconcileResult:
    status: str
    transmission: str
    nzbget: str
    prowlarr: str
    indexers: dict[str, int]
    metadata: str = "unavailable"
    post_processing: str = "unavailable"


def _marker(settings: object, role: str) -> bool:
    if not isinstance(settings, str):
        return False
    try:
        value = json.loads(settings)
    except (TypeError, ValueError):
        return False
    return isinstance(value, dict) and value.get("owner") == MANAGED_MARKER and value.get("role") == role


def _endpoint_fields(endpoint: object, default_port: int, *, drop_path: bool = False) -> dict[str, object]:
    """Translate Mudos' full service endpoint into Questarr's fields."""
    raw = str(endpoint or "")
    parsed = urlsplit(raw if "://" in raw else f"http://{raw}")
    scheme = parsed.scheme if parsed.scheme in {"http", "https"} else "http"
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or default_port
    path = "" if drop_path else (parsed.path or "")
    return {
        "url": f"{scheme}://{host}", "port": port,
        "useSsl": scheme == "https", "urlPath": path,
    }


class QuestarrReconciler:
    def __init__(self, *, api: QuestarrApi | None = None,
                 config: ProviderConfigurationService | None = None,
                 secrets: SecretStore | None = None,
                 lock_path: Path | None = None) -> None:
        self.secrets = secrets or SecretStore()
        self.config = config or ProviderConfigurationService.from_environment(secrets=self.secrets)
        self.api = api or QuestarrApi()
        self.lock_path = lock_path or Path(os.environ.get(
            "XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")) / "lulu/questarr-reconcile.lock"

    def _provider_secret(self, provider: str, key: str) -> str | None:
        return self.config.provider(provider).secret(key)

    def _downloader(self, role: str, desired: dict[str, object]) -> str:
        existing = self.api.get("/api/downloaders")
        if not isinstance(existing, list):
            raise QuestarrApiError("Questarr returned invalid downloader data")
        managed = next((item for item in existing if isinstance(item, dict) and _marker(item.get("settings"), role)), None)
        equivalent = next((item for item in existing if isinstance(item, dict)
                           and item.get("type") == desired["type"]
                           and item.get("url") == desired["url"]
                           and item.get("port") == desired["port"]), None)
        marker = json.dumps({"owner": MANAGED_MARKER, "role": role}, separators=(",", ":"))
        desired = {**desired, "settings": marker}
        if managed is not None:
            result = self.api.patch(f"/api/downloaders/{managed['id']}", desired)
            downloader_id = str(managed["id"])
            action = "updated" if result else "unchanged"
        elif equivalent is not None:
            # Do not adopt or overwrite an unmarked user entry.
            downloader_id = str(equivalent["id"])
            action = "manual-equivalent"
        else:
            result = self.api.post("/api/downloaders", desired)
            if not isinstance(result, dict) or "id" not in result:
                raise QuestarrApiError("Questarr did not return a downloader id")
            downloader_id = str(result["id"])
            action = "created"
        test = self.api.post(f"/api/downloaders/{downloader_id}/test", {})
        if not isinstance(test, dict) or not test.get("success"):
            raise QuestarrApiError(f"Questarr {role} connection test failed")
        return action

    def reconcile(self) -> ReconcileResult:
        try:
            self.lock_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            with self.lock_path.open("a+", encoding="ascii") as lock:
                try:
                    fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                except OSError as error:
                    if error.errno in (errno.EACCES, errno.EAGAIN):
                        return ReconcileResult("deferred", "coalesced", "coalesced", "coalesced", {})
                    raise
                try:
                    return self._reconcile_unlocked()
                finally:
                    fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
        except QuestarrRateLimited:
            LOGGER.warning("questarr reconciliation deferred: authentication rate limited")
            return ReconcileResult("deferred", "rate-limited", "rate-limited", "rate-limited", {})

    def _reconcile_unlocked(self) -> ReconcileResult:
        web = self.secrets.get("web/questarr", "username")
        password = self.secrets.get("web/questarr", "password")
        if not web or not password:
            return ReconcileResult("unconfigured", "skipped", "skipped", "skipped", {})
        if isinstance(self.api, QuestarrApi):
            self.api.ensure_authenticated(web, password)
        else:
            self.api.login(web, password)
        usenet = self.config.provider("providers.usenet")
        if not usenet.configured:
            return ReconcileResult("unconfigured", "skipped", "skipped", "skipped", {})
        # Questarr must submit through Acquisitiond, never the real NZBGet
        # endpoint. The loopback gateway projects Acquisitiond-owned jobs.
        nzbget_endpoint = _endpoint_fields("http://127.0.0.1:5001", 5001, drop_path=True)
        nzbget = self._downloader("nzbget", {
            "name": "Mudos NZBGet", "type": "nzbget", **nzbget_endpoint,
            "username": "", "password": "", "urlPath": "/xmlrpc",
            "enabled": True, "priority": 1, "category": "questarr", "label": "questarr",
        })
        prowlarr = self.config.provider("providers.prowlarr")
        prowlarr_status = "skipped"
        if prowlarr.configured:
            try:
                self.api.post("/api/indexers/prowlarr/sync", {
                    "url": prowlarr.get("endpoint", ""), "apiKey": prowlarr.secret("api_key") or "",
                })
                prowlarr_status = "synced"
            except QuestarrRateLimited:
                raise
            except QuestarrApiError:
                LOGGER.warning("Questarr Prowlarr sync is degraded")
                prowlarr_status = "degraded"
        metadata = self.config.provider("metadata.igdb")
        metadata_status = "incomplete"
        if metadata.configured:
            try:
                self.api.post("/api/settings/igdb", {
                    "clientId": metadata.get("client_id", ""),
                    "clientSecret": metadata.secret("client_secret") or "",
                })
                metadata_status = "configured"
            except QuestarrRateLimited:
                raise
            except QuestarrApiError:
                LOGGER.warning("Questarr IGDB configuration projection is degraded")
                metadata_status = "degraded"
        indexers = self.api.get("/api/indexers")
        counts = {"total": len(indexers) if isinstance(indexers, list) else 0,
                  "torrent": 0, "usenet": 0}
        for item in indexers if isinstance(indexers, list) else []:
            protocol = str(item.get("protocol", "")).casefold() if isinstance(item, dict) else ""
            counts["usenet" if protocol == "newznab" else "torrent"] += 1
        import_ready, _reason = questarr_post_processing_readiness()
        settings = self.api.get("/api/imports/config")
        if not isinstance(settings, dict):
            raise QuestarrApiError("Questarr returned invalid import configuration")
        desired_post_processing = bool(import_ready)
        if settings.get("enablePostProcessing") is not desired_post_processing:
            self.api.patch("/api/imports/config", {
                "enablePostProcessing": desired_post_processing,
            })
        post_processing = "enabled" if desired_post_processing else "safely-disabled"
        status = "ok" if import_ready else "degraded"
        return ReconcileResult(status, "deferred-until-torrent-gateway", nzbget,
                               prowlarr_status, counts, metadata_status, post_processing)
