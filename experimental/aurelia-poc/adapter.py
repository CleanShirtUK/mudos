#!/usr/bin/env python3
"""Small isolated JSON/CLI bridge prototype for Aurelia; never a production provider."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys


def run(binary: str, config_dir: Path, socket: Path, args: list[str], timeout: int = 3600,
        stream_progress: bool = False):
    env = os.environ.copy()
    env.update({
        "AURELIA_CONFIG_DIR": str(config_dir),
        "AURELIA_DAEMON_SOCKET": str(socket),
        "AURELIA_NO_DAEMON": "1",
        "AURELIA_NO_SPAWN": "1",
    })
    proc = subprocess.Popen([binary, "--json", *args], env=env, text=True,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=1)
    stderr_lines = []
    if stream_progress:
        # Install emits NDJSON progress on stderr. Relay only parsed JSON events;
        # preserve all non-event stderr as diagnostics in the terminal result.
        assert proc.stderr is not None
        for line in proc.stderr:
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                stderr_lines.append(line)
                continue
            if isinstance(event, dict) and event.get("event") == "progress":
                print(json.dumps({"provider": "aurelia", "event": "install-progress",
                                  "payload": event}), flush=True)
            else:
                stderr_lines.append(line)
        stderr = "".join(stderr_lines)
        stdout, remaining_stderr = proc.communicate(timeout=timeout)
        stderr += remaining_stderr or ""
    else:
        stdout, stderr = proc.communicate(timeout=timeout)
    # Install emits its terminal JSON object on stdout.
    value = None
    if stdout.strip():
        try:
            value = json.loads(stdout)
        except json.JSONDecodeError:
            value = {"unparsed_stdout": stdout}
    return proc.returncode, value, stderr


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", required=True, help="Aurelia executable")
    parser.add_argument("--config-dir", required=True, type=Path,
                        help="Isolated Aurelia config directory")
    parser.add_argument("--socket", type=Path, help="Isolated daemon socket (default in config dir)")
    parser.add_argument("--allow-write", action="store_true",
                        help="Acknowledge Steam file/account changes for install operations")
    parser.add_argument("--allow-launch", action="store_true",
                        help="Acknowledge starting/stopping games and possible Steam integration")
    sub = parser.add_subparsers(dest="operation", required=True)
    snapshot = sub.add_parser("snapshot", help="Read-only library/runtime/job/running snapshot")
    snapshot.add_argument("--app-id", type=int, default=40800)
    for name in ("install", "cancel-install", "launch", "stop"):
        op = sub.add_parser(name)
        op.add_argument("app_id", type=int)
    sub.choices["launch"].add_argument("--proton")
    sub.choices["launch"].add_argument("--umu", action="store_true")
    sub.choices["launch"].add_argument("--steam", action="store_true")
    args = parser.parse_args()

    if not args.config_dir.is_dir():
        parser.error("config directory must already exist; create an isolated one first")
    socket = args.socket or (args.config_dir / "daemon.sock")

    if args.operation == "snapshot":
        calls = {
            "libraries": ["libraries"],
            "installed": ["list", "--installed"],
            "availability": ["available", str(args.app_id)],
            "runtimes": ["config", "protons"],
            "install_jobs": ["install", "list"],
            "running": ["running"],
        }
        result = {"provider": "aurelia", "app_id": args.app_id, "phase": "inspection",
                  "cancellable": False, "observations": {}}
        for label, command in calls.items():
            code, value, stderr = run(args.binary, args.config_dir, socket, command, timeout=120)
            result["observations"][label] = {"exit_code": code, "data": value,
                                                "stderr": stderr[-4000:]}
            if code:
                result["error"] = {"code": "aurelia-command-failed", "command": command,
                                   "exit_code": code}
                print(json.dumps(result, indent=2))
                return code
        print(json.dumps(result, indent=2))
        return 0

    if args.operation in {"install", "cancel-install"} and not args.allow_write:
        parser.error(f"{args.operation} requires --allow-write")
    if args.operation in {"launch", "stop"} and not args.allow_launch:
        parser.error(f"{args.operation} requires --allow-launch")

    commands = {
        "install": ["install", str(args.app_id)],
        "cancel-install": ["install", "stop", str(args.app_id)],
        "launch": ["play", str(args.app_id), "--no-update", "--no-script"],
        "stop": ["stop", str(args.app_id)],
    }
    command = commands[args.operation]
    if args.operation == "launch":
        if args.proton:
            command.extend(["--proton", args.proton])
        if args.umu:
            command.append("--umu")
        if args.steam:
            command.append("--steam")
    code, value, stderr = run(args.binary, args.config_dir, socket, command,
                              stream_progress=args.operation == "install")
    output = {"provider": "aurelia", "operation": args.operation, "app_id": args.app_id,
              "exit_code": code, "result": value, "stderr": stderr,
              "error": None if code == 0 else {"code": "aurelia-command-failed",
                                                 "exit_code": code}}
    print(json.dumps(output, indent=2))
    return code


if __name__ == "__main__":
    sys.exit(main())
