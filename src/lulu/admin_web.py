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
import logging
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
from .plugins import ComponentRegistry, PluginRegistry

LOGGER = logging.getLogger("lulu.admin")

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

PROVIDER_META = {
    "providers.steam": ("Steam", "Steam games and account services.", "Connect Mudos to Steam when account access is required."),
    "providers.romm": ("RomM", "Your game library and artwork source.", "Use the address of your RomM server and its private API key."),
    "metadata.igdb": ("Game metadata", "Game names, artwork, and catalogue information.", "These settings are optional and are normally supplied by the appliance administrator."),
    "providers.torrent": ("Transmission", "Torrent downloads managed by Mudos.", "Mudos uses the same account for Transmission's Web UI and its connection to Mudos."),
    "providers.usenet": ("NZBGet", "Usenet downloads managed by Mudos.", "Mudos uses the same account for NZBGet's Web UI and its connection to Mudos."),
    "providers.usenet.server": ("Usenet provider", "The Usenet account used by NZBGet.", "Your Usenet provider supplies these connection details."),
    "providers.prowlarr": ("Prowlarr", "Search indexers used to find downloadable games.", "Mudos sends searches to Prowlarr and keeps its API key private."),
}

FIELD_HELP = {
    "endpoint": "The address Mudos uses to connect to this service.",
    "host": "The server name or address supplied by your provider.",
    "port": "The network port used by the service. Leave the default unless your provider says otherwise.",
    "connections": "Controls how many simultaneous connections NZBGet can make. Your provider may impose a maximum.",
    "tls": "Use an encrypted connection when contacting your Usenet provider.",
    "category": "An optional label used to organize downloads.",
}

