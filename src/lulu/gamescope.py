"""Reproducible, bounded Gamescope invocation for HOST presentation probes."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class GamescopeInvocation:
    output: str = "HDMI-A-1"
    output_width: int = 1920
    output_height: int = 1080
    nested_width: int = 1280
    nested_height: int = 720

    def argv(self, payload: list[str]) -> list[str]:
        if not payload:
            raise ValueError("Gamescope payload is required")
        if self.output == "DP-1":
            raise ValueError("DP-1 is reserved as the development/debug display")
        return [
            "gamescope",
            "--backend",
            "drm",
            "--prefer-output",
            self.output,
            "--expose-wayland",
            "--output-width",
            str(self.output_width),
            "--output-height",
            str(self.output_height),
            "--nested-width",
            str(self.nested_width),
            "--nested-height",
            str(self.nested_height),
            "--",
            *payload,
        ]
