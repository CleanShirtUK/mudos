#!/usr/bin/env python3
"""Invoke and retire the same Consoled Steam authentication surface as OOBE.

Run as the appliance user from an authenticated local shell/SSH session:
  python /opt/lulu/scripts/steam-auth-surface.py start
  python /opt/lulu/scripts/steam-auth-surface.py dismiss LAUNCH_TOKEN

This harness does not modify OOBE progress, provider selection, credentials, or
Steam installation state. Dismissal is token-scoped by Consoled.
"""
from __future__ import annotations

import argparse
import json
import os
import pwd
import secrets
import subprocess
import sys


def _busctl(*arguments: str) -> dict[str, object]:
    completed = subprocess.run(
        ["busctl", "--user", "--json=short", "call", "org.lulu.Consoled",
         "/org/lulu/Console", "org.lulu.Console", *arguments],
        stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=90,
        check=False,
    )
    if completed.returncode:
        detail = (completed.stderr or completed.stdout or "Consoled request failed").strip()
        raise RuntimeError(detail[-1000:])
    envelope = json.loads(completed.stdout)
    value = json.loads(envelope["data"][0])
    if not isinstance(value, dict):
        raise RuntimeError("Consoled returned an invalid response")
    return value


def start() -> dict[str, object]:
    authentication = _busctl("GetPluginAuthStatus", "s", "steam")
    if authentication.get("authenticated"):
        return {"status": "authenticated", "authentication": authentication,
                "message": "Steam is already authenticated; no new surface was opened."}
    result = _busctl("BeginPluginAuthenticationTraced", "ss", "steam", secrets.token_hex(6))
    result["authentication"] = authentication
    return result


def dismiss(token: str) -> dict[str, object]:
    if not token or any(character.isspace() for character in token):
        raise ValueError("provide the launch token returned by the start command")
    return _busctl("DismissPluginAuthentication", "ss", "steam", token)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_subparsers(dest="action", required=True)
    actions.add_parser("start", help="open the production Steam auth surface")
    close = actions.add_parser("dismiss", help="retire only the token-owned surface")
    close.add_argument("launch_token")
    args = parser.parse_args(argv)
    try:
        appliance_uid = pwd.getpwnam("lulu").pw_uid
        if os.geteuid() != appliance_uid:
            raise PermissionError("run this harness as the lulu appliance account")
        result = start() if args.action == "start" else dismiss(args.launch_token)
        print(json.dumps(result, sort_keys=True))
        return 0
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        print(f"steam auth surface: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
