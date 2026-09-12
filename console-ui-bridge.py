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

from dbus_next import BusType
from dbus_next.aio import MessageBus


class ConsoleUiBridge:
    def __init__(self, loop: asyncio.AbstractEventLoop, consoled: object, sessiond: object) -> None:
        self.loop = loop
        self.consoled = consoled
        self.sessiond = sessiond
        self.launch_logs = LaunchLogCapture()

    def call(self, operation: asyncio.Future, timeout: float | None = 15) -> object:
        return asyncio.run_coroutine_threadsafe(operation, self.loop).result(timeout=timeout)

    async def list_games(self, scope: str) -> list[dict[str, object]]:
        rows = await self.consoled.call_list_games(scope)
        return [{key: value.value for key, value in row.items()} for row in rows]

    async def list_platforms(self) -> list[dict[str, object]]:
        rows = await self.consoled.call_list_platform_categories()
        return [{key: value.value for key, value in row.items()} for row in rows]

    def launch_log(self) -> dict[str, object]:
        return self.launch_logs.snapshot()

    async def launch_game(self, game_id: str) -> dict[str, object]:
        LOGGER.info("launch request game_id=%s", game_id)
        appid = game_id.removeprefix("steam:")
        self.launch_logs.note("Lulu", f"HTTP launch request started game_id={game_id}")
        token = await self.consoled.call_launch_game(game_id, 15000)
        self.launch_logs.note("Lulu", f"launch boundary reached game_id={game_id} appid={appid}")
        if game_id.startswith("steam:"):
            self.launch_logs.note("Steam", f"steam://rungameid/{appid}")
        LOGGER.info("launch accepted game_id=%s token=%s", game_id, token)
        return {
            "token": token,
            "navigation_only": token.startswith("steam://nav/games/details/"),
        }

    async def state(self) -> dict[str, object]:
        return json.loads(await self.sessiond.call_get_state())

    async def open_steam_store(self) -> dict[str, str]:
        token = await self.sessiond.call_request_steam_store(15000)
        return {"token": token}

    async def list_system_settings(self, category: str) -> list[dict[str, object]]:
        rows = await self.consoled.call_list_system_settings(category)
        return [{key: value.value for key, value in row.items()} for row in rows]


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
        scope = parse_qs(urlparse(self.path).query).get("scope", ["recent"])[0]
        try:
            self._respond(200, self.bridge.call(self.bridge.list_games(scope)))
        except Exception as error:  # pragma: no cover - live IPC failure path
            self._respond(503, {"error": str(error)})

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        if path == "/store/steam":
            try:
                self._respond(200, self.bridge.call(self.bridge.open_steam_store(), timeout=20))
            except Exception as error:  # pragma: no cover - live IPC failure path
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
            token = self.bridge.call(self.bridge.launch_game(game_id), timeout=timeout)
            self._respond(200, {"token": token})
        except Exception as error:  # pragma: no cover - live IPC failure path
            self.bridge.launch_logs.note("Lulu", f"HTTP launch failed: {error}")
            self._respond(409, {"error": str(error) or type(error).__name__})

    def log_message(self, *_args: object) -> None:
        return


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    bus = await MessageBus(bus_type=BusType.SESSION).connect()
    introspection = await bus.introspect("org.lulu.Consoled", "/org/lulu/Console")
    proxy = bus.get_proxy_object("org.lulu.Consoled", "/org/lulu/Console", introspection)
    consoled = proxy.get_interface("org.lulu.Console")
    session_introspection = await bus.introspect(
        "org.lulu.ConsoleSessiond", "/org/lulu/ConsoleSession"
    )
    session_proxy = bus.get_proxy_object(
        "org.lulu.ConsoleSessiond", "/org/lulu/ConsoleSession", session_introspection
    )
    sessiond = session_proxy.get_interface("org.lulu.ConsoleSession")
    await consoled.call_refresh()

    loop = asyncio.get_running_loop()
    bridge = ConsoleUiBridge(loop, consoled, sessiond)
    ApiHandler.bridge = bridge
    server = ThreadingHTTPServer(("127.0.0.1", 38123), ApiHandler)
    Thread(target=server.serve_forever, daemon=True).start()

    environment = os.environ.copy()
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
