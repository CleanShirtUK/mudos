#!/usr/bin/env python3
"""Expose consoled's local D-Bus API to the QML shell."""

import asyncio
from collections import deque
import ctypes
from datetime import datetime
import json
import os
from pathlib import Path
import logging
import re
import select
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Lock, Thread
from urllib.parse import parse_qs, unquote, urlparse

from lulu.onboarding import dismiss_onboarding, onboarding_state, reopen_onboarding
from lulu.recovery import clear_failures, snapshot as recovery_snapshot


LOGGER = logging.getLogger("lulu.console-ui-bridge")


def normalize_launch_token(value: object) -> str:
    LOGGER.info("launch token raw type=%s value=%r", type(value).__name__, value)
    if isinstance(value, Variant):
        value = value.value
    elif isinstance(value, dict) and set(value) == {"value"}:
        value = value["value"]
    elif isinstance(value, dict) and set(value) == {"token"}:
        value = value["token"]
    elif isinstance(value, (tuple, list)) and len(value) == 1:
        value = value[0]
    if not isinstance(value, str) or not value:
        raise TypeError(f"launch token must be a non-empty string, got {type(value).__name__}: {value!r}")
    LOGGER.info("launch token normalized type=%s value=%s", type(value).__name__, value)
    return value


class LaunchLogCapture:
    """Event-driven tail of the current Steam launch logs for developer feedback."""

    SOURCES = {
        "Process": "gameprocess_log.txt",
        "Content": "content_log.txt",
        "Cloud": "cloud_log.txt",
        "Shader": "shader_log.txt",
        "Compat": "compat_log.txt",
    }
    IN_MODIFY = 0x00000002
    IN_CLOSE_WRITE = 0x00000008
    IN_MOVED_TO = 0x00000080
    IN_CREATE = 0x00000100

    def __init__(self) -> None:
        self.directory = Path.home() / ".local/share/Steam/logs"
        self._lock = Lock()
        self._lines: deque[str] = deque(maxlen=12)
        self._appid = ""
        self._game_id = ""
        self._active = False
        self._offsets: dict[Path, int] = {}
        self._fd: int | None = None
        self._thread: Thread | None = None

    def start(self, game_id: str) -> None:
        appid = game_id.removeprefix("steam:")
        with self._lock:
            self._appid = appid
            self._game_id = game_id
            self._active = True
            self._lines.clear()
            self._offsets = {
                self.directory / filename: (self.directory / filename).stat().st_size
                for filename in self.SOURCES.values()
                if (self.directory / filename).exists()
            }
            self._append("Lulu", f"selected game_id={game_id} appid={appid}")
            if self._fd is None:
                libc = ctypes.CDLL(None, use_errno=True)
                self._fd = libc.inotify_init1(os.O_NONBLOCK)
                if self._fd < 0:
                    self._fd = None
                else:
                    libc.inotify_add_watch(
                        self._fd,
                        os.fsencode(self.directory),
                        self.IN_MODIFY | self.IN_CLOSE_WRITE | self.IN_MOVED_TO | self.IN_CREATE,
                    )
                    self._thread = Thread(target=self._watch, daemon=True)
                    self._thread.start()

    def snapshot(self) -> dict[str, object]:
        with self._lock:
            return {
                "active": self._active,
                "appid": self._appid,
                "game_id": self._game_id,
                "lines": list(self._lines),
            }

    def note(self, source: str, line: str) -> None:
        with self._lock:
            if self._active:
                self._append(source, line)

    def note_cancellation(self) -> None:
        with self._lock:
            if not self._active or any("Cancelling launch" in line for line in self._lines):
                return
            self._append("Lulu", "Cancelling launch…")

    def _watch(self) -> None:
        while True:
            if self._fd is None:
                return
            try:
                select.select([self._fd], [], [], 1.0)
                os.read(self._fd, 4096)
            except (OSError, ValueError):
                return
            self._drain_files()

    def _drain_files(self) -> None:
        with self._lock:
            if not self._active:
                return
            for path, source in ((self.directory / name, source) for source, name in self.SOURCES.items()):
                try:
                    size = path.stat().st_size
                    if size < self._offsets.get(path, 0):
                        self._offsets[path] = 0
                    with path.open("r", encoding="utf-8", errors="replace") as stream:
                        stream.seek(self._offsets.get(path, 0))
                        data = stream.read()
                        self._offsets[path] = stream.tell()
                except (FileNotFoundError, OSError):
                    continue
                for line in data.splitlines():
                    if self._relevant(line):
                        self._append(source, line)

    def _relevant(self, line: str) -> bool:
        lowered = line.lower()
        return self._appid in line or any(
            word in lowered for word in (
                "launch", "process", "proton", "runtime", "shader", "download",
                "compil", "install", "update", "prepar", "cuphead", "error", "failed",
            )
        )

    def _append(self, source: str, line: str) -> None:
        timestamp = line[:22] if re.match(r"^\[?\d{4}-\d{2}-\d{2} ", line) else ""
        if not timestamp:
            timestamp = datetime.now().strftime("%H:%M:%S")
        self._lines.append(f"{timestamp} [{source}] {line}")

from dbus_next import BusType, Variant
from dbus_next.aio import MessageBus

from lulu.paths import PATHS
from lulu.service_readiness import introspect_lulu_services
from lulu.settings import SettingsStore


