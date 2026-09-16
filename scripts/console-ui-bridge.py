#!/usr/bin/env python3
"""Expose consoled's local D-Bus API to the QML shell."""

import asyncio
from collections import deque
import ctypes
from datetime import datetime
import json
import logging
import os
from pathlib import Path
import re
import select
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Lock, Thread
from urllib.parse import parse_qs, unquote, urlparse


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
            word in lowered for word in ("launch", "process", "proton", "cuphead", "error", "failed")
        )

    def _append(self, source: str, line: str) -> None:
        timestamp = line[:22] if re.match(r"^\[?\d{4}-\d{2}-\d{2} ", line) else ""
        if not timestamp:
            timestamp = datetime.now().strftime("%H:%M:%S")
        self._lines.append(f"{timestamp} [{source}] {line}")

from dbus_next import BusType, Variant
from dbus_next.aio import MessageBus
from dbus_next.errors import DBusError

from lulu.paths import PATHS
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

    def launch_log(self) -> dict[str, object]:
        return self.launch_logs.snapshot()

    async def launch_game(self, game_id: str) -> dict[str, object]:
        LOGGER.info("launch request game_id=%s", game_id)
        appid = game_id.removeprefix("steam:")
        self.launch_logs.note("Lulu", f"HTTP launch request started game_id={game_id}")
        if game_id.startswith("steam:"):
            token = normalize_launch_token(await self.sessiond.call_request_steam_launch(appid, 15000))
            self.launch_logs.note("Lulu", f"session launch boundary reached game_id={game_id} appid={appid} token={token}")
            self.launch_logs.note("Steam", f"steam://rungameid/{appid}")
        else:
            token = await self.consoled.call_launch_game(game_id, 15000)
            self.local_token = token
            self.launch_logs.note("Lulu", f"launch boundary reached game_id={game_id} appid={appid}")
        LOGGER.info("launch accepted game_id=%s token=%s", game_id, token)
        return {
            "token": token,
            "navigation_only": token.startswith("steam://nav/games/details/"),
        }

    async def state(self) -> dict[str, object]:
        return json.loads(await self.sessiond.call_get_state())

    async def acquisition(self) -> dict[str, object]:
        if self.acquisitiond is None:
            return {"jobs": [], "activeDownloadCount": 0}
        return json.loads(await self.acquisitiond.call_get_snapshot())

    async def open_steam_store(self) -> dict[str, str]:
        self.launch_logs.start("steam-store")
        self.launch_logs.note("Lulu", "Steam Store launch requested")
        token = await self.sessiond.call_request_steam_store(15000)
        return {"token": token}

    async def install_game(self, game_id: str) -> dict[str, str]:
        if self.acquisitiond is None:
            raise RuntimeError("acquisition service is unavailable")
        rows = await self.list_available_games("romm")
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
        else:
            raise ValueError("game provider is not acquirable")
        job_id = await self.acquisitiond.call_submit_job(provider, content_identity, title)
        asyncio.create_task(self._refresh_after_acquisition(job_id, provider))
        self.launch_logs.note("Lulu", f"{provider} acquisition submitted identity={content_identity} job_id={job_id}")
        return {"token": job_id}

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
                    stages = ["steam"] if provider == "steam" else ["local"]
                    await self.consoled.call_refresh_stages(stages)
                    return
                await asyncio.sleep(1)
        except Exception:
            LOGGER.exception("Steam acquisition catalogue refresh failed job_id=%s", job_id)

    async def cancel_launch(self) -> dict[str, str]:
        self.launch_logs.note_cancellation()
        if self.local_token is not None:
            await self.consoled.call_cancel_local_launch()
            self.local_token = None
        else:
            if hasattr(self.sessiond, "call_get_state"):
                state = await self.state()
                primary_id = str(state.get("primary_id") or "")
                if state.get("lifecycle") == "game" and primary_id.startswith("steam-install:"):
                    await self.sessiond.call_quit_delegated()
                else:
                    await self.sessiond.call_cancel_launch()
            else:
                await self.sessiond.call_cancel_launch()
        return {"status": "cancelled"}

    async def reset_mudos(self) -> dict[str, str]:
        result = await self.sessiond.call_reset_mudos()
        return {"status": result}

    async def list_system_settings(self, category: str) -> list[dict[str, object]]:
        rows = await self.consoled.call_list_system_settings(category)
        return [{key: value.value for key, value in row.items()} for row in rows]

    async def search_metadata(self, game_id: str, query: str) -> list[dict[str, object]]:
        rows = await self.consoled.call_search_metadata(game_id, query)
        return [{key: value.value for key, value in row.items()} for row in rows]

    async def set_metadata_match(self, game_id: str, payload: dict[str, object]) -> None:
        await self.consoled.call_set_metadata_match(
            game_id, str(payload.get("provider", "steamgriddb")),
            str(payload.get("metadata_game_id", "")), str(payload.get("canonical_title", "")),
        )

    async def set_title_override(self, game_id: str, title: str) -> None:
        await self.consoled.call_set_title_override(game_id, title)

    async def clear_title_override(self, game_id: str) -> None:
        await self.consoled.call_clear_title_override(game_id)

    async def set_artwork_suppressed(self, game_id: str, suppressed: bool) -> None:
        if suppressed:
            await self.consoled.call_suppress_artwork(game_id)
        else:
            await self.consoled.call_restore_artwork(game_id)


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
        if urlparse(self.path).path == "/state":
            try:
                self._respond(200, self.bridge.call(self.bridge.state()))
            except Exception as error:  # pragma: no cover - live IPC failure path
                self._respond(503, {"error": str(error)})
            return
        if urlparse(self.path).path == "/launch-log":
            self._respond(200, self.bridge.launch_log())
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
        if urlparse(self.path).path == "/platforms":
            try:
                self._respond(200, self.bridge.call(self.bridge.list_platforms()))
            except Exception as error:  # pragma: no cover - live IPC failure path
                self._respond(503, {"error": str(error)})
            return
        if urlparse(self.path).path == "/available":
            provider = parse_qs(urlparse(self.path).query).get("provider", ["romm"])[0]
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
                self._respond(200, self.bridge.call(self.bridge.search_metadata(game_id, search)))
            except Exception as error:  # pragma: no cover - live IPC failure path
                self._respond(503, {"error": str(error)})
            return
        scope = parse_qs(urlparse(self.path).query).get("scope", ["recent"])[0]
        try:
            self._respond(200, self.bridge.call(self.bridge.list_games(scope)))
        except Exception as error:  # pragma: no cover - live IPC failure path
            self._respond(503, {"error": str(error)})

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        if path == "/ui-refresh":
            try:
                group = parse_qs(urlparse(self.path).query).get("group", ["all"])[0]
                Path("/tmp/lulu-qml-refresh-request").write_text(group, encoding="ascii")
                self._respond(200, {"status": "requested", "group": group})
            except OSError as error:
                self._respond(409, {"error": str(error)})
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
                elif path.startswith("/metadata/match/"):
                    self.bridge.call(self.bridge.set_metadata_match(game_id, payload))
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
        if path == "/cancel":
            try:
                self._respond(200, self.bridge.call(self.bridge.cancel_launch(), timeout=10))
            except Exception as error:
                self._respond(409, {"error": str(error) or type(error).__name__})
            return
        if path == "/reset":
            try:
                self._respond(200, self.bridge.call(self.bridge.reset_mudos(), timeout=5))
            except Exception as error:  # pragma: no cover - session restart may close IPC
                self._respond(202, {"status": "reset-requested", "error": str(error)})
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


