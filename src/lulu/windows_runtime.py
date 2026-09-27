"""Shared UMU boundary for non-Steam Windows games."""

from __future__ import annotations

from pathlib import Path
import shutil

from .paths import PATHS


class WindowsRuntime:
    """Describe a deterministic, provider-independent UMU launch environment."""

    executable = "umu-run"
    proton_path = "UMU-Latest"

    def __init__(self, game_id: str, *, store: str) -> None:
        self.game_id = game_id
        self.store = store
        self.prefix = PATHS.game_install_root / "Prefixes/umu" / store / game_id

    @classmethod
    def runtime_executable(cls) -> str:
        executable = shutil.which(cls.executable)
        if executable is None:
            raise RuntimeError(
                "UMU runtime is unavailable: install the umu-launcher package to provide umu-run"
            )
        return executable

    def environment(self) -> dict[str, str]:
        self.prefix.mkdir(parents=True, exist_ok=True)
        return {
            "WINEPREFIX": str(self.prefix),
            "STORE": self.store,
            "GAMEID": "umu-default",
            "PROTONPATH": self.proton_path,
        }

    def legendary_wrapper_command(self) -> list[str]:
        """Return an env-prefixed Legendary command using UMU as its wrapper."""
        runtime_executable = self.runtime_executable()
        env = self.environment()
        return ["env", *[f"{key}={value}" for key, value in env.items()],
                "legendary", "launch", self.game_id, "--no-wine", "--wrapper", runtime_executable]

    def command(self, executable: Path, arguments: list[str]) -> list[str]:
        """Build the supervised UMU command from Legendary launch metadata."""
        runtime_executable = self.runtime_executable()
        env = self.environment()
        return ["env", *[f"{key}={value}" for key, value in env.items()],
                runtime_executable, str(executable), *arguments]
