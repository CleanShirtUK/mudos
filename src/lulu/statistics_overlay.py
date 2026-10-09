"""MangoHud launch-time profile selection for Sessiond-owned games."""

from __future__ import annotations

from dataclasses import dataclass
import logging
from pathlib import Path
import re
import shutil


@dataclass(frozen=True, slots=True)
class OverlayProfile:
    label: str
    config: str


# Keep this to metrics MangoHud exposes across common supported drivers.  The
# detailed profile intentionally uses MangoHud's built-in `full` preset.
PROFILES = {
    "off": OverlayProfile("Off", "no_display=1"),
    "fps": OverlayProfile("FPS Only", "fps_only=1"),
    "minimal": OverlayProfile(
        "Minimal", "fps,frametime,cpu_temp,gpu_temp,gpu_core_clock"
    ),
    "detailed": OverlayProfile("Detailed", "full,frametime,frame_timing_detailed"),
}

LOGGER = logging.getLogger(__name__)

_LAUNCHER_NAMES = {
    "env", "bash", "sh", "dash", "python", "python3", "umu-run", "legendary", "gogdl",
    "steam", "flatpak", "bwrap",
}
_LAUNCHER_MARKERS = ("proton", "wine", "pressure-vessel")


def profile(value: object) -> OverlayProfile:
    """Return a validated profile, defaulting unknown persisted data to Off."""
    return PROFILES.get(value, PROFILES["off"]) if isinstance(value, str) else PROFILES["off"]


def next_mode(value: object) -> str:
    """Advance the persisted System Settings choice, wrapping invalid data to Off."""
    modes = tuple(PROFILES)
    if value not in PROFILES:
        return modes[0]
    return modes[(modes.index(value) + 1) % len(modes)]


def launch_environment(value: object) -> dict[str, str]:
    """MangoHud environment for a game launched by Mudos, not shell/apps."""
    selected = profile(value)
    if selected is PROFILES["off"]:
        return {"MANGOHUD": "0"}
    return {"MANGOHUD": "1", "MANGOHUD_CONFIG": selected.config}


def adapt_native_launch(command: list[str] | tuple[str, ...], environment: dict[str, str], *,
                        wrapper: str | None = None) -> tuple[list[str], dict[str, str]]:
    """Use MangoHud's official wrapper for native games (not launchers).

    Vulkan already works through MANGOHUD=1, so this narrowly adds the wrapper
    for direct native executables and simple native game entry scripts to cover
    OpenGL. A script is eligible only when it explicitly execs a child and has
    no Wine/Proton/UMU marker. The wrapper's preload environment is inherited by
    that child. Proton/Wine and Flatpak boundaries use their own mechanisms.
    """
    argv = list(command)
    child_environment = dict(environment)
    if not argv or child_environment.get("MANGOHUD") != "1":
        return argv, child_environment
    executable = argv[0]
    basename = Path(executable).name.casefold()
    if basename in _LAUNCHER_NAMES or any(marker in basename for marker in _LAUNCHER_MARKERS):
        return argv, child_environment
    probe = Path(executable)
    if not probe.is_absolute():
        probe = Path.cwd() / probe
    try:
        with probe.open("rb") as binary:
            header = binary.read(4)
            if header != b"\x7fELF":
                binary.seek(0)
                script = binary.read(64 * 1024).decode("utf-8", errors="ignore")
                if (not script.startswith("#!") or not re.search(r"\bexec\s+\S+", script)
                        or re.search(r"\b(?:proton|wine|umu-run)\b", script, re.IGNORECASE)):
                    return argv, child_environment
    except OSError:
        return argv, child_environment
    mangohud = wrapper or shutil.which("mangohud")
    if not mangohud:
        LOGGER.warning("MangoHud wrapper unavailable; native OpenGL overlay will not be active: %s", executable)
        return argv, child_environment
    return [mangohud, "--dlsym", *argv], child_environment
