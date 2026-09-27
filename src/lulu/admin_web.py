"""Small authenticated appliance administration frontend.

The HTTP layer is intentionally boring: it renders HTML and delegates
configuration mutation to ProviderConfigurationService and SecretStore.
"""
from __future__ import annotations

import hmac
import html
import http.server
import json
import logging
import os
import pwd
from pathlib import Path
import secrets
import shutil
import subprocess
import tempfile
import time
import urllib.parse
import urllib.error
import urllib.request
from typing import Any

from .credential import SecretStore
from .auth_transactions import AuthTransactionState, AuthTransactionStore
from .provider_config import ProviderConfigurationService
from .paths import PATHS
from .plugins import ComponentRegistry, PluginRegistry
from .onboarding import (INTEGRATION_METADATA, dismiss_onboarding, finish_onboarding,
                         integration_manifest, onboarding_state, provider_manifest,
                         save_admin_password_configured, save_progress, save_validation)
from .recovery import snapshot as recovery_state_snapshot

LOGGER = logging.getLogger("lulu.admin")

PORT = 80
SESSION_SECONDS = 1800

PROVIDERS = (
    ("steam", "Steam"), ("gog", "GOG"), ("epic", "Epic Games"), ("providers.romm", "RomM"),
    ("metadata.igdb", "IGDB / metadata"), ("metadata.steamgriddb", "SteamGridDB"),
    ("providers.torrent", "Transmission"),
    ("providers.usenet", "NZBGet"), ("providers.usenet.server", "Usenet news server"),
    ("providers.prowlarr", "Prowlarr"),
)

PROVIDER_META = {
    "steam": ("Steam", "Steam games and account services.", "SteamCMD acquisition credentials are kept separately from the Steam client session."),
    "gog": ("GOG", "GOG games and gogdl account services.", "Sign in with GOG to authorize gogdl without entering a GOG password into Mudos."),
    "epic": ("Epic Games", "Epic games and Legendary account services.", "Legendary authentication will use the same provider transaction flow."),
    "providers.romm": ("RomM", "Your game library and artwork source.", "Use the address of your RomM server and its private API key."),
    "metadata.igdb": ("Game metadata", "Game names, artwork, and catalogue information.", "These settings are optional and are normally supplied by the appliance administrator."),
    "metadata.steamgriddb": ("SteamGridDB", "Preferred automatic cover artwork.", "Use validated SteamGridDB covers after IGDB canonical identity resolution."),
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


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item)[:100] for item in value[:64] if isinstance(item, str)]


def _setup_service_url(value: object, label: str) -> str:
    url = str(value or "").strip().rstrip("/")
    parsed = urllib.parse.urlsplit(url)
    if label == "RomM" and parsed.scheme not in {"http", "https"}:
        raise ValueError("Enter a RomM URL beginning with http:// or https://")
    if (parsed.scheme not in {"http", "https"} or not parsed.hostname
            or parsed.username is not None or parsed.password is not None
            or parsed.query or parsed.fragment):
        raise ValueError(f"Enter a valid {label} URL without embedded credentials")
    try:
        parsed.port
    except ValueError as error:
        raise ValueError(f"Enter a valid {label} URL") from error
    return url


def _setup_page_document(body: str) -> bytes:
    styles = '''
*{box-sizing:border-box}body{margin:0;background:#10131a;color:#f3f4f6;font:16px/1.55 system-ui,sans-serif}
.setup-wrap{max-width:1080px;margin:auto;padding:clamp(22px,5vw,64px)}h1{font-size:clamp(2rem,5vw,3.5rem);line-height:1.08;margin:.15em 0}h2{margin-top:0}.eyebrow{letter-spacing:.16em;color:#91b5ff;font-weight:700}
 .steps,.actions{display:flex;gap:12px;flex-wrap:wrap;margin:22px 0}.steps span,.card{background:#1a1f29;border:1px solid #343b49;border-radius:14px;padding:16px}.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,260px),1fr));gap:14px}.card{display:flex;flex-direction:column;gap:9px}.card span,.card small{color:#bac3d2}.card input[type=checkbox]{width:20px;height:20px;accent-color:#8ab4ff}button,.button{display:inline-block;border:0;border-radius:9px;background:#8ab4ff;color:#10131a;padding:12px 18px;font:inherit;font-weight:700;text-decoration:none;cursor:pointer}.secondary{background:#303846;color:#f3f4f6}label{display:grid;gap:6px}.setup-wrap [hidden]{display:none!important}input:not([type=checkbox]){width:100%;padding:12px;border:1px solid #515b6b;border-radius:8px;background:#0e1117;color:#fff;font:inherit}.credential{margin:16px 0}a{color:#a9c9ff}#notice{min-height:1.6em;color:#ffd17d}#busy{display:flex;align-items:center;gap:10px;color:#a9c9ff;min-height:1.8em}#busy[hidden]{display:none}.spinner{width:18px;height:18px;border:3px solid #52647e;border-top-color:#a9c9ff;border-radius:50%;animation:spin .8s linear infinite}@keyframes spin{to{transform:rotate(360deg)}}button:disabled{opacity:.55;cursor:wait}button:focus,a:focus,input:focus{outline:3px solid #a9c9ff;outline-offset:2px}@media(max-width:520px){.setup-wrap{padding:22px 16px}.steps span{flex:1 1 100%}}
'''
    return ("<!doctype html><html lang=en><head><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'>"
            "<meta name=color-scheme content='dark'><title>Mudos Setup</title><style>" + styles
            + "</style></head><body>" + body + "</body></html>").encode()


def _recovery_snapshot() -> dict[str, object]:
    try:
        with urllib.request.urlopen("http://127.0.0.1:38124/v1/status", timeout=4) as response:
            value = json.loads(response.read(256 * 1024))
            if isinstance(value, dict):
                return value
    except (OSError, urllib.error.URLError, TimeoutError, ValueError, json.JSONDecodeError):
        pass
    diagnostic = recovery_state_snapshot()
    return {
        "schema_version": 1,
        "overall_state": "unknown",
        "checked_at": "",
        "components": {},
        "actions": [],
        "control_plane_available": False,
        "failure_history": {
            "active": bool(diagnostic.get("active", False)),
            "failure_count": int(diagnostic.get("failure_count", 0)),
            "last_failure": str(diagnostic.get("last_failure", ""))[:240],
        },
        "message": "The independent Mudos Recovery control plane is unavailable.",
    }


def _status_label(value: str) -> tuple[str, str]:
    normalized = value.casefold()
    if normalized == "connected":
        return "Connected", "success"
    if normalized == "healthy":
        return "Healthy", "success"
    if normalized == "available":
        return "Available", "success"
    if normalized == "active":
        return "Running", "success"
    if normalized == "authenticated":
        return "Authenticated", "success"
    if normalized == "configured":
        return "Configured", "muted"
    if normalized in {"disabled", "n/a"}:
        return "Not configured", "muted"
    if normalized == "unconfigured":
        return "Not configured", "muted"
    if normalized == "inactive":
        return "Stopped", "warning"
    if normalized == "missing":
        return "Not installed", "warning"
    if normalized == "unhealthy":
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
    checked = " checked" if kind == "checkbox" and bool(value) else ""
    value_attr = "" if kind == "checkbox" else f' value="{html.escape(str(value))}"'
    input_html = (f'<input id="{field_id}" name="{html.escape(name)}" type="{kind}" '
                  f'{value_attr}{checked}{described}{extra}{required_attr}>')
    return (f'<div class="setting"><div class="setting-label"><label for="{field_id}">{html.escape(label)}</label>'
            f'{_help(help_text, field_id) if help_text else ""}</div>{input_html}'
            f'{f"<p class=help-text>{html.escape(help_text)}</p>" if help_text else ""}</div>')


