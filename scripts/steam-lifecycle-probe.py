#!/usr/bin/env python3
"""Observe Steam/game Xwayland surfaces without owning or changing lifecycle."""

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from datetime import datetime


INTEGER = re.compile(r"(?:0x[0-9a-fA-F]+|\d+)")


def emit(event: str, **fields: object) -> None:
    stamp = datetime.now().astimezone().isoformat(timespec="milliseconds")
    values = " ".join(
        f"{key}={json.dumps(value, ensure_ascii=True, separators=(',', ':'))}"
        for key, value in fields.items()
    )
    print(f"{stamp} {event}" + (f" {values}" if values else ""), flush=True)


def xprop(display: str, *args: str) -> str:
    environment = os.environ.copy()
    environment["DISPLAY"] = display
    completed = subprocess.run(
        ["xprop", *args], capture_output=True, text=True, env=environment, check=False
    )
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or f"xprop failed ({completed.returncode})")
    return completed.stdout


def numbers(value: str) -> list[int]:
    return [int(item, 0) for item in INTEGER.findall(value)]


def property_value(output: str, name: str) -> str | None:
    for line in output.splitlines():
        if line.startswith(f"{name}(") or line.startswith(f"{name} ="):
            return line.split("=", 1)[1].strip()
    return None


def clean_value(value: str | None) -> str | int | None:
    if value is None:
        return None
    value = value.strip()
    if value.startswith('"'):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value.strip('"')
    parsed = numbers(value)
    return parsed[0] if parsed else value


def root_snapshot(display: str) -> tuple[set[int], int | None, int | None]:
    output = xprop(
        display,
        "-root",
        "_NET_CLIENT_LIST",
        "GAMESCOPE_FOCUSABLE_WINDOWS",
        "_NET_ACTIVE_WINDOW",
        "GAMESCOPECTRL_BASELAYER_WINDOW",
    )
    clients: set[int] = set()
    focusable: list[int] = []
    active = None
    base = None
    for line in output.splitlines():
        if line.startswith("_NET_CLIENT_LIST"):
            clients.update(numbers(line.split("=", 1)[-1]))
        elif line.startswith("GAMESCOPE_FOCUSABLE_WINDOWS"):
            focusable = numbers(line.split("=", 1)[-1])
        elif line.startswith("_NET_ACTIVE_WINDOW"):
            values = numbers(line.split("=", 1)[-1])
            active = values[0] if values else None
        elif line.startswith("GAMESCOPECTRL_BASELAYER_WINDOW"):
            values = numbers(line.split("=", 1)[-1])
            base = values[0] if values else None
    # Gamescope exposes (window, app id, pid) triples even when the EWMH list
    # is incomplete for rootless Xwayland clients.
    clients.update(focusable[index] for index in range(0, len(focusable) - 2, 3))
    return clients, active, base


def window_snapshot(display: str, window_id: int) -> dict[str, object]:
    output = xprop(
        display,
        "-id",
        str(window_id),
        "STEAM_GAME",
        "_NET_WM_NAME",
        "WM_NAME",
        "_NET_WM_PID",
        "WM_CLASS",
    )
    properties = {
        "steam_game": clean_value(property_value(output, "STEAM_GAME")),
        "title": clean_value(property_value(output, "_NET_WM_NAME"))
        or clean_value(property_value(output, "WM_NAME")),
        "pid": clean_value(property_value(output, "_NET_WM_PID")),
        "wm_class": clean_value(property_value(output, "WM_CLASS")),
    }
    return properties


def process_snapshot() -> dict[int, tuple[str, ...]]:
    result: dict[int, tuple[str, ...]] = {}
    for entry in Path("/proc").iterdir():
        if not entry.name.isdecimal():
            continue
        try:
            argv = tuple(item.decode(errors="replace") for item in (entry / "cmdline").read_bytes().split(b"\0") if item)
            executable = os.path.basename(os.path.realpath(entry / "exe")).lower()
        except (FileNotFoundError, PermissionError, OSError):
            continue
        if executable in {"steam", "steamwebhelper"} or any("steam://" in item for item in argv):
            result[int(entry.name)] = argv
    return result


def observe(display: str, appid: str, interval: float) -> None:
    expected = int(appid)
    emit("launch-request", appid=appid, display=display, observation_only=True)
    previous_windows: dict[int, dict[str, object]] = {}
    previous_processes: dict[int, tuple[str, ...]] = {}
    previous_active: int | None = None
    previous_base: int | None = None
    game_windows: set[int] = set()
    first = True
    while True:
        windows, active, base = root_snapshot(display)
        for window_id in sorted(windows):
            try:
                metadata = window_snapshot(display, window_id)
            except RuntimeError:
                continue
            if window_id not in previous_windows:
                emit("surface-created", id=window_id, initial=not first, **metadata)
            elif metadata != previous_windows[window_id]:
                emit("surface-metadata", id=window_id, **metadata)
            previous_windows[window_id] = metadata

        for window_id in sorted(set(previous_windows) - windows):
            metadata = previous_windows.pop(window_id)
            emit("surface-destroyed", id=window_id, **metadata)

        current_game_windows = {
            window_id
            for window_id, metadata in previous_windows.items()
            if str(metadata.get("steam_game")) == appid
        }
        if current_game_windows and not game_windows:
            emit("game-surface-seen", appid=appid, surfaces=sorted(current_game_windows))
        elif game_windows and not current_game_windows:
            emit("game-surfaces-zero", appid=appid)
        game_windows = current_game_windows

        if active != previous_active:
            emit("focus-changed", active_window=active)
            previous_active = active
        if base != previous_base:
            emit("presentation-changed", base_layer_window=base)
            previous_base = base

        processes = process_snapshot()
        for pid, argv in processes.items():
            if pid not in previous_processes or argv != previous_processes[pid]:
                command = " ".join(argv)
                if "-applaunch" in argv or "steam://" in command:
                    emit("steam-command", pid=pid, argv=list(argv))
        previous_processes = processes
        first = False
        time.sleep(interval)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--appid", default="268910", help="expected Steam AppID (default: Cuphead)")
    parser.add_argument("--display", default=os.environ.get("DISPLAY", ":0"))
    parser.add_argument("--interval", type=float, default=0.1)
    args = parser.parse_args()
    if not args.appid.isdecimal() or int(args.appid) < 1:
        parser.error("--appid must be a positive integer")
    if args.interval <= 0:
        parser.error("--interval must be positive")
    try:
        observe(args.display, args.appid, args.interval)
    except KeyboardInterrupt:
        emit("probe-stopped", reason="interrupt")
    except RuntimeError as error:
        emit("probe-error", error=str(error))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