async def wait_for_dbus_service(bus: object, name: str, path: str,
                                timeout: float = 5.0, interval: float = 0.1) -> object:
    """Wait for a service name and object path without masking daemon failure."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while True:
        try:
            return await bus.introspect(name, path)
        except DBusError as error:
            if error.type not in {
                "org.freedesktop.DBus.Error.ServiceUnknown",
                "org.freedesktop.DBus.Error.NameHasNoOwner",
            }:
                raise
            remaining = deadline - loop.time()
            if remaining <= 0:
                raise RuntimeError(
                    f"D-Bus service unavailable after {timeout:.1f}s: {name}{path}"
                ) from error
            await asyncio.sleep(min(interval, remaining))


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    bus = await MessageBus(bus_type=BusType.SESSION).connect()
    introspection = await wait_for_dbus_service(bus, "org.lulu.Consoled", "/org/lulu/Console")
    proxy = bus.get_proxy_object("org.lulu.Consoled", "/org/lulu/Console", introspection)
    consoled = proxy.get_interface("org.lulu.Console")
    session_introspection = await wait_for_dbus_service(
        bus, "org.lulu.ConsoleSessiond", "/org/lulu/ConsoleSession"
    )
    session_proxy = bus.get_proxy_object(
        "org.lulu.ConsoleSessiond", "/org/lulu/ConsoleSession", session_introspection
    )
    sessiond = session_proxy.get_interface("org.lulu.ConsoleSession")
    acquisition_introspection = await wait_for_dbus_service(
        bus, "org.lulu.Acquisitiond", "/org/lulu/Acquisition"
    )
    acquisition_proxy = bus.get_proxy_object(
        "org.lulu.Acquisitiond", "/org/lulu/Acquisition", acquisition_introspection
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
