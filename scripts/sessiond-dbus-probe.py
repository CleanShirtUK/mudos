#!/usr/bin/env python
"""Deterministic real-process probe for console-sessiond over D-Bus."""

import asyncio
import json
import os
from pathlib import Path
import signal
import sys

from dbus_next import DBusError
from dbus_next.aio import MessageBus


PYTHON = sys.executable


async def wait_for_result(session, expected_outcome: str, timeout: float = 3.0) -> dict:
    async def poll() -> dict:
        while True:
            state = json.loads(await session.call_get_state())
            result = state.get("last_result")
            if state["lifecycle"] == "shell" and result and result["outcome"] == expected_outcome:
                return state
            await asyncio.sleep(0.02)

    return await asyncio.wait_for(poll(), timeout)


async def launch(session, code: str, timeout_ms: int = 1000) -> str:
    return await session.call_request_launch([PYTHON, "-c", code], timeout_ms)


async def main() -> None:
    bus = await MessageBus().connect()
    introspection = await bus.introspect("org.lulu.ConsoleSessiond", "/org/lulu/ConsoleSession")
    proxy = bus.get_proxy_object("org.lulu.ConsoleSessiond", "/org/lulu/ConsoleSession", introspection)
    session = proxy.get_interface("org.lulu.ConsoleSession")

    token = await launch(session, "pass")
    state = await wait_for_result(session, "success")
    assert state["last_result"]["token"] == token
    assert state["last_result"]["exit_code"] == 0
    print("normal exit: PASS")

    await launch(session, "raise SystemExit(7)")
    state = await wait_for_result(session, "failed")
    assert state["last_result"]["exit_code"] == 7
    print("non-zero exit: PASS")

    try:
        await session.call_request_launch(["/lulu/nonexistent-executable"], 1000)
    except DBusError:
        state = json.loads(await session.call_get_state())
        assert state["lifecycle"] == "shell"
        assert state["last_result"]["outcome"] == "start-failed"
        print("start failure: PASS")
    else:
        raise AssertionError("nonexistent executable was accepted")

    token = await launch(session, "import time; time.sleep(5)")
    running_state = json.loads(await session.call_get_state())
    assert running_state["lifecycle"] == "running"
    active = running_state["active_identity"]
    assert active["token"] == token
    try:
        await launch(session, "pass")
    except DBusError:
        print("competing launch: PASS")
    else:
        raise AssertionError("competing launch was accepted")
    os.kill(active["pid"], signal.SIGTERM)
    state = await wait_for_result(session, "failed")
    assert state["last_result"]["signal"] == signal.SIGTERM
    print("unexpected termination: PASS")

    descendant_file = Path("/tmp/lulu-sessiond-descendant.pid")
    descendant_file.unlink(missing_ok=True)
    code = (
        "import pathlib, subprocess; "
        f"p=subprocess.Popen(['/usr/bin/sleep', '30']); pathlib.Path({str(descendant_file)!r}).write_text(str(p.pid))"
    )
    await launch(session, code)
    state = await wait_for_result(session, "success")
    descendant_pid = int(descendant_file.read_text())
    await asyncio.sleep(0.1)
    assert not os.path.exists(f"/proc/{descendant_pid}")
    print("descendant cleanup: PASS")

    for _ in range(3):
        await launch(session, "pass")
        await wait_for_result(session, "success")
    print("repeated cycles: PASS")
    bus.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
