"""Small authenticated appliance administration frontend.

The HTTP layer is intentionally boring: it renders HTML and delegates
configuration mutation to ProviderConfigurationService and SecretStore.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import html
import http.server
import json
import os
from pathlib import Path
import secrets
import subprocess
import time
import urllib.parse
import urllib.error
import urllib.request
from typing import Any

from .credential import SecretStore
from .provider_config import ProviderConfigurationService
from .paths import PATHS

PORT = 80
SESSION_SECONDS = 1800
ADMIN_NAMESPACE = "admin"
ADMIN_SECRET = "password-hash"

PROVIDERS = (
    ("providers.steam", "Steam"), ("providers.romm", "RomM"),
    ("metadata.igdb", "IGDB / metadata"), ("providers.torrent", "Transmission"),
    ("providers.usenet", "NZBGet"), ("providers.usenet.server", "Usenet news server"),
    ("providers.prowlarr", "Prowlarr"),
)

SERVICES = (
    ("dufs", "File Manager — DUFS", "lulu-file-browser.service", "http", 8080, "/", True),
    ("nzbget", "NZBGet", "nzbget.service", "http", 6789, "/", True),
    ("transmission", "Transmission", "lulu-transmission.service", "http", 9091, "/transmission/web/", True),
    ("questarr", "Questarr", "lulu-questarr.service", "http", 5000, "/", True, "/api/health"),
    ("sunshine", "Sunshine", "lulu-sunshine-dev.service", "https", 47990, "/", True),
)


def _hash_password(password: str, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 240_000)
    return f"pbkdf2-sha256$240000${base64.urlsafe_b64encode(salt).decode()}${base64.urlsafe_b64encode(digest).decode()}"


def _check_password(password: str, encoded: str) -> bool:
    try:
        algorithm, rounds, salt, expected = encoded.split("$", 3)
        if algorithm != "pbkdf2-sha256":
            return False
        actual = _hash_password(password, base64.urlsafe_b64decode(salt + "==")).split("$", 3)[3]
        return hmac.compare_digest(actual, expected) and int(rounds) == 240000
    except (ValueError, TypeError):
        return False


def _host(request: http.server.BaseHTTPRequestHandler) -> str:
    value = request.headers.get("Host", "mudos.local").split(":", 1)[0]
    return value if value else "mudos.local"


def _service_url(request: http.server.BaseHTTPRequestHandler, service: tuple[Any, ...]) -> str:
    _, _, _, protocol, port, path, *_ = service
    return f"{protocol}://{_host(request)}:{port}{path}"


def _service_url_from_service(service: tuple[Any, ...], host: str) -> str:
    _, _, _, protocol, port, path, *_ = service
    return f"{protocol}://{host}:{port}{path.rstrip('/')}"


def _deployment() -> str:
    root = Path(os.environ.get("LULU_INSTALL_ROOT", "/opt/lulu/current"))
    marker = root / "NON_PROMOTABLE"
    if marker.is_file():
        values = {}
        for line in marker.read_text(errors="replace").splitlines():
            if "=" in line:
                key, value = line.split("=", 1); values[key] = value
        return f"dev {values.get('head', 'unknown')} ({values.get('branch', 'unknown')})"
    release = root / "RELEASE"
    return release.read_text().strip() if release.is_file() else root.name


class AdminApp:
    def __init__(self) -> None:
        self.secrets = SecretStore()
        self.sessions: dict[str, tuple[float, str]] = {}
        self.config = ProviderConfigurationService.from_environment(secrets=self.secrets)

    def password_configured(self) -> bool:
        return self.secrets.configured(ADMIN_NAMESPACE, ADMIN_SECRET)

    def authenticate(self, password: str) -> bool:
        stored = self.secrets.get(ADMIN_NAMESPACE, ADMIN_SECRET)
        return bool(stored and _check_password(password, stored))

    def login(self) -> tuple[str, str]:
        token = secrets.token_urlsafe(32)
        csrf = secrets.token_urlsafe(24)
        self.sessions[token] = (time.time() + SESSION_SECONDS, csrf)
        return token, csrf

    def session(self, token: str | None) -> str | None:
        if not token or token not in self.sessions:
            return None
        expiry, csrf = self.sessions[token]
        if expiry < time.time():
            self.sessions.pop(token, None)
            return None
        return csrf

    def logout(self, token: str | None) -> None:
        if token:
            self.sessions.pop(token, None)

    def provider_rows(self) -> list[dict[str, object]]:
        rows = []
        for provider_id, name in PROVIDERS:
            config = self.config.provider(provider_id)
            rows.append({"id": provider_id, "name": name, "status": config.status,
                         "secrets": {key: config.secret_available(key) for key in config.secret_refs}})
        return rows

    def service_state(self, unit: str) -> str:
        try:
            result = subprocess.run(["systemctl", "is-active", unit], text=True,
                                    capture_output=True, timeout=2, check=False)
            return result.stdout.strip() or "inactive"
        except (OSError, subprocess.TimeoutExpired):
            return "unknown"

    def service_health(self, service: tuple[Any, ...]) -> str:
        path = service[7] if len(service) > 7 else ""
        if not path:
            return "n/a"
        try:
            with urllib.request.urlopen(_service_url_from_service(service, "127.0.0.1") + path, timeout=2) as response:
                return "healthy" if response.status == 200 else f"HTTP {response.status}"
        except (OSError, urllib.error.URLError, TimeoutError):
            return "unhealthy"

    def test_provider(self, provider_id: str) -> tuple[bool, str]:
        config = self.config.provider(provider_id)
        if provider_id == "providers.prowlarr":
            try:
                endpoint = str(config.get("endpoint", "")).rstrip("/")
                api_key = config.secret("api_key") or ""
                if not endpoint or not api_key:
                    return False, "Prowlarr is not configured"
                request = urllib.request.Request(
                    endpoint + "/api/v1/system/status",
                    headers={"X-Api-Key": api_key, "Accept": "application/json"},
                )
                with urllib.request.urlopen(request, timeout=5) as response:
                    status = json.loads(response.read())
                version = str(status.get("version", "unknown"))
                return True, f"Prowlarr API healthy (version {version})"
            except (OSError, urllib.error.URLError, ValueError, json.JSONDecodeError):
                return False, "Prowlarr API unavailable or not authenticated"
        if provider_id == "providers.usenet":
            try:
                import asyncio
                from .plugins.usenet import NzbGetClient, NzbGetConfig
                asyncio.run(NzbGetClient(NzbGetConfig(
                    endpoint=str(config.get("endpoint", "http://127.0.0.1:6789/jsonrpc")),
                    username=str(config.get("username", "mudos")), password=config.secret("rpc_password") or "",
                )).health())
                return True, "NZBGet RPC healthy"
            except Exception:
                return False, "NZBGet RPC unavailable or not authenticated"
        if provider_id == "providers.torrent":
            try:
                import asyncio
                from .plugins.torrent import TransmissionClient, TransmissionConfig
                asyncio.run(TransmissionClient(TransmissionConfig(
                    endpoint=str(config.get("endpoint", "http://127.0.0.1:9091/transmission/rpc")),
                    username=config.secret("username") or "", password=config.secret("password") or "",
                )).call("session_get", {"fields": ["version"]}))
                return True, "Transmission RPC healthy"
            except Exception:
                return False, "Transmission RPC unavailable or not authenticated"
        return False, "No normalized health check is available for this provider"


APP = AdminApp()


def _page(title: str, body: str) -> bytes:
    return ("<!doctype html><html><head><meta charset=utf-8><title>" + html.escape(title) +
            " — Mudos</title><style>body{font:16px sans-serif;max-width:960px;margin:2em auto;padding:0 1em}"
            "nav a{margin-right:1em}table{border-collapse:collapse;width:100%}td,th{padding:.5em;border-bottom:1px solid #ccc}"
            "input{padding:.35em;margin:.2em 0}fieldset{margin:1em 0} .ok{color:green}.error{color:#a00}</style></head>"
            f"<body><nav><a href=/>Dashboard</a><a href=/providers>Providers</a><a href=/services>Services</a>"
            f"<form method=post action=/logout style='display:inline'><button>Logout</button></form></nav><h1>{html.escape(title)}</h1>{body}</body></html>").encode()


class Handler(http.server.BaseHTTPRequestHandler):
    server_version = "MudosAdmin/1"

    def log_message(self, format: str, *args: object) -> None:
        # Never log form bodies, credentials, or session tokens.
        super().log_message("%s", format % args)

    def _token(self) -> str | None:
        value = self.headers.get("Cookie", "")
        for part in value.split(";"):
            if part.strip().startswith("mudos_session="):
                return part.strip().split("=", 1)[1]
        return None

    def _send(self, content: bytes, status: int = 200, headers: dict[str, str] | None = None) -> None:
        self.send_response(status); self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        for key, value in (headers or {}).items(): self.send_header(key, value)
        self.end_headers(); self.wfile.write(content)

    def _redirect(self, location: str, cookie: str | None = None) -> None:
        headers = {"Location": location}
        if cookie: headers["Set-Cookie"] = cookie
        self._send(b"", 303, headers)

    def _form(self) -> dict[str, list[str]]:
        length = int(self.headers.get("Content-Length", "0"))
        return urllib.parse.parse_qs(self.rfile.read(length).decode(), keep_blank_values=True)

    def _require(self) -> str | None:
        csrf = APP.session(self._token())
        if csrf is None:
            self._redirect("/login")
        return csrf

    def do_GET(self) -> None:
        if self.path == "/login":
            message = "" if APP.password_configured() else "<p class=error>Admin credential is not bootstrapped. Run scripts/bootstrap-admin.sh.</p>"
            self._send(_page("Sign in", message + "<form method=post><label>Password <input type=password name=password autofocus></label><button>Sign in</button></form>")); return
        if self._require() is None: return
        if self.path == "/": self._dashboard(); return
        if self.path == "/providers": self._providers(); return
        if self.path.startswith("/provider/"): self._provider_form(urllib.parse.unquote(self.path[10:])); return
        if self.path == "/services": self._services(); return
        self._send(_page("Not found", "<p>Not found.</p>"), 404)

    def do_POST(self) -> None:
        if self.path == "/login":
            if self.authenticate_form(): return
            self._send(_page("Sign in", "<p class=error>Invalid credentials.</p><form method=post><input type=password name=password autofocus><button>Sign in</button></form>"), 401); return
        token = self._token(); csrf = APP.session(token)
        if csrf is None: self._redirect("/login"); return
        form = self._form()
        if not hmac.compare_digest(form.get("csrf", [""])[0], csrf):
            self._send(_page("Request rejected", "<p class=error>Invalid CSRF token.</p>"), 403); return
        if self.path == "/logout": APP.logout(token); self._redirect("/login", "mudos_session=; Max-Age=0; HttpOnly; SameSite=Lax"); return
        if self.path.startswith("/provider/"):
            self._save_provider(urllib.parse.unquote(self.path[10:]), form, token); return
        if self.path.startswith("/test/"):
            ok, message = APP.test_provider(urllib.parse.unquote(self.path[6:])); self._send(_page("Provider test", f"<p class={'ok' if ok else 'error'}>{html.escape(message)}</p><p><a href=/providers>Back</a></p>")); return
        self._send(_page("Not found", "<p>Not found.</p>"), 404)

    def authenticate_form(self) -> bool:
        form = self._form(); password = form.get("password", [""])[0]
        if not APP.authenticate(password): return False
        token, csrf = APP.login()
        self._redirect("/", f"mudos_session={token}; Max-Age={SESSION_SECONDS}; HttpOnly; SameSite=Lax")
        return True

    def _dashboard(self) -> None:
        host = _host(self); ip = self.client_address[0]
        services = "".join(f"<tr><td>{html.escape(name)}</td><td>{html.escape(APP.service_state(unit))}</td><td>{html.escape(APP.service_health(s))}</td><td><a href='{html.escape(_service_url(self,s))}'>Open</a></td></tr>" for s in SERVICES for _,name,unit,*_ in [s])
        body = f"<p><b>Mudos</b> — hostname {html.escape(host)}; client/LAN address {html.escape(ip)}</p><p>Deployment: {html.escape(_deployment())}</p><h2>Services</h2><table><tr><th>Service</th><th>State</th><th>Health</th><th></th></tr>{services}</table><p><a href=/providers>Configure providers</a></p>"
        self._send(_page("Dashboard", body))

    def _providers(self) -> None:
        csrf = APP.session(self._token()) or ""
        rows = "".join(f"<tr><td>{html.escape(str(r['name']))}</td><td>{html.escape(str(r['status']))}</td><td>{html.escape(json.dumps(r['secrets']))}</td><td><a href='/provider/{urllib.parse.quote(str(r['id']))}'>Edit</a> <form style='display:inline' method=post action='/test/{urllib.parse.quote(str(r['id']))}'><input type=hidden name=csrf value='{csrf}'><button>Test</button></form></td></tr>" for r in APP.provider_rows())
        self._send(_page("Providers", f"<table><tr><th>Provider</th><th>Status</th><th>Secrets configured</th><th>Actions</th></tr>{rows}</table>"))

    def _provider_form(self, provider_id: str) -> None:
        config = APP.config.provider(provider_id); csrf = APP.session(self._token()) or ""
        fields = "".join(f"<label>{html.escape(key)} <input name='{html.escape(key)}' value='{html.escape(str(config.get(key,'')))}'></label><br>" for key in ("enabled", "host", "port", "tls", "connections", "endpoint", "username", "category"))
        secrets = "".join(f"<label>{html.escape(key)} ({'Configured' if config.secret_available(key) else 'Not configured'}) <input type=password name='secret_{html.escape(key)}' value=''></label> <label>Clear <input type=checkbox name='clear_{html.escape(key)}'></label><br>" for key in config.secret_refs)
        if provider_id == "providers.usenet.server" and not config.secret_refs: secrets = "<label>username <input type=password name=secret_username></label><br><label>password <input type=password name=secret_password></label><br>"
        self._send(_page("Edit " + provider_id, f"<form method=post action='/provider/{urllib.parse.quote(provider_id)}'><input type=hidden name=csrf value='{csrf}'>{fields}<h2>Secrets</h2>{secrets}<button>Save</button></form>"))

    def _save_provider(self, provider_id: str, form: dict[str, list[str]], token: str | None) -> None:
        before = APP.config.provider(provider_id)
        before_values = {key: value for key, value in before.values.items()
                         if key != "secrets" and isinstance(value, (str, int, float, bool))}
        before_secrets = {key: before.secret(key) for key in before.secret_refs
                          if before.secret(key) is not None}
        values = {key: value[0] for key, value in form.items() if not key.startswith(("csrf", "secret_", "clear_"))}
        for key in ("enabled", "tls"):
            if key in values: values[key] = values[key].lower() in {"1", "true", "on", "yes"}
        for key in ("port", "connections"):
            if key in values and values[key]:
                try: values[key] = int(values[key])
                except ValueError: self._send(_page("Invalid configuration", f"<p class=error>{key} must be an integer.</p>"), 400); return
        secrets_in = {key[7:]: value[0] for key, value in form.items() if key.startswith("secret_") and value[0]}
        clears = {key[6:] for key in form if key.startswith("clear_") and form[key][0] == "on"}
        if provider_id == "providers.usenet" and "rpc_password" in clears:
            self._send(_page("Save failed", "<p class=error>NZBGet authentication cannot be cleared. Enter a replacement password instead.</p>"), 400); return
        try:
            APP.config.update_provider(provider_id, values, secrets_in, clears)
            if provider_id == "providers.usenet":
                from .nzbget_admin import apply_control_credentials, apply_packaged_paths
                updated = APP.config.provider(provider_id)
                apply_packaged_paths()
                apply_control_credentials(str(updated.get("username", "mudos")),
                                          updated.secret("rpc_password") or "")
                subprocess.run(["systemctl", "restart", "nzbget.service"],
                               stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL, check=True, timeout=10)
            if provider_id == "providers.usenet.server":
                from .nzbget_admin import apply_news_server, apply_packaged_paths
                updated = APP.config.provider(provider_id)
                apply_packaged_paths()
                server_secrets = updated.secret_refs
                username = updated.secret("username") or ""
                password = updated.secret("password") or ""
                apply_news_server(str(updated.get("host", "")), int(updated.get("port", 0)),
                                  bool(updated.get("tls", False)), int(updated.get("connections", 0)),
                                  username, password, bool(updated.get("enabled", True)))
                subprocess.run(["systemctl", "restart", "nzbget.service"],
                               stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL, check=True, timeout=10)
            if provider_id in {"providers.usenet", "providers.usenet.server"}:
                subprocess.run(["systemctl", "restart", "lulu-acquisition.service"],
                               stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL, check=True, timeout=10)
        except (OSError, ValueError, subprocess.SubprocessError) as error:
            # Restore both configuration layers if materialization or the
            # required daemon restart fails; do not leave a new SecretStore
            # value paired with an old NZBGet runtime.
            try:
                APP.config.update_provider(provider_id, before_values, before_secrets)
            except (OSError, ValueError):
                pass
            self._send(_page("Save failed", f"<p class=error>{html.escape(str(error))}</p>"), 400); return
        self._redirect("/providers")

    def _services(self) -> None:
        rows = "".join(f"<li><b>{html.escape(name)}</b> — {html.escape(APP.service_state(unit))} — {html.escape(APP.service_health(s))} — <a href='{html.escape(_service_url(self,s))}'>Open UI</a></li>" for s in SERVICES for _,name,unit,*_ in [s])
        self._send(_page("Services", f"<ul>{rows}</ul>"))


def serve() -> None:
    http.server.ThreadingHTTPServer.allow_reuse_address = True
    http.server.ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()


if __name__ == "__main__": serve()
