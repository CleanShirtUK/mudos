"""Reproducible, bounded Gamescope invocation for HOST presentation probes."""

from dataclasses import dataclass
import os
import re
import subprocess
import time


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


class GamescopePresentation:
    """Selects the Gamescope base layer through its Xwayland control property."""

    def __init__(self, display: str | None = None, poll_interval: float = 0.05) -> None:
        self.display = display or os.environ.get("DISPLAY", ":0")
        self.poll_interval = poll_interval
        self.shell_window: int | None = None

    def _xprop(self, *arguments: str) -> str:
        environment = os.environ.copy()
        environment["DISPLAY"] = self.display
        completed = subprocess.run(
            ["xprop", "-root", *arguments],
            check=True,
            capture_output=True,
            text=True,
            env=environment,
        )
        return completed.stdout

    def _focusable_windows(self) -> list[tuple[int, int, int]]:
        output = self._xprop("GAMESCOPE_FOCUSABLE_WINDOWS")
        values = [int(value, 0) for value in re.findall(r"0x[0-9a-fA-F]+|\d+", output.split("=", 1)[-1])]
        return [tuple(values[index : index + 3]) for index in range(0, len(values) - 2, 3)]

    def window_for_pid(self, pid: int, timeout: float = 2.0) -> int:
        deadline = time.monotonic() + timeout
        while True:
            for window, _app_id, window_pid in self._focusable_windows():
                if window_pid == pid:
                    return window
            if time.monotonic() >= deadline:
                raise TimeoutError(f"Gamescope window for PID {pid} was not found")
            time.sleep(self.poll_interval)

    def select_pid(self, pid: int) -> int:
        window = self.window_for_pid(pid)
        self._xprop(
            "-f",
            "GAMESCOPECTRL_BASELAYER_WINDOW",
            "32c",
            "-set",
            "GAMESCOPECTRL_BASELAYER_WINDOW",
            str(window),
        )
        return window

    def select_shell(self, pid: int) -> int:
        self.shell_window = self.select_pid(pid)
        return self.shell_window

    def clear_selection(self) -> None:
        self._xprop(
            "-f",
            "GAMESCOPECTRL_BASELAYER_WINDOW",
            "32c",
            "-set",
            "GAMESCOPECTRL_BASELAYER_WINDOW",
            "0",
        )
