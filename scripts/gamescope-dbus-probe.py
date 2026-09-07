#!/usr/bin/env python
"""Real console-sessiond -> Gamescope -> Wayland payload HOST probe."""

import asyncio
import json

from dbus_next.aio import MessageBus

from lulu.gamescope import GamescopeInvocation


async def wait_for_result(session, expected_outcome: str, timeout: float = 10.0) -> dict:
    async def poll() -> dict:
        while True:
            state = json.loads(await session.call_get_state())
            result = state.get("last_result")
            if state["lifecycle"] == "shell" and result and result["outcome"] == expected_outcome:
                return state
            await asyncio.sleep(0.05)

    return await asyncio.wait_for(poll(), timeout)


async def main() -> None:
    bus = await MessageBus().connect()
    introspection = await bus.introspect("org.lulu.ConsoleSessiond", "/org/lulu/ConsoleSession")
    proxy = bus.get_proxy_object("org.lulu.ConsoleSessiond", "/org/lulu/ConsoleSession", introspection)
    session = proxy.get_interface("org.lulu.ConsoleSession")
    invocation = GamescopeInvocation()
    payload = ["/usr/bin/timeout", "1", "/usr/bin/weston-simple-egl", "-o"]

    for cycle in range(2):
        token = await session.call_request_launch(invocation.argv(payload), 10000)
        running = json.loads(await session.call_get_state())
        assert running["lifecycle"] == "running"
        assert running["active_identity"]["token"] == token
        assert running["active_identity"]["executable"].endswith("/gamescope")
        result = await wait_for_result(session, "success")
        assert result["last_result"]["executable"].endswith("/gamescope")
        print(f"Gamescope visual cycle {cycle + 1}: PASS")

    failed_command = ["gamescope", "--backend", "not-a-backend", "--", "/usr/bin/true"]
    token = await session.call_request_launch(failed_command, 10000)
    result = await wait_for_result(session, "failed")
    assert result["last_result"]["token"] == token
    assert result["last_result"]["exit_code"] != 0
    print("Gamescope startup failure: PASS")

    bus.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
