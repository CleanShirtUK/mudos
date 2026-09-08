#!/usr/bin/env python3
"""Expose consoled's local D-Bus API to the QML shell."""

import asyncio
import json
import logging
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from urllib.parse import parse_qs, unquote, urlparse


LOGGER = logging.getLogger("lulu.console-ui-bridge")

from dbus_next import BusType
from dbus_next.aio import MessageBus


class ConsoleUiBridge:
    def __init__(self, loop: asyncio.AbstractEventLoop, consoled: object, sessiond: object) -> None:
        self.loop = loop
        self.consoled = consoled
        self.sessiond = sessiond

    def call(self, operation: asyncio.Future, timeout: float = 15) -> object:
        return asyncio.run_coroutine_threadsafe(operation, self.loop).result(timeout=timeout)

    async def list_games(self, scope: str) -> list[dict[str, object]]:
        rows = await self.consoled.call_list_games(scope)
        return [{key: value.value for key, value in row.items()} for row in rows]

    async def launch_game(self, game_id: str) -> str:
        LOGGER.info("launch request game_id=%s", game_id)
        token = await self.consoled.call_launch_game(game_id, 15000)
        LOGGER.info("launch accepted game_id=%s token=%s", game_id, token)
        return token

    async def state(self) -> dict[str, object]:
        return json.loads(await self.sessiond.call_get_state())


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
            LOGGER.info("http launch game_id=%s", game_id)
            token = self.bridge.call(self.bridge.launch_game(game_id), timeout=15)
            self._respond(200, {"token": token})
        except Exception as error:  # pragma: no cover - live IPC failure path
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
    process = await asyncio.create_subprocess_exec("qmlscene6", qml, env=environment)
    await process.wait()
    server.shutdown()
    bus.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
