"""DRM-backed gameplay display policy for the Lulu Gamescope session."""

from __future__ import annotations

from dataclasses import dataclass, asdict
import json
import os
from pathlib import Path
import re
import subprocess
from typing import Any


@dataclass(frozen=True, slots=True)
class DisplayMode:
    width: int
    height: int
    refresh: float
    preferred: bool = False

    @property
    def id(self) -> str:
        return f"{self.width}x{self.height}@{self.refresh:.2f}"


def _state_path() -> Path:
    return Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "lulu" / "display-state.json"


def _modes_from_drm(drm_path: str = "/sys/class/drm") -> list[dict[str, Any]]:
    modes: list[dict[str, Any]] = []
    for connector in sorted(Path(drm_path).glob("card*-*")):
        status = connector / "status"
        if not status.exists() or status.read_text().strip() != "connected":
            continue
        name = connector.name.split("-", 1)[1]
        raw = (connector / "modes").read_text(errors="replace").splitlines()
        parsed = []
        for value in raw:
            match = re.fullmatch(r"(\d+)x(\d+)", value.strip())
            if match:
                parsed.append((int(match.group(1)), int(match.group(2))))
        modes.append({"connector": name, "modes": parsed})
    return modes


def _modetest_modes() -> dict[str, list[DisplayMode]]:
    try:
        output = subprocess.run(["modetest", "-c"], check=True, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, text=True, timeout=4).stdout
    except (OSError, subprocess.SubprocessError):
        return {}
    result: dict[str, list[DisplayMode]] = {}
    connector = None
    for line in output.splitlines():
        match = re.search(r"\b(DP-\S+|HDMI-\S+|DVI-\S+)\s+", line)
        if match:
            connector = match.group(1)
            result.setdefault(connector, [])
            continue
        match = re.match(r"\s+#\d+\s+(\d+)x(\d+)\s+([0-9]+(?:\.[0-9]+)?)\s+.*type: (.*)", line)
        if connector and match:
            result[connector].append(DisplayMode(
                int(match.group(1)), int(match.group(2)), float(match.group(3)),
                "preferred" in match.group(4),
            ))
    return result


class DisplayManagerAdapter:
    """Normalize connected DRM connectors and persist only Lulu policy."""

    def __init__(self, state_path: Path | None = None, drm_path: str = "/sys/class/drm") -> None:
        self.state_path = state_path or _state_path()
        self.drm_path = drm_path

    def _policy(self) -> dict[str, Any]:
        try:
            value = json.loads(self.state_path.read_text())
            return value if isinstance(value, dict) else {}
        except (OSError, ValueError, json.JSONDecodeError):
            return {}

    def _save(self, value: dict[str, Any]) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(json.dumps(value, sort_keys=True) + "\n")

    def snapshot(self) -> dict[str, Any]:
        test_modes = _modetest_modes()
        displays = []
        for item in _modes_from_drm(self.drm_path):
            connector = item["connector"]
            modes = test_modes.get(connector, [])
            if not modes:
                modes = [DisplayMode(width, height, 60.0, index == 0)
                         for index, (width, height) in enumerate(dict.fromkeys(item["modes"]), 0)]
            unique = {mode.id: mode for mode in modes}
            modes = list(unique.values())
            preferred = next((mode for mode in modes if mode.preferred), modes[0] if modes else None)
            displays.append({
                "id": connector, "name": connector, "connector": connector,
                "connected": True, "active": False,
                "current": None, "preferred": asdict(preferred) if preferred else None,
                "modes": [asdict(mode) | {"id": mode.id} for mode in modes],
            })
        policy = self._policy()
        requested = policy.get("requested", {})
        known_good = policy.get("known_good", {})
        selected = next((item for item in displays if item["id"] == requested.get("output") and item["connected"]), None)
        if selected is None and displays:
            selected = next((item for item in displays if item["id"] == known_good.get("output")), displays[0])
        if selected:
            selected["active"] = True
        return {"available": bool(displays), "displays": displays, "requested": requested,
                "known_good": known_good, "selected": selected, "error": "" if displays else "no connected display"}

    def apply(self, output: str, width: int, height: int, refresh: float) -> dict[str, Any]:
        state = self.snapshot()
        display = next((item for item in state["displays"] if item["id"] == output), None)
        if display is None:
            raise ValueError("selected display is unavailable")
        mode = next((mode for mode in display["modes"]
                     if mode["width"] == width and mode["height"] == height
                     and abs(float(mode["refresh"]) - refresh) < 0.02), None)
        if mode is None:
            raise ValueError("selected display mode is unavailable")
        value = {"output": output, "width": width, "height": height, "refresh": refresh}
        policy = self._policy()
        policy["requested"] = value
        policy["known_good"] = value
        self._save(policy)
        return self.snapshot()


def display_environment() -> dict[str, str]:
    """Return Gamescope variables from a validated requested/known-good policy."""
    adapter = DisplayManagerAdapter()
    state = adapter.snapshot()
    policy = state.get("requested") or state.get("known_good") or {}
    selected = next((item for item in state["displays"] if item["id"] == policy.get("output")), None)
    # Keep the preference intact while falling back to a currently connected
    # output; disappearance must not prevent the session from starting.
    if selected is None:
        selected = state.get("selected")
    if selected is None:
        return {}
    mode = next((item for item in selected["modes"] if item["width"] == policy.get("width")
                 and item["height"] == policy.get("height")
                 and abs(float(item["refresh"]) - float(policy.get("refresh", 0))) < 0.02), None)
    if mode is None:
        mode = selected.get("preferred")
    if mode is None:
        return {"LULU_OUTPUT_CONNECTOR": selected["connector"]}
    return {"LULU_OUTPUT_CONNECTOR": selected["connector"], "LULU_OUTPUT_WIDTH": str(mode["width"]),
            "LULU_OUTPUT_HEIGHT": str(mode["height"]), "LULU_OUTPUT_REFRESH": str(mode["refresh"])}