class ConsoleUiBridge:
    def __init__(self, loop: asyncio.AbstractEventLoop, consoled: object,
                 sessiond: object, acquisitiond: object | None = None) -> None:
        self.loop = loop
        self.consoled = consoled
        self.sessiond = sessiond
        self.acquisitiond = acquisitiond
        self.launch_logs = LaunchLogCapture()
        self.local_token: str | None = None

    def call(self, operation: asyncio.Future, timeout: float | None = 15) -> object:
        return asyncio.run_coroutine_threadsafe(operation, self.loop).result(timeout=timeout)

    async def list_games(self, scope: str) -> list[dict[str, object]]:
        rows = await self.consoled.call_list_games(scope)
        return [{key: value.value for key, value in row.items()} for row in rows]

    async def utilities(self) -> list[dict[str, object]]:
        return json.loads(await self.consoled.call_list_utilities())

    async def launch_utility(self, application_ref: str) -> dict[str, str]:
        application_id = application_ref.split("/")[1] if application_ref.startswith("app/") else "unknown"
        utility_id = f"utility:flatpak:{application_id}"
        self.launch_logs.start(utility_id)
        self.launch_logs.note("Lulu", f"Flatpak Utility launch requested ref={application_ref}")
        try:
            token = await self.consoled.call_launch_utility(application_ref, 15000)
            self.launch_logs.note("Lulu", f"Flatpak Utility launch accepted ref={application_ref} token={token}")
            return {"token": token}
        except Exception as error:
            self.launch_logs.note("Lulu", f"Flatpak Utility launch failed ref={application_ref}: {error}")
            raise

    async def list_platforms(self) -> list[dict[str, object]]:
        rows = await self.consoled.call_list_platform_categories()
        return [{key: value.value for key, value in row.items()} for row in rows]

    async def list_available_games(self, provider: str) -> list[dict[str, object]]:
        rows = await self.consoled.call_list_available_games(provider)
        return [{key: value.value for key, value in row.items()} for row in rows]

    async def refresh_catalogue(self) -> dict[str, int]:
        count = await self.consoled.call_refresh()
        LOGGER.info("manual catalogue refresh completed games=%s", count)
        return {"games": int(count)}

    async def refresh_catalogue_stages(self, stages: list[str]) -> dict[str, int]:
        count = await self.consoled.call_refresh_stages(stages)
        LOGGER.info("manual staged catalogue refresh completed stages=%s games=%s",
                    ",".join(stages), count)
        return {"games": int(count)}

    async def startup_readiness(self) -> dict[str, bool]:
        ready = await self.consoled.call_get_startup_readiness()
        return {"ready": bool(ready)}

    def launch_log(self) -> dict[str, object]:
        return self.launch_logs.snapshot()

    async def launch_status(self) -> dict[str, object]:
        """Normalize Sessiond ownership with provider evidence for the launch screen."""
        state = await self.state()
        lifecycle = str(state.get("lifecycle", "shell"))
        game_id = str(state.get("primary_id") or self.launch_logs.snapshot().get("game_id") or "")
        provider = (game_id.split(":", 2)[1] if game_id.startswith("provider:")
                    else "steam" if game_id.startswith("steam:") or game_id.startswith("steam-")
                    else game_id.split(":", 1)[0] if ":" in game_id else "")
        stage_by_lifecycle = {
            "launch_requested": ("preparing", "Preparing launch"),
            "starting": (("provider_preparation", "Starting provider") if game_id.startswith("provider:")
                         else ("provider_preparation", "Waiting for Steam preparation") if provider == "steam"
                         else ("launching_executable", "Starting game process")),
            "presentation_pending": ("waiting_for_game_window", "Waiting for game window"),
            "game": ("presented", "Game presentation selected"),
            "returning": ("returning", "Returning to Mudos"),
        }
        stage, label = stage_by_lifecycle.get(lifecycle, ("idle", ""))
        log = self.launch_logs.snapshot()
        lines = log.get("lines", []) if log.get("game_id") == game_id else []
        # Promote a provider stage only when Steam's own log explicitly
        # names that activity. These are categorical observations, never a
        # synthetic percentage or a claim that an absent log means idle.
        if provider == "steam" and lifecycle in {"launch_requested", "starting"} and lines:
            evidence = str(lines[-1]).casefold()
            if "shader" in evidence:
                stage, label = "shader_cache_preparation", "Steam shader-cache activity"
            elif any(word in evidence for word in ("download", "installing content", "update state")):
                stage, label = "acquiring_components", "Steam content download / preparation"
            elif any(word in evidence for word in ("proton", "runtime", "umu")):
                stage, label = "runtime_preparation", "Steam / Proton runtime preparation"
        return {
            "token": state.get("launch_token") or "",
            "game_id": game_id,
            "title": state.get("session_title") or game_id,
            "lifecycle": lifecycle,
            "stage": stage,
            "stage_label": label,
            "provider": provider,
            "detail": lines[-1] if lines else "",
            "lines": lines[-3:],
            "progress": None,
            "cancellable": bool(state.get("launch_cancellable", False)),
            "failure": state.get("last_failure_reason") or "",
        }

    async def launch_game(self, game_id: str) -> dict[str, object]:
        LOGGER.info("launch request game_id=%s", game_id)
        appid = game_id.removeprefix("steam:")
        self.launch_logs.note("Lulu", f"HTTP launch request started game_id={game_id}")
        if game_id.startswith("steam:"):
            if os.environ.get("LULU_STEAM_LAUNCH_PROVIDER") == "steam-aurelia":
                token = normalize_launch_token(await self.sessiond.call_request_aurelia_launch(appid, 15000))
                self.launch_logs.note("Steam Aurelia", f"aurelia play {appid}")
            else:
                token = normalize_launch_token(await self.sessiond.call_request_steam_launch(appid, 15000))
            self.launch_logs.note("Lulu", f"session launch boundary reached game_id={game_id} appid={appid} token={token}")
            if os.environ.get("LULU_STEAM_LAUNCH_PROVIDER") != "steam-aurelia":
                self.launch_logs.note("Steam", f"steam://rungameid/{appid}")
        else:
            startup_timeout = 120000 if game_id.startswith("epic:") else 15000
            token = await self.consoled.call_launch_game(game_id, startup_timeout)
            self.local_token = token
            self.launch_logs.note("Lulu", f"launch boundary reached game_id={game_id} appid={appid}")
        LOGGER.info("launch accepted game_id=%s token=%s", game_id, token)
        return {
            "token": token,
            "navigation_only": token.startswith("steam://nav/games/details/"),
        }

    async def state(self) -> dict[str, object]:
        return json.loads(await self.sessiond.call_get_state())

    async def controller_mutation(self, action: str, payload: dict[str, object]) -> dict[str, object]:
        controller_id = str(payload.get("id", ""))
        if action == "player":
            result = await self.sessiond.call_set_controller_player(
                controller_id, int(payload.get("player", 0)))
        elif action == "navigation":
            result = await self.sessiond.call_set_navigation_controller(controller_id)
        elif action == "dolphin-wii-mode":
            result = await self.sessiond.call_set_dolphin_wii_remote_mode(controller_id)
        else:
            raise ValueError(f"unknown controller operation: {action}")
        return json.loads(result)

    async def acquisition(self) -> dict[str, object]:
        if self.acquisitiond is None:
            return {"jobs": [], "activeDownloadCount": 0}
        return json.loads(await self.acquisitiond.call_get_snapshot())

    async def retry_acquisition(self, job_id: str) -> dict[str, str]:
        if self.acquisitiond is None:
            raise RuntimeError("acquisition service is unavailable")
        return {"token": await self.acquisitiond.call_retry_job(job_id)}

    async def clear_acquisition(self, job_id: str) -> dict[str, str]:
        if self.acquisitiond is None:
            raise RuntimeError("acquisition service is unavailable")
        await self.acquisitiond.call_clear_failed_job(job_id)
        return {"status": "cleared"}

    async def acquisition_action(self, action: str, job_id: str) -> dict[str, str]:
        if self.acquisitiond is None:
            raise RuntimeError("acquisition service is unavailable")
        if action == "pause":
            await self.acquisitiond.call_pause_job(job_id)
        elif action == "resume":
            await self.acquisitiond.call_resume_job(job_id)
        elif action == "cancel":
            await self.acquisitiond.call_cancel_job(job_id)
        else:
            raise ValueError("unknown acquisition action")
        return {"status": action}

    async def browser_handoff(self, uri: str, source_origin: str) -> dict[str, str]:
        if self.acquisitiond is None:
            raise RuntimeError("acquisition service is unavailable")
        job_id = await self.acquisitiond.call_submit_browser_handoff(uri, source_origin)
        LOGGER.info("browser handoff accepted origin=%s uri=%s job_id=%s", source_origin, uri, job_id)
        if str(job_id).startswith("existing:"):
            return {"job_id": str(job_id).removeprefix("existing:"), "status": "already-installed",
                    "message": "Already installed"}
        asyncio.create_task(self._refresh_after_acquisition(job_id, "flatpak"))
        return {"job_id": job_id, "status": "accepted", "message": "Preparing installation…"}

    async def clear_requested_surface(self) -> dict[str, str]:
        await self.sessiond.call_clear_requested_surface()
        return {"status": "cleared"}

    async def open_steam_store(self) -> dict[str, str]:
        self.launch_logs.start("steam-store")
        self.launch_logs.note("Lulu", "Steam Store launch requested")
        token = await self.sessiond.call_request_steam_store(15000)
        return {"token": token}

    async def install_game(self, game_id: str) -> dict[str, str]:
        if self.acquisitiond is None:
            raise RuntimeError("acquisition service is unavailable")
        rows = await self.list_available_games("")
        selected = next((row for row in rows if str(row.get("game_id", "")) == game_id), None)
        if selected is None:
            raise ValueError("game is not available to acquire")
        provider = str(selected.get("provider", ""))
        title = str(selected.get("title", game_id))
        if provider == "steam":
            appid = await self.consoled.call_resolve_steam_install(game_id)
            content_identity = f"steam:{appid}"
        elif provider == "romm":
            rom_id = str(selected.get("provider_id", ""))
            if not rom_id.isdecimal() or int(rom_id) < 1:
                raise ValueError("RomM content identity is invalid")
            content_identity = f"romm:{rom_id}"
        elif provider == "lutris":
            content_identity = str(selected.get("content_identity", ""))
            if not content_identity:
                raise ValueError("PC source identity is missing")
            job_id = await self.acquisitiond.call_submit_pc_install(content_identity, title)
            asyncio.create_task(self._refresh_after_acquisition(job_id, provider))
            self.launch_logs.note("Lulu", f"{provider} installation submitted identity={content_identity} job_id={job_id}")
            return {"token": job_id}
        elif provider == "steam-aurelia":
            appid = str(selected.get("provider_id", ""))
            if not appid.isdecimal() or int(appid) < 1:
                raise ValueError("Aurelia AppID is invalid")
            content_identity = f"steam-aurelia:{appid}"
        elif provider in {"gog", "epic"}:
            provider_id = str(selected.get("provider_id", ""))
            if not provider_id:
                raise ValueError("provider content identity is missing")
            content_identity = f"{provider}:{provider_id}"
        elif provider == "flatpak":
            application_id = str(selected.get("provider_id", ""))
            if not application_id:
                raise ValueError("Flatpak application identity is missing")
            content_identity = f"flatpak:{application_id}"
        else:
            raise ValueError("game provider is not acquirable")
        existing_snapshot = await self.acquisition()
        existing = next((item for item in existing_snapshot.get("jobs", [])
                         if item.get("provider") == provider
                         and item.get("content_identity") == content_identity
                         and item.get("state") == "failed"
                         and not item.get("retired", False)), None)
        if existing is not None:
            error = existing.get("error") or {}
            authentication_recovered = (
                provider == "steam" and isinstance(error, dict)
                and error.get("code") == "authentication-required"
            )
            if not existing.get("retryable", False) and not authentication_recovered:
                raise ValueError("acquisition is not retryable")
            job_id = await self.acquisitiond.call_retry_job(str(existing["job_id"]))
        else:
            job_id = await self.acquisitiond.call_submit_job(provider, content_identity, title)
        asyncio.create_task(self._refresh_after_acquisition(job_id, provider))
        self.launch_logs.note("Lulu", f"{provider} acquisition submitted identity={content_identity} job_id={job_id}")
        return {"token": job_id}

    async def uninstall_capability(self, game_id: str) -> dict[str, object]:
        if self.acquisitiond is None:
            return {"supported": False, "installed": False}
        return json.loads(await self.acquisitiond.call_can_uninstall(game_id))

    async def uninstall_game(self, game_id: str) -> dict[str, str]:
        if self.acquisitiond is None:
            raise RuntimeError("acquisition service is unavailable")
        job_id = await self.acquisitiond.call_uninstall_game(game_id)
        asyncio.create_task(self._refresh_after_removal(job_id))
        return {"token": job_id}

    async def _refresh_after_removal(self, job_id: str) -> None:
        try:
            for _ in range(180):
                snapshot = json.loads(await self.acquisitiond.call_get_snapshot())
                job = next((item for item in snapshot.get("jobs", [])
                            if item.get("job_id") == job_id), None)
                if job is None:
                    return
                if job.get("state") == "completed":
                    await self.consoled.call_refresh_stages(["steam", "gog", "epic", "local", "romm", "components"])
                    return
                if job.get("state") in {"failed", "cancelled"}:
                    return
                await asyncio.sleep(1)
        except Exception:
            LOGGER.exception("uninstall catalogue refresh failed job_id=%s", job_id)

    async def _refresh_after_acquisition(self, job_id: str, provider: str) -> None:
        """Rejoin completed provider content with the local catalogue."""
        try:
            for _ in range(720):
                snapshot = json.loads(await self.acquisitiond.call_get_snapshot())
                job = next((item for item in snapshot.get("jobs", [])
                            if item.get("job_id") == job_id), None)
                if job is None or job.get("state") in {"failed", "cancelled"}:
                    return
                if job.get("state") == "completed":
                    stages = (["steam"] if provider == "steam-aurelia" else
                              [provider] if provider in {"steam", "gog", "epic"} else
                              ["components"] if provider == "flatpak" else ["local"])
                    await self.consoled.call_refresh_stages(stages)
                    return
                await asyncio.sleep(1)
        except Exception:
            LOGGER.exception("Steam acquisition catalogue refresh failed job_id=%s", job_id)

    async def cancel_launch(self) -> dict[str, str]:
        self.launch_logs.note_cancellation()
        state = await self.state() if hasattr(self.sessiond, "call_get_state") else {}
        primary_id = str(state.get("primary_id") or "")
        session_kind = str(state.get("session_kind") or "")
        # ``local_token`` is retained after a completed managed launch for
        # legacy local-runtime cancellation. It is not proof that Consoled
        # owns the currently active process: normal provider games are owned
        # by Sessiond and must cancel through its launch task.
        consoled_owns_process = (
            session_kind == "provider_standalone" or primary_id.startswith("local:")
        )
        if consoled_owns_process or (
            self.local_token is not None and state.get("lifecycle") in (None, "shell")
        ):
            await self.consoled.call_cancel_local_launch()
            self.local_token = None
        else:
            if state.get("lifecycle") == "game" and primary_id.startswith("steam-install:"):
                await self.sessiond.call_quit_delegated()
            else:
                await self.sessiond.call_cancel_launch()
            self.local_token = None
        return {"status": "cancelled"}

    async def reset_mudos(self) -> dict[str, str]:
        result = await self.sessiond.call_reset_mudos()
        return {"status": result}

    async def mudos_menu(self) -> list[dict[str, object]]:
        return json.loads(await self.consoled.call_list_mudos_providers())

    async def plugin_status(self) -> list[dict[str, object]]:
        return json.loads(await self.consoled.call_get_plugin_status())

    async def plugin_detail(self, plugin_id: str) -> dict[str, object]:
        plugins = await self.plugin_status()
        plugin = next((item for item in plugins if item.get("id") == plugin_id), None)
        if plugin is None:
            raise ValueError("unknown plugin")
        options: list[dict[str, object]] = []
        capabilities = plugin.get("capabilities", [])
        if plugin_id == "steam":
            options = [
                {"key": "plugin.steam.open", "label": "Open Steam for Sign In", "kind": "action", "value": "", "writable": True},
                {"key": "plugin.steamcmd.username", "label": "SteamCMD Username", "kind": "setting", "value": "", "writable": True},
                {"key": "plugin.steamcmd.password", "label": "SteamCMD Password", "kind": "secret", "value": "", "writable": True},
            ]
        elif plugin_id == "romm":
            options = [
                {"key": "plugin.romm.url", "label": "URL", "kind": "setting", "value": "", "writable": True},
                {"key": "plugin.romm.api_key", "label": "Pair RomM Device", "kind": "secret", "value": "", "writable": True},
            ]
        secret_names = {"steam": ["password"], "romm": ["api-key"]}.get(plugin_id, [])
        for name in secret_names:
            status = json.loads(await self.consoled.call_get_plugin_secret_status(plugin_id, name))
            option = next((item for item in options if item["key"].endswith(name.replace("-", "_"))), None)
            if option is not None and status.get("configured"):
                option["label"] += " (configured)"
                options.append({"key": option["key"] + ".clear", "label": option["label"].replace(" (configured)", "") + " — Clear", "kind": "action", "value": "", "writable": True})
        return {"plugin": plugin, "options": options}

    async def plugin_sign_in(self, plugin_id: str) -> dict[str, object]:
        return json.loads(await self.consoled.call_begin_plugin_authentication(plugin_id))

    async def credential_state(self) -> dict[str, object]:
        return json.loads(await self.consoled.call_get_credential_state())

    async def credential_begin(self, payload: dict[str, object]) -> dict[str, object]:
        return json.loads(await self.consoled.call_begin_credential_request(
            str(payload.get("title", "Credential")), str(payload.get("prompt", "Value")),
            str(payload.get("input_type", "text")), bool(payload.get("secret", False)),
             int(payload.get("min_length", 0)), int(payload.get("max_length", 4096)),
             bool(payload.get("multiline", False)),
             str(payload.get("presentation", "prompted"))))

    async def credential_submit(self, payload: dict[str, object]) -> dict[str, object]:
        return json.loads(await self.consoled.call_submit_credential(
            str(payload.get("id", "")), str(payload.get("value", ""))))

    async def credential_cancel(self, payload: dict[str, object]) -> dict[str, object]:
        return json.loads(await self.consoled.call_cancel_credential(str(payload.get("id", ""))))

    async def web_credential(self, operation: str, payload: dict[str, object]) -> dict[str, object]:
        profile = str(payload.get("profile", ""))
        origin = str(payload.get("origin", ""))
        if operation == "get":
            result = await self.consoled.call_get_web_credential(profile, origin)
        elif operation == "save":
            result = await self.consoled.call_save_web_credential(
                profile, origin, str(payload.get("username", "")), str(payload.get("password", "")))
        else:
            result = await self.consoled.call_clear_web_credential(profile, origin)
        return json.loads(result)

    async def plugin_secret(self, plugin_id: str, name: str, value: str) -> dict[str, object]:
        result = json.loads(await self.consoled.call_set_plugin_secret(plugin_id, name, value))
        if plugin_id == "steam" and name == "password":
            result["verification"] = json.loads(await self.consoled.call_verify_plugin_acquisition(plugin_id))
        return result

    async def plugin_clear_secret(self, plugin_id: str, name: str) -> dict[str, object]:
        return json.loads(await self.consoled.call_clear_plugin_secret(plugin_id, name))

    async def pair_romm(self, code: str) -> dict[str, object]:
        return json.loads(await self.consoled.call_pair_romm_device(code))

    async def plugin_setting(self, plugin_id: str, name: str, value: str) -> dict[str, object]:
        return json.loads(await self.consoled.call_set_plugin_setting(plugin_id, name, value))

    async def launch_provider(self, provider_id: str) -> dict[str, str]:
        token = await self.consoled.call_launch_provider_standalone(provider_id, 15000)
        self.local_token = token
        return {"token": token}

    async def system_power(self, action: str) -> dict[str, str]:
        method = self.sessiond.call_reboot if action == "reboot" else self.sessiond.call_shutdown
        return {"status": await method()}

    async def set_input_mode(self, mode: str) -> dict[str, str]:
        await self.sessiond.call_set_input_mode(mode)
        return {"input_mode": mode}

    async def set_browser_surface(self, active: bool) -> dict[str, str]:
        await self.sessiond.call_set_delegated_surface("browser" if active else "")
        return {"delegated_surface": "browser" if active else ""}

    async def list_system_settings(self, category: str) -> list[dict[str, object]]:
        rows = await self.consoled.call_list_system_settings(category)
        return [{key: value.value for key, value in row.items()} for row in rows]

    async def bluetooth_action(self, action: str, path: str) -> dict[str, object]:
        return json.loads(await self.consoled.call_bluetooth_action(action, path))

    async def network_state(self) -> dict[str, object]:
        return json.loads(await self.consoled.call_get_network_state())

    async def audio_state(self) -> dict[str, object]:
        return json.loads(await self.consoled.call_get_audio_state())

    async def storage_state(self) -> dict[str, object]:
        return json.loads(await self.consoled.call_get_storage_state())

    async def display_state(self) -> dict[str, object]:
        return json.loads(await self.consoled.call_get_display_state())

    async def display_apply(self, payload: dict[str, object]) -> dict[str, object]:
        result = await self.consoled.call_apply_display(str(payload.get("output", "")),
                                                        int(payload.get("width", 0)),
                                                        int(payload.get("height", 0)),
                                                        float(payload.get("refresh", 0)))
        return json.loads(result)

    async def storage_mutation(self, action: str, payload: dict[str, object]) -> dict[str, object]:
        device_id = str(payload.get("id", ""))
        if action == "mount":
            result = await self.consoled.call_mount_storage(device_id)
        elif action == "unmount":
            result = await self.consoled.call_unmount_storage(device_id)
        elif action == "eject":
            result = await self.consoled.call_eject_storage(device_id)
        elif action in {"target", "target-default"}:
            result = await self.consoled.call_select_storage_target(str(payload.get("kind", "")), device_id)
        else:
            raise ValueError(f"unknown storage operation: {action}")
        return json.loads(result)

    async def audio_mutation(self, action: str, payload: dict[str, object]) -> dict[str, object]:
        device_id = str(payload.get("id", ""))
        input_device = bool(payload.get("input", False))
        if action == "output":
            result = await self.consoled.call_set_audio_output(device_id)
        elif action == "input":
            result = await self.consoled.call_set_audio_input(device_id)
        elif action == "volume":
            result = await self.consoled.call_set_audio_volume(device_id, int(payload.get("volume", 0)), input_device)
        elif action == "mute":
            result = await self.consoled.call_set_audio_mute(device_id, bool(payload.get("muted", False)), input_device)
        else:
            raise ValueError(f"unknown audio operation: {action}")
        return json.loads(result)

    async def network_mutation(self, action: str, payload: dict[str, object]) -> dict[str, object]:
        if action == "wifi":
            result = await self.consoled.call_set_wifi_enabled(bool(payload.get("enabled")))
        elif action == "connect":
            result = await self.consoled.call_connect_wifi(str(payload.get("ssid", "")),
                                                           str(payload.get("password", "")))
        elif action == "disconnect":
            result = await self.consoled.call_disconnect_wifi()
        elif action == "forget":
            result = await self.consoled.call_forget_wifi(str(payload.get("ssid", "")))
        else:
            raise ValueError(f"unknown network operation: {action}")
        return json.loads(result)

    async def keyboard(self, action: str) -> dict[str, object]:
        method = (self.consoled.call_show_keyboard if action == "show" else
                  self.consoled.call_hide_keyboard if action == "hide" else
                  self.consoled.call_keyboard_visible)
        return {"visible": bool(await method())}

    async def search_metadata(self, game_id: str, query: str) -> list[dict[str, object]]:
        rows = await self.consoled.call_search_metadata(game_id, query)
        return [{key: value.value for key, value in row.items()} for row in rows]

    async def set_metadata_match(self, game_id: str, payload: dict[str, object]) -> None:
        await self.consoled.call_set_metadata_match(
            game_id, str(payload.get("provider", "steamgriddb")),
            str(payload.get("metadata_game_id", "")), str(payload.get("canonical_title", "")),
        )

    async def revert_metadata_match(self, game_id: str) -> None:
        await self.consoled.call_revert_metadata_match(game_id)

    async def set_title_override(self, game_id: str, title: str) -> None:
        await self.consoled.call_set_title_override(game_id, title)

    async def clear_title_override(self, game_id: str) -> None:
        await self.consoled.call_clear_title_override(game_id)

    async def set_artwork_suppressed(self, game_id: str, suppressed: bool) -> None:
        if suppressed:
            await self.consoled.call_suppress_artwork(game_id)
        else:
            await self.consoled.call_restore_artwork(game_id)

    async def artwork_candidates(self, game_id: str, role: str = "cover") -> list[dict[str, object]]:
        if role == "cover":
            rows = await self.consoled.call_list_artwork_candidates(game_id)
        else:
            rows = await self.consoled.call_list_presentation_artwork_candidates(game_id, role)
        return [{key: value.value for key, value in row.items()} for row in rows]

    async def select_artwork(self, game_id: str, source_url: str) -> None:
        await self.consoled.call_select_artwork(game_id, source_url)

    async def select_presentation_artwork(self, game_id: str, role: str, source_url: str) -> None:
        await self.consoled.call_select_presentation_artwork(game_id, role, source_url)

    async def restore_automatic_artwork(self, game_id: str) -> None:
        await self.consoled.call_restore_automatic_artwork(game_id)


