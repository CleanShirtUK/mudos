"""Reproducible, bounded Gamescope invocation for HOST presentation probes."""

from dataclasses import dataclass
import os
import logging
import re
import subprocess
import time
from pathlib import Path
from collections.abc import Callable


@dataclass(frozen=True, slots=True)
class GamescopeInvocation:
    steam: bool = False
    output: str | None = None
    output_width: int | None = None
    output_height: int | None = None
    output_refresh: int | None = None
    nested_width: int = 1920
    nested_height: int = 1080

    @classmethod
    def from_environment(cls) -> "GamescopeInvocation":
        def optional_int(name: str) -> int | None:
            value = os.environ.get(name)
            if value is None or value == "":
                return None
            parsed = int(value)
            if parsed < 1:
                raise ValueError(f"{name} must be positive")
            return parsed

        return cls(
            output=os.environ.get("LULU_OUTPUT_CONNECTOR") or None,
            output_width=optional_int("LULU_OUTPUT_WIDTH"),
            output_height=optional_int("LULU_OUTPUT_HEIGHT"),
            output_refresh=optional_int("LULU_OUTPUT_REFRESH"),
            nested_width=optional_int("LULU_NESTED_WIDTH") or 1920,
            nested_height=optional_int("LULU_NESTED_HEIGHT") or 1080,
        )

    def argv(self, payload: list[str]) -> list[str]:
        if not payload:
            raise ValueError("Gamescope payload is required")
        command = [
            "gamescope",
        ]
        if self.steam:
            command += ["--steam"]
        command += [
            "--backend",
            "drm",
        ]
        if self.output is not None:
            command += ["--prefer-output", self.output]
        if self.output_width is not None:
            command += ["--output-width", str(self.output_width)]
        if self.output_height is not None:
            command += ["--output-height", str(self.output_height)]
        if self.output_refresh is not None:
            command += ["--output-refresh", str(self.output_refresh)]
        command += [
            "--expose-wayland",
            "--nested-width",
            str(self.nested_width),
            "--nested-height",
            str(self.nested_height),
        ]
        command += ["--", *payload]
        return command


def discover_presentation_output(drm_path: str = "/sys/class/drm") -> str:
    """Return a connected DRM connector, leaving mode choice to Gamescope."""
    connected = sorted(
        entry.parent.name.split("-", 1)[1]
        for entry in Path(drm_path).glob("card*-*/status")
        if entry.read_text().strip() == "connected"
    )
    if not connected:
        raise RuntimeError("no connected DRM presentation output found")
    return connected[0]


class GamescopePresentation:
    """Selects the Gamescope base layer through its Xwayland control property."""

    def __init__(self, display: str | None = None, poll_interval: float = 0.05) -> None:
        self.display = display or os.environ.get("DISPLAY", ":0")
        self.poll_interval = poll_interval
        self.shell_window: int | None = None
        self._logger = logging.getLogger("lulu.gamescope")

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
                if window_pid == pid or self._is_descendant(window_pid, pid):
                    return window
            if time.monotonic() >= deadline:
                raise TimeoutError(f"Gamescope window for PID {pid} was not found")
            time.sleep(self.poll_interval)

    @staticmethod
    def _is_descendant(pid: int, ancestor_pid: int) -> bool:
        current = pid
        while current > 1:
            try:
                status = Path(f"/proc/{current}/status").read_text()
            except (FileNotFoundError, PermissionError):
                return False
            parent = re.search(r"^PPid:\s+(\d+)$", status, re.MULTILINE)
            if parent is None:
                return False
            current = int(parent.group(1))
            if current == ancestor_pid:
                return True
        return False

    def select_pid(self, pid: int) -> int:
        window = self.window_for_pid(pid)
        self._logger.info("select pid=%s window=%s", pid, window)
        self._xprop(
            "-f",
            "GAMESCOPECTRL_BASELAYER_WINDOW",
            "32c",
            "-set",
            "GAMESCOPECTRL_BASELAYER_WINDOW",
            str(window),
        )
        return window

    def window_for_pids(self, pids: list[int] | Callable[[], list[int]], timeout: float = 10.0) -> int:
        deadline = time.monotonic() + timeout
        while True:
            wanted = set(pids() if callable(pids) else pids)
            for window, _app_id, window_pid in self._focusable_windows():
                if window_pid in wanted or any(self._is_descendant(window_pid, pid) for pid in wanted):
                    return window
            if time.monotonic() >= deadline:
                raise TimeoutError(f"Gamescope window for process set {sorted(wanted)} was not found")
            time.sleep(self.poll_interval)

    def select_pids(self, pids: list[int] | Callable[[], list[int]], timeout: float = 10.0) -> int:
        window = self.window_for_pids(pids, timeout)
        self._logger.info("select process set=%s window=%s", pids() if callable(pids) else pids, window)
        self._xprop(
            "-f", "GAMESCOPECTRL_BASELAYER_WINDOW", "32c", "-set",
            "GAMESCOPECTRL_BASELAYER_WINDOW", str(window),
        )
        return window

    def ensure_shell(self, pid: int) -> int:
        window = self.window_for_pid(pid)
        try:
            selected = self._xprop("GAMESCOPECTRL_BASELAYER_WINDOW")
        except subprocess.CalledProcessError:
            selected = ""
        values = re.findall(r"0x[0-9a-fA-F]+|\d+", selected.split("=", 1)[-1])
        current = int(values[0], 0) if values else 0
        if current != window:
            self._logger.info("reassert shell pid=%s window=%s previous=%s", pid, window, current)
            self.select_pid(pid)
        self.shell_window = window
        return window

    def select_shell(self, pid: int) -> int:
        self.shell_window = self.select_pid(pid)
        return self.shell_window

    def clear_selection(self) -> None:
        self._logger.info("clear selection")
        self._xprop(
            "-f",
            "GAMESCOPECTRL_BASELAYER_WINDOW",
            "32c",
            "-set",
            "GAMESCOPECTRL_BASELAYER_WINDOW",
            "0",
        )
