"""LAN-facing Questarr reverse proxy backed by the appliance PAM identity."""

from __future__ import annotations

import json
import logging
import os
import secrets as random_secrets
import threading
import time
from collections import defaultdict, deque
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .credential import SecretStore
from .managed_account import MANAGED_ADMIN_ACCOUNT, authenticate_managed_account

LOGGER = logging.getLogger("lulu.questarr-auth-proxy")
PUBLIC_HOST = "0.0.0.0"
PUBLIC_PORT = 5000
UPSTREAM = "http://127.0.0.1:5002"
INTERNAL_NAMESPACE = "web/questarr"
QUESTARR_PAM_ACCOUNT = os.environ.get("LULU_QUESTARR_PAM_ACCOUNT", "josh")
_LOGIN_LOCK = threading.Lock()
_LOGIN_ATTEMPTS: dict[str, deque[float]] = defaultdict(deque)
_LOGIN_CHECKS = 0
_PAM_SLOTS = threading.BoundedSemaphore(8)
_SESSION_LOCK = threading.Lock()
_PAM_SESSIONS: dict[str, float] = {}
_PAM_SESSION_TTL = 8 * 60 * 60
_PUBLIC_API_PATHS = {"/api/auth/status", "/api/health", "/api/config"}


def _allow_login_attempt(address: str, *, now: float | None = None) -> bool:
    global _LOGIN_CHECKS
    current = time.monotonic() if now is None else now
    with _LOGIN_LOCK:
        _LOGIN_CHECKS += 1
        attempts = _LOGIN_ATTEMPTS[address]
        while attempts and current - attempts[0] >= 900:
            attempts.popleft()
        if _LOGIN_CHECKS % 256 == 0:
            for stale in [key for key, values in _LOGIN_ATTEMPTS.items() if not values or current - values[-1] >= 900]:
                _LOGIN_ATTEMPTS.pop(stale, None)
            _LOGIN_ATTEMPTS[address]  # recreate after pruning if this address expired
            attempts = _LOGIN_ATTEMPTS[address]
        if len(attempts) >= 20:
            return False
        attempts.append(current)
        return True


def _json_request(path: str, value: dict[str, object] | None = None) -> tuple[int, bytes]:
    body = None if value is None else json.dumps(value).encode("utf-8")
    headers = {"Accept": "application/json"}
    if body is not None:
        headers["Content-Type"] = "application/json"
    try:
        with urlopen(Request(UPSTREAM + path, data=body, headers=headers,
                            method="GET" if body is None else "POST"), timeout=10) as response:
            return response.status, response.read(1_048_576)
    except HTTPError as error:
        return error.code, error.read(1_048_576)
    except (URLError, TimeoutError, OSError):
        return 503, b'{"error":"Questarr is unavailable"}'


def _internal_password() -> str | None:
    secrets = SecretStore()
    username = secrets.get(INTERNAL_NAMESPACE, "username")
    password = secrets.get(INTERNAL_NAMESPACE, "password")
    if not username or not password:
        return None
    return password


def provision_internal_identity() -> bool:
    """Create Questarr's required private record without asking for a password."""
    secret_store = SecretStore()
    username = secret_store.get(INTERNAL_NAMESPACE, "username")
    password = secret_store.get(INTERNAL_NAMESPACE, "password")
    status, payload = _json_request("/api/auth/status")
    if status != 200:
        LOGGER.warning("Questarr auth status unavailable status=%d", status)
        return False
    try:
        has_users = json.loads(payload).get("hasUsers") is True
    except (ValueError, AttributeError):
        return False
    if not has_users:
        username = username or MANAGED_ADMIN_ACCOUNT
        password = password or random_secrets.token_urlsafe(48)
        # Persist the randomly generated credential only in Mudos SecretStore.
        secret_store.put(INTERNAL_NAMESPACE, "username", username)
        secret_store.put(INTERNAL_NAMESPACE, "password", password)
        status, _ = _json_request("/api/auth/setup", {"username": username, "password": password})
        if status not in {200, 201}:
            LOGGER.warning("Questarr managed first-run setup failed status=%d", status)
            return False
        LOGGER.info("Questarr internal identity provisioned from managed appliance configuration")
        return True
    if not username or not password:
        LOGGER.error("Questarr has an unlinked internal user; refusing to replace credentials")
        return False
    status, _ = _json_request("/api/auth/login", {"username": username, "password": password})
    if status != 200:
        LOGGER.warning("Questarr managed identity validation failed status=%d", status)
        return False
    return True


