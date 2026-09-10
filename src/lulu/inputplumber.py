"""Small command adapter for the documented InputPlumber D-Bus API."""

from dataclasses import dataclass
from pathlib import Path
import re
import subprocess

from .contracts import InputMode


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
        paths = sorted(
            set(
                re.findall(
                    r"(/org/shadowblip/InputPlumber/CompositeDevice\d+)", tree
                )
            )
        )
        return {path: self.composite_status(path) for path in paths}
