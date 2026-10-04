"""Persistent, minimal Mudos onboarding state and setup manifests."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import threading
import time
from typing import Any

from .paths import PATHS
from .plugins import ComponentRegistry, PluginRegistry


_LOCK = threading.RLock()
_STATE_PATH = PATHS.config_root / "onboarding.json"


def _read() -> dict[str, Any]:
    try:
        value = json.loads(_STATE_PATH.read_text())
        if isinstance(value, dict):
            value.setdefault("oobe_dismissed", bool(value.get("dismissed_at"))
                             or value.get("status") == "dismissed")
            value.setdefault("skipped_integrations", [])
            return value
    except (OSError, ValueError):
        pass
    return {"status": "never", "oobe_dismissed": False, "selected_providers": [],
            "selected_integrations": [], "skipped_integrations": [], "completed_at": None,
            "dismissed_at": None, "validation": {}}


def _write(value: dict[str, Any]) -> None:
    _STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=".onboarding-", dir=_STATE_PATH.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(value, stream, sort_keys=True)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, _STATE_PATH)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def onboarding_state() -> dict[str, Any]:
    with _LOCK:
        state = _read()
        # Migrate historical dismissed records, while keeping setup progress
        # independent from the console's explicit first-run decision.
        if "oobe_dismissed" not in state:
            state["oobe_dismissed"] = (bool(state.get("dismissed_at"))
                                        or state.get("status") == "dismissed")
        state["required"] = (not state["oobe_dismissed"]
                             and state.get("status", "never") != "completed")
        return state


def save_progress(*, providers: list[str] | None = None,
                  integrations: list[str] | None = None) -> dict[str, Any]:
    with _LOCK:
        state = _read()
        if state.get("status") not in {"completed", "dismissed"}:
            state["status"] = "partial"
        if providers is not None:
            state["selected_providers"] = sorted(set(map(str, providers)))
        if integrations is not None:
            selected_integrations = set(map(str, integrations))
            state["selected_integrations"] = sorted(selected_integrations)
            state["skipped_integrations"] = sorted(
                set(state.get("skipped_integrations", [])) - selected_integrations)
        state["updated_at"] = int(time.time())
        _write(state)
        return onboarding_state()


def skip_integration(integration: str) -> dict[str, Any]:
    """Persist explicit Skip separately from configuration and validation."""
    value = str(integration).strip()
    if value not in INTEGRATION_METADATA:
        raise ValueError("unsupported setup integration")
    with _LOCK:
        state = _read()
        state["selected_integrations"] = [
            item for item in state.get("selected_integrations", []) if item != value]
        state["skipped_integrations"] = sorted(set(state.get("skipped_integrations", [])) | {value})
        state.setdefault("validation", {}).pop(value, None)
        state["updated_at"] = int(time.time())
        _write(state)
        return onboarding_state()


def dismiss_onboarding() -> dict[str, Any]:
    with _LOCK:
        state = _read()
        if state.get("status") != "completed":
            state["status"] = "dismissed"
            state["dismissed_at"] = int(time.time())
            state["oobe_dismissed"] = True
        _write(state)
        return onboarding_state()


def reopen_onboarding() -> dict[str, Any]:
    with _LOCK:
        state = _read()
        state["status"] = "partial"
        state["oobe_dismissed"] = False
        state["updated_at"] = int(time.time())
        _write(state)
        return onboarding_state()


def reset_onboarding() -> dict[str, Any]:
    """Return OOBE progress to first-run without changing credentials/config."""
    with _LOCK:
        state = _read()
        state.update({"status": "never", "oobe_dismissed": False,
                      "selected_providers": [], "selected_integrations": [],
                      "skipped_integrations": [],
                      "completed_at": None, "dismissed_at": None,
                      "validation": {}, "install_start_failures": {},
                      "updated_at": int(time.time())})
        _write(state)
        return onboarding_state()


def finish_onboarding() -> dict[str, Any]:
    with _LOCK:
        state = _read()
        require_validated_integrations(state)
        state["status"] = "completed"
        state["oobe_dismissed"] = True
        state["completed_at"] = int(time.time())
        _write(state)
        return onboarding_state()


def require_validated_integrations(state: dict[str, Any] | None = None) -> None:
    """Never complete selected credential setup on a stale/failed test."""
    state = state if state is not None else onboarding_state()
    validation = state.get("validation")
    validation = validation if isinstance(validation, dict) else {}
    for integration in state.get("selected_integrations", []):
        result = validation.get(integration)
        if not isinstance(result, dict) or result.get("ok") is not True:
            raise ValueError("Test and Save each selected integration, or Skip it before finishing setup")


def save_admin_password_configured() -> dict[str, Any]:
    """Record that PAM password management was completed; store no password."""
    with _LOCK:
        state = _read()
        state["admin_password_configured"] = True
        state["admin_password_updated_at"] = int(time.time())
        _write(state)
        return onboarding_state()


def save_validation(integration: str, ok: bool, message: str) -> dict[str, Any]:
    with _LOCK:
        state = _read()
        validation = state.get("validation")
        if not isinstance(validation, dict):
            validation = {}
        validation[integration] = {"ok": bool(ok), "message": str(message)[:240],
                                   "checked_at": int(time.time())}
        state["validation"] = validation
        if state.get("status") not in {"completed", "dismissed"}:
            state["status"] = "partial"
        _write(state)
        return onboarding_state()


def install_start_failure(provider_id: str) -> str:
    with _LOCK:
        failures = _read().get("install_start_failures", {})
        return str(failures.get(provider_id, "")) if isinstance(failures, dict) else ""


def record_install_start_failure(provider_id: str, message: str) -> None:
    """Keep a rejected installer request visible until an accepted retry."""
    with _LOCK:
        state = _read()
        failures = state.get("install_start_failures", {})
        failures = dict(failures) if isinstance(failures, dict) else {}
        if message:
            failures[provider_id] = message[:240]
        else:
            failures.pop(provider_id, None)
        state["install_start_failures"] = failures
        _write(state)


@dataclass(frozen=True, slots=True)
class ProviderInfo:
    provider_id: str
    name: str
    summary: str
    packages: tuple[str, ...]
    commands: tuple[str, ...]
    documentation: str = ""
    category: str = "provider"


# These descriptors enrich actual built-in/plugin implementations; they never
# create a provider that is absent from Mudos' component registry.
PROVIDER_INFO = {
    "steam": ProviderInfo("steam", "Steam", "PC games from Steam.", ("steam", "steam-devices"), ("steam",)),
    "epic": ProviderInfo("epic", "Epic Games", "PC games from Epic Games Store.", ("legendary",), ("legendary",)),
    "gog": ProviderInfo("gog", "GOG", "DRM-free PC games from GOG.", ("gogdl",), ("gogdl",)),
    "lutris": ProviderInfo("lutris", "Lutris", "PC/Linux/Windows games managed through Lutris runners.", ("lutris",), ("lutris",)),
    "flatpak": ProviderInfo("flatpak", "Flatpak", "Linux games and apps distributed through Flatpak.", ("flatpak",), ("flatpak",)),
    "retroarch": ProviderInfo("retroarch", "RetroArch", "Classic and legacy platforms including Nintendo, Sega, Atari, NEC, PlayStation 1, arcade and handheld systems.", ("retroarch", "libretro", "libretro-core-info"), ("retroarch",)),
    "dolphin": ProviderInfo("dolphin", "Dolphin", "Nintendo GameCube and Wii.", ("dolphin-emu",), ("dolphin-emu",)),
    "eden": ProviderInfo("eden", "Eden", "Nintendo Switch.", (), ("eden",)),
    "pcsx2": ProviderInfo("pcsx2", "PCSX2", "PlayStation 2.", (), ("pcsx2-qt",)),
    "romm": ProviderInfo("romm", "RomM", "Games from your existing RomM library.", (), (), "https://docs.romm.app/latest/developers/client-api-tokens/", "plugin"),
    "torrent": ProviderInfo("torrent", "Transmission", "Mudos-managed torrent downloads.", ("transmission-cli",), ("transmission-daemon",), "", "plugin"),
    "usenet": ProviderInfo("usenet", "NZBGet", "Mudos-managed Usenet downloads; configure a news server to use it.", ("nzbget",), ("nzbget",), "", "plugin"),
}

FLATPAK_PROVIDER_APPS = {
    "pcsx2": "net.pcsx2.PCSX2",
    "eden": "dev.eden_emu.eden",
}


def provider_manifest(components: ComponentRegistry | None = None) -> list[dict[str, Any]]:
    if components is None:
        registry = PluginRegistry(PATHS.install_root / "config" / "plugins")
        registry.discover()
        components = ComponentRegistry(registry)
        components.discover()
    rows = []
    for component in components.all():
        if ("builtin_provider" not in component.capabilities
                and "provider" not in component.capabilities
                and not set(component.provider_ids).intersection(PROVIDER_INFO)):
            continue
        component_ids = ((component.component_id,) if component.component_id in {"torrent", "usenet"}
                         else component.provider_ids or (component.component_id,))
        for provider_id in component_ids:
            info = PROVIDER_INFO.get(provider_id)
            if not info:
                continue
            installed = _provider_installed(provider_id, info)
            rows.append({"id": provider_id, "name": info.name, "summary": info.summary,
                         "installed": installed,
                          "installable": (provider_id in {"torrent", "usenet"}
                                         or provider_id in FLATPAK_PROVIDER_APPS
                                         and _repository_packages_available(("flatpak",))
                                         or bool(info.packages) and _repository_packages_available(info.packages)),
                         "category": info.category,
                         "status": "installed" if installed else "not_installed",
                         "documentation": info.documentation,
                         "packages": list(info.packages), "dependencies": list(component.dependencies.requires_all),
                         "dependencies_any": [list(group) for group in component.dependencies.requires_any],
                         "credentials": [{"slot": item.slot, "label": item.label,
                                          "description": item.description, "required": item.required}
                                         for item in component.secrets],
                         "documentation": info.documentation,
                         "removable": "uninstall" in component.capabilities,
                         "capabilities": sorted(component.capabilities)})
    return rows


def _provider_installed(provider_id: str, info: ProviderInfo) -> bool:
    if provider_id == "romm":
        # The RomM client is part of this installed Mudos integration; URL and
        # token configuration belong to readiness, not installation state.
        return True
    if provider_id in {"torrent", "usenet"}:
        package = "transmission-cli" if provider_id == "torrent" else "nzbget"
        unit = "lulu-transmission.service" if provider_id == "torrent" else "nzbget.service"
        return _pacman_installed(package) and _systemd_unit_loaded(unit)
    if provider_id == "steam":
        # The launcher alone is not enough: OOBE also depends on the standard
        # Steam device rules and a separately provisioned SteamCMD runtime.
        return (_pacman_installed("steam") and _pacman_installed("steam-devices")
                and bool(shutil.which("steam"))
                and PATHS.steamcmd_executable.is_file()
                and os.access(PATHS.steamcmd_executable, os.X_OK))
    if provider_id in FLATPAK_PROVIDER_APPS:
        if not shutil.which("flatpak"):
            return False
        try:
            installed = subprocess.run(
                ["flatpak", "info", "--system", FLATPAK_PROVIDER_APPS[provider_id]],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                timeout=5, check=False,
            ).returncode == 0
            return installed and bool(info.commands) and all(shutil.which(command) for command in info.commands)
        except (OSError, subprocess.SubprocessError):
            return False
    if provider_id in {"epic", "gog"}:
        executable = shutil.which("legendary" if provider_id == "epic" else "gogdl")
        if not executable:
            return False
        try:
            return subprocess.run([executable, "--version"], stdout=subprocess.DEVNULL,
                                  stderr=subprocess.DEVNULL, timeout=5, check=False).returncode == 0
        except (OSError, subprocess.SubprocessError):
            return False
    if info.commands and all(shutil.which(command) for command in info.commands):
        return True
    if not info.packages:
        return False
    if "libretro" in info.packages:
        if (not _pacman_installed("retroarch")
                or not _pacman_installed("libretro-core-info")
                or not Path("/usr/lib/libretro").is_dir()):
            return False
        try:
            group = subprocess.run(["pacman", "-Sgq", "libretro"], text=True,
                                   capture_output=True, timeout=3, check=False)
            members = [line.strip() for line in group.stdout.splitlines() if line.strip()]
            return bool(members) and all(_pacman_installed(package) for package in members)
        except (OSError, subprocess.SubprocessError):
            return False
    return all(_pacman_installed(package) for package in info.packages)


def _pacman_installed(package: str) -> bool:
    try:
        return subprocess.run(["pacman", "-Q", package], stdout=subprocess.DEVNULL,
                              stderr=subprocess.DEVNULL, timeout=2, check=False).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return bool(shutil.which(package))


def _systemd_unit_loaded(unit: str) -> bool:
    try:
        result = subprocess.run(["systemctl", "show", unit, "--property=LoadState", "--value"],
                                capture_output=True, text=True, timeout=2, check=False)
        return result.returncode == 0 and result.stdout.strip() == "loaded"
    except (OSError, subprocess.SubprocessError):
        return False


def _repository_packages_available(packages: tuple[str, ...]) -> bool:
    # These two provider tools are installed by Mudos-owned isolated venv
    # provisioning scripts, not by Arch repository packages.
    if packages == ("legendary",) or packages == ("gogdl",):
        return True
    try:
        for package in packages:
            args = ["pacman", "-Sgq", package] if package == "libretro" else ["pacman", "-Si", package]
            result = subprocess.run(args, stdout=subprocess.PIPE if package == "libretro" else subprocess.DEVNULL,
                                    stderr=subprocess.DEVNULL, text=package == "libretro",
                                    timeout=3, check=False)
            if result.returncode or package == "libretro" and not result.stdout.strip():
                return False
        return True
    except (OSError, subprocess.SubprocessError):
        return False


INTEGRATION_METADATA = {
    "providers.steam": {"name": "Steam ownership and downloads", "description": "Confirm your signed-in Steam username from the authenticated Steam client, provide a Web API key and Steam account password, then approve SteamCMD with Steam Guard or enter a code.", "fields": [
        {"name": "steam_username", "label": "Steam username", "type": "text", "required": True},
        {"name": "steam_password", "label": "Steam account password", "type": "secret", "required": True},
        {"name": "api_key", "label": "Steam Web API Key", "type": "secret"}],
        "help": "https://steamcommunity.com/dev/apikey"},
    "metadata.igdb": {"name": "IGDB", "description": "Game identity, descriptions and artwork from IGDB.", "fields": [
        {"name": "client_id", "label": "Client ID", "type": "text"},
        {"name": "client_secret", "label": "Client Secret", "type": "secret"}],
        "help": "https://api-docs.igdb.com/#getting-started"},
    "metadata.steamgriddb": {"name": "SteamGridDB", "description": "Optional community artwork for your games.", "fields": [
        {"name": "api_key", "label": "API Key", "type": "secret"}],
        "help": "https://www.steamgriddb.com/profile/preferences"},
    "providers.romm": {"name": "RomM", "description": "Remote games from your own RomM server.", "fields": [
        {"name": "url", "label": "RomM server/base URL", "type": "url"},
        {"name": "api_key", "label": "Client API Token", "type": "secret"}],
        "help": "https://docs.romm.app/latest/developers/client-api-tokens/"},
    "providers.usenet.server": {"name": "Usenet server", "description": "Connection details supplied by your Usenet provider for NZBGet.", "fields": [
        {"name": "host", "label": "Server hostname", "type": "text"},
        {"name": "port", "label": "Port", "type": "number", "default": 563},
        {"name": "tls", "label": "Use TLS", "type": "checkbox", "default": True},
        {"name": "connections", "label": "Connections", "type": "number", "default": 8},
        {"name": "username", "label": "Username", "type": "text"},
        {"name": "password", "label": "Password", "type": "secret"}],
        "help": "https://nzbget.com/documentation/"},
}


def integration_manifest() -> list[dict[str, Any]]:
    rows = []
    for component_id, metadata in INTEGRATION_METADATA.items():
        rows.append({"id": component_id, **metadata})
    return rows
