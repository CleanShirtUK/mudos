"""Reproducible, bounded Gamescope invocation for HOST presentation probes."""

from dataclasses import dataclass
import os
import logging
import re
import subprocess
import time
from pathlib import Path
from collections.abc import Callable
from .display_manager import display_environment


def optional_int_value(value: str | None) -> int | None:
    if value in (None, ""):
        return None
    parsed = int(float(value))
    return parsed if parsed > 0 else None


def optional_float_value(value: str | None) -> float | None:
    if value in (None, ""):
        return None
    parsed = float(value)
    return parsed if parsed > 0 else None


@dataclass(frozen=True, slots=True)
class GamescopeInvocation:
    steam: bool = False
    output: str | None = None
    output_width: int | None = None
    output_height: int | None = None
    output_refresh: float | None = None
    nested_width: int = 1920
    nested_height: int = 1080

    @classmethod
    def from_environment(cls) -> "GamescopeInvocation":
        policy = display_environment()
        def optional_int(name: str) -> int | None:
            value = os.environ.get(name)
            if value is None or value == "":
                return None
            parsed = int(value)
            if parsed < 1:
                raise ValueError(f"{name} must be positive")
            return parsed

        def optional_refresh(name: str) -> float | None:
            value = os.environ.get(name)
            if value in (None, ""):
                return None
            parsed = float(value)
            if parsed <= 0:
                raise ValueError(f"{name} must be positive")
            return parsed

        return cls(
            output=os.environ.get("LULU_OUTPUT_CONNECTOR") or policy.get("LULU_OUTPUT_CONNECTOR"),
            output_width=optional_int("LULU_OUTPUT_WIDTH") or optional_int_value(policy.get("LULU_OUTPUT_WIDTH")),
            output_height=optional_int("LULU_OUTPUT_HEIGHT") or optional_int_value(policy.get("LULU_OUTPUT_HEIGHT")),
            output_refresh=optional_refresh("LULU_OUTPUT_REFRESH") or optional_float_value(policy.get("LULU_OUTPUT_REFRESH")),
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
            # Gamescope exposes refresh as nested-refresh; there is no
            # output-refresh option.  Passing the latter makes Gamescope
            # exit before the shell starts.
            command += ["--nested-refresh", str(self.output_refresh)]
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
    if len(connected) > 1:
        raise RuntimeError(
            "multiple connected DRM presentation outputs found; set LULU_OUTPUT_CONNECTOR: "
            + ", ".join(connected)
        )
    return connected[0]


class GamescopePresentation:
    """Selects the Gamescope base layer through its Xwayland control property."""

    def __init__(self, display: str | None = None, poll_interval: float = 0.05) -> None:
        self.display = display or os.environ.get("DISPLAY", ":0")
        self.poll_interval = poll_interval
        self.shell_window: int | None = None
        self.shell_window_pid: int | None = None
        self.shell_owner_pid: int | None = None
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
        try:
            output = self._xprop("GAMESCOPE_FOCUSABLE_WINDOWS")
        except subprocess.CalledProcessError:
            return []
        values = [int(value, 0) for value in re.findall(r"0x[0-9a-fA-F]+|\d+", output.split("=", 1)[-1])]
        return [tuple(values[index : index + 3]) for index in range(0, len(values) - 2, 3)]

    def focusable_windows(self) -> list[tuple[int, int, int]]:
        """Expose the current Xwayland/Gamescope candidate set for diagnostics."""
        return self._focusable_windows()

    def selected_base_window(self) -> int | None:
        try:
            output = self._xprop("GAMESCOPECTRL_BASELAYER_WINDOW")
        except (OSError, subprocess.CalledProcessError):
            return None
        values = re.findall(r"0x[0-9a-fA-F]+|(?<![A-Za-z])\d+", output.split("=", 1)[-1])
        return int(values[0], 0) if values else None

    def window_for_pid(self, pid: int, timeout: float = 2.0) -> int:
        deadline = time.monotonic() + timeout
        while True:
            for window, _app_id, window_pid in self._focusable_windows():
                if window_pid == pid or self._is_descendant(window_pid, pid):
                    return window
            if time.monotonic() >= deadline:
                raise TimeoutError(f"Gamescope window for PID {pid} was not found")
            time.sleep(self.poll_interval)

    def _window_pid(self, window: int) -> int | None:
        return next((pid for candidate, _app_id, pid in self._focusable_windows()
                     if candidate == window), None)

    def _cached_shell_matches(self, pid: int) -> bool:
        window_pid = self.shell_window_pid
        return bool(
            self.shell_window is not None
            and window_pid is not None
            and (window_pid == pid or self._is_descendant(window_pid, pid))
        )

    def _window_command(self, action: str, window: int) -> None:
        environment = os.environ.copy()
        environment["DISPLAY"] = self.display
        subprocess.run(
            ["xdotool", f"window{action}", str(window)],
            check=True,
            capture_output=True,
            text=True,
            env=environment,
        )

    def _unmapped_window_for_pid(self, pid: int) -> int:
        """Find a shell XID even when Gamescope no longer advertises it."""
        environment = os.environ.copy()
        environment["DISPLAY"] = self.display
        completed = subprocess.run(
            ["xdotool", "search", "--pid", str(pid)],
            check=True,
            capture_output=True,
            text=True,
            env=environment,
        )
        windows = [int(value) for value in completed.stdout.split() if value.isdecimal()]
        if not windows:
            raise TimeoutError(f"X11 window for shell PID {pid} was not found")
        return windows[0]

    def _wait_for_focusable_window(self, window: int, pid: int, timeout: float) -> int:
        deadline = time.monotonic() + timeout
        while True:
            for candidate, _app_id, window_pid in self._focusable_windows():
                if candidate == window and (
                    window_pid == pid or self._is_descendant(window_pid, pid)
                ):
                    return candidate
            if time.monotonic() >= deadline:
                raise TimeoutError(
                    f"Gamescope window {window} for shell PID {pid} was not focusable after mapping"
                )
            time.sleep(self.poll_interval)

    def _map_shell_before_selection(self, pid: int, timeout: float = 10.0,
                                    *, map_first: bool = False) -> int:
        """Restore the remembered shell XID before looking it up in Gamescope.

        An unmapped X11 shell is intentionally absent from
        GAMESCOPE_FOCUSABLE_WINDOWS. Keep its XID while the shell process lives,
        map it at the existing return-to-shell boundary, then wait for Gamescope
        to publish it as focusable before selecting it.
        """
        if not self._cached_shell_matches(pid):
            try:
                window = self.window_for_pid(pid, timeout=timeout)
                window_pid = self._window_pid(window)
            except TimeoutError:
                # The session daemon may have restarted while the shell stayed
                # alive and unmapped. Recover its XID from the X server, map it,
                # and only then rely on Gamescope's focusable-window list.
                window = self._unmapped_window_for_pid(pid)
                self._window_command("map", window)
                self._wait_for_focusable_window(window, pid, timeout)
                window_pid = pid
            self.shell_window = window
            self.shell_window_pid = window_pid
            return window

        assert self.shell_window is not None
        window = self.shell_window
        if map_first or not any(candidate == window for candidate, _app_id, _window_pid
                                in self._focusable_windows()):
            self._logger.info("map hidden shell window before return pid=%s window=%s", pid, window)
            self._window_command("map", window)
        self._wait_for_focusable_window(window, pid, timeout)
        self.shell_owner_pid = pid
        return window

    def _unmap_shell_after_game_selection(self, game_window: int) -> None:
        shell_window = self.shell_window
        if shell_window is None or shell_window == game_window:
            return
        if not any(candidate == shell_window for candidate, _app_id, _pid
                   in self._focusable_windows()):
            return
        self._logger.info("unmap shell after game selection shell=%s game=%s",
                          shell_window, game_window)
        try:
            self._window_command("unmap", shell_window)
        except (OSError, subprocess.SubprocessError):
            # If the X server accepted the unmap but the helper reported an
            # error, restore focusability before the caller rolls back launch.
            self._window_command("map", shell_window)
            owner_pid = self.shell_owner_pid or self.shell_window_pid
            if owner_pid is not None:
                self._wait_for_focusable_window(shell_window, owner_pid, 2.0)
            raise

    def _select_window(self, window: int) -> bool:
        self._xprop(
            "-f", "GAMESCOPECTRL_BASELAYER_WINDOW", "32c", "-set",
            "GAMESCOPECTRL_BASELAYER_WINDOW", str(window),
        )
        selected = self.selected_base_window()
        accepted = selected == window
        self._logger.info(
            "gamescope_surface_selection stage=select-result requested_window=%s selected_window=%s accepted=%s",
            window, selected, accepted,
        )
        return accepted

    def request_window_close(self, window: int) -> None:
        """Ask an Xwayland client to close through WM_DELETE_WINDOW."""
        environment = os.environ.copy()
        environment["DISPLAY"] = self.display
        subprocess.run(
            ["xdotool", "windowclose", str(window)],
            check=True,
            capture_output=True,
            text=True,
            env=environment,
        )

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
        window = self.window_for_pid(pid, timeout=10.0)
        self._logger.info("select pid=%s window=%s", pid, window)
        if not self._select_window(window):
            raise RuntimeError(f"Gamescope did not select window {window} for PID {pid}")
        return window

    def window_for_pids(self, pids: list[int] | Callable[[], list[int]], timeout: float = 10.0,
                        process_alive: Callable[[], bool] | None = None) -> int:
        deadline = time.monotonic() + timeout
        started = time.monotonic()
        next_progress = started
        wanted: set[int] = set()
        windows: list[tuple[int, int, int]] = []
        while True:
            wanted = set(pids() if callable(pids) else pids)
            windows = self._focusable_windows()
            for window, app_id, window_pid in windows:
                if window_pid in wanted or any(self._is_descendant(window_pid, pid) for pid in wanted):
                    self._logger.info("gamescope_surface_selection stage=eligible-window-found elapsed_s=%.3f wanted_pids=%s candidates=%s selected=%s",
                                      time.monotonic() - started, sorted(wanted), windows,
                                      (window, app_id, window_pid))
                    return window
            now = time.monotonic()
            if process_alive is not None and not process_alive():
                self._logger.error("gamescope_surface_selection stage=process-tree-exited elapsed_s=%.3f wanted_pids=%s candidates=%s",
                                   now - started, sorted(wanted), windows)
                raise RuntimeError("owned game process tree exited before a Gamescope window appeared")
            if now >= deadline:
                self._logger.error("gamescope_surface_selection stage=eligible-window-timeout elapsed_s=%.3f wanted_pids=%s candidates=%s",
                                   now - started, sorted(wanted), windows)
                raise TimeoutError(f"Gamescope window for process set {sorted(wanted)} was not found")
            if now >= next_progress:
                self._logger.info("gamescope_surface_selection stage=waiting-for-window elapsed_s=%.3f remaining_s=%.1f game_pids=%s candidates=%s",
                                  now - started, deadline - now, sorted(wanted), windows)
                next_progress = now + 5.0
            time.sleep(self.poll_interval)

    def window_is_focusable(self, window: int) -> bool:
        return any(candidate == window for candidate, _app_id, _pid in self._focusable_windows())

    def select_pids(self, pids: list[int] | Callable[[], list[int]], timeout: float = 10.0,
                    process_alive: Callable[[], bool] | None = None) -> int:
        window = self.window_for_pids(pids, timeout, process_alive)
        requested_pids = pids() if callable(pids) else pids
        self._logger.info("gamescope_surface_selection stage=select-request pids=%s window=%s",
                          requested_pids, window)
        if not self._select_window(window):
            raise RuntimeError(f"Gamescope did not select window {window} for process set {requested_pids}")
        return window

    def suspend_shell_window(self) -> None:
        """Unmap the cached shell after a game surface owns Gamescope."""
        selected = self.selected_base_window()
        if selected is None:
            raise RuntimeError("Gamescope selected surface could not be verified")
        self._unmap_shell_after_game_selection(selected)

    def ensure_shell(self, pid: int) -> int:
        window = self._map_shell_before_selection(pid)
        try:
            selected = self._xprop("GAMESCOPECTRL_BASELAYER_WINDOW")
        except subprocess.CalledProcessError:
            selected = ""
        values = re.findall(r"0x[0-9a-fA-F]+|\d+", selected.split("=", 1)[-1])
        current = int(values[0], 0) if values else 0
        if current != window:
            self._logger.info("reassert shell pid=%s window=%s previous=%s", pid, window, current)
            self._select_window(window)
        self.shell_window = window
        self.shell_owner_pid = pid
        return window

    def select_shell(self, pid: int) -> int:
        # Mapping precedes Gamescope discovery/selection. This ordering is
        # required because an unmapped shell is not advertised as focusable.
        window = self._map_shell_before_selection(pid, map_first=True)
        if not self._select_window(window):
            raise RuntimeError(f"Gamescope did not select shell window {window}")
        self.shell_window = window
        self.shell_owner_pid = pid
        return window

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
