#!/usr/bin/env python3
"""Submit one local NZB through Acquisitiond for physical acceptance testing."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
from pathlib import Path
import pwd
import shutil
import subprocess
import sys
import time
import uuid


def _child(source: Path, timeout: float) -> int:
    # Imports are deferred until the unprivileged process connects to the user's bus.
    from dbus_next.aio import MessageBus

    async def follow() -> int:
        bus = await MessageBus().connect()
        intro = await bus.introspect("org.lulu.Acquisitiond", "/org/lulu/Acquisition")
        proxy = bus.get_proxy_object("org.lulu.Acquisitiond", "/org/lulu/Acquisition", intro)
        api = proxy.get_interface("org.lulu.Acquisition")
        readiness = json.loads(await api.call_get_usenet_readiness())
        if not all(readiness.get(key) for key in
                   ("enabled", "configured", "executor_registered", "rpc_secret_available")):
            raise RuntimeError("Acquisitiond Usenet readiness precondition failed")

        title = f"Acceptance {source.stem} {uuid.uuid4().hex[:8]}"
        job_id = await api.call_submit_job("usenet", str(source), title)
        print(json.dumps({"event": "submitted", "mudos_job_id": job_id,
                          "source": str(source), "title": title}), flush=True)
        deadline = time.monotonic() + timeout
        last = None
        while time.monotonic() < deadline:
            snapshot = json.loads(await api.call_get_snapshot())
            job = next((item for item in snapshot.get("jobs", [])
                        if item.get("job_id") == job_id), None)
            if job is not None:
                result = {
                    "event": "state", "mudos_job_id": job_id,
                    "mudos_state": job.get("state"), "stage": job.get("stage"),
                    "nzbget_id": job.get("provider_job_id"),
                    "dupe_key": job.get("ownership_label"),
                    "nzbget_queue_state": job.get("provider_state"),
                    "progress": job.get("progress"),
                    "downloaded_bytes": job.get("downloaded_bytes"),
                    "total_bytes": job.get("total_bytes"),
                    "provider_failure_details": job.get("error"),
                }
                signature = json.dumps(result, sort_keys=True)
                if signature != last:
                    print(json.dumps(result, sort_keys=True), flush=True)
                    last = signature
                if job.get("state") in {"completed", "failed", "cancelled"}:
                    bus.disconnect()
                    return 0 if job["state"] == "completed" else 1
            await asyncio.sleep(1)
        print(json.dumps({"event": "timeout", "mudos_job_id": job_id,
                          "timeout_seconds": timeout}), flush=True)
        bus.disconnect()
        return 2

    return asyncio.run(follow())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("nzb", type=Path, help="NZB input; never imported by staging it into NZBGet")
    parser.add_argument("--timeout", type=float, default=7200,
                        help="maximum wait for a Mudos terminal state (default: 7200 seconds)")
    parser.add_argument("--_owned-input", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.timeout <= 0:
        parser.error("--timeout must be positive")

    if args._owned_input:
        return _child(args._owned_input.resolve(), args.timeout)

    source = args.nzb.expanduser().resolve(strict=True)
    if not source.is_file():
        parser.error("input must be a regular NZB file")
    if os.geteuid() != 0:
        parser.error("run with sudo so the harness can safely read user-owned fixtures")
    target_user = pwd.getpwnam("lulu")
    staging = Path(target_user.pw_dir) / ".cache/lulu/usenet-acceptance"
    staging.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    owned = staging / f"acceptance-{digest[:12]}-{uuid.uuid4().hex[:8]}.nzb"
    shutil.copyfile(source, owned)
    os.chown(owned, target_user.pw_uid, target_user.pw_gid)
    os.chmod(owned, 0o640)
    env = os.environ.copy()
    env.update({"HOME": target_user.pw_dir, "USER": "lulu", "LOGNAME": "lulu",
                "XDG_CONFIG_HOME": f"{target_user.pw_dir}/.config",
                "XDG_DATA_HOME": f"{target_user.pw_dir}/.local/share",
                "XDG_RUNTIME_DIR": f"/run/user/{target_user.pw_uid}",
                "DBUS_SESSION_BUS_ADDRESS": f"unix:path=/run/user/{target_user.pw_uid}/bus",
                "PYTHONPATH": "/opt/lulu/current/lib", "LULU_INSTALL_ROOT": "/opt/lulu/current"})
    try:
        command = ["runuser", "-u", "lulu", "--", sys.executable, str(Path(__file__).resolve()),
                   str(owned), "--timeout", str(args.timeout), "--_owned-input", str(owned)]
        return subprocess.run(command, env=env, check=False).returncode
    finally:
        owned.unlink(missing_ok=True)


if __name__ == "__main__":
    raise SystemExit(main())
