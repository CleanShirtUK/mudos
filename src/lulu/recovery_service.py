"""Independent, loopback-only Mudos recovery control plane.

This service deliberately observes the normal runtime without importing or
depending on Sessiond, Consoled, Acquisitiond, Admin, or the shell. Mutations
are fixed action identifiers mapped to fixed systemd operations.
"""

from __future__ import annotations

from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import hmac
import json
import logging
import os
from pathlib import Path
import shutil
import subprocess
import time
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen

from .recovery import recovery_required, snapshot as recovery_snapshot
from .paths import PATHS


LOGGER = logging.getLogger("lulu.recovery-service")
HOST = "127.0.0.1"
PORT = 38124
MAX_REQUEST_BYTES = 4096

UNITS = {
    "mudos_session": ("lulu-session@2.service", "Mudos graphical session"),
    "admin": ("lulu-admin.service", "Mudos Admin"),
    "consoled": ("lulu-consoled.service", "Mudos game catalogue"),
    "acquisitiond": ("lulu-acquisition.service", "Mudos downloads"),
    "inputplumber": ("inputplumber.service", "Controller input"),
    "network_manager": ("NetworkManager.service", "Network connection"),
    "bluetooth": ("bluetooth.service", "Bluetooth"),
    "questarr": ("lulu-questarr.service", "Questarr"),
    "transmission": ("lulu-transmission.service", "Transmission downloads"),
    "nzbget": ("nzbget.service", "NZBGet downloads"),
}

RESTART_ACTIONS = {
    "restart_mudos": {
        "component": "mudos_session", "unit": "lulu-session@2.service",
        "label": "Restart Mudos", "impact": [
            "The graphical session will restart.",
            "An active delegated game or application may be terminated.",
            "Consoled and Acquisitiond may cycle because of their session relationships.",
        ],
    },
    "restart_consoled": {
        "component": "consoled", "unit": "lulu-consoled.service",
        "label": "Restart the game catalogue service", "impact": [
            "Catalogue requests and in-progress credential prompts may be interrupted.",
            "Persistent catalogue data is not deliberately removed.",
        ],
    },
    "restart_acquisitiond": {
        "component": "acquisitiond", "unit": "lulu-acquisition.service",
        "label": "Restart the downloads service", "impact": [
            "Mudos job tracking will restart and reconcile persisted jobs.",
            "Provider-owned transfers may continue; local transfers may pause or resume.",
        ],
    },
    "restart_admin": {
        "component": "admin", "unit": "lulu-admin.service",
        "label": "Restart Mudos Admin", "impact": [
            "The web portal will be briefly unavailable and web sessions may need to sign in again.",
        ],
    },
}