def _page(title: str, body: str, *, subtitle: str = "", active: str = "") -> bytes:
    nav = "".join(f'<a class="{"active" if active == key else ""}" href="{href}">{label}</a>'
                   for key, href, label in (("overview", "/", "Overview"),
                                             ("integrations", "/integrations", "Integrations"),
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
        self.auth_transactions = AuthTransactionStore()

    def setup_snapshot(self) -> dict[str, object]:
        integrations = []
        config_ids = {"providers.romm": "providers.romm",
                      "providers.steam": "providers.steam",
                      "providers.prowlarr": "providers.prowlarr",
                      "providers.usenet.server": "providers.usenet.server",
                      "metadata.igdb": "metadata.igdb",
                      "metadata.steamgriddb": "metadata.steamgriddb",
                      "questarr": "questarr"}
        state = onboarding_state()
        selected = set(state.get("selected_providers", []))
        selected_integrations = set(state.get("selected_integrations", []))
        skipped_integrations = set(state.get("skipped_integrations", []))
        visible_integrations = {"metadata.igdb", "metadata.steamgriddb"}
        if "romm" in selected:
            visible_integrations.add("providers.romm")
        if "steam" in selected:
            visible_integrations.add("providers.steam")
        if "questarr" in selected:
            visible_integrations.add("providers.prowlarr")
        if "usenet" in selected:
            visible_integrations.add("providers.usenet.server")
        for item in integration_manifest():
            if item["id"] not in visible_integrations:
                continue
            provider_id = config_ids[item["id"]]
            metadata = dict(item)
            if provider_id == "questarr":
                metadata["enabled"] = self.service_state("lulu-questarr.service") == "active"
                # The public account probe cannot verify authenticated
                # downloader/indexer configuration.
                metadata["configured"] = False
            elif provider_id == "providers.romm":
                from .plugins.romm import RommConfig
                from .plugins.romm.readiness import RommReadinessStore
                romm = RommConfig.from_file()
                metadata["configured"] = bool(romm and self.secrets.configured("romm", "api-key"))
                metadata["enabled"] = bool(romm)
                metadata["readiness"] = RommReadinessStore().snapshot(
                    selected=("romm" in selected),
                    installed=True, config=romm,
                )
            elif provider_id == "providers.steam":
                from .plugins.steam.entitlements import SteamEntitlementConfig
                steam_config = SteamEntitlementConfig.from_file()
                metadata["configured"] = bool(steam_config and self.secrets.configured("steam", "web-api-key"))
                metadata["enabled"] = metadata["configured"]
                metadata["readiness"] = {"status": "configured" if steam_config and self.secrets.configured(
                    "steam", "web-api-key") else "configuration_required",
                    "message": "Steam ownership configuration is saved." if steam_config and self.secrets.configured(
                        "steam", "web-api-key") else "A SteamID64 and Web API key are required to query owned titles."}
            else:
                config = self.config.provider(provider_id)
                metadata["configured"] = config.configured
                metadata["enabled"] = config.enabled
            from .provider_state import normalized_provider_state
            readiness_status = str((metadata.get("readiness") or {}).get("status", "")) \
                if isinstance(metadata.get("readiness"), dict) else ""
            service_unit = {"questarr": "lulu-questarr.service"}.get(provider_id)
            is_running = self.service_state(service_unit) == "active" if service_unit else None
            integration_selected = item["id"] in selected_integrations
            provider_selected = {
                "providers.romm": "romm", "providers.steam": "steam",
                "providers.prowlarr": "questarr", "providers.usenet.server": "usenet",
            }.get(item["id"])
            metadata["selected"] = (provider_selected in selected if provider_selected
                                    else integration_selected)
            metadata["skipped"] = item["id"] in skipped_integrations
            metadata["state"] = normalized_provider_state(
                status=readiness_status or ("configured" if metadata.get("configured") else "not_configured"),
                installed=True, selected=bool(metadata["selected"]), configured=bool(metadata.get("configured")),
                catalogue_reconciled=(readiness_status == "ready") if provider_id == "providers.romm" else None,
                acquisition_configured=(bool(metadata.get("configured"))
                    if provider_id == "providers.romm" else None),
                running=is_running, healthy=(is_running if service_unit else None),
                skipped=bool(metadata["skipped"]),
                degraded=bool(service_unit and is_running is False))
            integrations.append(metadata)
        from .setup_files import file_setup_manifest
        return {"onboarding": onboarding_state(),
                "providers": self.setup_provider_states(),
                "integrations": integrations,
                "setup_files": file_setup_manifest(selected)}

    def setup_provider_states(self) -> list[dict[str, object]]:
        from .provider_readiness import ProviderReadinessStore
        setup_state = onboarding_state()
        selected = set(setup_state.get("selected_providers", []))
        validations = setup_state.get("validation", {})
        validations = validations if isinstance(validations, dict) else {}
        readiness = ProviderReadinessStore()
        result = []
        installable_ids = {"steam", "epic", "gog", "lutris", "flatpak", "retroarch",
                           "dolphin", "pcsx2", "eden", "questarr", "torrent", "usenet"}
        for source in provider_manifest(self.components):
            row = dict(source)
            provider_id = str(row["id"])
            row["selected"] = provider_id in selected
            if provider_id not in selected:
                row["status"] = "not_selected"
                row["status_message"] = "Not selected."
            elif not row.get("installed"):
                state = (self.provider_install_status(provider_id)
                         if provider_id in installable_ids else {"status": "selected"})
                row["status"] = state["status"]
                row["status_message"] = state.get("message", "Selected; installation is required.")
            elif provider_id == "romm":
                from .plugins.romm import RommConfig
                from .plugins.romm.readiness import RommReadinessStore
                value = RommReadinessStore().snapshot(
                    selected=True, installed=True, config=RommConfig.from_file())
                state = value.get("status", "configuration_required")
                acquisition_config = RommConfig.from_file()
                acquisition_configured = bool(acquisition_config and acquisition_config.client_token)
                row["status"] = ("catalogue_ready_acquisition_required"
                                 if state == "ready" and not acquisition_configured else state)
                row["status_message"] = ("RomM catalogue is reconciled, but Acquisitiond does not have usable RomM configuration."
                                          if state == "ready" and not acquisition_configured else
                                          value.get("message", "Configure the RomM URL and Client API Token."))
                row["catalogue_reconciled"] = state == "ready"
                row["acquisition_configured"] = acquisition_configured
            elif provider_id in {"steam", "epic", "gog"}:
                value = readiness.get(provider_id)
                if provider_id == "steam":
                    auth = self.steam_auth_status()
                    current = str(value.get("status", ""))
                    if not auth.get("authenticated"):
                        row["status"] = (current if current in {"auth_failed", "authorization_pending"}
                                         else "authentication_required")
                        row["status_message"] = (str(value.get("message", ""))
                                                 if current in {"auth_failed", "authorization_pending"} else
                                                 "Authenticate in the Steam client using its QR or Steam Guard flow.")
                    elif not auth.get("entitlement_configured"):
                        row["status"] = "configuration_required"
                        row["status_message"] = ("Steam GUI account authenticated; configure the Steam ownership "
                                                 "API to reconcile titles.")
                    elif current == "ready":
                        row["status"] = "ready"
                        row["status_message"] = value.get("message", "Account validated and catalogue reconciled.")
                    elif current in {"auth_failed", "authorization_pending", "authenticated",
                                     "configuration_required", "reconciling", "sync_failed"}:
                        row["status"] = current
                        row["status_message"] = str(value.get("message", ""))
                    else:
                        row["status"] = "authenticated"
                        row["status_message"] = "Steam account authenticated; owned-library reconciliation is pending."
                    row["authentication"] = auth
                else:
                    auth = self.auth_status(provider_id)
                    if not auth.get("authenticated", False):
                        row["status"] = "authentication_required"
                        row["status_message"] = ("Account authentication status is unavailable; retry shortly."
                                                 if auth.get("status") in {"error", "unavailable"} else
                                                 f"Sign in to {row['name']} to continue.")
                    else:
                        row["status"] = value.get("status", "syncing")
                        row["status_message"] = value.get("message", "Account catalogue reconciliation is pending.")
                    row["authentication"] = {"status": auth.get("status", "authentication_required"),
                                              "authenticated": bool(auth.get("authenticated")),
                                              "methods": auth.get("methods", [])}
            elif provider_id == "questarr":
                running = self.service_state("lulu-questarr.service") == "active"
                healthy, message = self.test_provider("questarr")
                # Health, an account, and a backend do not prove Questarr's
                # authenticated configuration or initial reconciliation.
                row["configured"] = False
                row["running"] = running
                row["healthy"] = bool(healthy)
                row["status"] = "running" if running and healthy else "degraded"
                row["status_message"] = (
                    (message + " Operator-owned Questarr account/configuration is still required.")
                    if running and healthy else
                    (message or "Questarr service is not running; inspect its service logs."))
            elif provider_id in {"torrent", "usenet"}:
                target = "providers.torrent" if provider_id == "torrent" else "providers.usenet"
                ok, message = self.test_provider(target)
                row["connected"] = bool(ok)
                row["running"] = self.service_state(
                    "lulu-transmission.service" if provider_id == "torrent" else "nzbget.service") == "active"
                row["healthy"] = bool(ok)
                if not ok:
                    row["status"] = "configuration_required"
                    row["status_message"] = message
                elif provider_id == "usenet":
                    server = self.config.provider("providers.usenet.server")
                    acquisition = self.config.provider("providers.usenet")
                    server_credentials_configured = (
                        server.enabled and bool(str(server.get("host", "")).strip())
                        and server.secret_available("username") and server.secret_available("password"))
                    server_configured = server_credentials_configured and acquisition.enabled
                    server_validation = validations.get("providers.usenet.server")
                    server_authenticated = (bool(server_validation.get("ok"))
                                            if isinstance(server_validation, dict) else None)
                    row["authentication"] = {
                        "status": ("authenticated" if server_authenticated is True else
                                   "auth_failed" if server_authenticated is False else
                                   "authentication_required"),
                        "authenticated": server_authenticated,
                    }
                    row["news_server"] = {
                        "configured": bool(server_credentials_configured),
                        "executor_enabled": bool(acquisition.enabled),
                        "authenticated": server_authenticated,
                        "checked_at": server_validation.get("checked_at")
                            if isinstance(server_validation, dict) else None,
                        "message": server_validation.get("message", "")
                            if isinstance(server_validation, dict) else
                            "Usenet server credentials have not been tested.",
                    }
                    row["status"] = "configured" if server_configured else "configuration_required"
                    row["configured"] = server_configured
                    row["acquisition_configured"] = server_configured
                    row["status_message"] = (
                        "NZBGet RPC healthy; NNTP credentials were accepted, but a real transfer is not validated."
                        if server_configured and server_authenticated is True else
                        "NZBGet RPC healthy; NNTP connection test failed. Correct the server settings and retry."
                        if server_configured and server_authenticated is False else
                        "NZBGet RPC healthy; test the saved Usenet server credentials before downloads can be Ready."
                        if server_configured else
                        "Usenet server credentials are saved, but Acquisitiond has no registered Usenet executor."
                        if server_credentials_configured else
                        "NZBGet RPC healthy; configure and test a news server before downloads can be Ready.")
                else:
                    row["status"] = "configured"
                    row["configured"] = True
                    row["status_message"] = "Transmission RPC healthy; a real transfer has not been validated."
            else:
                row["status"] = "installed"
                row["status_message"] = "Installed; game and content launch readiness has not been validated."
            from .provider_state import normalized_provider_state
            current = str(row.get("status", "unknown"))
            auth = row.get("authentication") if isinstance(row.get("authentication"), dict) else {}
            row["state"] = normalized_provider_state(
                status=current, installed=bool(row.get("installed")),
                selected=bool(row.get("selected")),
                configured=bool(row.get("configured")) if "configured" in row else None,
                authenticated=bool(auth.get("authenticated")) if "authenticated" in auth else None,
                catalogue_reconciled=bool(row["catalogue_reconciled"])
                    if "catalogue_reconciled" in row else None,
                acquisition_configured=bool(row["acquisition_configured"])
                    if "acquisition_configured" in row else None,
                connected=bool(row["connected"]) if "connected" in row else None,
                running=bool(row["running"]) if "running" in row else None,
                healthy=bool(row["healthy"]) if "healthy" in row else None,
                failed=current in {"install_failed", "auth_failed", "sync_failed"},
                degraded=current in {"degraded", "catalogue_ready_acquisition_required"})
            result.append(row)
        return result

    def save_setup_credentials(self, provider_id: str, payload: dict[str, object]) -> dict[str, object]:
        if provider_id not in INTEGRATION_METADATA:
            raise ValueError("unsupported setup integration")
        if provider_id == "questarr":
            return {"configured": self.service_state("lulu-questarr.service") == "active"}
        if provider_id == "providers.steam":
            auth = self.steam_auth_status()
            steam_id = str(auth.get("steam_id", "")).strip()
            username = str(payload.get("steam_username", "")).strip()
            steam_password = str(payload.get("steam_password", ""))
            api_key = str(payload.get("api_key", ""))
            if not auth.get("authenticated") or not steam_id.isdecimal() or int(steam_id) < 1:
                raise ValueError("Steam sign-in must be active so Mudos can read your account ID")
            identities = {str(auth.get(key, "")).strip().casefold()
                          for key in ("account", "persona") if auth.get(key)}
            if not username or username.casefold() not in identities:
                raise ValueError("Enter the Steam username shown for the signed-in account")
            if not steam_password and not self.secrets.configured("steam", "password"):
                raise ValueError("Enter your Steam account password for SteamCMD verification")
            if not api_key and not self.secrets.configured("steam", "web-api-key"):
                raise ValueError("Enter your Steam Web API key")
            self.secrets.put("steam", "username", username)
            if steam_password:
                self.secrets.put("steam", "password", steam_password)
            if api_key:
                self.secrets.put("steam", "web-api-key", api_key)
            config_path = PATHS.plugins_root / "steam" / "steam.json"
            config_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            descriptor, temporary = tempfile.mkstemp(prefix=".steam-config-", dir=config_path.parent)
            try:
                with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                    json.dump({"steam_id": steam_id, "steam_username": username,
                               "api_key_file": "secret:steam/web-api-key", "timeout": 8}, stream)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.chmod(temporary, 0o600)
                os.replace(temporary, config_path)
            finally:
                try:
                    os.unlink(temporary)
                except FileNotFoundError:
                    pass
            return {"configured": True}
        values: dict[str, object] = {"enabled": True}
        secrets_in: dict[str, str] = {}
        references: dict[str, str] = {}
        if provider_id == "metadata.igdb":
            values["client_id"] = str(payload.get("client_id", "")).strip()
            secrets_in["client_secret"] = str(payload.get("client_secret", ""))
            references["client_secret"] = "metadata/igdb-client-secret"
        elif provider_id == "metadata.steamgriddb":
            secrets_in["api_key"] = str(payload.get("api_key", ""))
            references["api_key"] = "metadata/steamgriddb-api-key"
        elif provider_id == "providers.romm":
            from .plugins.romm import RommConfig
            endpoint = _setup_service_url(payload.get("url", ""), "RomM") if payload.get("url") else ""
            current_romm = RommConfig.from_file()
            if endpoint:
                RommConfig.save_url(endpoint)
            elif current_romm is None:
                raise ValueError("Enter your RomM server/base URL")
            token = str(payload.get("api_key", ""))
            if token:
                self.secrets.put("romm", "api-key", token)
            elif not self.secrets.configured("romm", "api-key"):
                raise ValueError("Enter the RomM Client API Token")
            return {"configured": bool(RommConfig.from_file()
                                        and self.secrets.configured("romm", "api-key"))}
        elif provider_id == "providers.prowlarr":
            values["endpoint"] = (_setup_service_url(payload.get("endpoint", ""), "Prowlarr")
                                   if payload.get("endpoint") else "")
            secrets_in["api_key"] = str(payload.get("api_key", ""))
            references["api_key"] = "prowlarr/api-key"
        elif provider_id == "providers.usenet.server":
            values = {
                "host": str(payload.get("host", "")).strip(),
                "port": int(payload.get("port", 563) or 563),
                "tls": str(payload.get("tls", "true")).casefold() in {"true", "1", "yes", "on"},
                "connections": int(payload.get("connections", 8) or 8),
                "enabled": True,
            }
            if not values["host"]:
                raise ValueError("Enter the hostname supplied by your Usenet provider")
            secrets_in.update({
                "username": str(payload.get("username", "")),
                "password": str(payload.get("password", "")),
            })
            references.update({"username": "usenet/server-username",
                               "password": "usenet/server-password"})
        current = self.config.provider(provider_id)
        if provider_id in {"providers.romm", "providers.prowlarr"} and not values.get("endpoint"):
            if not current.get("endpoint", ""):
                raise ValueError("Enter the service address")
            values.pop("endpoint", None)
        if provider_id == "metadata.igdb" and not values.get("client_id"):
            if not current.get("client_id", ""):
                raise ValueError("Enter the Twitch application Client ID")
            values.pop("client_id", None)
        values = {key: value for key, value in values.items() if value is not None}
        missing_secrets = [key for key, value in secrets_in.items()
                           if not value and not current.secret_available(key)]
        if missing_secrets:
            label = {"metadata.igdb": "Client Secret", "metadata.steamgriddb": "API key",
                     "providers.romm": "Client API Token", "providers.prowlarr": "API key",
                     "providers.usenet.server": "Usenet server credentials"}[provider_id]
            raise ValueError(f"Enter the {label}")
        usenet_acquisition_was_enabled = (
            self.config.provider("providers.usenet").enabled
            if provider_id == "providers.usenet.server" else False)
        self.config.update_provider(provider_id, values, secrets_in, secret_references=references)
        if provider_id == "providers.usenet.server":
            updated = self.config.provider(provider_id)
            from .nzbget_admin import apply_news_server
            try:
                apply_news_server(str(updated.get("host", "")), int(updated.get("port", 563)),
                                  bool(updated.get("tls", True)), int(updated.get("connections", 8)),
                                  updated.secret("username") or "", updated.secret("password") or "",
                                  bool(updated.get("enabled", True)))
                subprocess.run(["systemctl", "restart", "nzbget.service"],
                               stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL, check=True, timeout=10)
                ready, readiness_message = self.wait_for_nzbget_rpc()
                if not ready:
                    raise RuntimeError(readiness_message)
                # Acquisitiond registers this executor from the generic
                # providers.usenet configuration at service startup. NNTP-only
                # settings must not leave a healthy NZBGet daemon with no job
                # executor available to Mudos.
                self.config.update_provider("providers.usenet", {"enabled": True})
                try:
                    subprocess.run(["systemctl", "restart", "lulu-acquisition.service"],
                                   stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                   stderr=subprocess.DEVNULL, check=True, timeout=10)
                except (OSError, subprocess.SubprocessError):
                    self.config.update_provider("providers.usenet",
                                                {"enabled": usenet_acquisition_was_enabled})
                    raise ValueError("Usenet settings were applied to NZBGet, but Acquisitiond could not "
                                     "reload its provider executor. Check lulu-acquisition.service.") from None
            except (OSError, subprocess.SubprocessError, RuntimeError):
                # The generic provider settings and encrypted references have
                # already been saved. Report the daemon failure distinctly;
                # callers must not interpret that as a working transfer route.
                raise ValueError("Usenet settings were saved, but NZBGet could not apply them or restart. "
                                 "Check the NZBGet service before retrying setup.") from None
        return {"configured": self.config.provider(provider_id).configured}

    @staticmethod
    def start_provider_install(provider_id: str) -> dict[str, str]:
        allowed = {"steam", "epic", "gog", "lutris", "flatpak", "retroarch",
                   "dolphin", "pcsx2", "eden", "questarr", "torrent", "usenet"}
        if provider_id not in allowed:
            raise ValueError("This provider has no allowlisted installer")
        unit = f"lulu-provider-install@{provider_id}.service"
        subprocess.run(["systemctl", "reset-failed", unit],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       timeout=5, check=False)
        result = subprocess.run(["systemctl", "--no-block", "start", unit],
                                capture_output=True, text=True, timeout=5, check=False)
        if result.returncode:
            LOGGER.warning("provider install request failed provider=%s error=%s", provider_id,
                           result.stderr.strip().splitlines()[0] if result.stderr else "unknown")
            from .onboarding import record_install_start_failure
            record_install_start_failure(provider_id, "The provider installer could not be started. Retry installation.")
            raise ValueError("The provider installer could not be started")
        from .onboarding import record_install_start_failure
        record_install_start_failure(provider_id, "")
        return {"provider": provider_id, "status": "installing"}

    @staticmethod
    def provider_install_status(provider_id: str) -> dict[str, str]:
        if provider_id not in {"steam", "epic", "gog", "lutris", "flatpak", "retroarch",
                               "dolphin", "pcsx2", "eden", "questarr", "torrent", "usenet"}:
            raise ValueError("Unknown provider installer")
        unit = f"lulu-provider-install@{provider_id}.service"
        result = subprocess.run(["systemctl", "show", unit,
                                 "--property=ActiveState,SubState,Result,ExecMainStatus,ExecMainStartTimestamp"],
                                capture_output=True, text=True, timeout=3, check=False)
        values = dict(line.split("=", 1) for line in result.stdout.splitlines() if "=" in line)
        if values.get("ActiveState") in {"activating", "active"}:
            status = "installing"
        else:
            from .onboarding import PROVIDER_INFO, _provider_installed
            actual_id = {"transmission": "torrent", "nzbget": "usenet"}.get(provider_id, provider_id)
            info = PROVIDER_INFO.get(actual_id)
            installed = bool(info and _provider_installed(actual_id, info))
            if installed:
                status = "installed"
            elif (values.get("ActiveState") == "failed"
                  or values.get("ExecMainStartTimestamp") and values.get("Result") != "success"):
                status = "install_failed"
            elif (values.get("ExecMainStartTimestamp")
                  and values.get("ExecMainStatus") not in {"", "0"}):
                status = "install_failed"
            else:
                status = "selected"
        from .onboarding import install_start_failure
        start_failure = install_start_failure(provider_id) if status == "selected" else ""
        if start_failure:
            status = "install_failed"
        messages = {"installing": "Installation is running.",
                            "installed": "Installed.",
                            "install_failed": "Installation failed. See the service log for the actionable error.",
                            "selected": "Selected; installation has not started."}
        if start_failure:
            messages[status] = start_failure
        elif status == "install_failed":
            try:
                detail = subprocess.run(["journalctl", "-u", unit, "-n", "12", "-o", "cat", "--no-pager"],
                                        capture_output=True, text=True, timeout=3, check=False).stdout.strip()
                if detail:
                    messages[status] = detail[-700:]
            except (OSError, subprocess.SubprocessError):
                pass
        return {"provider": provider_id, "status": status, "message": messages[status]}

    @staticmethod
    def record_provider_install_timeout(provider_id: str) -> dict[str, str]:
        # The unit may have started between the final browser poll and this
        # request. Never write a failure over running or installed evidence.
        state = AdminApp.provider_install_status(provider_id)
        if state["status"] != "selected":
            return state
        from .onboarding import record_install_start_failure
        message = "Installer did not start within 16 seconds. Check its service status and retry."
        record_install_start_failure(provider_id, message)
        return {"provider": provider_id, "status": "install_failed", "message": message}

    def begin_steam_oobe_auth(self) -> dict[str, object]:
        from .provider_readiness import ProviderReadinessStore
        request_id = secrets.token_hex(6)
        LOGGER.info("steam_auth_stage stage=admin-request-accepted request_id=%s", request_id)
        current_auth = self.steam_auth_status()
        if current_auth.get("authenticated"):
            LOGGER.info("steam_auth_stage stage=already-authenticated request_id=%s", request_id)
            return {"status": "authenticated", "message": "Steam is already signed in."}
        readiness = ProviderReadinessStore()
        readiness.set("steam", "authenticating",
                      message="Starting the Steam client authentication flow.")
        account = pwd.getpwnam("lulu")
        environment = dict(os.environ)
        environment.update({"HOME": account.pw_dir,
                            "XDG_CONFIG_HOME": str(Path(account.pw_dir) / ".config"),
                            "XDG_DATA_HOME": str(Path(account.pw_dir) / ".local/share"),
                            "XDG_RUNTIME_DIR": f"/run/user/{account.pw_uid}",
                            "DBUS_SESSION_BUS_ADDRESS": f"unix:path=/run/user/{account.pw_uid}/bus"})
        message = ("Steam is opening on the Mudos screen. Startup can take a little while; "
                   "sign in there, then return to setup.")
        try:
            result = subprocess.run(
                ["busctl", "--user", "--json=short", "--timeout=70s", "call", "org.lulu.Consoled",
                 "/org/lulu/Console", "org.lulu.Console", "BeginPluginAuthenticationTraced",
                 "ss", "steam", request_id],
                stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=75,
                check=False, env=environment)
        except subprocess.TimeoutExpired:
            LOGGER.error("steam_auth_stage stage=consoled-request-timeout request_id=%s", request_id)
            readiness.set("steam", "auth_failed",
                          message="Steam launch request timed out before a surface token was returned.")
            return {"status": "request_timeout", "message":
                    "Steam did not finish starting its sign-in surface. Check Consoled, Sessiond, and Gamescope logs."}
        if result.returncode:
            LOGGER.error("steam_auth_stage stage=consoled-request-failed request_id=%s returncode=%s stderr=%s",
                         request_id, result.returncode, (result.stderr or result.stdout or "")[-1000:])
            readiness.set("steam", "auth_failed",
                          message="Consoled could not accept the Steam launch request.")
            raise RuntimeError("Mudos could not launch Steam sign-in. Check the console session and retry.")
        readiness.set("steam", "authorization_pending",
                      message="Steam is open. Complete QR sign-in or Steam Guard approval on the console.")
        try:
            response = json.loads(result.stdout)
            launch = json.loads(response["data"][0]).get("launch", "")
        except (ValueError, TypeError, KeyError, IndexError):
            launch = ""
        LOGGER.info("steam_auth_stage stage=consoled-request-complete request_id=%s token=%s",
                    request_id, launch or "none")
        return {"status": "authorization_pending", "launch": launch,
                "message": "Steam is open. Complete QR sign-in or Steam Guard approval on the console."}

    @staticmethod
    def dismiss_steam_oobe_auth(launch_token: str) -> bool:
        if not launch_token:
            return False
        account = pwd.getpwnam("lulu")
        environment = dict(os.environ)
        environment.update({"HOME": account.pw_dir,
                            "XDG_RUNTIME_DIR": f"/run/user/{account.pw_uid}",
                            "DBUS_SESSION_BUS_ADDRESS": f"unix:path=/run/user/{account.pw_uid}/bus"})
        result = subprocess.run(
            ["busctl", "--user", "--json=short", "call", "org.lulu.Consoled",
             "/org/lulu/Console", "org.lulu.Console", "DismissPluginAuthentication",
             "ss", "steam", launch_token],
            stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=8,
            check=True, env=environment)
        response = json.loads(result.stdout)
        return bool(json.loads(response["data"][0]).get("dismissed"))

    def steam_oobe_auth_status(self) -> dict[str, object]:
        from .provider_readiness import ProviderReadinessStore
        auth = self.steam_auth_status()
        readiness = ProviderReadinessStore()
        current = readiness.get("steam")
        if auth.get("authenticated"):
            state = "authenticated" if auth.get("entitlement_configured") else "configuration_required"
            message = ("Steam account authenticated; owned-library reconciliation can start."
                       if state == "authenticated" else
                       "Steam account authenticated; Steam Web API ownership configuration is required.")
            readiness.set("steam", state, message=message)
            return {"status": state, "message": message, "authentication": auth}
        if current.get("status") == "authorization_pending" and auth.get("client_running"):
            return {"status": "authorization_pending", "message": current.get("message", "Waiting for Steam approval."),
                    "authentication": auth}
        if current.get("status") == "authorization_pending":
            try:
                age = max(0, int(time.time()) - int(current.get("updated_at", 0)))
            except (TypeError, ValueError):
                age = 60
            if age < 45:
                return {"status": "authorization_pending",
                        "message": "Steam is opening on the Mudos screen. Startup can take a little while.",
                        "authentication": auth}
        if current.get("status") in {"authorization_pending", "authenticating"}:
            message = "The Steam sign-in window is no longer open. Resume authentication to continue QR or Guard approval."
            readiness.set("steam", "authentication_required", message=message)
            return {"status": "authentication_required", "message": message,
                    "authentication": auth}
        return {"status": "authentication_required",
                "message": "Authenticate in the Steam client using its QR or Steam Guard flow.",
                "authentication": auth}

    def steam_auth_status(self) -> dict[str, object]:
        """Read GUI auth state from Consoled's public plugin-auth boundary."""
        account = pwd.getpwnam("lulu")
        environment = dict(os.environ)
        environment.update({"HOME": account.pw_dir,
                            "XDG_CONFIG_HOME": str(Path(account.pw_dir) / ".config"),
                            "XDG_DATA_HOME": str(Path(account.pw_dir) / ".local/share"),
                            "XDG_RUNTIME_DIR": f"/run/user/{account.pw_uid}",
                            "DBUS_SESSION_BUS_ADDRESS": f"unix:path=/run/user/{account.pw_uid}/bus"})
        try:
            result = subprocess.run(
                ["busctl", "--user", "--json=short", "call", "org.lulu.Consoled",
                 "/org/lulu/Console", "org.lulu.Console", "GetPluginAuthStatus", "s", "steam"],
                stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=5,
                check=True, env=environment)
            response = json.loads(result.stdout)
            values = response.get("data", []) if isinstance(response, dict) else []
            if isinstance(values, list) and len(values) == 1:
                status = json.loads(values[0])
                if isinstance(status, dict):
                    return status
        except (OSError, ValueError, TypeError, subprocess.SubprocessError):
            LOGGER.info("Consoled Steam auth status unavailable; using local status source")
        return self.auth_status("steam")

    def password_configured(self) -> bool:
        return bool(onboarding_state().get("admin_password_configured", False))

    def authenticate(self, password: str) -> bool:
        from .managed_account import MANAGED_ADMIN_ACCOUNT, authenticate_managed_account
        return authenticate_managed_account(password, MANAGED_ADMIN_ACCOUNT)

    def set_initial_admin_password(self, password: str, confirmation: str) -> bool:
        state = onboarding_state()
        if (state.get("status") not in {"never", "partial", "dismissed"}
                or self.password_configured()):
            raise ValueError("Initial password establishment is no longer available")
        if password != confirmation:
            raise ValueError("The new passwords do not match.")
        if len(password) < 8 or len(password) > 1024 or "\0" in password:
            raise ValueError("Use a password of at least 8 characters.")
        try:
            result = subprocess.run(
                ["/usr/bin/pkexec", "/usr/libexec/mudos-set-initial-password"],
                input=f"{password}\n{confirmation}\n", capture_output=True,
                text=True, timeout=30, check=False,
            )
        except (OSError, subprocess.SubprocessError) as error:
            LOGGER.warning("initial managed-account password operation failed error_type=%s",
                           type(error).__name__)
            return False
        if result.returncode:
            diagnostic = (result.stderr or result.stdout or "").strip().splitlines()
            LOGGER.warning("initial managed-account password operation failed status=%d detail=%s",
                           result.returncode, diagnostic[0][:180] if diagnostic else "unavailable")
            return False
        from .managed_account import MANAGED_ADMIN_ACCOUNT, authenticate_managed_account
        if not authenticate_managed_account(password, MANAGED_ADMIN_ACCOUNT):
            LOGGER.error("initial managed-account password was written but PAM verification failed")
            return False
        self.secrets.clear("admin", "password-hash")
        save_admin_password_configured()
        return True

    def change_admin_password(self, current_password: str, new_password: str) -> bool:
        from .managed_account import MANAGED_ADMIN_ACCOUNT, change_managed_account_password
        changed = change_managed_account_password(current_password, new_password,
                                                  MANAGED_ADMIN_ACCOUNT)
        if changed:
            # A former separate web hash must never remain a parallel login
            # authority after the OS account becomes authoritative.
            self.secrets.clear("admin", "password-hash")
            save_admin_password_configured()
        return changed

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
            auth = self._auth(provider_id)
            auth_state = auth.status() if auth else {"status": "unavailable"}
            status = config.status
            configured = config.configured
            if provider_id in {"epic", "gog"}:
                # OOBE and the catalogue/acquisition clients use Legendary's
                # and gogdl's provider-owned auth files. Generic TOML config is
                # not their authentication authority.
                configured = bool(auth_state.get("authenticated") or auth_state.get("configured"))
                status = "configured" if configured else "not_configured"
            elif provider_id == "providers.romm":
                from .plugins.romm import RommConfig
                romm = RommConfig.from_file()
                configured = bool(romm and romm.client_token)
                status = "configured" if configured else "not_configured"
            elif provider_id == "steam":
                from .plugins.steam.entitlements import SteamEntitlementConfig
                steam = SteamEntitlementConfig.from_file()
                configured = bool(steam and self.secrets.configured("steam", "web-api-key"))
                status = "configured" if configured else "not_configured"
            rows.append({"id": provider_id, "name": name, "status": status,
                         "configured": configured,
                         "secrets": {key: config.secret_available(key) for key in config.secret_refs},
                         "authentication": auth_state})
        return rows

    def _auth(self, provider_id: str) -> object | None:
        values = self.plugins.for_plugin(provider_id, "authentication")
        return values[0] if values else None

    def auth_status(self, provider_id: str) -> dict[str, object]:
        auth = self._auth(provider_id)
        if auth is None:
            return {"provider_id": provider_id, "status": "unavailable", "methods": []}
        try:
            value = dict(auth.status())
            value.setdefault("provider_id", provider_id)
            value.setdefault("methods", list(getattr(auth, "authentication_methods", lambda: ())()))
            return value
        except Exception as error:
            LOGGER.exception("provider auth status failed provider=%s", provider_id)
            return {"provider_id": provider_id, "status": "error", "methods": [], "error": str(error)}

    def begin_auth(self, provider_id: str):
        auth = self._auth(provider_id)
        if auth is None:
            raise ValueError("provider authentication is unavailable")
        begin = getattr(auth, "begin_admin_auth", None) or auth.begin
        details = dict(begin())
        method = str(details.get("auth_method") or (auth.authentication_methods()[0]
                                                     if hasattr(auth, "authentication_methods") and auth.authentication_methods()
                                                     else "auth_browser"))
        handoff = {key: str(details.get(key, "")) for key in ("verification_url", "user_code", "qr_payload")}
        transaction = self.auth_transactions.create(provider_id, method, **handoff)
        return transaction

    def complete_auth(self, transaction_id: str, code: str) -> dict[str, object]:
        transaction = self.auth_transactions.get(transaction_id)
        if transaction is None:
            raise ValueError("authentication transaction expired")
        auth = self._auth(transaction.provider)
        if auth is None or not hasattr(auth, "complete_code"):
            raise ValueError("this provider has no browser-code completion boundary")
        self.auth_transactions.update(transaction_id, AuthTransactionState.EXCHANGING_TOKEN)
        try:
            value = auth.complete_code(code.strip())
            self.auth_transactions.update(transaction_id, AuthTransactionState.AUTHENTICATED)
            return {"transaction": self.auth_transactions.get(transaction_id).public(), "status": value}
        except Exception as error:
            self.auth_transactions.update(transaction_id, AuthTransactionState.FAILED, error=str(error))
            raise

    def complete_setup_auth(self, provider_id: str, transaction_id: str, code: str) -> dict[str, object]:
        if provider_id not in {"epic", "gog"}:
            raise ValueError("OOBE browser sign-in is unavailable for this provider")
        transaction = self.auth_transactions.get(transaction_id)
        if transaction is None or transaction.provider != provider_id:
            raise ValueError("authentication transaction expired")
        try:
            self.complete_auth(transaction_id, code)
        except FileNotFoundError as error:
            if provider_id in {"epic", "gog"}:
                provider_name = "Legendary" if provider_id == "epic" else "gogdl"
                raise ValueError(
                    f"{provider_id.title()} sign-in could not start because {provider_name} is "
                    "missing or incomplete. Retry the provider installation, then enter a fresh "
                    "authorization code."
                ) from error
            raise
        except RuntimeError as error:
            if provider_id == "gog" and "heroic-gogdl Python module is unavailable" in str(error):
                raise ValueError(
                    "GOG sign-in could not start because gogdl is missing or incomplete. "
                    "Retry the GOG provider installation, then enter a fresh authorization code."
                ) from error
            raise
        auth = self.auth_status(provider_id)
        if not auth.get("authenticated"):
            raise ValueError(f"{provider_id.title()} did not confirm the sign-in")
        return {"status": "authenticated", "provider": provider_id}

    def cancel_auth(self, transaction_id: str) -> None:
        if self.auth_transactions.get(transaction_id):
            self.auth_transactions.update(transaction_id, AuthTransactionState.CANCELLED)

    def sign_out(self, provider_id: str) -> None:
        auth = self._auth(provider_id)
        if auth is None or not hasattr(auth, "sign_out"):
            raise ValueError("provider sign out is unavailable")
        auth.sign_out()

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

    @staticmethod
    def questarr_account_status() -> str:
        # Upstream's public first-run status is not evidence of an authenticated
        # API session, downloader configuration, or a completed reconciliation.
        try:
            with urllib.request.urlopen("http://127.0.0.1:5000/api/auth/status", timeout=2) as response:
                value = json.loads(response.read(4096))
            if isinstance(value, dict) and type(value.get("hasUsers")) is bool:
                return "present" if value["hasUsers"] else "missing"
        except (OSError, urllib.error.URLError, TimeoutError, ValueError):
            pass
        return "unknown"

    @staticmethod
    def plugin_service_status(service: object) -> str:
        # The Flatpak contribution describes a local command provider, not a
        # daemon. A running/stopped systemd badge would be misleading. Do not
        # turn arbitrary plugin health IDs or URLs into commands/network calls.
        if getattr(service, "service_id", "") != "flatpak" or getattr(service, "health", "") != "flatpak":
            return "unknown"
        executable = shutil.which("flatpak")
        if not executable:
            return "missing"
        try:
            result = subprocess.run([executable, "--version"], capture_output=True,
                                    text=True, timeout=2, check=False)
            return "available" if result.returncode == 0 else "unknown"
        except (OSError, subprocess.TimeoutExpired):
            return "unknown"

    def test_provider(self, provider_id: str) -> tuple[bool, str]:
        config = self.config.provider(provider_id)
        if provider_id == "providers.steam":
            try:
                from .plugins.steam.entitlements import SteamEntitlementConfig, SteamEntitlementSource
                source = SteamEntitlementSource()
                games = source.refresh()
                if not source.last_refresh_succeeded:
                    return False, source.last_error or "Steam ownership query failed"
                account = pwd.getpwnam("lulu")
                environment = dict(os.environ)
                environment.update({"HOME": account.pw_dir,
                                    "XDG_CONFIG_HOME": str(Path(account.pw_dir) / ".config"),
                                    "XDG_DATA_HOME": str(Path(account.pw_dir) / ".local/share"),
                                    "XDG_RUNTIME_DIR": f"/run/user/{account.pw_uid}",
                                    "DBUS_SESSION_BUS_ADDRESS": f"unix:path=/run/user/{account.pw_uid}/bus"})
                result = subprocess.run(
                    ["busctl", "--user", "--timeout=120s", "call", "org.lulu.Consoled",
                     "/org/lulu/Console", "org.lulu.Console", "RefreshStages", "as", "1", "steam"],
                    stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=125,
                    check=False, env=environment)
                if result.returncode:
                    return False, "Steam titles were fetched, but catalogue reconciliation failed"
                authentication = subprocess.run(
                    ["busctl", "--user", "--timeout=360s", "call", "org.lulu.Consoled",
                     "/org/lulu/Console", "org.lulu.Console", "VerifySteamAcquisition"],
                    stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=365,
                    check=False, env=environment)
                if authentication.returncode:
                    return False, ("Steam ownership is configured, but SteamCMD authentication "
                                   "was not completed. Approve the login on your Steam Guard device "
                                   "or choose Enter Code on the Mudos screen.")
                return True, f"Steam ownership validated; {len(games)} titles reconciled into Installable"
            except Exception:
                LOGGER.exception("Steam ownership validation/reconciliation failed")
                return False, "Steam ownership validation or catalogue reconciliation failed"
        if provider_id == "questarr":
            if self.service_state("lulu-questarr.service") != "active":
                return False, "Questarr service is not installed or running"
            questarr_service = next((item for item in SERVICES if item[0] == "questarr"), None)
            if questarr_service is None or self.service_health(questarr_service) != "healthy":
                return False, "Questarr API health check failed"
            account = self.questarr_account_status()
            if account == "missing":
                return False, "Create the Questarr first-run account in its UI before configuring downloads"
            if account == "unknown":
                return False, "Questarr account setup status is unavailable"
            backends = [self.test_provider("providers.torrent"), self.test_provider("providers.usenet")]
            if not any(ok for ok, _ in backends):
                return False, "Questarr is running but no Transmission or NZBGet backend is ready"
            return False, ("Questarr account exists and an acquisition backend is healthy; "
                           "verify authenticated Questarr setup and initial reconciliation in its UI")
        if provider_id == "metadata.igdb":
            try:
                from .igdb import IGDBClient, IGDBError
                result = IGDBClient(self.config).test_connection()
                return (True, "IGDB connection established") if result == "connected" else (False, "IGDB credentials are incomplete")
            except IGDBError as error:
                reason = str(error)
                if reason.startswith(("token-http-401", "token-http-403")):
                    return False, "IGDB authentication failed"
                return False, "IGDB service unavailable"
            except Exception:
                return False, "IGDB service unavailable"
        if provider_id == "metadata.steamgriddb":
            try:
                from .artwork import SteamGridDBArtwork
                result = SteamGridDBArtwork().test_connection()
                return (True, "SteamGridDB connection established") if result == "connected" else (False, "SteamGridDB credentials are incomplete")
            except urllib.error.HTTPError as error:
                return (False, "SteamGridDB authentication failed") if error.code in {401, 403} else (False, "SteamGridDB service unavailable")
            except (OSError, urllib.error.URLError, TimeoutError, ValueError):
                return False, "SteamGridDB service unavailable"
            except Exception:
                return False, "SteamGridDB service unavailable"
        if provider_id == "providers.romm":
            romm = None
            try:
                from .plugins.romm import RommClient, RommConfig, RommApiError
                from .plugins.romm.readiness import RommReadinessStore
                romm = RommConfig.from_file()
                if romm is None or not romm.client_token:
                    RommReadinessStore().set("missing_configuration", romm,
                                             message="RomM server URL and Client API Token are required.")
                    return False, "RomM address or Client API Token is missing"
                games = RommClient(romm).list_games()
                RommReadinessStore().set(
                    "authenticated", romm,
                    message="RomM Client API Token validated; initial catalogue sync is starting.",
                )
                return True, f"RomM authenticated; {len(games)} library records are accessible"
            except RommApiError as error:
                text = str(error).casefold()
                if "401" in text or "403" in text or "unauthor" in text:
                    from .plugins.romm.readiness import RommReadinessStore
                    RommReadinessStore().set("configuration_invalid", romm,
                                             message="RomM rejected the Client API Token.")
                    return False, "RomM rejected the Client API Token"
                from .plugins.romm.readiness import RommReadinessStore
                RommReadinessStore().set("sync_failed", romm,
                                         message="RomM authentication or library validation failed.")
                return False, "RomM service unavailable or returned an unsupported response"
            except Exception:
                return False, "RomM service unavailable or returned an unsupported response"
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
        if provider_id == "providers.usenet.server":
            config = self.config.provider(provider_id)
            host = str(config.get("host", "")).strip()
            username = config.secret("username") or ""
            password = config.secret("password") or ""
            try:
                port = int(config.get("port", 0))
            except (TypeError, ValueError):
                port = 0
            if not host or not (1 <= port <= 65535) or not username or not password:
                return False, "Usenet server hostname, port and credentials are required"
            try:
                import socket
                import ssl
                if any(char in host + username + password for char in "\r\n"):
                    return False, "Usenet server settings contain invalid line breaks"
                with socket.create_connection((host, port), timeout=6) as raw:
                    raw.settimeout(6)
                    connection = (ssl.create_default_context().wrap_socket(raw, server_hostname=host)
                                  if bool(config.get("tls", True)) else raw)
                    pending = b""

                    def response() -> int:
                        nonlocal pending
                        while b"\n" not in pending:
                            chunk = connection.recv(512)
                            if not chunk or len(pending) + len(chunk) > 4096:
                                raise OSError("invalid NNTP response")
                            pending += chunk
                        line, pending = pending.split(b"\n", 1)
                        line = line.rstrip(b"\r")
                        if len(line) < 3 or not line[:3].isdigit():
                            raise OSError("invalid NNTP response")
                        return int(line[:3])

                    if response() not in {200, 201}:
                        return False, "Usenet server rejected the NNTP connection"
                    connection.sendall(b"AUTHINFO USER " + username.encode("utf-8") + b"\r\n")
                    status = response()
                    if status == 381:
                        connection.sendall(b"AUTHINFO PASS " + password.encode("utf-8") + b"\r\n")
                        status = response()
                    if status != 281:
                        return False, "Usenet server did not accept the configured credentials"
                    connection.sendall(b"QUIT\r\n")
                    return True, "Usenet NNTP server authenticated successfully"
            except (OSError, ssl.SSLError, UnicodeError, TimeoutError):
                return False, "Usenet server is unavailable or did not accept the configured credentials"
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

    def wait_for_nzbget_rpc(self, *, attempts: int = 20, interval: float = 0.25) -> tuple[bool, str]:
        """Wait for a restarted NZBGet daemon to expose authenticated JSON-RPC."""
        import time
        result = (False, "NZBGet RPC did not become ready")
        for attempt in range(max(1, attempts)):
            result = self.test_provider("providers.usenet")
            if result[0]:
                return result
            if attempt + 1 < attempts:
                time.sleep(max(0.0, interval))
        return result

    def reconcile_romm_catalogue(self) -> dict[str, object]:
        """Run the normal Consoled RomM reconciliation and wait for its result."""
        import pwd
        account = pwd.getpwnam("lulu")
        environment = dict(os.environ)
        environment.update({
            "HOME": account.pw_dir,
            "XDG_CONFIG_HOME": str(Path(account.pw_dir) / ".config"),
            "XDG_DATA_HOME": str(Path(account.pw_dir) / ".local/share"),
            "XDG_RUNTIME_DIR": f"/run/user/{account.pw_uid}",
            "DBUS_SESSION_BUS_ADDRESS": f"unix:path=/run/user/{account.pw_uid}/bus",
        })
        command = ["busctl", "--user", "--timeout=180s", "call", "org.lulu.Consoled",
                   "/org/lulu/Console", "org.lulu.Console", "RefreshStages", "as", "1", "romm"]
        try:
            result = subprocess.run(command, stdin=subprocess.DEVNULL, capture_output=True,
                                    text=True, timeout=185, check=False, env=environment)
        except (OSError, subprocess.TimeoutExpired) as error:
            LOGGER.warning("RomM initial reconciliation could not be requested error_type=%s",
                           type(error).__name__)
            return {"ok": False, "status": "sync_failed",
                    "message": "RomM authenticated, but its initial catalogue sync could not start."}
        if result.returncode:
            LOGGER.warning("RomM initial reconciliation failed to run exit=%d", result.returncode)
            return {"ok": False, "status": "sync_failed",
                    "message": "RomM authenticated, but its initial catalogue sync failed."}
        from .plugins.romm import RommConfig
        from .plugins.romm.readiness import RommReadinessStore
        state = RommReadinessStore().snapshot(selected=True, installed=True,
                                               config=RommConfig.from_file())
        return {**state, "ok": state.get("status") == "ready"}


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

    def _json(self, value: object, status: int = 200) -> None:
        data = json.dumps(value, separators=(",", ":")).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _json_body(self) -> dict[str, object]:
        length = min(int(self.headers.get("Content-Length", "0")), 65536)
        value = json.loads(self.rfile.read(length) or b"{}")
        if not isinstance(value, dict):
            raise ValueError("Expected a JSON object")
        return value

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
            if urllib.parse.urlsplit(self.path).path.startswith("/api/"):
                self._json({"error": "Your admin session expired. Sign in again to continue setup."}, 401)
            else:
                self._redirect("/login")
        return csrf

    def do_GET(self) -> None:
        path = urllib.parse.urlsplit(self.path).path
        query = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
        if path == "/login":
            if not APP.password_configured():
                self._redirect("/setup")
                return
            message = "" if APP.password_configured() else "Admin access has not been set up yet."
            self._send(_login_page(message) if message else _login_page()); return
        if path == "/setup":
            if APP.password_configured() and self._require() is None:
                return
            self._setup_page(query.get("local", [""])[0] == "1")
            return
        if path in {"/setup/qr.png", "/recovery/qr.png"}:
            try:
                target = "http://mudos.local/recovery" if path.startswith("/recovery/") \
                    else "http://mudos.local/setup"
                result = subprocess.run(["qrencode", "-t", "PNG", "-o", "-", target],
                                        capture_output=True, timeout=3, check=True)
                self.send_response(200); self.send_header("Content-Type", "image/png")
                self.send_header("Cache-Control", "public, max-age=3600")
                self.send_header("Content-Length", str(len(result.stdout))); self.end_headers()
                self.wfile.write(result.stdout)
            except (OSError, subprocess.SubprocessError):
                self._send(b"QR code generator is unavailable", 503)
            return
        if path == "/recovery":
            if APP.password_configured() and self._require() is None:
                return
            self._recovery_page()
            return
        if path == "/api/setup/state":
            if (APP.password_configured() or onboarding_state().get("status") == "completed") \
                    and self._require() is None:
                return
            self._json(APP.setup_snapshot())
            return
        if path == "/api/setup/steam/auth-status":
            if (APP.password_configured() or onboarding_state().get("status") == "completed") \
                    and self._require() is None:
                return
            self._json(APP.steam_oobe_auth_status())
            return
        if path.startswith("/api/setup/install/"):
            if (APP.password_configured() or onboarding_state().get("status") == "completed") \
                    and self._require() is None:
                return
            provider_id = urllib.parse.unquote(path.removeprefix("/api/setup/install/"))
            try:
                self._json(APP.provider_install_status(provider_id))
            except (ValueError, OSError, subprocess.SubprocessError) as error:
                self._json({"error": str(error)}, 400)
            return
        if path == "/api/recovery/status":
            self._json(_recovery_snapshot())
            return
        if self._require() is None: return
        if path == "/": self._dashboard(); return
        if path == "/providers": self._redirect("/integrations"); return
        if path == "/integrations": self._providers(); return
        if path == "/api/providers":
            self._json(APP.provider_rows()); return
        if path.endswith("/callback") and path.startswith("/auth/"):
            parts = [urllib.parse.unquote(item) for item in path.split("/") if item]
            try:
                APP.complete_auth(parts[2], query.get("code", [""])[0])
                self._send(_page("Authentication complete", _notice("Connected", "Provider authentication completed.", "success")))
            except Exception as error:
                self._send(_page("Authentication failed", _notice("Authentication failed", str(error), "error")), 400)
            return
        if path.startswith("/auth/"):
            self._auth_page(*[urllib.parse.unquote(item) for item in path.split("/")[2:]]); return
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
        path = urllib.parse.urlsplit(self.path).path
        request_payload = None
        protected_setup = APP.password_configured() or onboarding_state().get("status") == "completed"
        if protected_setup and (path.startswith("/api/setup/") or path == "/api/setup/install"):
            if self._require() is None:
                return
            token = self._token()
            csrf = APP.session(token)
            if path != "/api/setup/files":
                request_payload = self._json_body()
                if not hmac.compare_digest(str(request_payload.get("csrf", "")), csrf or ""):
                    self._json({"error": "Request rejected"}, 403)
                    return
        if path.startswith("/api/setup/") and path != "/api/setup/install":
            try:
                if path == "/api/setup/files":
                    from .setup_files import read_multipart, save_platform_files
                    content_length = int(self.headers.get("Content-Length", "0"))
                    fields, uploads = read_multipart(
                        self.rfile, self.headers.get("Content-Type", ""), content_length)
                    if protected_setup:
                        csrf = APP.session(self._token())
                        if not hmac.compare_digest(fields.get("csrf", ""), csrf or ""):
                            for upload in uploads:
                                upload.path.unlink(missing_ok=True)
                            self._json({"error": "Request rejected"}, 403)
                            return
                    try:
                        saved = save_platform_files(
                            fields.get("platform", ""), fields.get("requirement", ""), uploads)
                    except OSError:
                        for upload in uploads:
                            upload.path.unlink(missing_ok=True)
                        LOGGER.exception("emulator setup file write failed platform=%s requirement=%s",
                                         fields.get("platform", ""), fields.get("requirement", ""))
                        raise ValueError("System files could not be written to the selected storage target. "
                                         "Check that the target is mounted and writable.") from None
                    except Exception:
                        for upload in uploads:
                            upload.path.unlink(missing_ok=True)
                        raise
                    try:
                        refresh = urllib.request.Request(
                            "http://127.0.0.1:38123/refresh?stage=local",
                            data=b"", method="POST")
                        with urllib.request.urlopen(refresh, timeout=30):
                            pass
                        update_view = urllib.request.Request(
                            "http://127.0.0.1:38123/ui-refresh?group=library-platforms",
                            data=b"", method="POST")
                        with urllib.request.urlopen(update_view, timeout=5):
                            pass
                    except (OSError, urllib.error.URLError, TimeoutError):
                        LOGGER.info("emulator setup file uploaded; live catalogue refresh unavailable")
                    self._json({"saved": saved, "setup_files": __import__(
                        "lulu.setup_files", fromlist=["file_setup_manifest"]
                    ).file_setup_manifest(set(onboarding_state().get("selected_providers", [])))})
                    return
                payload = request_payload if request_payload is not None else self._json_body()
                action = path.removeprefix("/api/setup/")
                if action == "progress":
                    requested = (_string_list(payload["providers"])
                                 if "providers" in payload else None)
                    if requested is not None:
                        plan = APP.components.resolve_selection(requested)
                        if plan.unknown:
                            raise ValueError("Unknown Mudos component selection: " + ", ".join(plan.unknown))
                        if plan.missing_any:
                            missing = "; ".join(f"{component} needs one of {', '.join(options)}"
                                                 for component, options in plan.missing_any)
                            raise ValueError(missing)
                        requested = list(plan.selected)
                    state = save_progress(
                        providers=requested,
                        integrations=_string_list(payload["integrations"]) if "integrations" in payload else None)
                    self._json({"state": state})
                elif action == "skip-integration":
                    from .onboarding import skip_integration
                    self._json({"state": skip_integration(str(payload.get("integration", "")))})
                elif action == "steam/authenticate":
                    self._json(APP.begin_steam_oobe_auth())
                elif action == "steam/dismiss":
                    self._json({"dismissed": APP.dismiss_steam_oobe_auth(
                        str(payload.get("launch", "")))})
                elif action == "provider-authenticate":
                    provider_id = str(payload.get("provider", ""))
                    if provider_id not in {"epic", "gog"}:
                        raise ValueError("OOBE browser sign-in is unavailable for this provider")
                    if provider_id not in onboarding_state().get("selected_providers", []):
                        raise ValueError("Select and install this provider before signing in")
                    transaction = APP.begin_auth(provider_id)
                    self._json(transaction.public())
                elif action == "provider-auth-complete":
                    provider_id = str(payload.get("provider", ""))
                    transaction_id = str(payload.get("transaction_id", ""))
                    code = str(payload.get("code", ""))
                    result = APP.complete_setup_auth(provider_id, transaction_id, code)
                    try:
                        refresh = urllib.request.Request(
                            f"http://127.0.0.1:38123/refresh?stage={urllib.parse.quote(provider_id)}",
                            data=b"", method="POST")
                        with urllib.request.urlopen(refresh, timeout=90):
                            pass
                        update_view = urllib.request.Request(
                            "http://127.0.0.1:38123/ui-refresh?group=store",
                            data=b"", method="POST")
                        with urllib.request.urlopen(update_view, timeout=5):
                            pass
                    except (OSError, urllib.error.URLError, TimeoutError):
                        LOGGER.info("provider authentication completed; live catalogue refresh unavailable provider=%s",
                                    provider_id)
                    self._json(result)
                elif action == "credentials":
                    integration = str(payload.get("integration", ""))
                    result = APP.save_setup_credentials(integration, payload)
                    save_validation(integration, False, "Connection details saved; test this integration before continuing.")
                    self._json(result)
                elif action == "install-timeout":
                    self._json(APP.record_provider_install_timeout(str(payload.get("provider", ""))))
                elif action == "test":
                    integration = str(payload.get("integration", ""))
                    ok, message = APP.test_provider(integration)
                    result = {"ok": ok, "message": message}
                    if ok and integration == "providers.romm":
                        result.update(APP.reconcile_romm_catalogue())
                        ok = bool(result.get("ok"))
                        message = ("RomM is Ready and its catalogue has been reconciled."
                                   if ok else str(result.get("message", "RomM initial catalogue sync failed.")))
                        result.update({"ok": ok, "message": message})
                    save_validation(integration, ok, message)
                    if ok and integration in {"metadata.igdb", "metadata.steamgriddb"}:
                        # Provider catalogues may already be present from the
                        # earlier account stage. Once metadata credentials are
                        # validated, run the normal metadata/media stages now.
                        stages = ("metadata", "metadata-enrichment", "artwork")
                        refresh = urllib.request.Request(
                            "http://127.0.0.1:38123/refresh?" + urllib.parse.urlencode(
                                [("stage", stage) for stage in stages]), data=b"", method="POST")
                        try:
                            with urllib.request.urlopen(refresh, timeout=120):
                                pass
                        except (OSError, urllib.error.URLError, TimeoutError):
                            LOGGER.info("metadata credentials validated; first enrichment refresh unavailable")
                    self._json(result, 200 if ok else 422)
                elif action == "initial-password":
                    if bool(payload.get("finish", False)):
                        from .onboarding import require_validated_integrations
                        require_validated_integrations()
                    password = str(payload.get("new_password", ""))
                    confirmation = str(payload.get("confirm_password", ""))
                    if not APP.set_initial_admin_password(password, confirmation):
                        self._json({"error": "Initial Linux account password could not be established."}, 422)
                    else:
                        if bool(payload.get("finish", False)):
                            finish_onboarding()
                        self._json({"configured": True,
                                    "account": __import__("lulu.managed_account", fromlist=["MANAGED_ADMIN_ACCOUNT"]).MANAGED_ADMIN_ACCOUNT,
                                    "completed": bool(payload.get("finish", False))})
                elif action == "admin-password":
                    if (onboarding_state().get("status") != "completed"
                            or not APP.password_configured()):
                        self._json({"error": "Normal password changes are available after setup is complete."}, 409)
                        return
                    if bool(payload.get("finish", False)):
                        from .onboarding import require_validated_integrations
                        require_validated_integrations()
                    current = str(payload.get("current_password", ""))
                    password = str(payload.get("new_password", ""))
                    if password != str(payload.get("confirm_password", "")):
                        self._json({"error": "The new passwords do not match."}, 400)
                    elif not APP.change_admin_password(current, password):
                        self._json({"error": "The current account password was not accepted."}, 422)
                    else:
                        if bool(payload.get("finish", False)):
                            finish_onboarding()
                        self._json({"configured": True,
                                    "account": __import__("lulu.managed_account", fromlist=["MANAGED_ADMIN_ACCOUNT"]).MANAGED_ADMIN_ACCOUNT,
                                    "completed": bool(payload.get("finish", False))})
                elif action == "finish":
                    if not APP.password_configured():
                        self._json({"error": "Set the managed Mudos account password before finishing setup."}, 409)
                        return
                    self._json({"state": finish_onboarding()})
                elif action == "dismiss":
                    self._json({"state": dismiss_onboarding()})
                else:
                    self._json({"error": "Unknown setup operation"}, 404)
            except (ValueError, TypeError, KeyError, json.JSONDecodeError) as error:
                self._json({"error": str(error)}, 400)
            except Exception as error:
                LOGGER.exception("setup operation failed action=%s", path.rsplit("/", 1)[-1])
                self._json({"error": "Setup could not complete this operation"}, 500)
            return
        if path == "/api/setup/install":
            try:
                payload = request_payload if request_payload is not None else self._json_body()
                self._json(APP.start_provider_install(str(payload.get("provider", ""))))
            except ValueError as error:
                self._json({"error": str(error)}, 400)
            except (OSError, subprocess.SubprocessError):
                self._json({"error": "The provider installer is unavailable"}, 503)
            return
        if path in {"/api/recovery/retry", "/api/recovery/setup",
                    "/api/recovery/reboot", "/api/recovery/shutdown"}:
            try:
                if not APP.password_configured():
                    self._json({"error": "Set the Admin password before requesting recovery mutations."}, 403)
                    return
                csrf = self._require()
                if csrf is None:
                    return
                token = self._token()
                expected = APP.session(token)
                supplied = self.headers.get("X-CSRF-Token", "")
                if not expected or not hmac.compare_digest(supplied, expected):
                    self._json({"error": "Request rejected."}, 403)
                    return
                payload = self._json_body()
                if path.endswith("setup"):
                    from .onboarding import reopen_onboarding
                    reopen_onboarding()
                action_id = ("restart_mudos" if path.endswith(("retry", "setup")) else
                             "reboot" if path.endswith("reboot") else "shutdown")
                request = urllib.request.Request(
                    "http://127.0.0.1:38124/v1/action",
                    data=json.dumps({"action_id": action_id,
                                     "confirmed": payload.get("confirmed") is True}).encode(),
                    headers={"Content-Type": "application/json",
                             "Authorization": "Bearer " + os.environ.get("LULU_RECOVERY_TOKEN", "")},
                    method="POST")
                with urllib.request.urlopen(request, timeout=5) as response:
                    self._json(json.loads(response.read(65536)), response.status)
            except ValueError as error:
                self._json({"error": str(error)}, 409)
            except (OSError, urllib.error.URLError, subprocess.SubprocessError,
                    TimeoutError, json.JSONDecodeError):
                self._json({"error": "The independent Recovery control plane is unavailable."}, 503)
            return
        token = self._token(); csrf = APP.session(token)
        if csrf is None: self._redirect("/login"); return
        form = self._form()
        if not hmac.compare_digest(form.get("csrf", [""])[0], csrf):
            self._send(_page("Request rejected", "<p class=error>Invalid CSRF token.</p>"), 403); return
        if self.path == "/logout": APP.logout(token); self._redirect("/login", "mudos_session=; Max-Age=0; HttpOnly; SameSite=Lax"); return
        if self.path.startswith("/auth/"):
            self._auth_post(self.path, form); return
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

    def _setup_page(self, local: bool) -> None:
        local_return = '<a class="button secondary" href="mudos://return">Return to Mudos</a>' if local else ""
        csrf = APP.session(self._token()) or ""
        from .managed_account import MANAGED_ADMIN_ACCOUNT
        managed_account = html.escape(MANAGED_ADMIN_ACCOUNT, quote=True)
        body = f'''<main class="setup-wrap"><header><p class="eyebrow">MUDOS SETUP</p><h1>Welcome to Mudos</h1>
<p>Choose the Mudos providers and plugins you want. You can configure connections next and return to setup later.</p></header>
        <nav class="steps"><span>1 · Install providers</span><span>2 · Store accounts</span><span>3 · Integrations and system files</span><span>4 · Review</span></nav>
<section id="content" aria-live="polite"><p>Loading your available Mudos components…</p></section>
<p id="busy" role="status" aria-live="polite" hidden><span class="spinner" aria-hidden="true"></span><span>Working…</span></p><p id="notice" role="status" aria-live="polite"></p>{local_return}</main>
<script>
const localSetup={str(local).lower()},setupCsrf={json.dumps(csrf)},managedAccount={json.dumps(managed_account)};let data=null,step=0,providerChoices=[],integrationChoices=[],credentialIndex=0,validationResults={{}},failedCredentialIds=new Set(),skippedCredentialIds=new Set(),testingCredentialIds=new Set(),providerInstallProgress=null,steamAuthBusy=false,steamSignin=false,steamAuthTimer=null,steamOobeLaunchToken=readSteamLaunchToken(),accountStep=false,accountIds=[],accountIndex=0,providerSignin='',providerTransaction=null,setupBusy=0,lastRenderContext='';
function readSteamLaunchToken(){{try{{return sessionStorage.getItem('mudos-setup-steam-launch')||''}}catch(e){{return ''}}}}
function rememberSteamLaunchToken(token){{try{{if(token)sessionStorage.setItem('mudos-setup-steam-launch',token);else sessionStorage.removeItem('mudos-setup-steam-launch')}}catch(e){{}}}}
const statusNames={{not_selected:'Not selected',selected:'Selected',installing:'Installing',install_failed:'Installation failed',installed:'Installed',configured:'Configured',connected:'Connected',configuration_required:'Configuration required',authentication_required:'Authentication required',authenticating:'Authenticating',authorization_pending:'Waiting for Steam approval',auth_failed:'Authentication failed',authenticated:'Authenticated',reconciling:'Reconciling library',validating:'Validating',syncing:'Syncing catalogue',sync_failed:'Catalogue sync failed',ready:'Ready',running:'Running — configuration required',degraded:'Degraded',catalogue_ready_acquisition_required:'Catalogue ready — acquisition not configured',not_configured:'Not configured'}};
function stateName(value){{return statusNames[value]||String(value||'Unknown').replaceAll('_',' ')}}
function esc(v){{return String(v||"").replace(/[&<>\"']/g,c=>({{'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;',"'":'&#39;'}}[c]))}}
function setBusy(delta){{let wasBusy=setupBusy>0;setupBusy=Math.max(0,setupBusy+delta);let isBusy=setupBusy>0;let busy=document.querySelector('#busy');if(busy)busy.hidden=!isBusy;if(!wasBusy&&isBusy)document.querySelectorAll('#content button,#content input').forEach(e=>{{e.dataset.setupWasDisabled=e.disabled?'1':'0';e.disabled=true}});else if(wasBusy&&!isBusy)document.querySelectorAll('#content button,#content input').forEach(e=>{{e.disabled=e.dataset.setupWasDisabled==='1';delete e.dataset.setupWasDisabled}})}}
async function api(path,body){{setBusy(1);try{{let payload=body?{{...body,csrf:setupCsrf}}:undefined;let r=await fetch(path,{{method:body?'POST':'GET',headers:body?{{'Content-Type':'application/json'}}:{{}},body:body?JSON.stringify(payload):undefined}});let type=r.headers.get('content-type')||'';if(!type.includes('application/json')){{if(r.redirected||r.status===401)throw Error('Your admin session expired. Sign in again, then continue setup.');throw Error('Setup returned an unexpected response. Reload the page and try again.')}}let v=await r.json();if(!r.ok)throw Error(v.error||v.message||'Request failed');return v}}finally{{setBusy(-1)}}}}
function notice(text){{document.querySelector('#notice').textContent=text}}
function stopSteamAuthPolling(){{if(steamAuthTimer){{clearInterval(steamAuthTimer);steamAuthTimer=null}}}}
 function renderSteamSignin(){{stopSteamAuthPolling();let provider=data.providers.find(p=>p.id==='steam');let auth=provider?.authentication||{{}};let identity=auth.persona||auth.account||'';let ready=!!auth.authenticated;let root=document.querySelector('#content');root.innerHTML='<section class="card"><p class="eyebrow">STEAM ACCOUNT</p><h2>Sign in to Steam</h2><p>Steam is installed. Select Open Steam sign-in to show Steam on your Mudos screen, then sign in there. Afterward, setup verifies SteamCMD separately: enter your Steam password in the secure setup field, then approve the login on your Steam Guard device or choose Enter Code on the Mudos screen.</p><p id="steam-auth-state" role="status">'+(ready?'✓ Signed in as '+esc(identity||'Steam account'):'Waiting for Steam sign-in…')+'</p><div class="actions"><button id="steam-open" '+(ready?'hidden':'')+' onclick="beginSteamAuth()">Open Steam sign-in</button><button id="steam-continue" '+(ready?'':'disabled')+' onclick="continueSteamSignin()">Continue</button><button class="secondary" onclick="steamSignin=false;step=0;render()">Back</button></div></section>';setTimeout(()=>document.querySelector(ready?'#steam-continue':'#steam-open')?.focus(),0);if(!ready)steamAuthTimer=setInterval(()=>void checkSteamAuth(),3000)}}
function render(){{let context=[step,steamSignin,providerSignin,accountStep?accountIds[accountIndex]:'',integrationChoices[credentialIndex]||'',providerInstallProgress?'installing':''].join('|');if(context!==lastRenderContext){{notice('');lastRenderContext=context}}if(providerInstallProgress){{renderInstallProgress();return}}if(steamSignin){{renderSteamSignin();return}}if(providerSignin){{renderProviderSignin();return}}if(accountStep){{renderAccountStep();return}}stopSteamAuthPolling();renderSetupPage()}}
function startAccountStep(){{accountIds=data.providers.filter(p=>providerChoices.includes(p.id)&&['epic','gog'].includes(p.id)&&p.installed).map(p=>p.id);accountIndex=0;accountStep=accountIds.length>0;step=1;render()}}
function renderAccountStep(){{let id=accountIds[accountIndex],provider=data.providers.find(p=>p.id===id),ready=!!provider?.authentication?.authenticated;let root=document.querySelector('#content');root.innerHTML='<section class="card"><p class="eyebrow">STORE ACCOUNTS · '+(accountIndex+1)+' OF '+accountIds.length+'</p><h2>'+esc(provider?.name||id)+' sign-in</h2><p>Sign in to this store to make your owned games available. This is separate from optional API keys and system files on the next screen.</p><p role="status">'+(ready?'✓ Account signed in. Catalogue reconciliation can continue in the background.':esc(provider?.status_message||'Sign-in is required to load this store’s library.'))+'</p><div class="actions"><button onclick="beginProviderSignin(&quot;'+esc(id)+'&quot;)">'+(ready?'Reconnect':'Sign in')+'</button><button class="secondary" onclick="advanceAccountStep()">'+(ready?(accountIndex<accountIds.length-1?'Next store':'Continue to integrations'):'Skip for now')+'</button><button class="secondary" onclick="accountStep=false;step=0;render()">Back to providers</button></div></section>'}}
function advanceAccountStep(){{accountIndex++;if(accountIndex>=accountIds.length){{accountStep=false;step=1}}render()}}
function backToAccountStep(){{accountIndex=accountIds.length-1;accountStep=true;render()}}
function renderInstallProgress(){{let items=providerInstallProgress||[];let completed=items.filter(item=>!['Pending','Installing'].includes(item.status)).length;let active=items.find(item=>item.status==='Installing');let root=document.querySelector('#content');root.innerHTML='<h2>Installing providers and plugins</h2><p role="status">'+(active?'Installing '+esc(active.name)+'…':completed===items.length?'Installation complete':'Preparing installation…')+'</p><p>'+completed+' of '+items.length+' completed</p><progress value="'+completed+'" max="'+Math.max(1,items.length)+'"></progress><ul>'+items.map(item=>`<li><strong>${{esc(item.name)}} — ${{esc(item.status)}}</strong>${{item.message?`<br><small>${{esc(item.message)}}</small>`:''}}</li>`).join('')+'</ul>'}}
async function checkSteamAuth(){{if(!steamSignin)return false;try{{let state=await api('/api/setup/steam/auth-status');let auth=state.authentication||{{}};let ready=!!auth.authenticated;let label=document.querySelector('#steam-auth-state');let next=document.querySelector('#steam-continue');if(label)label.textContent=ready?'✓ Signed in as '+(auth.persona||auth.account||'Steam account'):state.status==='authorization_pending'?'Waiting for Steam sign-in…':'Steam sign-in is incomplete. Open Steam to retry.';if(next)next.disabled=!ready;let provider=data.providers.find(p=>p.id==='steam');if(provider){{provider.status=ready?'authenticated':state.status;provider.authentication=auth}}return ready}}catch(e){{let label=document.querySelector('#steam-auth-state');if(label)label.textContent='Steam sign-in status is temporarily unavailable. Retry shortly.';return false}}}}
async function beginSteamAuth(){{if(steamAuthBusy)return;steamAuthBusy=true;let button=document.querySelector('#steam-open');if(button)button.disabled=true;let label=document.querySelector('#steam-auth-state');if(label)label.textContent='Opening Steam sign-in…';try{{let result=await api('/api/setup/steam/authenticate',{{}});if(result.launch){{steamOobeLaunchToken=result.launch;rememberSteamLaunchToken(steamOobeLaunchToken)}}notice(result.message||'Steam was opened. Complete sign-in in Steam.');await checkSteamAuth()}}catch(e){{notice(e.message);if(label)label.textContent='Steam could not be opened. You can retry.'}}finally{{steamAuthBusy=false;if(button)button.disabled=false}}}}
async function continueSteamSignin(){{if(!await checkSteamAuth()){{notice('Steam sign-in is not verified yet. Complete sign-in on Mudos, wait for your account name to appear here, then select Continue.');return}}stopSteamAuthPolling();integrationChoices=[...new Set([...integrationChoices,'providers.steam'])];await api('/api/setup/progress',{{providers:providerChoices,integrations:integrationChoices}});let launch=steamOobeLaunchToken;if(launch){{try{{await api('/api/setup/steam/dismiss',{{launch}});steamOobeLaunchToken='';rememberSteamLaunchToken('')}}catch(e){{notice('Steam sign-in succeeded, but the sign-in window could not be dismissed: '+e.message)}}}}steamSignin=false;startAccountStep()}}
function renderProviderSignin(){{let provider=data.providers.find(p=>p.id===providerSignin);let root=document.querySelector('#content');let transaction=providerTransaction;root.innerHTML=`<section class="card"><p class="eyebrow">ACCOUNT SIGN-IN</p><h2>Sign in to ${{esc(provider?.name||providerSignin)}}</h2><p>Open the provider sign-in page, complete sign-in, then paste its one-time authorization code here. Mudos does not store the code or your provider password.</p>${{transaction?.verification_url?`<p><a class="button" href="${{esc(transaction.verification_url)}}" target="_blank" rel="noopener noreferrer">Open ${{esc(provider?.name||providerSignin)}} sign-in</a></p>`:''}}<label>One-time authorization code<input id="provider-auth-code" type="text" autocomplete="one-time-code" value="" required></label><div class="actions"><button onclick="${{transaction?'completeProviderSignin()':'beginProviderSignin(providerSignin)'}}" ${{transaction?'':'disabled'}}>Complete sign-in</button>${{transaction?'':'<button onclick="beginProviderSignin(providerSignin)">Retry sign-in</button>'}}<button class="secondary" onclick="providerSignin='';providerTransaction=null;step=1;render()">Back to setup</button></div></section>`}}
async function beginProviderSignin(id){{providerSignin=id;providerTransaction=null;render();try{{providerTransaction=await api('/api/setup/provider-authenticate',{{provider:id}});render()}}catch(e){{notice(e.message);providerTransaction=null;render()}}}}
async function completeProviderSignin(){{let code=document.querySelector('#provider-auth-code')?.value||'';if(!code.trim()){{notice('Enter the one-time authorization code from the provider page.');return}}try{{await api('/api/setup/provider-auth-complete',{{provider:providerSignin,transaction_id:providerTransaction?.transaction_id,code}});data=await api('/api/setup/state');providerSignin='';providerTransaction=null;step=1;render();notice('Provider sign-in completed. Catalogue reconciliation will continue in the background.')}}catch(e){{notice(e.message)}}}}
async function nextProviders(){{if(!await nextProvidersOriginal())return;if(providerChoices.includes('steam')){{let steam=data.providers.find(p=>p.id==='steam');if(!steam?.installed){{step=0;render();notice('Steam installation must succeed before sign-in. Review the installation status and retry.');return}}integrationChoices=[...new Set([...integrationChoices,'providers.steam'])];await api('/api/setup/progress',{{providers:providerChoices,integrations:integrationChoices}});steamSignin=true;render();await checkSteamAuth()}}else startAccountStep()}}
function renderSetupPage(){{let root=document.querySelector('#content');if(!data)return;if(step===3)setTimeout(()=>{{let initial=!data.onboarding.admin_password_configured&&data.onboarding.status!=='completed';let current=document.querySelector('#admin-current');if(current)current.closest('label').hidden=initial;let intro=root.querySelector('p');if(intro)intro.textContent=initial?'Choose an initial password for the managed Mudos Linux account ('+managedAccount+'). You do not need its existing password. After setup, password changes require the current account password.':'Admin authentication uses the same password as the managed Mudos Linux account ('+managedAccount+'). Enter its current password and choose a replacement password of at least 8 characters.'}},0);
 if(step===0){{let cards=data.providers.map(p=>`<label class="card"><input type="checkbox" data-provider="${{esc(p.id)}}" ${{providerChoices.includes(p.id)?'checked':''}}><strong>${{esc(p.name)}}</strong><span>${{esc(p.summary)}}</span><small>Status: ${{esc(stateName(p.status))}}</small>${{p.status==='install_failed'&&p.status_message?`<small role="alert">${{esc(p.status_message)}}</small>`:''}}${{p.dependencies.length||p.dependencies_any.length?`<small>Dependencies: ${{esc([...p.dependencies,...p.dependencies_any.flat()].join(', '))}}</small>`:''}}</label>`).join('');root.innerHTML='<h2>Providers and Plugins</h2><div class="cards">'+cards+'</div><div class="actions"><button onclick="nextProviders()">Install selected and continue</button><button class="secondary" onclick="skipSetup()">Continue to Home</button></div>'}}
 else if(step===1){{root.innerHTML='<h2>Integrations and system files</h2><p>Choose optional connections and upload required system files. Store account sign-in is handled separately.</p><div class="cards">'+data.integrations.map(i=>`<label class="card"><input type="checkbox" data-integration="${{esc(i.id)}}" ${{integrationChoices.includes(i.id)?'checked':''}}><strong>${{esc(i.name)}}</strong><span>${{esc(i.description||'Optional connection used by Mudos.')}}</span><small>${{i.configured?'Configured':'Optional'}}</small></label>`).join('')+'</div><div id="setup-files-section">'+setupFilesMarkup()+'</div><div class="actions"><button onclick="nextCredentials()">Continue</button><button class="secondary" onclick="'+(accountIds.length?'backToAccountStep()':'step=0;render()')+'">Back</button></div>'}}
  else if(step===2){{credentialIndex=Math.min(credentialIndex,integrationChoices.length);let id=integrationChoices[credentialIndex];let failed=id&&failedCredentialIds.has(id);let ready=id&&validationResults[id]?.ok;root.innerHTML='<h2>Connection details</h2>'+(id?'<p>Integration '+(credentialIndex+1)+' of '+integrationChoices.length+'</p>'+credentialForm(id):'<p>'+(integrationChoices.length?'All selected connections are complete.':'No integrations selected. You can add them later.')+'</p>')+(failed?'':'<div class="actions">'+(ready&&credentialIndex<integrationChoices.length-1?'<button onclick="nextCredential()">Next integration</button>':ready||!id?'<button onclick="reviewSetup()">Review Setup</button>':'')+'<button class="secondary" onclick="step=1;render()">Back</button></div>')}}
else {{root.innerHTML='<h2>Setup review</h2><p>Review every available item below. Scroll to see all providers, integrations, and their current status.</p><h3>Providers and Plugins</h3><ul>'+ (data.providers.map(p=>`<li><strong>${{esc(p.name)}} — ${{p.installed?'Installed':'Not installed'}} · ${{esc(stateName(p.status))}}</strong>${{p.status_message?`<br><small>${{esc(p.status_message)}}</small>`:''}}</li>`).join('')||'<li>No providers available</li>')+'</ul><h3>Integrations</h3><ul>'+ (data.integrations.map(i=>{{let skipped=skippedCredentialIds.has(i.id);let result=skipped?null:validationResults[i.id]||data.onboarding.validation?.[i.id];let status=skipped?'Skipped':result?(result.ok?(i.id==='providers.romm'?'Ready':'Connected'):'Validation failed'):i.readiness?stateName(i.readiness.status):i.configured?'Configured; not validated':'Configuration required';let message=skipped?'':result?.message||i.readiness?.message||'';return `<li><strong>${{esc(i.name)}} — ${{i.configured?'Configured':'Not configured'}} · ${{esc(status)}}</strong>${{message?`<br><small>${{esc(message)}}</small>`:''}}</li>`}}).join('')||'<li>No integrations available</li>')+'</ul><p>Admin authentication uses the same password as the managed Mudos Linux account ('+esc(managedAccount)+'). Enter its current password and choose a new password of at least 8 characters. This change is explicit and will also change Linux account authentication.</p><label>Current Mudos account password<input id="admin-current" type="password" autocomplete="current-password"></label><label>New Mudos admin password<input id="admin-new" type="password" autocomplete="new-password" minlength="8"></label><label>Confirm new password<input id="admin-confirm" type="password" autocomplete="new-password" minlength="8"></label><p>After setup, open <a href="http://mudos.local/">mudos.local</a> for Mudos administration. Return to <a href="http://mudos.local/setup">mudos.local/setup</a> to change selections.</p><div class="actions"><button onclick="finishSetup()">Set Password &amp; Finish Setup</button>'+(localSetup?'<a class="button secondary" href="mudos://return">Return to Mudos</a>':'')+'<button class="secondary" onclick="step=2;render()">Back</button></div>'}}}}
function fieldDefault(id,f){{if(id==='providers.steam'&&f.name==='steam_username'){{let auth=data.providers.find(p=>p.id==='steam')?.authentication||{{}};return auth.account||auth.persona||''}}return f.default??''}}
  function credentialForm(id){{let i=data.integrations.find(x=>x.id===id);if(!i)return '';let failed=failedCredentialIds.has(id);if(validationResults[id]?.ok&&!failed)return `<article class="card credential"><h3>${{esc(i.name)}}</h3><p role="status">✓ Setup completed successfully. You can continue to the next integration or review setup.</p><div class="actions"><button class="secondary" onclick="delete validationResults['${{esc(id)}}'];render()">Amend details</button></div></article>`;return `<article class="card credential"><h3>${{esc(i.name)}}</h3><p><a href="${{esc(i.help)}}" target="_blank" rel="noreferrer">Where do I get this?</a></p>${{i.fields.map(f=>`<label>${{esc(f.label)}}<input autocomplete="off" type="${{id==='providers.steam'&&f.name==='steam_username'?'text':f.type==='secret'?'password':f.type==='url'?'url':f.type==='checkbox'?'checkbox':f.type==='number'?'number':'text'}}" data-integration="${{esc(id)}}" data-field="${{esc(f.name)}}" ${{f.type==='checkbox'&&f.default?'checked':''}} ${{f.required?'required':''}} value="${{f.type==='checkbox'?'on':esc(fieldDefault(id,f))}}" placeholder="${{f.type==='secret'?'Leave blank to keep saved value':''}}">${{id==='providers.romm'&&f.name==='url'?'<small class="field-error" role="alert"></small>':''}}</label>`).join('')}}${{failed?`<p role="alert">${{esc(validationResults[id]?.message||'Connection test failed.')}}</p>`:''}}<div class="actions"><button onclick="testAndSave('${{esc(id)}}')">${{failed?'Retry':'Test and Save'}}</button>${{failed?`<button class="secondary" onclick="skipIntegration('${{esc(id)}}')">Skip</button>`:''}}<small>${{i.configured?'Configured; secret values remain private':''}}</small></div></article>`}}
function setupFilesMarkup(){{let rows=data.setup_files||[];if(!rows.length)return '';return '<h2>BIOS, keys and firmware</h2><p>Provide any required BIOS, keys, or firmware for selected systems now or later. Files are stored in the matching Mudos BIOS folder.</p>'+rows.map(function(system){{let requirements=system.requirements.map(function(req){{let status=req.ready?'Added':(req.required?'Required':'Optional');let present=req.present.length?'Current files: '+esc(req.present.join(', ')):'No files uploaded';return '<label><strong>'+esc(req.label)+' — '+status+'</strong><span>'+esc(req.description)+'</span><small>'+present+'</small><input type="file" data-platform="'+esc(system.platform)+'" data-requirement="'+esc(req.id)+'" accept="'+req.extensions.join(',')+'" '+(req.multiple?'multiple':'')+' onchange="uploadSetupFiles(this)"></label>'}}).join('');return '<article class="card credential"><h3>'+esc(system.platform_label)+'</h3>'+requirements+'</article>'}}).join('')}}
async function uploadSetupFiles(input){{if(!input.files||!input.files.length)return;let body=new FormData();body.append('csrf',setupCsrf);body.append('platform',input.dataset.platform);body.append('requirement',input.dataset.requirement);for(let file of input.files)body.append('file',file,file.name);input.disabled=true;notice('Uploading system files…');setBusy(1);try{{let response=await fetch('/api/setup/files',{{method:'POST',body:body}});let result=await response.json();if(!response.ok)throw Error(result.error||'Upload failed');data.setup_files=result.setup_files||[];document.querySelector('#setup-files-section').innerHTML=setupFilesMarkup();notice('System files uploaded.')}}catch(error){{notice(error.message);input.disabled=false}}finally{{setBusy(-1)}}}}
async function nextProvidersOriginal(){{providerChoices=[...document.querySelectorAll('[data-provider]:checked')].map(e=>e.dataset.provider);try{{let saved=await api('/api/setup/progress',{{providers:providerChoices}});providerChoices=saved.state.selected_providers||providerChoices;providerInstallProgress=providerChoices.map(id=>{{let p=data.providers.find(x=>x.id===id);return {{id,name:p?.name||id,status:p?.installed?'Installed':p?.installable?'Pending':'Unavailable',message:''}}}});if(providerInstallProgress.length)render();for(const item of providerInstallProgress){{if(item.status!=='Pending')continue;item.status='Installing';render();notice(`Installing ${{item.name}}…`);try{{await api('/api/setup/install',{{provider:item.id}});let result={{status:'installing',message:''}},notStartedPolls=0;while(['installing','selected'].includes(result.status)){{await new Promise(r=>setTimeout(r,1600));result=await api('/api/setup/install/'+encodeURIComponent(item.id));if(result.status==='selected'){{if(++notStartedPolls>=10){{result=await api('/api/setup/install-timeout',{{provider:item.id}});if(result.status==='installing')notStartedPolls=0;else break}}notice(`Waiting for ${{item.name}} installer to start…`)}}else if(result.status==='installing'){{notStartedPolls=0;notice(item.id==='retroarch'?'Installing official RetroArch cores…':`Installing ${{item.name}}…`)}}}}item.status=result.status==='installed'?'Installed':'Failed';item.message=result.status==='installed'?'':result.message||'Installer did not verify the installed provider.';notice(result.status==='installed'?`${{item.name}} installed; checking readiness…`:`${{item.name}} installation failed: ${{item.message}}`)}}catch(e){{item.status='Failed';item.message=e.message;notice(`${{item.name}} installation failed: ${{e.message}}`)}}render()}}await api('/api/setup/progress',{{integrations:integrationChoices}});data=await api('/api/setup/state');providerInstallProgress=null;step=1;render();return true}}catch(e){{providerInstallProgress=null;step=0;render();notice(e.message);return false}}}}
async function nextCredentials(){{integrationChoices=[...document.querySelectorAll('[data-integration]:checked')].map(e=>e.dataset.integration);await api('/api/setup/progress',{{providers:providerChoices,integrations:integrationChoices}});credentialIndex=0;step=2;render()}}
function nextCredential(){{let id=integrationChoices[credentialIndex];if(!id||!validationResults[id]?.ok||failedCredentialIds.has(id)){{notice('Test and Save or Skip this integration before continuing.');return}}credentialIndex++;render()}}
async function reviewSetup(){{try{{data=await api('/api/setup/state');validationResults=data.onboarding.validation||{{}};failedCredentialIds=new Set(integrationChoices.filter(id=>validationResults[id]&&validationResults[id].ok===false));let pending=integrationChoices.filter(id=>testingCredentialIds.has(id)||!validationResults[id]?.ok);if(pending.length){{render();notice('Test and Save each selected integration, or Skip it before continuing.');return}}await api('/api/setup/progress',{{providers:providerChoices,integrations:integrationChoices}});data=await api('/api/setup/state');step=3;render()}}catch(e){{notice(e.message)}}}}
function integrationPayload(id){{let payload={{integration:id}};document.querySelectorAll(`[data-integration="${{CSS.escape(id)}}"][data-field]`).forEach(e=>payload[e.dataset.field]=e.type==='checkbox'?e.checked:e.value);return payload}}
function restoreIntegrationDraft(id,draft){{document.querySelectorAll(`[data-integration="${{CSS.escape(id)}}"][data-field]`).forEach(e=>{{if(Object.hasOwn(draft,e.dataset.field)){{if(e.type==='checkbox')e.checked=!!draft[e.dataset.field];else e.value=draft[e.dataset.field]}}}})}}
function rommUrlCheck(id){{if(id!=='providers.romm')return true;let input=document.querySelector('[data-integration="providers.romm"][data-field="url"]');let error=input?.closest('label')?.querySelector('.field-error');if(!input||!input.value.trim())return true;let valid=/^https?:[/][/]/i.test(input.value.trim());if(error)error.textContent=valid?'':'Enter a RomM URL beginning with http:// or https://';input.setAttribute('aria-invalid',valid?'false':'true');return valid}}
async function testAndSave(id){{if(testingCredentialIds.has(id))return;let draft=integrationPayload(id);if(!rommUrlCheck(id)){{validationResults[id]={{ok:false,message:'Enter a valid connection URL, then Retry or Skip.'}};failedCredentialIds.add(id);render();restoreIntegrationDraft(id,draft);rommUrlCheck(id);notice(validationResults[id].message);return}}testingCredentialIds.add(id);try{{await api('/api/setup/credentials',draft);if(id==='providers.steam')notice('Verifying SteamCMD. Approve the login on your Steam Guard device or choose Enter Code on the Mudos screen.');let result=await api('/api/setup/test',{{integration:id}});validationResults[id]=result;if(result.ok)failedCredentialIds.delete(id);else failedCredentialIds.add(id);data=await api('/api/setup/state');render();notice(result.message|| (result.ok?'Connection verified and saved.':'Connection test failed. Retry or Skip.'))}}catch(e){{validationResults[id]={{ok:false,message:e.message}};failedCredentialIds.add(id);render();restoreIntegrationDraft(id,draft);if(id==='providers.romm')rommUrlCheck(id);notice(e.message)}}finally{{testingCredentialIds.delete(id)}}}}
async function skipIntegration(id){{try{{let next=integrationChoices.filter(value=>value!==id);let saved=await api('/api/setup/progress',{{providers:providerChoices,integrations:next}});integrationChoices=saved.state.selected_integrations||next;let skipped=await api('/api/setup/skip-integration',{{integration:id}});failedCredentialIds.delete(id);skippedCredentialIds=new Set(skipped.state.skipped_integrations||[]);delete validationResults[id];data=await api('/api/setup/state');render();notice('Integration skipped. You can configure it later.')}}catch(e){{notice(e.message)}}}}
async function finishSetup(){{try{{let current=document.querySelector('#admin-current')?.value||'',newPassword=document.querySelector('#admin-new').value,confirmation=document.querySelector('#admin-confirm').value;if(newPassword!==confirmation)throw Error('The new passwords do not match.');if(newPassword.length<8)throw Error('Use a new password of at least 8 characters.');let initial=!data.onboarding.admin_password_configured&&data.onboarding.status!=='completed';await api(initial?'/api/setup/initial-password':'/api/setup/admin-password',{{current_password:current,new_password:newPassword,confirm_password:confirmation,finish:true}});window.location.assign('/')}}catch(e){{notice(e.message)}}}}
async function skipSetup(){{try{{await api('/api/setup/dismiss',{{}});notice('Setup skipped. You can return any time at mudos.local/setup.')}}catch(e){{notice(e.message)}}}}
api('/api/setup/state').then(v=>{{data=v;providerChoices=v.onboarding.selected_providers||[];integrationChoices=v.onboarding.selected_integrations||[];validationResults=v.onboarding.validation||{{}};skippedCredentialIds=new Set(v.onboarding.skipped_integrations||[]);failedCredentialIds=new Set(integrationChoices.filter(id=>validationResults[id]&&validationResults[id].ok===false));steamSignin=providerChoices.includes('steam')&&!!data.providers.find(p=>p.id==='steam')?.installed;render();if(steamSignin)void checkSteamAuth()}}).catch(e=>notice(e.message));
</script>'''
        self._send(_setup_page_document(body))

    def _recovery_page(self) -> None:
        csrf = APP.session(self._token()) or ""
        body = f'''<main class="setup-wrap"><p class="eyebrow">MUDOS RECOVERY</p><h1>What needs attention?</h1>
<p>The Recovery control plane runs separately from the Mudos graphical session. Actions are sent only to its fixed, allowlisted API.</p>
<section class="card"><h2 id="overall">Loading system health…</h2><div id="state">Checking component evidence…</div></section>
<section class="card"><h2>Safe actions</h2><div id="actions" class="actions"></div><p id="notice" role="status"></p></section>
<p><a href="/setup">Open Setup / Reconfigure</a></p></main>
<script>
const csrf={json.dumps(csrf)};
const esc=value=>String(value??'').replace(/[&<>"']/g,c=>({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[c]));
async function confirmAction(action){{
 if(!confirm(`${{action.label}}?\\n\\n${{(action.impact||[]).join('\\n')}}`))return;
 const notice=document.querySelector('#notice');notice.textContent='Sending request…';
 try{{const response=await fetch('/api/recovery/'+({{restart_mudos:'retry',reboot:'reboot',shutdown:'shutdown'}}[action.action_id]||'retry'),{{method:'POST',headers:{{'Content-Type':'application/json','X-CSRF-Token':csrf}},body:JSON.stringify({{confirmed:true}})}});const value=await response.json();notice.textContent=response.ok?'Request accepted.':(value.error||'Request rejected.');setTimeout(load,1200)}}catch(error){{notice.textContent='The independent Recovery control plane is unavailable.'}}
}}
async function load(){{
 try{{const response=await fetch('/api/recovery/status',{{cache:'no-store'}});const s=await response.json();
 document.querySelector('#overall').textContent='Overall state: '+(s.overall_state||'unknown').replaceAll('_',' ');
 const components=s.components||{{}};document.querySelector('#state').innerHTML=Object.entries(components).map(([id,c])=>`<article class="card"><strong>${{esc(id.replaceAll('_',' '))}} · ${{esc(c.state||'unknown')}}</strong><p>${{esc(c.summary||'Evidence unavailable')}}</p><small>Checked: ${{esc(c.checked_at||'unknown')}} · evidence: ${{esc(c.freshness||'unknown')}}</small>${{c.last_error?`<p>${{esc(c.last_error)}}</p>`:''}}</article>`).join('')||'<p>Component evidence is unavailable.</p>';
 const actions=document.querySelector('#actions');actions.replaceChildren();
 for(const action of (s.actions||[])){{if(action.action_id==='restart_consoled'||action.action_id==='restart_acquisitiond'||action.action_id==='restart_admin')continue;const button=document.createElement('button');button.textContent=action.label;button.onclick=()=>confirmAction(action);actions.append(button)}}
 if(!csrf){{actions.innerHTML='<p>Sign in to Mudos Admin to authorize recovery actions.</p>'}}
 }}catch(error){{document.querySelector('#overall').textContent='Recovery status unavailable';document.querySelector('#state').textContent='The independent recovery service is not responding.'}}
}}
load();setInterval(load,10000);
</script>'''
        self._send(_setup_page_document(body))

    def authenticate_form(self) -> bool:
        form = self._form(); password = form.get("password", [""])[0]
        if not APP.authenticate(password): return False
        token, csrf = APP.login()
        self._redirect("/", f"mudos_session={token}; Max-Age={SESSION_SECONDS}; HttpOnly; SameSite=Lax")
        return True

    def _dashboard(self) -> None:
        host = _host(self)
        configured = sum(1 for provider_id, _ in PROVIDERS if APP.config.provider(provider_id).configured)
        cards = "".join(f'<a class="card-link card" href="/integrations#services"><div class="card-head"><h3>{html.escape(name)}</h3>{_badge(APP.service_state(unit))}</div><p>{html.escape(_service_description(key))}</p></a>' for key,name,unit,*_ in SERVICES[:3])
        body = (f'<div class="card"><div class="card-head"><div><h2>Appliance at {html.escape(host)}</h2><p>Ready for local administration.</p></div>{_badge("active")}</div>'
                f'<p class="meta">Deployment: {html.escape(_deployment())} · {configured} integrations configured</p>'
                f'<div class="actions"><a class="button" href="/integrations">Configure integrations</a><a class="button button-secondary" href="/integrations#services">View all services</a></div></div>'
                '<div class="section-title"><h2>Service snapshot</h2><a href="/integrations#services">See all</a></div>'
                f'<div class="grid">{cards}</div>')
        self._send(_page("Overview", body, subtitle="A clear view of your Mudos appliance.", active="overview"))

    def _providers(self) -> None:
        cards = []
        for provider_id, name in PROVIDERS:
            title, description, _ = PROVIDER_META.get(provider_id, (name, "", ""))
            config = APP.config.provider(provider_id)
            cards.append(f'<a class="card-link card" href="/integration/{urllib.parse.quote(provider_id)}"><div class="card-head"><h2>{html.escape(title)}</h2>{_badge(config.status)}</div><p>{html.escape(description)}</p><span class="meta">Configure connection →</span></a>')
        notice = _notice("Changes saved", "The integration settings were updated.", "success") if urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query).get("updated") else ""
        body = (notice + '<h2>Connections</h2><div class="grid">' + "".join(cards) + '</div>'
                + '<section id="services"><div class="section-title"><h2>Services</h2></div>'
                + '<div class="service-list">' + self._service_rows() + '</div></section>')
        self._send(_page("Integrations and Services", body, subtitle="Configure integrations and check appliance services in one place.", active="integrations"))

    def _provider_form(self, provider_id: str) -> None:
        config = APP.config.provider(provider_id); csrf = APP.session(self._token()) or ""
        title, description, explanation = PROVIDER_META.get(provider_id, (provider_id, "", ""))
        if provider_id in {component.component_id for component in APP.components.all()}:
            component = APP.components.get(provider_id)
            title, description, explanation = component.name, component.description, component.description
        component_ids = {component.component_id for component in APP.components.all()}
        if provider_id not in dict(PROVIDERS) and provider_id not in component_ids:
            self._send(_page("Not found", '<div class="notice error"><strong>Integration not found</strong><p>Choose an integration from the list.</p></div><a class="button" href="/integrations">Back to integrations</a>', active="integrations"), 404); return
        component = next((item for item in APP.components.all() if provider_id in item.provider_ids), None)
        if component and (component.configuration or component.secrets):
            fields = ""
            for item in component.configuration:
                if item.kind == "boolean":
                    fields += _field(item.label, item.key, config.get(item.key, item.default or False), kind="checkbox", help_text=item.description)
                elif not item.secret:
                    fields += _field(item.label, item.key, config.get(item.key, item.default or ""),
                                     kind={"integer": "number", "url": "url"}.get(item.kind, "text"),
                                     help_text=item.description, required=item.required)
            secrets = ""
            for item in component.secrets:
                secrets += _field(item.label, "secret_" + item.slot, "", kind="password",
                                  help_text=item.description + " Leave blank to preserve the existing secret.")
                secrets += f'<p class="meta">{html.escape(item.label)}: {_badge("configured" if config.secret_available(item.slot) else "unconfigured")}</p>'
        elif provider_id == "providers.torrent":
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
        auth = APP.auth_status(provider_id)
        auth_form = ""
        if auth.get("status") != "unavailable":
            auth_state = str(auth.get("status", "authentication_required"))
            account = str(auth.get("account", ""))
            identity = f'<p class="meta">Account: {html.escape(account)}</p>' if account else ""
            auth_action = "/auth/" + urllib.parse.quote(provider_id) + "/start"
            auth_buttons = '<button class="button" type=submit>Sign in</button>'
            if auth_state in {"configured", "authenticated", "connected"}:
                auth_buttons = '<button class="button button-secondary" type=submit>Reauthenticate</button>'
                auth_buttons += ' <button class="button button-quiet" type=submit name=action value=sign_out>Sign out</button>'
            auth_form = (f'<div class="card auth-card"><div class="card-head"><div><h2>Authentication</h2>'
                         f'<p>{html.escape(" · ".join(str(item) for item in auth.get("methods", [])))}</p></div>{_badge(auth_state)}</div>'
                         f'{identity}<p class="meta">Secrets and provider session material are never shown here.</p>'
                         f'<form method=post action="{auth_action}"><input type=hidden name=csrf value="{csrf}">{auth_buttons}</form></div>')
        body = (auth_form + f'<div class="card"><div class="card-head"><div><h2>{html.escape(title)}</h2><p>{html.escape(explanation)}</p></div>{_badge(config.status)}</div>'
                f'<form method=post action="{form_action}"><input type=hidden name=csrf value="{csrf}"><section><div class="section-title"><h2>Connection</h2></div>{fields}{secrets}</section><div class="actions">{actions}</div></form></div>'
                '<details class="technical"><summary>Technical details</summary><p>Integration identifier: ' + html.escape(provider_id) + '</p></details>')
        self._send(_page(title, body, subtitle=description, active="integrations"))

    def _json(self, value: object, status: int = 200) -> None:
        payload = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
        self._send(payload, status, {"Content-Type": "application/json; charset=utf-8",
                                     "Cache-Control": "no-store"})

    def _auth_page(self, provider_id: str, transaction_id: str = "") -> None:
        transaction = APP.auth_transactions.get(transaction_id) if transaction_id else None
        if transaction is None:
            self._send(_page("Authentication", _notice("Authentication unavailable", "This authentication transaction has expired or does not exist.", "error")), 404)
            return
        csrf = APP.session(self._token()) or ""
        url = transaction.verification_url
        link = f'<p><a class="button" href="{html.escape(url)}" target="_blank" rel="noopener">Open login page</a></p>' if url else ""
        if hasattr(APP._auth(transaction.provider), "complete_code"):
            code = ('<div class="setting"><label for=auth-code>Authorization code</label>'
                    '<input id=auth-code name=code type=text autocomplete=one-time-code required>'
                    '<p class=help-text>Only the one-time authorization code is submitted; Mudos never stores it.</p></div>')
            complete = (f'<button class=button type=submit>Complete sign in</button>'
                        f'<button class="button button-quiet" formaction="/auth/{urllib.parse.quote(provider_id)}/{urllib.parse.quote(transaction_id)}/cancel">Cancel</button>')
        else:
            code = '<p class=meta>Save the provider credentials on the previous page. Steam Guard codes are requested only during the acquisition operation and are never persisted.</p>'
            complete = (f'<a class="button button-secondary" href="/integration/{urllib.parse.quote(provider_id)}">Provider settings</a>'
                        f'<button class="button button-quiet" formaction="/auth/{urllib.parse.quote(provider_id)}/{urllib.parse.quote(transaction_id)}/cancel">Back</button>')
        body = (f'<div class="card"><div class="card-head"><h2>{html.escape(provider_id.title())}</h2>{_badge(transaction.state.value)}</div>'
                f'<p>Complete authentication in the provider login page, then return here.</p>{link}'
                f'<form method=post action="/auth/{urllib.parse.quote(provider_id)}/{urllib.parse.quote(transaction_id)}/complete">'
                f'<input type=hidden name=csrf value="{csrf}">{code}<div class=actions>{complete}</div></form></div>')
        self._send(_page("Provider authentication", body, subtitle="Temporary authentication transaction", active="integrations"))

    def _auth_post(self, path: str, form: dict[str, list[str]]) -> None:
        parts = [urllib.parse.unquote(item) for item in path.split("/") if item]
        # /auth/<provider>/start or /auth/<provider>/<transaction>/<action>
        provider_id = parts[1] if len(parts) > 1 else ""
        if len(parts) == 3 and parts[2] == "start":
            if form.get("action", [""])[0] == "sign_out":
                APP.sign_out(provider_id)
                self._redirect("/integration/" + urllib.parse.quote(provider_id) + "?updated=1")
                return
            transaction = APP.begin_auth(provider_id)
            self._redirect("/auth/{}/{}".format(urllib.parse.quote(provider_id), urllib.parse.quote(transaction.transaction_id)))
            return
        transaction_id = parts[2] if len(parts) > 2 else ""
        action = parts[3] if len(parts) > 3 else ""
        if action == "cancel":
            APP.cancel_auth(transaction_id)
            self._redirect("/integration/" + urllib.parse.quote(provider_id))
            return
        if action == "complete":
            try:
                APP.complete_auth(transaction_id, form.get("code", [""])[0])
                self._redirect("/integration/" + urllib.parse.quote(provider_id) + "?updated=1")
            except Exception as error:
                self._send(_page("Authentication failed", _notice("Authentication failed", str(error), "error")
                                      + f'<p><a class=button href="/auth/{urllib.parse.quote(provider_id)}/{urllib.parse.quote(transaction_id)}">Try again</a></p>'), 400)

    def _save_provider(self, provider_id: str, form: dict[str, list[str]], token: str | None) -> None:
        before = APP.config.provider(provider_id)
        before_values = {key: value for key, value in before.values.items()
                         if key != "secrets" and isinstance(value, (str, int, float, bool))}
        before_secrets = {key: before.secret(key) for key in before.secret_refs
                          if before.secret(key) is not None}
        before_usenet_parent = (APP.config.provider("providers.usenet")
                                if provider_id == "providers.usenet.server" else None)
        before_usenet_parent_values = ({key: value for key, value in before_usenet_parent.values.items()
                                        if key != "secrets" and isinstance(value, (str, int, float, bool))}
                                       if before_usenet_parent else {})
        if before_usenet_parent is not None:
            before_usenet_parent_values["enabled"] = before_usenet_parent.enabled
        before_usenet_parent_secrets = ({key: before_usenet_parent.secret(key)
                                         for key in before_usenet_parent.secret_refs
                                         if before_usenet_parent.secret(key) is not None}
                                        if before_usenet_parent else {})
        values = {key: value[0] for key, value in form.items() if not key.startswith(("csrf", "secret_", "clear_"))}
        component = next((item for item in APP.components.all() if provider_id in item.provider_ids), None)
        if component:
            for item in component.configuration:
                if item.kind == "boolean" and item.key not in values:
                    values[item.key] = False
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
        secret_references = {item.slot: item.reference for item in component.secrets
                             if item.reference} if component else {}
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
                    # Questarr reconciliation is deferred until its setup
                    # selection and persisted readiness state authorize it.
                    reconcile=lambda: None,
                )
            else:
                APP.config.update_provider(provider_id, values, secrets_in, clears, secret_references)
            if provider_id == "providers.usenet":
                from .nzbget_admin import apply_control_credentials, apply_packaged_paths
                updated = APP.config.provider(provider_id)
                apply_packaged_paths()
                apply_control_credentials(str(updated.get("username", "mudos")),
                                          updated.secret("rpc_password") or "")
                subprocess.run(["systemctl", "restart", "nzbget.service"],
                               stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL, check=True, timeout=10)
                ready, readiness_message = APP.wait_for_nzbget_rpc()
                if not ready:
                    raise RuntimeError(readiness_message)
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
                APP.config.update_provider("providers.usenet", {"enabled": True})
            if provider_id == "metadata.igdb":
                subprocess.Popen(["busctl", "call", "org.lulu.Consoled", "/org/lulu/Console",
                                  "org.lulu.Console", "RefreshStages", "as", "3",
                                  "metadata", "metadata-enrichment", "artwork"],
                                 stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL, close_fds=True)
            if provider_id in {"providers.usenet", "providers.usenet.server"}:
                subprocess.run(["systemctl", "restart", "lulu-acquisition.service"],
                               stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL, check=True, timeout=10)
        except Exception as error:
            # Restore both configuration layers if materialization or the
            # required daemon restart fails; do not leave a new SecretStore
            # value paired with an old NZBGet runtime.
            try:
                APP.config.update_provider(provider_id, before_values, before_secrets)
                if before_usenet_parent is not None:
                    APP.config.update_provider("providers.usenet", before_usenet_parent_values,
                                               before_usenet_parent_secrets)
            except (OSError, ValueError):
                pass
            LOGGER.exception("provider save failed provider=%s error_type=%s", provider_id, type(error).__name__)
            message = ("Could not update Transmission credentials; previous credentials were preserved."
                       if provider_id == "providers.torrent"
                       else "Could not save these settings. Your previous settings were kept.")
            LOGGER.error("provider save failed provider=%s error_type=%s", provider_id, type(error).__name__)
            self._send(_page("Save failed", f"<p class=error>{html.escape(message)}</p>"), 400); return
        if provider_id in INTEGRATION_METADATA:
            save_validation(provider_id, False, "Connection details changed in Admin; retest before finishing setup.")
        self._redirect("/integrations?updated=1")

    def _service_rows(self) -> str:
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
                    f'{_badge(APP.plugin_service_status(service))}</div><p>{html.escape(service.description)}</p></div>{link}</div>')
        return rows + "".join(generic_rows)

    def _services(self) -> None:
        """Retain old service bookmarks without maintaining a second view."""
        self._redirect("/integrations#services")

    def _system(self) -> None:
        host = _host(self)
        body = f'<div class="grid"><div class="card"><h2>Appliance</h2><p>Hostname</p><strong>{html.escape(host)}</strong><p class="meta">Deployment: {html.escape(_deployment())}</p></div><div class="card"><h2>About this page</h2><p>System-wide settings are intentionally kept separate from service connections.</p><p class="meta">Service credentials are managed under Integrations.</p></div></div>'
        self._send(_page("System", body, subtitle="Appliance information and administration boundaries.", active="system"))


def serve() -> None:
    http.server.ThreadingHTTPServer.allow_reuse_address = True
    http.server.ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()


if __name__ == "__main__": serve()
