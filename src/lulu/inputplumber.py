"""Small command adapter for the documented InputPlumber D-Bus API."""

from dataclasses import dataclass
from pathlib import Path
import subprocess

from .contracts import InputMode


@dataclass(frozen=True, slots=True)
class InputPlumberClient:
    """controllerd-side client; InputPlumber remains runtime authority."""

    object_path: str
    profile_paths: dict[InputMode, Path]
    busctl: str = "busctl"

    def load_mode(self, mode: InputMode, *, execute: bool = True) -> list[str]:
        command = [
            self.busctl,
            "call",
            "org.shadowblip.InputPlumber",
            self.object_path,
            "org.shadowblip.Input.CompositeDevice",
            "LoadProfilePath",
            "s",
            str(self.profile_paths[mode]),
        ]
        if execute:
            subprocess.run(command, check=True)
        return command

    def set_intercept_mode(self, mode: int, *, execute: bool = True) -> list[str]:
        if mode not in range(4):
            raise ValueError("InputPlumber InterceptMode must be between 0 and 3")
        command = [
            self.busctl,
            "set-property",
            "org.shadowblip.InputPlumber",
            self.object_path,
            "org.shadowblip.Input.CompositeDevice",
            "InterceptMode",
            "u",
            str(mode),
        ]
        if execute:
            subprocess.run(command, check=True)
        return command