def _login_system_user(username: str, password: str) -> tuple[int, bytes]:
    if username != QUESTARR_PAM_ACCOUNT or not password:
        return 401, b'{"error":"Invalid appliance credentials"}'
    if not authenticate_managed_account(password, account=QUESTARR_PAM_ACCOUNT):
        return 401, b'{"error":"Invalid appliance credentials"}'
    secret_store = SecretStore()
    internal_user = secret_store.get(INTERNAL_NAMESPACE, "username")
    internal_password = _internal_password()
    if not internal_user or not internal_password:
        LOGGER.error("Questarr internal identity is not provisioned")
        return 503, b'{"error":"Questarr authentication is not configured"}'
    status, payload = _json_request("/api/auth/login", {
        "username": internal_user, "password": internal_password,
    })
    if status != 200:
        LOGGER.warning("Questarr internal login failed status=%d", status)
    return status, payload


def _create_pam_session() -> str:
    session = random_secrets.token_urlsafe(32)
    now = time.monotonic()
    with _SESSION_LOCK:
        if len(_PAM_SESSIONS) > 1024:
            for stale in [key for key, expiry in _PAM_SESSIONS.items() if expiry <= now]:
                _PAM_SESSIONS.pop(stale, None)
        _PAM_SESSIONS[session] = now + _PAM_SESSION_TTL
    return session


def _is_active_pam_session(cookie_header: str) -> bool:
    cookie = SimpleCookie()
    try:
        cookie.load(cookie_header)
        value = cookie.get("mudos_questarr_session")
    except Exception:
        return False
    if value is None:
        return False
    session = value.value
    now = time.monotonic()
    with _SESSION_LOCK:
        expiry = _PAM_SESSIONS.get(session, 0)
        if expiry <= now:
            _PAM_SESSIONS.pop(session, None)
            return False
        return True


