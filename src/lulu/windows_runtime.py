"""Shared UMU boundary for non-Steam Windows games."""

from __future__ import annotations

from pathlib import Path

from .paths import PATHS


class WindowsRuntime:
    """Describe a deterministic, provider-independent UMU launch environment."""

    executable = "umu-run"
    proton_path = "UMU-Latest"

    def __init__(self, game_id: str, *, store: str) -> None:
        self.game_id = game_id
        self.store = store
        self.prefix = PATHS.game_install_root / "Prefixes/umu" / store / game_id

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
        env = self.environment()
        return ["env", *[f"{key}={value}" for key, value in env.items()],
                "legendary", "launch", self.game_id, "--no-wine", "--wrapper", self.executable]

    def command(self, executable: Path, arguments: list[str]) -> list[str]:
        """Build the supervised UMU command from Legendary launch metadata."""
        env = self.environment()
        return ["env", *[f"{key}={value}" for key, value in env.items()],
                self.executable, str(executable), *arguments]
