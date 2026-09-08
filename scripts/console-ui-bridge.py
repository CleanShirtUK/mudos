#!/usr/bin/env python3
"""Expose consoled's local D-Bus API to the QML shell."""

import asyncio
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from urllib.parse import parse_qs, unquote, urlparse

from dbus_next import BusType
from dbus_next.aio import MessageBus


class ConsoleUiBridge:
    def __init__(self, loop: asyncio.AbstractEventLoop, consoled: object) -> None:
        self.loop = loop
        self.consoled = consoled

    def call(self, operation: asyncio.Future, timeout: float = 15) -> object:
        return asyncio.run_coroutine_threadsafe(operation, self.loop).result(timeout=timeout)

    async def list_games(self, scope: str) -> list[dict[str, object]]:
        rows = await self.consoled.call_list_games(scope)
        return [{key: value.value for key, value in row.items()} for row in rows]

    async def launch_game(self, game_id: str) -> str:
        return await self.consoled.call_launch_game(game_id, 15000)


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
        scope = parse_qs(urlparse(self.path).query).get("scope", ["recent"])[0]
        try:
            self._respond(200, self.bridge.call(self.bridge.list_games(scope)))
        except Exception as error:  # pragma: no cover - live IPC failure path
            self._respond(503, {"error": str(error)})

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        if not path.startswith("/launch/"):
            self._respond(404, {"error": "not found"})
            return
        try:
            game_id = unquote(path.removeprefix("/launch/"))
            token = self.bridge.call(self.bridge.launch_game(game_id), timeout=330)
            self._respond(200, {"token": token})
        except Exception as error:  # pragma: no cover - live IPC failure path
            self._respond(409, {"error": str(error) or type(error).__name__})

    def log_message(self, *_args: object) -> None:
        return


async def main() -> None:
    bus = await MessageBus(bus_type=BusType.SESSION).connect()
    introspection = await bus.introspect("org.lulu.Consoled", "/org/lulu/Console")
    proxy = bus.get_proxy_object("org.lulu.Consoled", "/org/lulu/Console", introspection)
    consoled = proxy.get_interface("org.lulu.Console")
    await consoled.call_refresh()

    loop = asyncio.get_running_loop()
    bridge = ConsoleUiBridge(loop, consoled)
    ApiHandler.bridge = bridge
    server = ThreadingHTTPServer(("127.0.0.1", 38123), ApiHandler)
    Thread(target=server.serve_forever, daemon=True).start()

    environment = os.environ.copy()
    qml = os.environ.get("LULU_UI_FILE", "/opt/lulu/ui/ConsoleShell.qml")
    process = await asyncio.create_subprocess_exec("qmlscene6", qml, env=environment)
    await process.wait()
    server.shutdown()
    bus.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
