"""Read-only observation of the systemd-owned resident Steam/Xvfb service."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import subprocess


UNIT = "lulu-steam-runtime.service"
READY_STATUS = "Steam authenticated on isolated Xvfb :99"


@dataclass(frozen=True, slots=True)
class ResidentSteamRuntimeStatus:
    """A cached systemd view, not an independent runtime supervisor."""

    state: str = "unknown"
    active_state: str = "unknown"
    sub_state: str = "unknown"
    result: str = ""
    status_text: str = ""
    authentication: str = "unknown"
    restart_count: int | None = None
    error: str = ""

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


def parse_systemd_properties(output: str) -> ResidentSteamRuntimeStatus:
    properties = dict(
        line.split("=", 1) for line in output.splitlines() if "=" in line
    )
    load = properties.get("LoadState", "unknown")
    active = properties.get("ActiveState", "unknown")
    sub = properties.get("SubState", "unknown")
    result = properties.get("Result", "")
    status_text = properties.get("StatusText", "")
    try:
        restart_count = int(properties["NRestarts"])
    except (KeyError, ValueError):
        restart_count = None

    if load != "loaded":
        state = "unknown"
    elif active == "active":
        # Type=notify is sent only after Xvfb has opened and a fresh Steam
        # authentication success appears in the connection log. This is
        # readiness-at-notification, not a continuous authentication claim.
        state = "ready" if status_text == READY_STATUS else "degraded"
    elif active in {"activating", "reloading"}:
        state = "recovering" if sub == "auto-restart" else "starting"
    elif active == "failed":
        state = "failed"
    elif active == "inactive":
        state = "inactive"
    else:
        state = "unknown"

    exec_status = properties.get("ExecMainStatus", "")
    if state == "ready":
        authentication = "authenticated-at-readiness"
    elif active == "failed" and exec_status == "78":
        # The runtime script reserves 78 for AuthenticationUnavailable and
        # systemd explicitly prevents automatic restart for that exit status.
        authentication = "authentication-required"
    else:
        authentication = "unknown"

    return ResidentSteamRuntimeStatus(
        state=state,
        active_state=active,
        sub_state=sub,
        result=result,
        status_text=status_text,
        authentication=authentication,
        restart_count=restart_count,
    )


def read_resident_steam_runtime_status() -> ResidentSteamRuntimeStatus:
    """Read systemd's service state; never start, stop, or restart the unit."""
    try:
        completed = subprocess.run(
            [
                "/usr/bin/systemctl", "show", UNIT,
                "--property=LoadState,ActiveState,SubState,StatusText,Result,NRestarts,ExecMainStatus",
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=2,
        )
    except (OSError, subprocess.SubprocessError) as error:
        return ResidentSteamRuntimeStatus(error=type(error).__name__)
    return parse_systemd_properties(completed.stdout)
