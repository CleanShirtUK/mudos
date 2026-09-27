#!/usr/bin/env python3
"""Inspect or exercise Mudos' production Usenet configuration path.

Run as the lulu account:
  python /opt/lulu/scripts/usenet-readiness.py inspect
  python /opt/lulu/scripts/usenet-readiness.py apply-saved
  python /opt/lulu/scripts/usenet-readiness.py reconcile

``apply-saved`` calls AdminApp.save_setup_credentials, the same backend method
used by OOBE. ``reconcile`` additionally invokes Mudos' existing provider
installer only when the managed NZBGet config is absent; it refuses to run the
installer if a config exists, since that installer materializes a fresh file.
No secret values are printed or placed in command arguments.
"""
from __future__ import annotations

import argparse
import grp
import json
import os
from pathlib import Path
import pwd
import subprocess
import sys
import time
from typing import Any

from lulu.admin_web import AdminApp
from lulu.nzbget_admin import CONFIG_PATH


SERVER_FIELDS = (
    "Server1.Active", "Server1.Host", "Server1.Port", "Server1.Encryption",
    "Server1.Username", "Server1.Password", "Server1.Connections",
)
CONTROL_FIELDS = ("ControlUsername", "ControlPassword", "ControlPort")


def _run(command: list[str], *, timeout: float = 5.0) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, stdin=subprocess.DEVNULL, capture_output=True,
                          text=True, timeout=timeout, check=False)


def _unit_state(unit: str) -> dict[str, str]:
    result = _run(["systemctl", "show", unit,
                   "--property=ActiveState,SubState,Result,ExecMainStatus,ExecMainStartTimestamp"])
    values = dict(line.split("=", 1) for line in result.stdout.splitlines() if "=" in line)
    if result.returncode:
        values["query_error_type"] = "SystemctlError"
        values["query_error"] = (result.stderr or "systemctl show failed").strip()[-500:]
    return values


def _config_diagnostics() -> dict[str, object]:
    parent_exists = CONFIG_PATH.parent.is_dir()
    if not CONFIG_PATH.is_file():
        result: dict[str, object] = {"path": str(CONFIG_PATH), "exists": False,
                                     "parent_exists": parent_exists,
                                     "server1_fields": {}, "control_fields": {}}
        if parent_exists:
            parent = CONFIG_PATH.parent.stat()
            result["parent"] = {"owner": pwd.getpwuid(parent.st_uid).pw_name,
                                "group": grp.getgrgid(parent.st_gid).gr_name,
                                "mode": oct(parent.st_mode & 0o777),
                                "lulu_can_write": os.access(CONFIG_PATH.parent, os.W_OK | os.X_OK)}
        return result
    values: dict[str, str] = {}
    for line in CONFIG_PATH.read_text(errors="replace").splitlines():
        key, separator, value = line.partition("=")
        if separator:
            values[key] = value
    metadata = CONFIG_PATH.stat()
    try:
        nzbget = pwd.getpwnam("nzbget")
        nzbget_groups = set(os.getgrouplist(nzbget.pw_name, nzbget.pw_gid))
    except KeyError:
        nzbget = None
        nzbget_groups = set()
    parent = CONFIG_PATH.parent.stat()
    return {
        "path": str(CONFIG_PATH), "exists": True, "parent_exists": parent_exists,
        "owner": pwd.getpwuid(metadata.st_uid).pw_name,
        "group": grp.getgrgid(metadata.st_gid).gr_name,
        "mode": oct(metadata.st_mode & 0o777),
        "parent": {"owner": pwd.getpwuid(parent.st_uid).pw_name,
                   "group": grp.getgrgid(parent.st_gid).gr_name,
                   "mode": oct(parent.st_mode & 0o777),
                   "lulu_can_write": os.access(CONFIG_PATH.parent, os.W_OK | os.X_OK)},
        "nzbget_can_read_config": bool(
            nzbget and ((metadata.st_uid == nzbget.pw_uid and metadata.st_mode & 0o400)
                        or (metadata.st_gid in nzbget_groups and metadata.st_mode & 0o040)
                        or metadata.st_mode & 0o004)),
        "server1_fields": {key: bool(values.get(key, "")) for key in SERVER_FIELDS},
        "control_fields": {key: bool(values.get(key, "")) for key in CONTROL_FIELDS},
    }