SERVICES = (
    ("dufs", "File Manager — DUFS", "lulu-file-browser.service", "http", 8080, "/", True),
    ("nzbget", "NZBGet", "nzbget.service", "http", 6789, "/", True),
    ("transmission", "Transmission", "lulu-transmission.service", "http", 9091, "/transmission/web/", True),
    ("questarr", "Questarr", "lulu-questarr.service", "http", 5000, "/", True, "/api/health"),
    ("prowlarr", "Prowlarr", "prowlarr.service", "http", 9696, "/", True),
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


def _status_label(value: str) -> tuple[str, str]:
    normalized = value.casefold()
    if normalized in {"configured", "healthy", "active", "connected"}:
        return "Connected", "success"
    if normalized in {"disabled", "n/a"}:
        return "Not configured", "muted"
    if normalized in {"inactive", "unhealthy", "unconfigured"}:
        return "Needs attention", "warning"
    return value.replace("_", " ").title(), "muted"


def _badge(value: str) -> str:
    label, tone = _status_label(value)
    return f'<span class="badge badge-{tone}"><span aria-hidden="true">●</span> {html.escape(label)}</span>'


def _notice(title: str, message: str, tone: str = "") -> str:
    return f'<div class="notice {html.escape(tone)}"><strong>{html.escape(title)}</strong><p>{html.escape(message)}</p></div>'


def _service_description(key: str) -> str:
    return {
        "dufs": "Browse appliance files.",
        "nzbget": "View and manage Usenet downloads.",
        "transmission": "View and manage torrent downloads.",
        "questarr": "Find and manage downloadable games.",
        "sunshine": "Manage remote streaming.",
        "prowlarr": "Manage search indexers.",
    }.get(key, "Appliance service.")


def _help(text: str, key: str) -> str:
    safe_key = "help-" + "".join(char if char.isalnum() else "-" for char in key)
    return (f'<details class="help"><summary aria-label="Help">?</summary>'
            f'<span id="{safe_key}" class="help-popover" role="tooltip">{html.escape(text)}</span></details>')


def _field(label: str, name: str, value: object = "", *, kind: str = "text",
           help_text: str = "", placeholder: str = "", required: bool = False) -> str:
    field_id = "field-" + "".join(char if char.isalnum() else "-" for char in name)
    described = f' aria-describedby="help-{field_id}"' if help_text else ""
    required_attr = " required" if required else ""
    extra = f' placeholder="{html.escape(placeholder)}"' if placeholder else ""
    input_html = (f'<input id="{field_id}" name="{html.escape(name)}" type="{kind}" '
                  f'value="{html.escape(str(value))}"{described}{extra}{required_attr}>')
    return (f'<div class="setting"><div class="setting-label"><label for="{field_id}">{html.escape(label)}</label>'
            f'{_help(help_text, field_id) if help_text else ""}</div>{input_html}'
            f'{f"<p class=help-text>{html.escape(help_text)}</p>" if help_text else ""}</div>')


def _page(title: str, body: str, *, subtitle: str = "", active: str = "") -> bytes:
    nav = "".join(f'<a class="{"active" if active == key else ""}" href="{href}">{label}</a>'
                   for key, href, label in (("overview", "/", "Overview"),
                                             ("integrations", "/integrations", "Integrations"),
                                             ("services", "/services", "Services"),
                                             ("system", "/system", "System")))
    return ("<!doctype html><html lang=en><head><meta charset=utf-8><meta name=viewport content='width=device-width, initial-scale=1'>"
            "<meta name=color-scheme content='dark'><title>" + html.escape(title) +
            " — Mudos</title><style>" + _STYLES + "</style></head><body>"
            f'<div class="app-shell"><header class="topbar"><a class="brand" href="/"><span class="brand-mark">M</span><span>Mudos</span></a>'
            f'<nav aria-label="Main navigation">{nav}</nav><form method=post action=/logout><button class="button button-quiet">Sign out</button></form></header>'
            f'<main><div class="page-heading"><p class="eyebrow">MUDOS ADMIN</p><h1>{html.escape(title)}</h1>{f"<p class=subtitle>{html.escape(subtitle)}</p>" if subtitle else ""}</div>{body}</main>'
            f'<footer>Managed locally on <strong>{html.escape(_deployment())}</strong></footer></div></body></html>').encode()


_STYLES = """
:root{color-scheme:dark;--bg:#0b1017;--surface:#121a25;--raised:#182333;--text:#edf3fb;--muted:#99a8ba;--accent:#72b7ff;--accent-strong:#a6d2ff;--success:#55d6a0;--warning:#f2bf68;--error:#ff7f8f;--border:#2a3a4e;--focus:#b8dcff;--radius:16px;--space:8px;--shadow:0 18px 45px #0005;font:16px/1.5 system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}
*{box-sizing:border-box}body{margin:0;background:radial-gradient(circle at 15% 0,#1a3048 0,transparent 34rem),var(--bg);color:var(--text)}a{color:var(--accent-strong);text-decoration:none}a:hover{text-decoration:underline}button,input,select{font:inherit}button{cursor:pointer}.app-shell{max-width:1180px;margin:auto;padding:0 24px}.topbar{min-height:76px;display:flex;align-items:center;gap:28px;border-bottom:1px solid var(--border)}.brand{display:flex;align-items:center;gap:10px;font-weight:750;font-size:1.15rem;color:var(--text);white-space:nowrap}.brand-mark{display:grid;place-items:center;width:32px;height:32px;border-radius:10px;background:var(--accent);color:#08111c;font-weight:900}.topbar nav{display:flex;align-self:stretch;gap:4px;flex:1}.topbar nav a{display:flex;align-items:center;padding:0 14px;color:var(--muted);border-bottom:2px solid transparent}.topbar nav a:hover,.topbar nav a.active{color:var(--text);border-color:var(--accent)}main{padding:42px 0 60px}.page-heading{max-width:720px;margin-bottom:28px}.eyebrow{color:var(--accent);font-size:.72rem;letter-spacing:.16em;font-weight:750;margin:0 0 8px}.page-heading h1{font-size:clamp(2rem,5vw,3.2rem);line-height:1.05;margin:0 0 10px;letter-spacing:-.035em}.subtitle{color:var(--muted);font-size:1.05rem;margin:0}.grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:18px}.card{background:linear-gradient(145deg,#1b2a3b99,#101925dd);border:1px solid var(--border);border-radius:var(--radius);padding:24px;box-shadow:var(--shadow)}.card h2,.card h3{margin:0 0 8px}.card p{color:var(--muted);margin:6px 0}.card-link{display:block;color:inherit}.card-link:hover{text-decoration:none;border-color:var(--accent)}.card-head{display:flex;justify-content:space-between;gap:14px;align-items:flex-start}.badge{display:inline-flex;align-items:center;gap:6px;border:1px solid var(--border);border-radius:999px;padding:3px 10px;font-size:.78rem;white-space:nowrap}.badge-success{color:var(--success);border-color:#318c6c}.badge-warning{color:var(--warning);border-color:#997237}.badge-muted{color:var(--muted)}.notice{border:1px solid var(--border);border-left:4px solid var(--accent);background:var(--surface);padding:14px 16px;border-radius:10px;margin:0 0 20px}.notice.success{border-left-color:var(--success)}.notice.error{border-left-color:var(--error)}.notice.warning{border-left-color:var(--warning)}.notice strong{display:block}.actions{display:flex;flex-wrap:wrap;gap:10px;align-items:center;margin-top:22px}.button{display:inline-flex;align-items:center;justify-content:center;min-height:42px;border:1px solid var(--accent);border-radius:10px;padding:8px 16px;background:var(--accent);color:#08111c;font-weight:700;text-decoration:none}.button:hover{text-decoration:none;background:var(--accent-strong)}.button-secondary{background:transparent;color:var(--accent-strong);border-color:var(--border)}.button-secondary:hover{background:var(--raised)}.button-danger{background:transparent;color:var(--error);border-color:#984554}.button-quiet{border:0;background:transparent;color:var(--muted);padding:8px}.button-quiet:hover{color:var(--text);background:var(--raised)}.setting{padding:17px 0;border-bottom:1px solid #263548}.setting:last-child{border-bottom:0}.setting-label{display:flex;align-items:center;gap:8px;margin-bottom:6px}.setting label{font-weight:650}.setting input,.setting select{width:100%;min-height:44px;background:#0d151f;color:var(--text);border:1px solid var(--border);border-radius:9px;padding:9px 12px}.setting input:focus,.setting select:focus,.button:focus,.topbar a:focus,.help summary:focus{outline:3px solid #72b7ff66;outline-offset:2px;border-color:var(--focus)}.help-text{font-size:.88rem;color:var(--muted);margin:6px 0 0}.help{position:relative;display:inline-block}.help summary{list-style:none;display:grid;place-items:center;width:21px;height:21px;border:1px solid var(--muted);border-radius:50%;color:var(--muted);font-size:.75rem;font-weight:800;cursor:pointer}.help summary::-webkit-details-marker{display:none}.help-popover{position:absolute;z-index:4;top:28px;left:-8px;width:260px;background:var(--raised);border:1px solid var(--border);border-radius:9px;padding:10px 12px;color:var(--text);font-size:.86rem;box-shadow:var(--shadow)}.section-title{display:flex;justify-content:space-between;align-items:center;margin:30px 0 12px}.section-title h2{margin:0;font-size:1.25rem}.meta{font-size:.86rem;color:var(--muted)}.split{display:grid;grid-template-columns:minmax(0,1.3fr) minmax(260px,.7fr);gap:22px}.service-list{display:grid;gap:12px}.service-row{display:flex;align-items:center;justify-content:space-between;gap:18px;padding:18px 20px;background:var(--surface);border:1px solid var(--border);border-radius:13px}.service-row h3{margin:0}.service-row p{margin:2px 0 0;color:var(--muted)}details.technical{margin-top:18px;color:var(--muted)}details.technical summary{cursor:pointer;color:var(--accent-strong)}footer{border-top:1px solid var(--border);padding:20px 0 30px;color:var(--muted);font-size:.82rem}@media(max-width:720px){.app-shell{padding:0 15px}.topbar{flex-wrap:wrap;gap:10px;padding:14px 0}.topbar nav{order:3;width:100%;overflow:auto}.topbar nav a{padding:8px 11px}.topbar form{margin-left:auto}.grid,.split{grid-template-columns:1fr}.service-row{align-items:flex-start;flex-direction:column}.actions .button{width:100%}main{padding-top:28px}}
"""


def _login_page(message: str = "", *, status: int = 200) -> bytes:
    notice = _notice("Sign-in unsuccessful", message, "error") if message else ""
    body = (f'<main><div class="login-wrap"><div class="login-card card"><p class="eyebrow">MUDOS ADMIN</p>'
            '<div class="brand login-brand"><span class="brand-mark">M</span><span>Mudos</span></div>'
            '<h1>Sign in</h1><p class="subtitle">Sign in to manage this Mudos appliance.</p>'
            f'{notice}<form method=post action=/login><div class="setting"><div class="setting-label"><label for=password>Password</label></div>'
            '<input id=password name=password type=password autocomplete=current-password autofocus required></div>'
            '<div class="actions"><button class="button" type=submit>Sign in</button></div></form></div></div></main>')
    return ("<!doctype html><html lang=en><head><meta charset=utf-8><meta name=viewport content='width=device-width, initial-scale=1'>"
            "<meta name=color-scheme content='dark'><title>Sign in — Mudos</title><style>" + _STYLES +
            ".login-wrap{max-width:480px;margin:10vh auto}.login-card{padding:34px}.login-brand{margin-bottom:28px}.login-card h1{font-size:2.4rem;margin:0 0 8px}.login-card .subtitle{margin-bottom:22px}</style></head><body>"
            + body + "</body></html>").encode()


class AdminApp:
    def __init__(self) -> None:
        self.secrets = SecretStore()
        self.sessions: dict[str, tuple[float, str]] = {}
        self.config = ProviderConfigurationService.from_environment(secrets=self.secrets)
        plugin_root = PATHS.plugins_root
        installed_plugins = PATHS.install_root / "config" / "plugins"
        if (not plugin_root.is_dir() or not any(plugin_root.glob("*/plugin.toml"))) and installed_plugins.is_dir():
            plugin_root = installed_plugins
        self.plugins = PluginRegistry(plugin_root)
        self.plugins.discover()
        self.components = ComponentRegistry(self.plugins)
        self.components.discover()

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
        declared = list(PROVIDERS)
        known = {provider_id for provider_id, _ in declared}
        declared.extend((component.component_id, component.name)
                        for component in self.components.all()
                        if component.component_id not in known and component.provider_ids)
        for provider_id, name in declared:
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
        for provider in self.plugins.with_capability("provider"):
            if provider_id in tuple(getattr(provider, "provider_ids", ())):
                if not getattr(provider, "available", False):
                    return False, "The provider is not installed"
                return True, "Provider is available"
        return False, "No normalized health check is available for this provider"


APP = AdminApp()


class Handler(http.server.BaseHTTPRequestHandler):
    server_version = "MudosAdmin/1"

    def handle(self) -> None:
        try:
            super().handle()
        except Exception:
            # Keep unexpected route/template failures from becoming an empty
            # TCP response. Request metadata is safe; form bodies and tokens
            # are intentionally excluded from the log.
            LOGGER.exception("admin request failed method=%s path=%s",
                             getattr(self, "command", "unknown"),
                             urllib.parse.urlsplit(getattr(self, "path", "")).path)
            try:
                self._send(_page("Something went wrong", _notice(
                    "Something went wrong", "Mudos could not complete that request. Please try again.", "error")), 500)
            except Exception:
                pass

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
        path = urllib.parse.urlsplit(self.path).path
        if path == "/login":
            message = "" if APP.password_configured() else "Admin access has not been set up yet."
            self._send(_login_page(message) if message else _login_page()); return
        if self._require() is None: return
        if path == "/": self._dashboard(); return
        if path == "/providers": self._redirect("/integrations"); return
        if path == "/integrations": self._providers(); return
        if path.startswith("/provider/"):
            self._redirect("/integration/" + urllib.parse.quote(urllib.parse.unquote(path[10:])))
            return
        if path.startswith("/integration/"):
            self._provider_form(urllib.parse.unquote(path[13:])); return
        if path == "/services": self._services(); return
        if path == "/system": self._system(); return
        self._send(_page("Not found", "<p>Not found.</p>"), 404)

    def do_POST(self) -> None:
        if self.path == "/login":
            if self.authenticate_form(): return
            self._send(_login_page("The password was not accepted.", status=401), 401); return
        token = self._token(); csrf = APP.session(token)
        if csrf is None: self._redirect("/login"); return
        form = self._form()
        if not hmac.compare_digest(form.get("csrf", [""])[0], csrf):
            self._send(_page("Request rejected", "<p class=error>Invalid CSRF token.</p>"), 403); return
        if self.path == "/logout": APP.logout(token); self._redirect("/login", "mudos_session=; Max-Age=0; HttpOnly; SameSite=Lax"); return
        if self.path.startswith("/provider/") or self.path.startswith("/integration/"):
            prefix = "/provider/" if self.path.startswith("/provider/") else "/integration/"
            self._save_provider(urllib.parse.unquote(self.path[len(prefix):]), form, token); return
        if self.path.startswith("/test/") or self.path.startswith("/integration-test/"):
            prefix = "/test/" if self.path.startswith("/test/") else "/integration-test/"
            provider_id = urllib.parse.unquote(self.path[len(prefix):])
            ok, message = APP.test_provider(provider_id)
            title, _, _ = PROVIDER_META.get(provider_id, (provider_id, "", ""))
            notice = _notice("Connection successful" if ok else "Connection needs attention", message, "success" if ok else "error")
            self._send(_page(title, notice + f'<p><a class="button button-secondary" href="/integration/{urllib.parse.quote(provider_id)}">Back to settings</a></p>', subtitle="Connection test", active="integrations")); return
        self._send(_page("Not found", "<p>Not found.</p>"), 404)

    def authenticate_form(self) -> bool:
        form = self._form(); password = form.get("password", [""])[0]
        if not APP.authenticate(password): return False
        token, csrf = APP.login()
        self._redirect("/", f"mudos_session={token}; Max-Age={SESSION_SECONDS}; HttpOnly; SameSite=Lax")
        return True

    def _dashboard(self) -> None:
        host = _host(self)
        configured = sum(1 for provider_id, _ in PROVIDERS if APP.config.provider(provider_id).configured)
        cards = "".join(f'<a class="card-link card" href="/services"><div class="card-head"><h3>{html.escape(name)}</h3>{_badge(APP.service_state(unit))}</div><p>{html.escape(_service_description(key))}</p></a>' for key,name,unit,*_ in SERVICES[:3])
        body = (f'<div class="card"><div class="card-head"><div><h2>Appliance at {html.escape(host)}</h2><p>Ready for local administration.</p></div>{_badge("active")}</div>'
                f'<p class="meta">Deployment: {html.escape(_deployment())} · {configured} integrations configured</p>'
                f'<div class="actions"><a class="button" href="/integrations">Configure integrations</a><a class="button button-secondary" href="/services">View all services</a></div></div>'
                '<div class="section-title"><h2>Service snapshot</h2><a href="/services">See all</a></div>'
                f'<div class="grid">{cards}</div>')
        self._send(_page("Overview", body, subtitle="A clear view of your Mudos appliance.", active="overview"))

    def _providers(self) -> None:
        cards = []
        for provider_id, name in PROVIDERS:
            title, description, _ = PROVIDER_META.get(provider_id, (name, "", ""))
            config = APP.config.provider(provider_id)
            cards.append(f'<a class="card-link card" href="/integration/{urllib.parse.quote(provider_id)}"><div class="card-head"><h2>{html.escape(title)}</h2>{_badge(config.status)}</div><p>{html.escape(description)}</p><span class="meta">Configure connection →</span></a>')
        notice = _notice("Changes saved", "The integration settings were updated.", "success") if urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query).get("updated") else ""
        body = notice + '<div class="grid">' + "".join(cards) + '</div>'
        self._send(_page("Integrations", body, subtitle="Connect the services Mudos uses. Each integration has one canonical settings page.", active="integrations"))

    def _provider_form(self, provider_id: str) -> None:
        config = APP.config.provider(provider_id); csrf = APP.session(self._token()) or ""
        title, description, explanation = PROVIDER_META.get(provider_id, (provider_id, "", ""))
        if provider_id in {component.component_id for component in APP.components.all()}:
            component = APP.components.get(provider_id)
            title, description, explanation = component.name, component.description, component.description
        component_ids = {component.component_id for component in APP.components.all()}
        if provider_id not in dict(PROVIDERS) and provider_id not in component_ids:
            self._send(_page("Not found", '<div class="notice error"><strong>Integration not found</strong><p>Choose an integration from the list.</p></div><a class="button" href="/integrations">Back to integrations</a>', active="integrations"), 404); return
        if provider_id == "providers.torrent":
            fields = (_field("Username", "username", config.secret("username") or "", help_text="The account name used by Mudos and the Transmission Web UI.", required=True)
                      + _field("Connection address", "endpoint", config.get("endpoint", ""), help_text="The local address Mudos uses to connect to Transmission."))
            secrets = _field("Password", "secret_password", "", kind="password", help_text="Leave blank to keep the existing password. Enter a new value to replace it.") + f'<p class="meta">Password: {_badge("configured" if config.secret_available("password") else "unconfigured")}</p>'
        else:
            fields = ""
            for key, label in (("endpoint", "Server address"), ("host", "Server address"), ("port", "Port"), ("connections", "Maximum connections"), ("category", "Download category")):
                if key in config.values:
                    fields += _field(label, key, config.get(key, ""), kind="number" if key in {"port", "connections"} else "text", help_text=FIELD_HELP.get(key, ""))
            if "username" in config.values:
                fields += _field("Username", "username", config.get("username", ""), help_text="The username supplied by this service or provider.")
            if "tls" in config.values:
                fields += _field("Use encrypted connection", "tls", "true" if config.get("tls") else "false", help_text=FIELD_HELP["tls"])
            secret_parts = []
            for key in config.secret_refs:
                label = {"rpc_password": "Password", "api_key": "API key", "username": "Username", "password": "Password"}.get(key, "Private credential")
                secret_parts.append(_field(label, "secret_" + key, "", kind="password", help_text="Leave blank to keep the existing value. Enter a new value to replace it.") + f'<p class="meta">{html.escape(label)}: {_badge("configured" if config.secret_available(key) else "unconfigured")}</p>')
            secrets = "".join(secret_parts) or '<p class="meta">No credentials are required for this integration.</p>'
        form_action = "/integration/" + urllib.parse.quote(provider_id)
        test_action = "/integration-test/" + urllib.parse.quote(provider_id)
        service_key = {"providers.torrent": "transmission", "providers.usenet": "nzbget"}.get(provider_id)
        open_link = next((service for service in SERVICES if service[0] == service_key), None)
        actions = f'<button class="button" type=submit>Save changes</button><button class="button button-secondary" formaction="{test_action}" formmethod=post>Test connection</button>'
        if open_link:
            actions += f'<a class="button button-secondary" href="{html.escape(_service_url(self, open_link))}">Open Web UI</a>'
        body = (f'<div class="card"><div class="card-head"><div><h2>{html.escape(title)}</h2><p>{html.escape(explanation)}</p></div>{_badge(config.status)}</div>'
                f'<form method=post action="{form_action}"><input type=hidden name=csrf value="{csrf}"><section><div class="section-title"><h2>Connection</h2></div>{fields}{secrets}</section><div class="actions">{actions}</div></form></div>'
                '<details class="technical"><summary>Technical details</summary><p>Integration identifier: ' + html.escape(provider_id) + '</p></details>')
        self._send(_page(title, body, subtitle=description, active="integrations"))

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
        if provider_id == "providers.torrent":
            rpc_username = values.pop("username", "").strip()
            if rpc_username:
                secrets_in["username"] = rpc_username
        clears = {key[6:] for key in form if key.startswith("clear_") and form[key][0] == "on"}
        if provider_id == "providers.usenet" and "rpc_password" in clears:
            self._send(_page("Save failed", "<p class=error>NZBGet authentication cannot be cleared. Enter a replacement password instead.</p>"), 400); return
        if provider_id == "providers.torrent" and "password" in clears:
            self._send(_page("Save failed", "<p class=error>Transmission authentication cannot be cleared. Enter a replacement password instead.</p>"), 400); return
        transmission_credentials_changed = provider_id == "providers.torrent" and (
            "password" in secrets_in
            or ("username" in secrets_in and secrets_in["username"] != (before.secret("username") or ""))
        )
        try:
            if transmission_credentials_changed:
                from .plugins.torrent import TransmissionClient, TransmissionConfig
                from .transmission_admin import apply_rpc_credentials, replace_rpc_credentials
                updated = APP.config.provider(provider_id)
                username = secrets_in.get("username", before.secret("username") or "")
                password = secrets_in.get("password", before.secret("password") or "")

                def systemctl(verb: str, unit: str) -> None:
                    result = subprocess.run(["systemctl", verb, unit], stdin=subprocess.DEVNULL,
                                            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                            text=True, check=False, timeout=70)
                    if result.returncode:
                        detail = (result.stderr or result.stdout or "unknown systemctl failure").strip()
                        LOGGER.error("Transmission credential lifecycle failed verb=%s unit=%s detail=%s",
                                     verb, unit, detail[-400:])
                        raise RuntimeError(f"Transmission service {verb} failed")

                def health(check_username: str, check_password: str) -> None:
                    import asyncio
                    asyncio.run(TransmissionClient(TransmissionConfig(
                        username=check_username, password=check_password)).health())

                def commit() -> None:
                    APP.config.update_provider(provider_id, values, secrets_in, clears)

                def rollback_commit() -> None:
                    APP.config.update_provider(provider_id, before_values, before_secrets)

                replace_rpc_credentials(
                    username, password, before.secret("username") or "", before.secret("password") or "",
                    stop=lambda: systemctl("stop", "lulu-transmission.service"),
                    start=lambda: (systemctl("start", "lulu-transmission.service"),
                                   systemctl("start", "lulu-transmission-config.service")),
                    materialize=lambda check_username, check_password: (
                        systemctl("start", "lulu-transmission-config.service"),
                        apply_rpc_credentials(check_username, check_password)),
                    health=health,
                    commit=commit,
                    rollback_commit=rollback_commit,
                    refresh=lambda: systemctl("restart", "lulu-acquisition.service"),
                    reconcile=lambda: systemctl("start", "lulu-questarr-reconcile.service"),
                )
            else:
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
            if provider_id in {"providers.torrent", "providers.usenet", "providers.prowlarr"}:
                # The reconciler is optional on immutable installations.
                subprocess.run(["systemctl", "start", "lulu-questarr-reconcile.service"],
                               stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL, check=False, timeout=10)
        except Exception as error:
            # Restore both configuration layers if materialization or the
            # required daemon restart fails; do not leave a new SecretStore
            # value paired with an old NZBGet runtime.
            try:
                APP.config.update_provider(provider_id, before_values, before_secrets)
            except (OSError, ValueError):
                pass
            message = ("Could not update Transmission credentials; previous credentials were preserved."
                       if provider_id == "providers.torrent"
                       else "Could not save these settings. Your previous settings were kept.")
            LOGGER.error("provider save failed provider=%s error_type=%s", provider_id, type(error).__name__)
            self._send(_page("Save failed", f"<p class=error>{html.escape(message)}</p>"), 400); return
        self._redirect("/integrations?updated=1")

    def _services(self) -> None:
        rows = "".join(f'<div class="service-row"><div><div class="card-head"><h3>{html.escape(name)}</h3>{_badge(APP.service_state(unit))}</div><p>{html.escape(_service_description(key))}</p>{_badge(APP.service_health(s))}</div><a class="button button-secondary" href="{html.escape(_service_url(self,s))}">Open</a></div>' for s in SERVICES for key,name,unit,*_ in [s])
        known = {service[0] for service in SERVICES}
        generic_rows = []
        for component in APP.components.all():
            if not component.enabled:
                continue
            for service in component.services:
                if service.service_id in known:
                    continue
                link = (f'<a class="button button-secondary" href="{html.escape(service.url)}">Open</a>'
                        if service.url else "")
                generic_rows.append(
                    f'<div class="service-row"><div><div class="card-head"><h3>{html.escape(service.name)}</h3>'
                    f'{_badge("active")}</div><p>{html.escape(service.description)}</p></div>{link}</div>')
        rows += "".join(generic_rows)
        self._send(_page("Services", f'<div class="service-list">{rows}</div>', subtitle="Open the appliance services you use every day. Editing stays on Integrations.", active="services"))

    def _system(self) -> None:
        host = _host(self)
        body = f'<div class="grid"><div class="card"><h2>Appliance</h2><p>Hostname</p><strong>{html.escape(host)}</strong><p class="meta">Deployment: {html.escape(_deployment())}</p></div><div class="card"><h2>About this page</h2><p>System-wide settings are intentionally kept separate from service connections.</p><p class="meta">Service credentials are managed under Integrations.</p></div></div>'
        self._send(_page("System", body, subtitle="Appliance information and administration boundaries.", active="system"))


def serve() -> None:
    http.server.ThreadingHTTPServer.allow_reuse_address = True
    http.server.ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()


if __name__ == "__main__": serve()
