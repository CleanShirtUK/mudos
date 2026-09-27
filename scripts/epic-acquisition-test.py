#!/usr/bin/env python3
"""Inspect or explicitly submit an owned Epic game through Acquisitiond."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path
import pwd
import re
import subprocess
import sys
import time


async def _run(args) -> int:
    from dbus_next.aio import MessageBus
    from lulu.plugins.epic import EpicAcquisitionExecutor

    bus = await MessageBus().connect()
    consoled_intro = await bus.introspect("org.lulu.Consoled", "/org/lulu/Console")
    consoled_obj = bus.get_proxy_object("org.lulu.Consoled", "/org/lulu/Console", consoled_intro)
    consoled = consoled_obj.get_interface("org.lulu.Console")
    acquisition_intro = await bus.introspect("org.lulu.Acquisitiond", "/org/lulu/Acquisition")
    acquisition_obj = bus.get_proxy_object("org.lulu.Acquisitiond", "/org/lulu/Acquisition", acquisition_intro)
    acquisition = acquisition_obj.get_interface("org.lulu.Acquisition")

    _generation, snapshot_json = await consoled.call_get_catalogue_snapshot()
    games = json.loads(snapshot_json)
    games = [game for game in games if game.get("provider") == "epic"]
    executor = EpicAcquisitionExecutor()
    entries = []
    for game in games:
        app_id = str(game.get("provider_id", ""))
        if not re.fullmatch(r"[A-Za-z0-9._-]+", app_id):
            continue
        identity = f"epic:{app_id}"
        command = executor._command_for_install(identity, executor.install_root)
        try:
            executor.command_builder(identity, executor.install_root)
            supported = True
            blocked_reason = ""
        except Exception as error:
            supported = False
            blocked_reason = str(error)
        entries.append({"provider_id": app_id, "game_id": game.get("game_id"),
                        "title": game.get("title"), "identity": identity,
                        "install_state": game.get("install_state"),
                        "availability_state": game.get("availability_state"),
                        "install_root": str(executor.install_root),
                        "expected_payload_directory": str(executor.install_root / app_id),
                        "command": command, "install_supported_by_legendary": supported,
                        "blocked_reason": blocked_reason})

    if args.submit is None:
        print(json.dumps({"mode": "inspection-only", "games": entries}, sort_keys=True))
        bus.disconnect()
        return 0

    selected = next((game for game in entries if game["provider_id"] == args.submit
                     and game["install_state"] == "available"
                     and game["availability_state"] == "available"), None)
    if selected is None:
        print(json.dumps({"error": "Epic entitlement is not currently installable in Mudos",
                          "provider_id": args.submit}, sort_keys=True))
        bus.disconnect()
        return 3
    if not selected["install_supported_by_legendary"]:
        print(json.dumps({"error": selected["blocked_reason"], "provider_id": args.submit,
                          "command_not_run": True}, sort_keys=True))
        bus.disconnect()
        return 3

    print(json.dumps({"event": "planned", **selected}, sort_keys=True), flush=True)
    job_id = await acquisition.call_submit_job("epic", selected["identity"], str(selected["title"]))
    print(json.dumps({"event": "submitted", "mudos_job_id": job_id,
                      "epic_identity": selected["identity"], "title": selected["title"]}), flush=True)

    deadline = time.monotonic() + args.timeout
    last = None
    while time.monotonic() < deadline:
        snapshot = json.loads(await acquisition.call_get_snapshot())
        job = next((item for item in snapshot.get("jobs", []) if item.get("job_id") == job_id), None)
        if job is None:
            await asyncio.sleep(0.5)
            continue
        state = {"event": "state", "mudos_job_id": job_id, "state": job.get("state"),
                 "stage": job.get("stage"), "progress": job.get("progress"),
                 "provider_state": job.get("provider_state"),
                 "error": job.get("error"), "expected_payload_directory": selected["expected_payload_directory"]}
        signature = json.dumps(state, sort_keys=True)
        if signature != last:
            print(signature, flush=True)
            last = signature
        if job.get("state") in {"completed", "failed", "cancelled"}:
            payload = Path(selected["expected_payload_directory"])
            print(json.dumps({"event": "terminal", "mudos_job_id": job_id,
                              "mudos_state": job.get("state"), "payload_exists": payload.is_dir(),
                              "payload_files": sum(1 for item in payload.rglob("*") if item.is_file())
                              if payload.is_dir() else 0,
                              "marker_exists": (payload / ".mudos-game.json").is_file()}, sort_keys=True), flush=True)
            bus.disconnect()
            return 0 if job.get("state") == "completed" else 1
        await asyncio.sleep(1)
    print(json.dumps({"event": "timeout", "mudos_job_id": job_id,
                      "timeout_seconds": args.timeout}, sort_keys=True), flush=True)
    bus.disconnect()
    return 2


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--submit", metavar="EPIC_APP_ID",
                        help="explicitly submit one currently-owned Epic app ID; omitted means inspection only")
    parser.add_argument("--timeout", type=float, default=14400)
    parser.add_argument("--_as-user", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.timeout <= 0:
        parser.error("--timeout must be positive")

    if os.geteuid() == 0 and not args._as_user:
        user = pwd.getpwnam("lulu")
        env = os.environ.copy()
        env.update({"HOME": user.pw_dir, "USER": "lulu", "LOGNAME": "lulu",
                    "XDG_CONFIG_HOME": f"{user.pw_dir}/.config",
                    "XDG_DATA_HOME": f"{user.pw_dir}/.local/share",
                    "XDG_CACHE_HOME": f"{user.pw_dir}/.cache",
                    "XDG_RUNTIME_DIR": f"/run/user/{user.pw_uid}",
                    "DBUS_SESSION_BUS_ADDRESS": f"unix:path=/run/user/{user.pw_uid}/bus",
                    "PYTHONPATH": "/opt/lulu/current/lib", "LULU_INSTALL_ROOT": "/opt/lulu/current"})
        command = ["runuser", "-u", "lulu", "--", sys.executable,
                   str(Path(__file__).resolve()), "--_as-user", "--timeout", str(args.timeout)]
        if args.submit is not None:
            command.extend(("--submit", args.submit))
        return subprocess.run(command, env=env, check=False).returncode
    return asyncio.run(_run(args))


if __name__ == "__main__":
    raise SystemExit(main())