POWER_ACTIONS = {
    "reboot": {"label": "Reboot", "command": "reboot", "impact": [
        "The appliance will restart.",
        "Running games and applications will be stopped.",
        "Active downloads may be interrupted; their providers and Mudos will reconcile them on startup.",
    ]},
    "shutdown": {"label": "Shut down", "command": "poweroff", "impact": [
        "The appliance will shut down.",
        "Running games and applications will be stopped.",
        "Active downloads may be interrupted; their providers and Mudos will reconcile them on startup.",
    ]},
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _authorized_action_request(header: str | None) -> bool:
    expected = os.environ.get("LULU_RECOVERY_TOKEN", "")
    if not expected or not header or not header.startswith("Bearer "):
        return False
    supplied = header.removeprefix("Bearer ")
    return bool(supplied) and hmac.compare_digest(supplied, expected)


def _run(command: list[str], *, timeout: float = 2.0) -> subprocess.CompletedProcess[str] | None:
    try:
        return subprocess.run(command, capture_output=True, text=True, timeout=timeout, check=False)
    except (OSError, subprocess.SubprocessError):
        return None


def _systemd(unit: str) -> dict[str, str] | None:
    result = _run(["systemctl", "show", unit, "--property=LoadState,ActiveState,SubState,Result"])
    if result is None or result.returncode:
        return None
    return dict(line.split("=", 1) for line in result.stdout.splitlines() if "=" in line)


def _unit_state(unit: str) -> tuple[str, dict[str, str] | None]:
    info = _systemd(unit)
    if info is None or info.get("LoadState") != "loaded":
        return "unknown", info
    active, sub = info.get("ActiveState", "unknown"), info.get("SubState", "unknown")
    if active == "active":
        return "healthy", info
    if active in {"activating", "reloading"}:
        return "recovering", info
    if active == "failed":
        return "failed", info
    if active == "inactive":
        return "degraded", info
    return "unknown", info


def _component(component_id: str, state: str, summary: str, evidence: dict[str, Any], *,
               actions: list[str] | None = None, last_error: str = "",
               impact: str = "No user data is intentionally changed.") -> dict[str, Any]:
    return {
        "component_id": component_id,
        "state": state,
        "summary": summary,
        "checked_at": _now(),
        "freshness": "current" if evidence.get("available", True) else "unavailable",
        "evidence": evidence,
        "last_error": last_error[:240],
        "safe_actions": actions or [],
        "data_impact": impact,
    }


def _unit_component(component_id: str) -> dict[str, Any]:
    unit, label = UNITS[component_id]
    state, detail = _unit_state(unit)
    if detail is None:
        return _component(component_id, "unknown", f"{label} status is unavailable.",
                          {"available": False, "unit": unit}, last_error="systemd status unavailable")
    active = detail.get("ActiveState", "unknown")
    sub = detail.get("SubState", "unknown")
    summary = {
        "healthy": f"{label} is running.",
        "recovering": f"{label} is starting or restarting.",
        "failed": f"{label} is not running.",
        "degraded": f"{label} is stopped or inactive.",
        "unknown": f"The state of {label} could not be determined.",
    }[state]
    available_actions = [key for key, value in RESTART_ACTIONS.items()
                         if value["component"] == component_id]
    return _component(component_id, state, summary,
                      {"available": True, "unit": unit, "active_state": active,
                       "sub_state": sub, "result": detail.get("Result", "")},
                      actions=available_actions,
                      last_error=detail.get("Result", "") if state == "failed" else "")


def _bus_api(name: str, path: str, *, system: bool = False) -> tuple[bool, str]:
    command = ["busctl"]
    command += ["--system"] if system else ["--user"]
    command += ["--no-pager", "introspect", name, path]
    result = _run(command)
    if result is None:
        return False, "D-Bus could not be queried"
    if result.returncode:
        return False, "The service API did not respond"
    return True, ""


def _user_method(name: str, path: str, interface: str, method: str) -> str | None:
    result = _run(["busctl", "--user", "--no-pager", "call", name, path, interface, method], timeout=4)
    if result is None or result.returncode:
        return None
    return result.stdout.strip()


def _decode_bus_string(value: str | None) -> Any:
    if not value or not value.startswith("s "):
        return None
    try:
        return json.loads(value[2:])
    except (ValueError, json.JSONDecodeError):
        return None


def _api_component(component_id: str, unit_component: dict[str, Any], name: str,
                   path: str, interface: str) -> dict[str, Any]:
    state = unit_component["state"]
    detail = unit_component["evidence"]
    if state in {"failed", "unknown", "recovering", "degraded"}:
        return unit_component
    available, error = _bus_api(name, path)
    if not available:
        failed_state = "degraded" if state == "healthy" else state
        return _component(component_id, failed_state,
                          f"{unit_component['summary']} Its Mudos API is not responding.",
                          {**detail, "api_available": False, "available": detail.get("available", True)},
                          actions=unit_component["safe_actions"], last_error=error)
    evidence = {**detail, "api_available": True}
    if component_id == "sessiond":
        raw = _user_method(name, path, interface, "GetState")
        data = _decode_bus_string(raw)
        if isinstance(data, str):
            try:
                data = json.loads(data)
            except (ValueError, json.JSONDecodeError):
                data = None
        controllers = (data.get("controller", {}).get("controllers", {})
                       if isinstance(data, dict) else {})
        connected = sum(1 for item in controllers.values()
                        if isinstance(item, dict) and item.get("connected"))
        evidence.update({"connected_controllers": connected,
                         "session_state_available": isinstance(data, dict)})
        if not isinstance(data, dict):
            return _component(component_id, "degraded", "Sessiond responds, but session details are unavailable.",
                              evidence, last_error="Session state could not be decoded")
    if component_id == "acquisitiond":
        raw = _user_method(name, path, interface, "GetSnapshot")
        data = _decode_bus_string(raw)
        if isinstance(data, str):
            try:
                data = json.loads(data)
            except (ValueError, json.JSONDecodeError):
                data = None
        if isinstance(data, dict):
            evidence.update({"active_download_count": data.get("activeDownloadCount"),
                             "job_count": len(data.get("jobs", []))})
        else:
            evidence["job_snapshot_available"] = False
    return _component(component_id, state, unit_component["summary"], evidence,
                      actions=unit_component["safe_actions"])


def _http_probe(url: str, *, expected: tuple[int, ...] = (200,), timeout: float = 2.0) -> tuple[bool, int | None, str]:
    try:
        with urlopen(Request(url, headers={"User-Agent": "Mudos-Recovery/1"}), timeout=timeout) as response:
            return response.status in expected, response.status, ""
    except Exception as error:  # HTTPError carries a useful, bounded status code.
        code = getattr(error, "code", None)
        if code in expected:
            return True, int(code), ""
        if code is not None:
            return False, int(code), f"HTTP {code}"
        return False, None, "The local health endpoint did not respond"


def _http_service(component_id: str, url: str, label: str,
                  expected: tuple[int, ...] = (200,)) -> dict[str, Any]:
    unit_component = _unit_component(component_id)
    if unit_component["state"] in {"failed", "unknown", "recovering"}:
        return unit_component
    ok, status, error = _http_probe(url, expected=expected)
    state = "healthy" if ok else "failed"
    summary = f"{label} is responding." if ok else f"{label} is running but its API is not responding."
    evidence = {**unit_component["evidence"], "api_available": ok, "http_status": status}
    return _component(component_id, state, summary, evidence,
                      actions=unit_component["safe_actions"], last_error=error)


def _network_component() -> dict[str, Any]:
    unit, detail = _unit_state(UNITS["network_manager"][0])
    if unit in {"unknown", "failed"}:
        return _component("network", unit,
                          "NetworkManager is unavailable." if unit == "failed" else "Network state is unknown.",
                          {"available": detail is not None,
                           "unit": UNITS["network_manager"][0]},
                          last_error="NetworkManager status unavailable" if detail is None else "")
    result = _run(["nmcli", "-t", "-f", "STATE", "general"])
    if result is None or result.returncode:
        return _component("network", "unknown", "NetworkManager is running, but link state is unavailable.",
                          {"available": False, "unit_state": unit}, last_error="nmcli state unavailable")
    state_text = result.stdout.strip()
    if state_text.startswith("connected"):
        state = "healthy"
        summary = "A network connection is available."
    elif state_text in {"connecting", "connecting (getting IP configuration)"}:
        state = "recovering"
        summary = "The network connection is being established."
    else:
        state = "degraded"
        summary = "The appliance is running without a network connection."
    return _component("network", state, summary,
                      {"available": True, "network_manager": unit,
                       "connectivity_state": state_text})


def _controller_component() -> dict[str, Any]:
    result = _run(["busctl", "--system", "--no-pager", "get-property",
                   "org.shadowblip.InputPlumber", "/org/shadowblip/InputPlumber/Manager",
                   "org.shadowblip.InputManager", "GamepadOrder"])
    if result is None or result.returncode:
        return _component("controllers", "unknown", "Controller inventory is unavailable.",
                          {"available": False}, last_error="InputPlumber inventory unavailable")
    paths = result.stdout.count("/org/shadowblip/InputPlumber/CompositeDevice")
    state = "healthy" if paths else "requires_user_action"
    summary = (f"{paths} controller input device{'s are' if paths != 1 else ' is'} connected."
               if paths else "No controller input device is connected; connect or reconnect a controller.")
    return _component("controllers", state, summary,
                      {"available": True, "connected_count": paths,
                       "source": "InputPlumber GamepadOrder"})


def _bluetooth_component() -> dict[str, Any]:
    base = _unit_component("bluetooth")
    if base["state"] in {"failed", "unknown"}:
        return base
    result = _run(["busctl", "--system", "--no-pager", "tree", "org.bluez"])
    if result is None or result.returncode:
        return _component("bluetooth", "degraded", "Bluetooth is running, but BlueZ is not responding.",
                          {**base["evidence"], "api_available": False},
                          last_error="BlueZ D-Bus API unavailable")
    adapter_count = result.stdout.count("/org/bluez/hci")
    return _component("bluetooth", "healthy", "Bluetooth service and BlueZ are responding.",
                      {**base["evidence"], "api_available": True,
                       "adapter_count": adapter_count})


def _storage_component() -> dict[str, Any]:
    roots = {"system": Path("/"), "home": Path(PATHS.home),
             "games": Path(PATHS.game_install_root)}
    result: dict[str, Any] = {}
    for name, path in roots.items():
        try:
            usage = shutil.disk_usage(path)
            result[name] = {"path_available": True, "total_bytes": usage.total,
                            "free_bytes": usage.free,
                            "free_percent": round(usage.free * 100 / usage.total, 1) if usage.total else 0}
        except OSError:
            result[name] = {"path_available": False}
    unavailable = [name for name, item in result.items() if not item["path_available"]]
    low = [name for name, item in result.items()
           if item["path_available"] and item["free_percent"] < 5]
    state = "failed" if "system" in unavailable else "degraded" if unavailable or low else "healthy"
    summary = ("System storage could not be inspected." if "system" in unavailable else
               "Some storage is unavailable or nearly full." if unavailable or low else
               "System, home, and game storage space are available.")
    return _component("storage", state, summary,
                      {"available": not unavailable, "mounts": result,
                       "low_space_mounts": low})


def collect_health() -> dict[str, Any]:
    components: dict[str, dict[str, Any]] = {}
    components["mudos_session"] = _unit_component("mudos_session")
    components["sessiond"] = _api_component(
        "sessiond", components["mudos_session"], "org.lulu.ConsoleSessiond",
        "/org/lulu/ConsoleSession", "org.lulu.ConsoleSession")
    for component_id, name, path, interface in (
        ("consoled", "org.lulu.Consoled", "/org/lulu/Console", "org.lulu.Console"),
        ("acquisitiond", "org.lulu.Acquisitiond", "/org/lulu/Acquisition", "org.lulu.Acquisition"),
    ):
        components[component_id] = _api_component(
            component_id, _unit_component(component_id), name, path, interface)
    components["admin"] = _http_service("admin", "http://127.0.0.1/recovery", "Mudos Admin")
    components["inputplumber"] = _unit_component("inputplumber")
    if components["inputplumber"]["state"] not in {"failed", "unknown"}:
        result = _run(["busctl", "--system", "--no-pager", "tree", "org.shadowblip.InputPlumber"])
        api_ok = result is not None and result.returncode == 0
        components["inputplumber"] = _component(
            "inputplumber", components["inputplumber"]["state"] if api_ok else "failed",
            "Controller input service is responding." if api_ok else
            "Controller input service is running but its API is unavailable.",
            {**components["inputplumber"]["evidence"], "api_available": api_ok},
            last_error="InputPlumber D-Bus API unavailable" if not api_ok else "")
    components["network"] = _network_component()
    components["bluetooth"] = _bluetooth_component()
    components["questarr"] = _http_service("questarr", "http://127.0.0.1:5000/api/health", "Questarr")
    # Transmission's RPC endpoint returning 409 means the daemon answered and
    # requested its normal session-id handshake; it is an API response, not a failure.
    components["transmission"] = _http_service(
        "transmission", "http://127.0.0.1:9091/transmission/rpc", "Transmission", (200, 401, 409))
    # NZBGet's API requires credentials. Unit state is authoritative evidence;
    # avoid reading secrets just to produce a recovery summary.
    components["nzbget"] = _unit_component("nzbget")
    components["controllers"] = _controller_component()
    components["storage"] = _storage_component()
    priority = {"failed": 0, "requires_advanced_repair": 1, "requires_user_action": 2,
                "degraded": 3, "recovering": 4, "unknown": 5, "healthy": 6}
    relevant = [item["state"] for key, item in components.items()
                if key not in {"controllers"}]
    overall = min(relevant, key=lambda state: priority.get(state, 5)) if relevant else "unknown"
    if overall == "healthy" and any(state in {"unknown", "degraded"} for state in relevant):
        overall = "degraded"
    failure = recovery_snapshot()
    return {
        "schema_version": 1,
        "overall_state": overall,
        "checked_at": _now(),
        "failure_history": {
            "active": recovery_required(),
            "failure_count": int(failure.get("failure_count", 0)),
            "last_failure": str(failure.get("last_failure", ""))[:240],
        },
        "components": components,
        "actions": available_actions(components),
    }


def available_actions(components: dict[str, dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    health = components if components is not None else collect_health()["components"]
    result = []
    for action_id, info in RESTART_ACTIONS.items():
        component = health.get(info["component"], {})
        if action_id != "restart_mudos" and component.get("state") == "healthy":
            continue
        result.append({"action_id": action_id, "label": info["label"],
                       "requires_confirmation": True, "impact": list(info["impact"]),
                       "data_risk": "May interrupt service-owned work; does not intentionally delete user data."})
    acquisition = health.get("acquisitiond", {})
    active = acquisition.get("evidence", {}).get("active_download_count")
    active_text = (f"Mudos currently reports {active} active acquisition job(s)."
                   if isinstance(active, int) else
                   "Active acquisition count is unavailable; downloads may be running.")
    for action_id, info in POWER_ACTIONS.items():
        result.append({"action_id": action_id, "label": info["label"],
                       "requires_confirmation": True,
                       "impact": [*info["impact"], active_text],
                       "data_risk": "Volatile session state is lost; persisted user files are not intentionally deleted."})
    return result


def _request_systemd(verb: str, unit: str | None = None) -> None:
    command = ["systemctl", "--no-block", verb]
    if unit is not None:
        command.append(unit)
    result = _run(command, timeout=5)
    if result is None or result.returncode:
        raise RuntimeError("The system rejected the recovery request")


def _restart_mudos() -> None:
    """Prefer Sessiond's graceful lifecycle operation, with one fixed fallback."""
    healthy, _ = _bus_api("org.lulu.ConsoleSessiond", "/org/lulu/ConsoleSession")
    if healthy:
        result = _run(["busctl", "--user", "--no-pager", "call",
                       "org.lulu.ConsoleSessiond", "/org/lulu/ConsoleSession",
                       "org.lulu.ConsoleSession", "ResetMudos"], timeout=5)
        if result is not None and result.returncode == 0:
            return
    _request_systemd("restart", "lulu-session@2.service")


def perform_action(action_id: str, confirmed: bool) -> dict[str, Any]:
    if not confirmed:
        raise ValueError("This action requires explicit confirmation")
    if action_id in RESTART_ACTIONS:
        info = RESTART_ACTIONS[action_id]
        if action_id != "restart_mudos":
            health = collect_health()["components"].get(info["component"], {})
            if health.get("state") == "healthy":
                raise ValueError("This service is currently healthy; no restart is needed")
        if action_id == "restart_mudos":
            _restart_mudos()
        else:
            _request_systemd("restart", info["unit"])
        return {"action_id": action_id, "status": "requested",
                "impact": list(info["impact"])}
    if action_id in POWER_ACTIONS:
        info = POWER_ACTIONS[action_id]
        _request_systemd(info["command"])
        return {"action_id": action_id, "status": "requested",
                "impact": list(info["impact"])}
    raise ValueError("Unknown recovery action")


class RecoveryHandler(BaseHTTPRequestHandler):
    server_version = "MudosRecovery/1"

    def _json(self, value: Any, status: int = 200) -> None:
        data = json.dumps(value, separators=(",", ":")).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:
        if self.path == "/v1/status":
            self._json(collect_health())
        elif self.path == "/v1/actions":
            self._json({"actions": available_actions()})
        else:
            self._json({"error": "Not found"}, 404)

    def do_POST(self) -> None:
        if not _authorized_action_request(self.headers.get("Authorization")):
            self._json({"error": "Recovery action authorization failed."}, 403)
            return
        if self.path != "/v1/action":
            self._json({"error": "Not found"}, 404)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length < 1 or length > MAX_REQUEST_BYTES:
                raise ValueError("Invalid request size")
            value = json.loads(self.rfile.read(length))
            if not isinstance(value, dict) or set(value) - {"action_id", "confirmed"}:
                raise ValueError("Invalid recovery request")
            action_id = value.get("action_id")
            if not isinstance(action_id, str):
                raise ValueError("A recovery action is required")
            result = perform_action(action_id, value.get("confirmed") is True)
            self._json(result, 202)
        except (ValueError, TypeError, json.JSONDecodeError) as error:
            self._json({"error": str(error)}, 400)
        except RuntimeError as error:
            self._json({"error": str(error)}, 503)

    def log_message(self, *_: object) -> None:
        return


def serve() -> None:
    server = ThreadingHTTPServer((HOST, PORT), RecoveryHandler)
    LOGGER.info("independent recovery control plane listening on %s:%s", HOST, PORT)
    try:
        server.serve_forever()
    finally:
        server.server_close()


def main() -> None:
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s %(message)s")
    serve()


if __name__ == "__main__":
    main()