class ApiHandler(BaseHTTPRequestHandler):
    bridge: ConsoleUiBridge

    def _respond(self, status: int, payload: object) -> None:
        data = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:
        if urlparse(self.path).path == "/onboarding":
            self._respond(200, onboarding_state())
            return
        if urlparse(self.path).path == "/recovery":
            self._respond(200, recovery_snapshot())
            return
        if urlparse(self.path).path == "/keyboard/status":
            try:
                self._respond(200, self.bridge.call(self.bridge.keyboard("status")))
            except Exception as error:
                self._respond(503, {"error": str(error) or type(error).__name__})
            return
        if urlparse(self.path).path == "/state":
            try:
                self._respond(200, self.bridge.call(self.bridge.state()))
            except Exception as error:  # pragma: no cover - live IPC failure path
                self._respond(503, {"error": str(error)})
            return
        if urlparse(self.path).path == "/mudos-menu":
            try:
                self._respond(200, self.bridge.call(self.bridge.mudos_menu()))
            except Exception as error:
                self._respond(503, {"error": str(error)})
            return
        if urlparse(self.path).path == "/launch-log":
            self._respond(200, self.bridge.launch_log())
            return
        if urlparse(self.path).path == "/launch-status":
            try:
                self._respond(200, self.bridge.call(self.bridge.launch_status()))
            except Exception as error:
                self._respond(503, {"error": str(error) or type(error).__name__})
            return
        if urlparse(self.path).path == "/acquisition":
            try:
                self._respond(200, self.bridge.call(self.bridge.acquisition()))
            except Exception as error:  # pragma: no cover - live IPC failure path
                self._respond(503, {"error": str(error)})
            return
        if urlparse(self.path).path == "/settings":
            category = parse_qs(urlparse(self.path).query).get("category", ["System"])[0]
            try:
                self._respond(200, self.bridge.call(self.bridge.list_system_settings(category)))
            except Exception as error:  # pragma: no cover - live IPC failure path
                self._respond(503, {"error": str(error)})
            return
        if urlparse(self.path).path == "/utilities":
            try:
                self._respond(200, self.bridge.call(self.bridge.utilities(), timeout=60))
            except Exception as error:
                self._respond(503, {"error": str(error) or type(error).__name__})
            return
        if urlparse(self.path).path == "/network":
            try:
                self._respond(200, self.bridge.call(self.bridge.network_state()))
            except Exception as error:
                self._respond(503, {"error": str(error)})
            return
        if urlparse(self.path).path == "/audio":
            try:
                self._respond(200, self.bridge.call(self.bridge.audio_state()))
            except Exception as error:
                self._respond(503, {"error": str(error)})
            return
        if urlparse(self.path).path == "/storage":
            try:
                self._respond(200, self.bridge.call(self.bridge.storage_state()))
            except Exception as error:
                self._respond(503, {"error": str(error)})
            return
        if urlparse(self.path).path == "/display":
            try:
                self._respond(200, self.bridge.call(self.bridge.display_state()))
            except Exception as error:
                self._respond(503, {"error": str(error)})
            return
        if urlparse(self.path).path == "/platforms":
            try:
                self._respond(200, self.bridge.call(self.bridge.list_platforms()))
            except Exception as error:  # pragma: no cover - live IPC failure path
                self._respond(503, {"error": str(error)})
            return
        if urlparse(self.path).path == "/startup-ready":
            try:
                self._respond(200, self.bridge.call(self.bridge.startup_readiness()))
            except Exception as error:
                self._respond(503, {"error": str(error)})
            return
        if urlparse(self.path).path == "/plugins":
            try:
                self._respond(200, self.bridge.call(self.bridge.plugin_status()))
            except Exception as error:
                self._respond(503, {"error": str(error)})
            return
        if urlparse(self.path).path.startswith("/plugins/") and not urlparse(self.path).path.endswith("/signin"):
            try:
                plugin_id = urlparse(self.path).path.removeprefix("/plugins/")
                self._respond(200, self.bridge.call(self.bridge.plugin_detail(plugin_id)))
            except Exception as error:
                self._respond(404, {"error": str(error)})
            return
        if urlparse(self.path).path == "/credential":
            try:
                self._respond(200, self.bridge.call(self.bridge.credential_state()))
            except Exception as error:
                self._respond(503, {"error": str(error)})
            return
        if urlparse(self.path).path == "/available":
            # The Installable surface is the combined entitled-but-uninstalled
            # catalogue. Provider-specific filtering remains available to
            # callers that explicitly request it.
            provider = parse_qs(urlparse(self.path).query).get("provider", [""])[0]
            try:
                self._respond(200, self.bridge.call(self.bridge.list_available_games(provider)))
            except Exception as error:  # pragma: no cover - live IPC failure path
                self._respond(503, {"error": str(error)})
            return
        if urlparse(self.path).path == "/metadata/search":
            query = parse_qs(urlparse(self.path).query)
            game_id = query.get("game_id", [""])[0]
            search = query.get("query", [""])[0]
            try:
                self._respond(200, self.bridge.call(
                    self.bridge.search_metadata(game_id, search), timeout=60))
            except Exception as error:  # pragma: no cover - live IPC failure path
                self._respond(503, {"error": str(error)})
            return
        if urlparse(self.path).path == "/artwork/candidates":
            query = parse_qs(urlparse(self.path).query)
            game_id = query.get("game_id", [""])[0]
            role = query.get("role", ["cover"])[0]
            try:
                self._respond(200, self.bridge.call(
                    self.bridge.artwork_candidates(game_id, role), timeout=30))
            except Exception as error:
                self._respond(409, {"error": str(error)})
            return
        if urlparse(self.path).path.startswith("/uninstall/capability/"):
            try:
                game_id = unquote(urlparse(self.path).path.removeprefix("/uninstall/capability/"))
                self._respond(200, self.bridge.call(self.bridge.uninstall_capability(game_id), timeout=20))
            except Exception as error:
                self._respond(409, {"error": str(error) or type(error).__name__})
            return
        scope = parse_qs(urlparse(self.path).query).get("scope", ["recent"])[0]
        try:
            self._respond(200, self.bridge.call(self.bridge.list_games(scope)))
        except Exception as error:  # pragma: no cover - live IPC failure path
            self._respond(503, {"error": str(error)})

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        if path in {"/onboarding/dismiss", "/onboarding/reopen"}:
            try:
                state = dismiss_onboarding() if path.endswith("dismiss") else reopen_onboarding()
                self._respond(200, state)
            except Exception as error:
                self._respond(500, {"error": str(error) or type(error).__name__})
            return
        if path in {"/recovery/retry", "/recovery/setup", "/recovery/reboot", "/recovery/shutdown"}:
            try:
                if path.endswith("setup"):
                    reopen_onboarding()
                if path.endswith(("retry", "setup")):
                    clear_failures()
                    result = self.bridge.call(self.bridge.reset_mudos(), timeout=5)
                else:
                    action = "reboot" if path.endswith("reboot") else "shutdown"
                    result = self.bridge.call(self.bridge.system_power(action), timeout=5)
                self._respond(200, result)
            except Exception as error:
                self._respond(409, {"error": str(error) or type(error).__name__})
            return
        if path == "/ui-refresh":
            try:
                group = parse_qs(urlparse(self.path).query).get("group", ["all"])[0]
                Path("/tmp/lulu-qml-refresh-request").write_text(group, encoding="ascii")
                self._respond(200, {"status": "requested", "group": group})
            except OSError as error:
                self._respond(409, {"error": str(error)})
            return
        if path == "/utilities/launch":
            try:
                length = int(self.headers.get("Content-Length", "0"))
                payload = json.loads(self.rfile.read(length) or b"{}")
                application_ref = str(payload.get("ref", ""))
                self._respond(200, self.bridge.call(
                    self.bridge.launch_utility(application_ref), timeout=20))
            except Exception as error:
                self._respond(409, {"error": str(error) or type(error).__name__})
            return
        if path.startswith("/artwork/"):
            try:
                game_id = unquote(path.removeprefix("/artwork/"))
                length = int(self.headers.get("Content-Length", "0"))
                payload = json.loads(self.rfile.read(length) or b"{}")
                role = str(payload.get("role", "cover"))
                if role in {"icon_square", "preview_still"}:
                    self.bridge.call(self.bridge.select_presentation_artwork(
                        game_id, role, str(payload.get("source_url", ""))), timeout=60)
                elif payload.get("restore"):
                    self.bridge.call(self.bridge.restore_automatic_artwork(game_id), timeout=30)
                else:
                    self.bridge.call(self.bridge.select_artwork(
                        game_id, str(payload.get("source_url", ""))), timeout=30)
                self._respond(200, {"status": "updated"})
            except Exception as error:
                self._respond(409, {"error": str(error)})
            return
        if path.startswith("/plugins/") and path.endswith("/signin"):
            try:
                plugin_id = path.removeprefix("/plugins/").removesuffix("/signin")
                self._respond(200, self.bridge.call(self.bridge.plugin_sign_in(plugin_id), timeout=30))
            except Exception as error:
                self._respond(409, {"error": str(error) or type(error).__name__})
            return
        if path == "/credential/begin":
            try:
                length = int(self.headers.get("Content-Length", "0"))
                payload = json.loads(self.rfile.read(length) or b"{}")
                self._respond(200, self.bridge.call(self.bridge.credential_begin(payload), timeout=30))
            except Exception as error:
                self._respond(409, {"error": str(error) or type(error).__name__})
            return
        if path in {"/web-credentials/get", "/web-credentials/save", "/web-credentials/clear"}:
            try:
                request_origin = self.headers.get("Origin", "")
                if request_origin not in {"", "null", "file://", "qrc:", "qrc://"}:
                    self._respond(403, {"error": "web credential bridge is not available to page origins"})
                    return
                length = int(self.headers.get("Content-Length", "0"))
                payload = json.loads(self.rfile.read(length) or b"{}")
                operation = path.rsplit("/", 1)[-1]
                self._respond(200, self.bridge.call(self.bridge.web_credential(operation, payload), timeout=30))
            except Exception as error:
                self._respond(409, {"error": str(error) or type(error).__name__})
            return
        if path in {"/credential/submit", "/credential/cancel"}:
            try:
                length = int(self.headers.get("Content-Length", "0"))
                payload = json.loads(self.rfile.read(length) or b"{}")
                operation = self.bridge.credential_submit if path.endswith("submit") else self.bridge.credential_cancel
                self._respond(200, self.bridge.call(operation(payload), timeout=30))
            except Exception as error:
                self._respond(409, {"error": str(error) or type(error).__name__})
            return
        if path == "/plugins/romm/pair":
            try:
                length = int(self.headers.get("Content-Length", "0"))
                payload = json.loads(self.rfile.read(length) or b"{}")
                self._respond(200, self.bridge.call(
                    self.bridge.pair_romm(str(payload.get("code", ""))), timeout=30))
            except Exception as error:
                self._respond(409, {"error": str(error) or type(error).__name__})
            return
        if path.startswith("/plugins/") and ("/secret/" in path or "/setting/" in path):
            try:
                length = int(self.headers.get("Content-Length", "0"))
                payload = json.loads(self.rfile.read(length) or b"{}")
                parts = path.split("/")
                plugin_id, kind, name = parts[2], parts[3], parts[4]
                if kind == "secret" and len(parts) > 5 and parts[5] == "clear":
                    self._respond(200, self.bridge.call(self.bridge.plugin_clear_secret(plugin_id, name), timeout=30))
                    return
                if kind == "secret":
                    result = self.bridge.plugin_secret(plugin_id, name, str(payload.get("value", "")))
                else:
                    result = self.bridge.plugin_setting(plugin_id, name, str(payload.get("value", "")))
                self._respond(200, self.bridge.call(result, timeout=30))
            except Exception as error:
                self._respond(409, {"error": str(error) or type(error).__name__})
            return
        if path.startswith("/network/"):
            try:
                length = int(self.headers.get("Content-Length", "0"))
                payload = json.loads(self.rfile.read(length) or b"{}")
                action = path.removeprefix("/network/")
                self._respond(200, self.bridge.call(self.bridge.network_mutation(action, payload), timeout=20))
            except Exception as error:
                self._respond(409, {"error": str(error) or type(error).__name__})
            return
        if path == "/bluetooth/action":
            try:
                length = int(self.headers.get("Content-Length", "0"))
                payload = json.loads(self.rfile.read(length) or b"{}")
                result = self.bridge.call(self.bridge.bluetooth_action(
                    str(payload.get("action", "")), str(payload.get("path", ""))), timeout=120)
                self._respond(200, result)
            except Exception as error:
                self._respond(409, {"error": str(error) or type(error).__name__})
            return
        if path.startswith("/audio/"):
            try:
                length = int(self.headers.get("Content-Length", "0"))
                payload = json.loads(self.rfile.read(length) or b"{}")
                action = path.removeprefix("/audio/")
                self._respond(200, self.bridge.call(self.bridge.audio_mutation(action, payload), timeout=10))
            except Exception as error:
                self._respond(409, {"error": str(error) or type(error).__name__})
            return
        if path.startswith("/storage/"):
            try:
                length = int(self.headers.get("Content-Length", "0"))
                payload = json.loads(self.rfile.read(length) or b"{}")
                action = path.removeprefix("/storage/")
                self._respond(200, self.bridge.call(self.bridge.storage_mutation(action, payload), timeout=20))
            except Exception as error:
                self._respond(409, {"error": str(error) or type(error).__name__})
            return
        if path == "/display/apply":
            try:
                length = int(self.headers.get("Content-Length", "0"))
                payload = json.loads(self.rfile.read(length) or b"{}")
                self._respond(200, self.bridge.call(self.bridge.display_apply(payload), timeout=20))
            except Exception as error:
                self._respond(409, {"error": str(error) or type(error).__name__})
            return
        if path.startswith("/controller/"):
            try:
                length = int(self.headers.get("Content-Length", "0"))
                payload = json.loads(self.rfile.read(length) or b"{}")
                action = path.removeprefix("/controller/")
                self._respond(200, self.bridge.call(self.bridge.controller_mutation(action, payload), timeout=10))
            except Exception as error:
                self._respond(409, {"error": str(error) or type(error).__name__})
            return
        if path in {"/keyboard/show", "/keyboard/hide"}:
            try:
                action = path.rsplit("/", 1)[1]
                self._respond(200, self.bridge.call(self.bridge.keyboard(action)))
            except Exception as error:
                self._respond(409, {"error": str(error) or type(error).__name__})
            return
        if path == "/refresh":
            try:
                stages = [item for item in parse_qs(urlparse(self.path).query).get("stage", []) if item]
                operation = (self.bridge.refresh_catalogue_stages(stages)
                             if stages else self.bridge.refresh_catalogue())
                self._respond(200, self.bridge.call(operation, timeout=None))
            except Exception as error:  # pragma: no cover - live IPC failure path
                self._respond(409, {"error": str(error) or type(error).__name__})
            return
        if path.startswith("/metadata/"):
            try:
                game_id = unquote(path.split("/", 3)[3])
                length = int(self.headers.get("Content-Length", "0"))
                payload = json.loads(self.rfile.read(length) or b"{}")
                if path.startswith("/metadata/title/clear/"):
                    game_id = unquote(path.removeprefix("/metadata/title/clear/"))
                    self.bridge.call(self.bridge.clear_title_override(game_id))
                elif path.startswith("/metadata/match/revert/"):
                    game_id = unquote(path.removeprefix("/metadata/match/revert/"))
                    self.bridge.call(self.bridge.revert_metadata_match(game_id), timeout=90)
                elif path.startswith("/metadata/match/"):
                    self.bridge.call(self.bridge.set_metadata_match(game_id, payload), timeout=60)
                elif path.startswith("/metadata/title/"):
                    self.bridge.call(self.bridge.set_title_override(game_id, str(payload.get("title", ""))))
                elif path.startswith("/metadata/artwork/"):
                    self.bridge.call(self.bridge.set_artwork_suppressed(game_id, bool(payload.get("suppressed", False))))
                else:
                    self._respond(404, {"error": "not found"})
                    return
                self._respond(200, {"ok": True})
            except Exception as error:  # pragma: no cover - live IPC failure path
                self._respond(409, {"error": str(error) or type(error).__name__})
            return
        if path.startswith("/uninstall/"):
            try:
                game_id = unquote(path.removeprefix("/uninstall/"))
                self._respond(200, self.bridge.call(self.bridge.uninstall_game(game_id), timeout=20))
            except Exception as error:
                self._respond(409, {"error": str(error) or type(error).__name__})
            return
        if path == "/cancel":
            try:
                self._respond(200, self.bridge.call(self.bridge.cancel_launch(), timeout=10))
            except Exception as error:
                self._respond(409, {"error": str(error) or type(error).__name__})
            return
        if path.startswith("/acquisition/retry/"):
            try:
                job_id = unquote(path.removeprefix("/acquisition/retry/"))
                self._respond(200, self.bridge.call(self.bridge.retry_acquisition(job_id), timeout=20))
            except Exception as error:
                self._respond(409, {"error": str(error) or type(error).__name__})
            return
        if path.startswith("/acquisition/clear/"):
            try:
                job_id = unquote(path.removeprefix("/acquisition/clear/"))
                self._respond(200, self.bridge.call(self.bridge.clear_acquisition(job_id), timeout=20))
            except Exception as error:
                self._respond(409, {"error": str(error) or type(error).__name__})
            return
        if path.startswith("/acquisition/"):
            try:
                parts = path.split("/")
                action, job_id = parts[2], unquote("/".join(parts[3:]))
                self._respond(200, self.bridge.call(
                    self.bridge.acquisition_action(action, job_id), timeout=20))
            except Exception as error:
                self._respond(409, {"error": str(error) or type(error).__name__})
            return
        if path == "/surface/clear":
            try:
                self._respond(200, self.bridge.call(self.bridge.clear_requested_surface()))
            except Exception as error:
                self._respond(409, {"error": str(error) or type(error).__name__})
            return
        if path == "/reset":
            try:
                self._respond(200, self.bridge.call(self.bridge.reset_mudos(), timeout=5))
            except Exception as error:  # pragma: no cover - session restart may close IPC
                self._respond(202, {"status": "reset-requested", "error": str(error)})
            return
        if path.startswith("/mudos/"):
            try:
                action = path.removeprefix("/mudos/")
                if action == "provider":
                    length = int(self.headers.get("Content-Length", "0"))
                    payload = json.loads(self.rfile.read(length) or b"{}")
                    result = self.bridge.launch_provider(str(payload.get("id", "")))
                elif action in {"reboot", "shutdown"}:
                    result = self.bridge.system_power(action)
                elif action == "refresh-metadata":
                    result = self.bridge.refresh_catalogue_stages(["metadata"])
                elif action == "refresh-library":
                    # Native PC storefront installs are projected by their
                    # provider-owned marker/catalogue sources, not filesystem
                    # discovery; include them in an explicit Library refresh.
                    result = self.bridge.refresh_catalogue_stages(
                        ["steam", "gog", "epic", "local", "romm", "artwork"])
                elif action == "refresh-downloads":
                    result = self.bridge.refresh_catalogue_stages(["steam", "romm"])
                else:
                    raise ValueError("unknown Mudos action")
                self._respond(200, self.bridge.call(result, timeout=None))
            except Exception as error:
                self._respond(409, {"error": str(error) or type(error).__name__})
            return
        if path.startswith("/input-mode/"):
            try:
                mode = path.removeprefix("/input-mode/")
                self._respond(200, self.bridge.call(self.bridge.set_input_mode(mode)))
            except Exception as error:
                self._respond(409, {"error": str(error)})
            return
        if path == "/browser-surface/active":
            try:
                length = int(self.headers.get("Content-Length", "0"))
                payload = json.loads(self.rfile.read(length) or b"{}")
                self._respond(200, self.bridge.call(
                    self.bridge.set_browser_surface(bool(payload.get("active", False)))))
            except Exception as error:
                self._respond(409, {"error": str(error)})
            return
        if path == "/browser-handoff":
            try:
                length = int(self.headers.get("Content-Length", "0"))
                payload = json.loads(self.rfile.read(length) or b"{}")
                result = self.bridge.call(self.bridge.browser_handoff(
                    str(payload.get("uri", "")), str(payload.get("source_origin", ""))), timeout=25)
                self._respond(202, result)
            except Exception as error:
                self._respond(409, {"error": str(error) or type(error).__name__})
            return
        if path == "/store/steam":
            try:
                self._respond(200, self.bridge.call(self.bridge.open_steam_store(), timeout=20))
            except Exception as error:  # pragma: no cover - live IPC failure path
                self._respond(409, {"error": str(error) or type(error).__name__})
            return
        if path.startswith("/install/"):
            try:
                game_id = unquote(path.removeprefix("/install/"))
                self.bridge.launch_logs.start(game_id)
                result = self.bridge.call(self.bridge.install_game(game_id), timeout=20)
                self._respond(200, result)
            except Exception as error:
                self.bridge.launch_logs.note("Lulu", f"HTTP install failed: {error}")
                self._respond(409, {"error": str(error) or type(error).__name__})
            return
        if not path.startswith("/launch/"):
            self._respond(404, {"error": "not found"})
            return
        try:
            game_id = unquote(path.removeprefix("/launch/"))
            LOGGER.info("http launch game_id=%s", game_id)
            self.bridge.launch_logs.start(game_id)
            timeout = None if game_id.startswith("steam:") else 15
            if game_id.startswith("epic:"):
                timeout = 125
            result = self.bridge.call(
                self.bridge.launch_game(game_id),
                timeout=timeout,
            )
            self._respond(200, result)
        except Exception as error:  # pragma: no cover - live IPC failure path
            self.bridge.launch_logs.note("Lulu", f"HTTP launch failed: {error}")
            self._respond(409, {"error": str(error) or type(error).__name__})

    def log_message(self, *_args: object) -> None:
        return


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    bus = await MessageBus(bus_type=BusType.SESSION).connect()
    try:
        introspections = await introspect_lulu_services(bus)
    except Exception:
        LOGGER.exception("required Lulu D-Bus services are not ready; refusing to launch shell")
        bus.disconnect()
        raise
    proxy = bus.get_proxy_object(
        "org.lulu.Consoled", "/org/lulu/Console", introspections["consoled"]
    )
    consoled = proxy.get_interface("org.lulu.Console")
    session_proxy = bus.get_proxy_object(
        "org.lulu.ConsoleSessiond", "/org/lulu/ConsoleSession", introspections["sessiond"]
    )
    sessiond = session_proxy.get_interface("org.lulu.ConsoleSession")
    acquisition_proxy = bus.get_proxy_object(
        "org.lulu.Acquisitiond", "/org/lulu/Acquisition", introspections["acquisitiond"]
    )
    acquisitiond = acquisition_proxy.get_interface("org.lulu.Acquisition")
    loop = asyncio.get_running_loop()
    bridge = ConsoleUiBridge(loop, consoled, sessiond, acquisitiond)
    ApiHandler.bridge = bridge
    server = ThreadingHTTPServer(("127.0.0.1", 38123), ApiHandler)
    Thread(target=server.serve_forever, daemon=True).start()

    environment = os.environ.copy()
    settings = SettingsStore(PATHS.config_root / "settings.sqlite3")
    environment["LULU_LAUNCH_OVERLAY_ENABLED"] = (
        "true" if settings.get("launch_overlay_enabled") else "false"
    )
    qml = os.environ.get("LULU_UI_FILE", "/opt/lulu/ui/ConsoleShell.qml")
    shell = os.environ.get("LULU_SHELL_EXECUTABLE", "/opt/lulu/bin/lulu-shell")
    process = await asyncio.create_subprocess_exec(shell, qml, env=environment)
    marker = Path(os.environ.get("LULU_SHELL_PID_FILE", "/run/user/958/mudos-shell.pid"))
    temporary_marker = marker.with_name(f".{marker.name}.{os.getpid()}")
    temporary_marker.write_text(str(process.pid))
    os.replace(temporary_marker, marker)
    try:
        await process.wait()
    finally:
        marker.unlink(missing_ok=True)
    server.shutdown()
    bus.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
