#!/usr/bin/env python3
"""Fail-closed online deployment of an immutable Mudos release.

`release.py` remains the low-level selector used for offline/bootstrap and
recovery. Online deployments must use this checked orchestration entry point.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import socket
from typing import Callable

ROOT = Path(__file__).resolve().parents[1]
RELEASE_TOOL = ROOT / "scripts" / "release.py"
ACTIVATION = Path("/opt/lulu/current")
RELEASE_ROOT = Path("/opt/lulu/releases")
USER = "lulu"
RUNTIME = "/run/user/958"
SESSION_BUS = ("org.lulu.ConsoleSessiond", "/org/lulu/ConsoleSession",
               "org.lulu.ConsoleSession", "GetState")
ACQUISITION_BUS = ("org.lulu.Acquisitiond", "/org/lulu/Acquisition",
                   "org.lulu.Acquisition", "GetSnapshot")
CONSOLED_BUS = ("org.lulu.Consoled", "/org/lulu/Console",
                "org.lulu.Console", "GetComponentRegistry")
REQUIRED_UNITS = ("lulu-session@2.service", "lulu-consoled.service",
                  "lulu-acquisition.service")


class GuardError(RuntimeError):
    pass


def _run(argv: list[str], *, check: bool = True, capture_output: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(argv, check=check, text=True, capture_output=capture_output)


def _as_user_bus_call(service: str, path: str, interface: str, method: str) -> str:
    command = ["sudo", "-n", "-u", USER, "env", f"XDG_RUNTIME_DIR={RUNTIME}",
               "busctl", "--user", "--json=short", "call", service, path, interface, method]
    try:
        result = _run(command)
    except (OSError, subprocess.CalledProcessError) as error:
        raise GuardError(f"user-bus query failed for {service}.{method}: {error}") from error
    try:
        envelope = json.loads(result.stdout)
        data = envelope["data"]
        if not isinstance(data, list) or len(data) != 1 or not isinstance(data[0], str):
            raise ValueError("expected exactly one string result")
        return data[0]
    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
        raise GuardError(f"malformed user-bus response from {service}.{method}") from error


def _require_healthy_units(run: Callable = _run) -> None:
    for unit in REQUIRED_UNITS:
        try:
            result = run(["systemctl", "show", unit, "--property=ActiveState", "--value"])
        except (OSError, subprocess.CalledProcessError) as error:
            raise GuardError(f"cannot establish health of {unit}: {error}") from error
        if result.stdout.strip() != "active":
            raise GuardError(f"required service is not active: {unit}")


def validate_idle_state(session_raw: str, acquisition_raw: str) -> None:
    try:
        session = json.loads(session_raw)
        acquisition = json.loads(acquisition_raw)
    except (json.JSONDecodeError, TypeError) as error:
        raise GuardError("Sessiond or Acquisitiond returned malformed JSON") from error
    if not isinstance(session, dict) or not isinstance(acquisition, dict):
        raise GuardError("Sessiond or Acquisitiond response has the wrong shape")
    required_session = ("lifecycle", "presentation", "presentation_ready", "active_identity",
                        "launch_token", "delegated_surface", "requested_surface", "session_kind",
                        "primary_id", "provider_id", "session_title", "resident_steam_runtime",
                        "controller")
    if any(key not in session for key in required_session):
        raise GuardError("Sessiond response is incomplete")
    if session["lifecycle"] != "shell" or session["presentation"] != "shell":
        raise GuardError("Sessiond is not in the normal shell lifecycle")
    if session["presentation_ready"] is not True:
        raise GuardError("Sessiond shell presentation is not ready")
    if session["active_identity"] is not None or session["launch_token"] is not None:
        raise GuardError("an active game identity or launch token exists")
    if session["delegated_surface"] is not None or session["requested_surface"] is not None:
        raise GuardError("a delegated or pending surface exists")
    if (session["session_kind"] != "shell" or session["primary_id"] is not None
            or session["provider_id"] is not None or session["session_title"] not in ("", None)):
        raise GuardError("Sessiond shell state contains contradictory game/session identity")
    steam = session["resident_steam_runtime"]
    if (not isinstance(steam, dict) or steam.get("state") != "ready"
            or "authenticated" not in str(steam.get("authentication", "")).lower()):
        raise GuardError("isolated Steam runtime is not ready and authenticated")
    controller = session["controller"]
    controllers = controller.get("controllers") if isinstance(controller, dict) else None
    if (not isinstance(controllers, dict)
            or not any(isinstance(device, dict) and device.get("connected") is True
                       for device in controllers.values())):
        raise GuardError("Sessiond cannot confirm an available controller input")
    jobs = acquisition.get("jobs")
    if not isinstance(jobs, list) or "activeDownloadCount" not in acquisition:
        raise GuardError("Acquisitiond response is incomplete")
    if not isinstance(acquisition["activeDownloadCount"], int) or acquisition["activeDownloadCount"] < 0:
        raise GuardError("Acquisitiond activeDownloadCount is malformed")
    active_states = {"queued", "starting", "transferring", "finalizing", "paused",
                     "pausing", "resuming", "cancelling"}
    for job in jobs:
        if not isinstance(job, dict) or not isinstance(job.get("state"), str):
            raise GuardError("Acquisitiond returned a malformed job")
        if job["state"] in active_states:
            raise GuardError(f"active acquisition operation exists ({job.get('operation', 'unknown')})")
    # activeDownloadCount is a legacy UI/actionable-queue badge, not a count of
    # running operations. Terminal jobs can keep it nonzero; the authoritative
    # gate is every job's explicit operation state above.


def read_and_validate(run: Callable = _run) -> None:
    _require_healthy_units(run)
    session = _as_user_bus_call(*SESSION_BUS)
    acquisition = _as_user_bus_call(*ACQUISITION_BUS)
    consoled = _as_user_bus_call(*CONSOLED_BUS)
    validate_idle_state(session, acquisition)
    try:
        registry = json.loads(consoled)
    except (json.JSONDecodeError, TypeError) as error:
        raise GuardError("Consoled returned malformed readiness data") from error
    if not isinstance(registry, list):
        raise GuardError("Consoled response has the wrong shape")


def deploy(release: Path, *, run: Callable = _run, sleep: Callable = time.sleep,
           readiness_timeout: float = 30.0) -> Path:
    release = release.resolve()
    if release.parent != RELEASE_ROOT.resolve() or not release.is_dir():
        raise GuardError("candidate must be a verified immutable release under /opt/lulu/releases")
    previous = ACTIVATION.resolve(strict=True)
    if previous == release:
        raise GuardError("candidate is already selected")
    run([sys.executable, str(RELEASE_TOOL), "verify", "--release-dir", str(release)])
    read_and_validate(run)
    # Last-moment recheck directly before the atomic selector operation.
    read_and_validate(run)
    try:
        run([sys.executable, str(RELEASE_TOOL), "activate", "--release-dir", str(release)])
        run(["systemctl", "restart", "lulu-session@2.service"])
        deadline = time.monotonic() + readiness_timeout
        last_error = "services have not recovered"
        while time.monotonic() < deadline:
            try:
                _require_healthy_units(run)
                read_and_validate(run)
                if ACTIVATION.resolve(strict=True) != release:
                    raise GuardError("selected release does not match the candidate")
                return previous
            except GuardError as error:
                last_error = str(error)
                sleep(0.5)
        raise GuardError(f"post-activation readiness failed: {last_error}")
    except Exception as error:
        # Restore only the selector and restart once; report both failures if
        # recovery itself cannot be established.
        try:
            run([sys.executable, str(RELEASE_TOOL), "activate", "--release-dir", str(previous)])
            run(["systemctl", "restart", "lulu-session@2.service"])
            if ACTIVATION.resolve(strict=True) != previous:
                raise GuardError("rollback selector did not resolve to the previous release")
        except Exception as rollback_error:
            raise GuardError(f"deployment failed ({error}); rollback failed ({rollback_error})") from error
        raise GuardError(f"deployment failed and selector was rolled back to {previous}: {error}") from error


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("release", type=Path, help="already-built immutable candidate release")
    args = parser.parse_args(argv)
    try:
        if os.geteuid() != 0:
            raise GuardError("run guarded online deployment with sudo")
        if ROOT.resolve() != Path("/home/josh/src/lulu") or socket.gethostname() != "lulu":
            raise GuardError("online deployment is restricted to the canonical lulu checkout and host")
        previous = deploy(args.release)
        print(json.dumps({"status": "deployed", "previous": str(previous),
                          "current": str(ACTIVATION.resolve(strict=True))}, sort_keys=True))
        return 0
    except (GuardError, OSError, subprocess.CalledProcessError) as error:
        print(f"guarded deployment refused/failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