def make_handler():
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"
        server_version = "MudosQuestarrAuth/1"

        def _response(self, status: int, payload: bytes, content_type: str = "application/json") -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store" if self.path.startswith("/api/auth/") else "no-cache")
            self.send_header("X-Content-Type-Options", "nosniff")
            if getattr(self, "_set_cookie", ""):
                self.send_header("Set-Cookie", self._set_cookie)
            self.end_headers()
            self.wfile.write(payload)

        def _has_pam_session(self) -> bool:
            return _is_active_pam_session(self.headers.get("Cookie", ""))

        def _handle(self) -> None:
            path = self.path
            if path.split("?", 1)[0] == "/api/auth/setup":
                self._response(403, b'{"error":"First-run setup is managed by Mudos"}')
                return
            if self.command == "POST" and path.split("?", 1)[0] == "/api/auth/login":
                if not _allow_login_attempt(self.client_address[0]):
                    self._response(429, b'{"error":"Too many login attempts"}')
                    return
                length = int(self.headers.get("Content-Length", "0"))
                if length <= 0 or length > 16_384:
                    self._response(400, b'{"error":"Invalid credentials request"}')
                    return
                try:
                    credentials = json.loads(self.rfile.read(length))
                    username = str(credentials.get("username", ""))
                    password = str(credentials.get("password", ""))
                except (ValueError, AttributeError, TypeError):
                    self._response(400, b'{"error":"Invalid credentials request"}')
                    return
                if len(password) > 1024:
                    self._response(401, b'{"error":"Invalid appliance credentials"}')
                    return
                if not _PAM_SLOTS.acquire(blocking=False):
                    self._response(429, b'{"error":"Authentication service is busy"}')
                    return
                try:
                    status, payload = _login_system_user(username, password)
                finally:
                    _PAM_SLOTS.release()
                if status == 200:
                    try:
                        token = json.loads(payload).get("token")
                    except (ValueError, AttributeError):
                        token = None
                    if not isinstance(token, str) or not token:
                        status, payload = 503, b'{"error":"Questarr authentication response was invalid"}'
                    else:
                        session = _create_pam_session()
                        self._set_cookie = ("mudos_questarr_session=" + session
                                            + "; HttpOnly; SameSite=Strict; Path=/; Max-Age=28800")
                self._response(status, payload)
                return

            path_only = path.split("?", 1)[0]
            if (path_only.startswith("/api/") and path_only not in _PUBLIC_API_PATHS
                    and not self._has_pam_session()):
                self._response(401, b'{"error":"Appliance authentication required"}')
                return
            if path_only.startswith("/socket.io") and not self._has_pam_session():
                self._response(401, b'{"error":"Appliance authentication required"}')
                return

            length = int(self.headers.get("Content-Length", "0"))
            if length < 0 or length > 64 * 1024 * 1024:
                self._response(413, b"request too large", "text/plain")
                return
            body = self.rfile.read(length) if length else None
            headers = {key: value for key, value in self.headers.items()
                       if key.lower() not in {"host", "connection", "content-length", "transfer-encoding",
                                              "accept-encoding", "upgrade", "sec-websocket-key",
                                              "sec-websocket-version", "sec-websocket-protocol"}}
            request = Request(UPSTREAM + path, data=body, headers=headers, method=self.command)
            try:
                with urlopen(request, timeout=120) as response:
                    payload = response.read(64 * 1024 * 1024 + 1)
                    if len(payload) > 64 * 1024 * 1024:
                        self._response(502, b"upstream response too large", "text/plain")
                        return
                    self._response(response.status, payload,
                                   response.headers.get("Content-Type", "application/octet-stream"))
            except HTTPError as error:
                self._response(error.code, error.read(64 * 1024 * 1024),
                               error.headers.get("Content-Type", "application/json"))
            except (URLError, TimeoutError, OSError):
                self._response(503, b'{"error":"Questarr is unavailable"}')

        do_GET = do_POST = do_PUT = do_PATCH = do_DELETE = do_OPTIONS = _handle

        def log_message(self, _format: str, *_args: object) -> None:
            # Avoid logging login payloads, tokens, query keys, or user content.
            return

    return Handler


def main() -> None:
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s %(message)s")
    provisioned = provision_internal_identity()
    if provisioned:
        try:
            from .questarr_reconciler import QuestarrReconciler
            reconciler = QuestarrReconciler()
            result = reconciler.reconcile()
            LOGGER.info("Questarr integration reconciled status=%s nzb_gateway=%s prowlarr=%s",
                        result.status, result.nzbget, result.prowlarr)

            def reconcile_loop(first_result) -> None:
                result = first_result
                while True:
                    if result.status == "ok":
                        return
                    time.sleep(30)
                    try:
                        result = reconciler.reconcile()
                    except Exception as error:
                        LOGGER.warning("Questarr periodic reconciliation failed error_type=%s",
                                       type(error).__name__)

            threading.Thread(target=reconcile_loop, args=(result,),
                             name="questarr-reconcile", daemon=True).start()
        except Exception as error:
            LOGGER.warning("Questarr integration reconciliation failed error_type=%s",
                           type(error).__name__)
    server = ThreadingHTTPServer((PUBLIC_HOST, PUBLIC_PORT), make_handler())
    server.daemon_threads = True
    LOGGER.info("Questarr PAM proxy listening on LAN port %d", PUBLIC_PORT)
    server.serve_forever()


if __name__ == "__main__":
    main()
