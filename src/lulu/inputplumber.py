"""Small command adapter for the documented InputPlumber D-Bus API."""

from dataclasses import dataclass
import logging
from pathlib import Path
import re
import subprocess

from .contracts import InputMode


DEFAULT_PROFILE_PATH = "/usr/share/inputplumber/profiles/default.yaml"
LOGGER = logging.getLogger("lulu.inputplumber")


@dataclass(frozen=True, slots=True)
class InputPlumberClient:
    """controllerd-side client; InputPlumber remains runtime authority."""

    object_path: str
    profile_paths: dict[InputMode, Path]
    busctl: str = "busctl"

    def load_mode(
        self,
        mode: InputMode,
        object_path: str | None = None,
        *,
        execute: bool = True,
    ) -> list[str]:
        object_path = object_path or self.object_path
        command = [
            self.busctl,
            "call",
            "org.shadowblip.InputPlumber",
            object_path,
            "org.shadowblip.Input.CompositeDevice",
            "LoadProfilePath",
            "s",
            str(self.profile_paths[mode]),
        ]
        if execute:
            tree = subprocess.run(
                [self.busctl, "tree", "org.shadowblip.InputPlumber"],
                check=True,
                capture_output=True,
                text=True,
            ).stdout
            if object_path not in tree:
                return command
            subprocess.run(command, check=True)
        return command

    def set_intercept_mode(
        self,
        mode: int,
        object_path: str | None = None,
        *,
        execute: bool = True,
    ) -> list[str]:
        if mode not in range(4):
            raise ValueError("InputPlumber InterceptMode must be between 0 and 3")
        object_path = object_path or self.object_path
        command = [
            self.busctl,
            "set-property",
            "org.shadowblip.InputPlumber",
            object_path,
            "org.shadowblip.Input.CompositeDevice",
            "InterceptMode",
            "u",
            str(mode),
        ]
        if execute:
            subprocess.run(command, check=True)
        return command

    def ensure_default_intercept(
        self, object_path: str | None = None, *, execute: bool = True
    ) -> list[list[str]]:
        """Restore the controller baseline for one live composite."""
        object_path = object_path or self.object_path
        load_command = [
            self.busctl, "call", "org.shadowblip.InputPlumber", object_path,
            "org.shadowblip.Input.CompositeDevice", "LoadProfilePath", "s",
            DEFAULT_PROFILE_PATH,
        ]
        mode_command = self.set_intercept_mode(1, object_path, execute=False)
        if not execute:
            return [load_command, mode_command]
        profile_path = Path(DEFAULT_PROFILE_PATH)
        profile_exists = profile_path.is_file()
        properties = {}
        for name in ("ProfilePath", "InterceptMode"):
            result = subprocess.run(
                [self.busctl, "get-property", "org.shadowblip.InputPlumber", object_path,
                 "org.shadowblip.Input.CompositeDevice", name],
                check=True, capture_output=True, text=True,
            )
            properties[name] = result.stdout.strip()
        if not profile_exists:
            LOGGER.error("InputPlumber default profile is missing: %s", DEFAULT_PROFILE_PATH)
            raise FileNotFoundError(DEFAULT_PROFILE_PATH)
        if properties["ProfilePath"] == f's "{DEFAULT_PROFILE_PATH}"' and properties["InterceptMode"] == "u 1":
            return []
        try:
            result = subprocess.run(load_command, check=True, capture_output=True, text=True)
        except subprocess.CalledProcessError as error:
            LOGGER.error(
                "InputPlumber LoadProfilePath failed object=%s rc=%s stdout=%r stderr=%r",
                object_path, error.returncode, error.stdout, error.stderr,
            )
            raise
        subprocess.run(mode_command, check=True)
        profile = subprocess.run(
            [self.busctl, "get-property", "org.shadowblip.InputPlumber", object_path,
             "org.shadowblip.Input.CompositeDevice", "ProfileName"],
            check=True, capture_output=True, text=True,
        ).stdout.strip()
        intercept = subprocess.run(
            [self.busctl, "get-property", "org.shadowblip.InputPlumber", object_path,
             "org.shadowblip.Input.CompositeDevice", "InterceptMode"],
            check=True, capture_output=True, text=True,
        ).stdout.strip()
        if profile != 's "Default"' or intercept != "u 1":
            raise RuntimeError(
                f"InputPlumber baseline verification failed: profile={profile!r} mode={intercept!r}"
            )
        return [load_command, mode_command]

    def composite_status(
        self, object_path: str | None = None, *, execute: bool = True
    ) -> tuple[str, tuple[str, ...]]:
        """Read one runtime composite identity and source paths."""
        object_path = object_path or self.object_path
        base = [
            self.busctl,
            "get-property",
            "org.shadowblip.InputPlumber",
            object_path,
            "org.shadowblip.Input.CompositeDevice",
        ]
        if not execute:
            return "", ()
        identity = subprocess.run(
            [*base, "PersistentId"], check=True, capture_output=True, text=True
        ).stdout
        sources = subprocess.run(
            [*base, "SourceDevicePaths"], check=True, capture_output=True, text=True
        ).stdout
        identity_values = re.findall(r'"([^"]*)"', identity)
        source_values = tuple(re.findall(r'"([^"]*)"', sources))
        return (identity_values[0] if identity_values else ""), source_values

    def runtime_composite_statuses(
        self, *, execute: bool = True
    ) -> dict[str, tuple[str, tuple[str, ...]]]:
        """Read the manager's current runtime composite topology."""
        if not execute:
            return {}
        tree = subprocess.run(
            [
                self.busctl,
                "tree",
                "org.shadowblip.InputPlumber",
            ],
            check=True,
            capture_output=True,
            text=True,
        ).stdout
        paths = list(self.gamepad_order())
        if not paths:
            paths = sorted(
                set(
                    re.findall(
                        r"(/org/shadowblip/InputPlumber/CompositeDevice\d+)", tree
                    )
                )
            )
        return {path: self.composite_status(path) for path in paths}

    def gamepad_order(self, *, execute: bool = True) -> tuple[str, ...]:
        """Return InputPlumber's current ordered composite handles."""
        if not execute:
            return ()
        result = subprocess.run(
            [
                self.busctl,
                "get-property",
                "org.shadowblip.InputPlumber",
                "/org/shadowblip/InputPlumber/Manager",
                "org.shadowblip.InputManager",
                "GamepadOrder",
            ],
            check=True,
            capture_output=True,
            text=True,
        ).stdout
        return tuple(re.findall(r'"(/org/shadowblip/InputPlumber/CompositeDevice\d+)"', result))

    def runtime_gamepad_slots(self, *, execute: bool = True) -> list[tuple[str, str, int]]:
        """Return ordered runtime handles and their current gamepad target indices."""
        if not execute:
            return []
        slots: list[tuple[str, str, int]] = []
        for runtime_path in self.gamepad_order():
            persistent_id, source_paths = self.composite_status(runtime_path)
            if not source_paths:
                continue
            targets = subprocess.run(
                [
                    self.busctl,
                    "get-property",
                    "org.shadowblip.InputPlumber",
                    runtime_path,
                    "org.shadowblip.Input.CompositeDevice",
                    "TargetDevices",
                ],
                check=True,
                capture_output=True,
                text=True,
            ).stdout
            gamepad_indices = [
                int(index)
                for index in re.findall(
                    r"/org/shadowblip/InputPlumber/devices/target/gamepad(\d+)", targets
                )
            ]
            if gamepad_indices:
                slots.append((runtime_path, persistent_id, gamepad_indices[0]))
        return slots