def _acquisitiond_readiness() -> dict[str, object]:
    environment = dict(os.environ)
    environment.setdefault("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
    environment.setdefault("DBUS_SESSION_BUS_ADDRESS",
                           f"unix:path={environment['XDG_RUNTIME_DIR']}/bus")
    try:
        result = subprocess.run(
            ["busctl", "--user", "--json=short", "call", "org.lulu.Acquisitiond",
             "/org/lulu/Acquisition", "org.lulu.Acquisition", "GetUsenetReadiness"],
            stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=5,
            check=False, env=environment,
        )
    except (OSError, subprocess.SubprocessError) as error:
        return {"available": False, "error_type": type(error).__name__}
    if result.returncode:
        return {"available": False, "error_type": "DBusError",
                "error": (result.stderr or result.stdout or "Acquisitiond query failed").strip()[-500:]}
    try:
        envelope = json.loads(result.stdout)
        return {"available": True, **json.loads(envelope["data"][0])}
    except (KeyError, IndexError, TypeError, json.JSONDecodeError):
        return {"available": False, "error_type": "InvalidResponse"}


def inspect(app: AdminApp) -> dict[str, object]:
    server = app.config.provider("providers.usenet.server")
    executor = app.config.provider("providers.usenet")
    rpc_ok, rpc_message = app.test_provider("providers.usenet")
    enabled_result = _run(["systemctl", "is-enabled", "nzbget.service"])
    return {
        "settings": {
            "source": server.source,
            "accepted": bool(server.enabled and str(server.get("host", "")).strip()
                              and server.secret_available("username")
                              and server.secret_available("password")),
            "host_present": bool(str(server.get("host", "")).strip()),
            "port": server.get("port"), "tls": server.get("tls"),
            "connections": server.get("connections"), "enabled": server.enabled,
            "username_secret_available": server.secret_available("username"),
            "password_secret_available": server.secret_available("password"),
        },
        "executor_config": {
            "enabled": executor.enabled, "configured": executor.configured,
            "endpoint_present": bool(executor.get("endpoint", "")),
            "rpc_username_present": bool(executor.get("username", "")),
            "rpc_password_secret_available": executor.secret_available("rpc_password"),
        },
        "nzbget_config": _config_diagnostics(),
        "service": {"enabled": enabled_result.stdout.strip() if enabled_result.returncode == 0
                    else "not-enabled", **_unit_state("nzbget.service")},
        "rpc": {"authenticated": bool(rpc_ok), "message": rpc_message},
        "acquisition_service": _unit_state("lulu-acquisition.service"),
        "acquisitiond": _acquisitiond_readiness(),
    }


def _saved_payload(app: AdminApp) -> dict[str, Any]:
    server = app.config.provider("providers.usenet.server")
    missing = [name for name in ("username", "password") if not server.secret_available(name)]
    if not server.enabled or not str(server.get("host", "")).strip() or missing:
        raise ValueError("Saved Usenet server settings or secret references are incomplete")
    # Empty secret inputs tell the production save method to retain its
    # existing SecretStore values. It will read them only inside the backend.
    return {"host": str(server.get("host", "")), "port": server.get("port", 563),
            "tls": str(bool(server.get("tls", True))).lower(),
            "connections": server.get("connections", 8), "username": "", "password": ""}


def _safe_error(app: AdminApp, error: Exception) -> str:
    """Retain useful failure details while redacting every Usenet secret."""
    message = str(error)
    for namespace, name in (("usenet", "server-username"),
                            ("usenet", "server-password"),
                            ("usenet", "rpc-password")):
        secret = app.secrets.get(namespace, name)
        if secret:
            message = message.replace(secret, "<redacted>")
    return message[-3000:]


def _wait_provider_installer(app: AdminApp, timeout: float = 1200.0) -> dict[str, str]:
    deadline = time.monotonic() + timeout
    unit = "lulu-provider-install@usenet.service"
    while time.monotonic() < deadline:
        state = _unit_state(unit)
        active = state.get("ActiveState", "")
        timestamp = state.get("ExecMainStartTimestamp", "")
        if active in {"active", "activating", "deactivating"} or not timestamp:
            time.sleep(0.5)
            continue
        if state.get("Result") == "success" and state.get("ExecMainStatus") == "0":
            return state
        journal = _run(["journalctl", "-u", unit, "-n", "30", "-o", "cat", "--no-pager"])
        detail = (journal.stdout or journal.stderr or "installer exited unsuccessfully").strip()[-2000:]
        raise RuntimeError(f"NZBGet provider provisioning failed: {detail}")
    raise TimeoutError("NZBGet provider installer did not finish within 20 minutes")


def reconcile(app: AdminApp) -> dict[str, object]:
    provision: dict[str, object] = {"status": "not-needed"}
    if not CONFIG_PATH.exists():
        if CONFIG_PATH.parent.exists():
            raise RuntimeError("NZBGet config is absent but its managed parent exists; refusing to overwrite provider state")
        install_result = app.start_provider_install("usenet")
        provision = {**install_result, "unit": "lulu-provider-install@usenet.service",
                     "result": _wait_provider_installer(app)}
    elif not CONFIG_PATH.is_file():
        raise RuntimeError("NZBGet config path exists but is not a regular file")

    saved = app.save_setup_credentials("providers.usenet.server", _saved_payload(app))
    rpc_ok, rpc_message = app.test_provider("providers.usenet")
    acquisitiond = _acquisitiond_readiness()
    result = {"provisioning": provision, "configuration_apply": "success",
              "rpc_authenticated": bool(rpc_ok), "rpc_message": rpc_message,
              "admin_configured": bool(saved.get("configured")),
              "acquisitiond": acquisitiond}
    if not rpc_ok or not saved.get("configured"):
        raise RuntimeError(json.dumps(result, sort_keys=True))
    if not acquisitiond.get("available") or not acquisitiond.get("executor_registered"):
        raise RuntimeError(json.dumps(result, sort_keys=True))
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("inspect", "apply-saved", "reconcile"))
    args = parser.parse_args(argv)
    appliance_uid = pwd.getpwnam("lulu").pw_uid
    if os.geteuid() != appliance_uid:
        print("run this harness as the lulu appliance account", file=sys.stderr)
        return 2
    app = AdminApp()
    try:
        if args.action == "inspect":
            result: dict[str, object] = inspect(app)
        elif args.action == "apply-saved":
            saved = app.save_setup_credentials("providers.usenet.server", _saved_payload(app))
            result = {"configuration_apply": "success", "configured": bool(saved.get("configured")),
                      "rpc": inspect(app)["rpc"], "acquisitiond": _acquisitiond_readiness()}
        else:
            result = reconcile(app)
        print(json.dumps(result, sort_keys=True))
        return 0
    except Exception as error:
        print(json.dumps({"status": "failed", "error_type": type(error).__name__,
                          "message": _safe_error(app, error)}, sort_keys=True))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
