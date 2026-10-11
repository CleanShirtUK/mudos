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
        ["busctl", "--user", "--json=short", "--timeout=250s", "call", "org.lulu.Consoled",
         "/org/lulu/Console", "org.lulu.Console", *arguments],
        stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=260,
        check=False,
    )
    if completed.returncode:
        raise RuntimeError("Consoled request failed")
    try:
        envelope = json.loads(completed.stdout)
        value = json.loads(envelope["data"][0])
    except (KeyError, IndexError, TypeError, json.JSONDecodeError) as error:
        raise RuntimeError("Consoled returned an invalid response") from error
    if not isinstance(value, dict):
        raise RuntimeError("Consoled returned an invalid response")
    return value


def start() -> dict[str, object]:
    authentication = _busctl("GetPluginAuthStatus", "s", "steam")
    if authentication.get("authenticated") is True:
        return {"status": "authenticated", "authentication": {"authenticated": True},
                "message": "Steam is already authenticated; no new surface was opened."}
    result = _busctl("BeginPluginAuthenticationTraced", "ss", "steam", secrets.token_hex(6))
    # Only the Consoled-owned launch token is returned because dismiss needs it.
    # Drop all other API fields so an expanded auth response cannot leak.
    returned_status = result.get("status")
    safe_status = returned_status if isinstance(returned_status, str) and returned_status in {
        "surface_requested", "already_authenticated", "unavailable"
    } else "unknown"
    safe: dict[str, object] = {"status": safe_status}
    launch = result.get("launch")
    if isinstance(launch, str) and launch and len(launch) <= 256:
        safe["launch"] = launch
    return safe


def dismiss(token: str) -> dict[str, object]:
    if not token or any(character.isspace() for character in token):
        raise ValueError("provide the launch token returned by the start command")
    result = _busctl("DismissPluginAuthentication", "ss", "steam", token)
    return {"dismissed": result.get("dismissed") is True}


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
