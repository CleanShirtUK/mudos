"""MangoHud launch-time profile selection for Sessiond-owned games."""

from __future__ import annotations

from dataclasses import dataclass


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
    return {"MANGOHUD": "1", "MANGOHUD_CONFIG": selected.config}
