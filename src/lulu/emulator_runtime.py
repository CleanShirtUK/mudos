"""Provider-neutral emulator launch intent boundary."""

from dataclasses import dataclass
from pathlib import Path

from .local_content import LocalContentGame


@dataclass(frozen=True, slots=True)
class EmulatorLaunchIntent:
    platform: str
    executable: str
    arguments: tuple[str, ...]


class EmulatorRuntimeAdapter:
    """Build backend launch intent without exposing runtime details to QML."""

    _retroarch_platforms = {"nes", "genesis"}

    def __init__(self, runtime_paths: dict[str, Path], core_paths: dict[str, Path] | None = None) -> None:
        self.runtime_paths = runtime_paths
        self.core_paths = core_paths or {}

    def launch_intent(self, game: LocalContentGame) -> EmulatorLaunchIntent:
        if not game.launchable:
            raise ValueError(f"content is not launchable: {game.reason}")
        executable = self.runtime_paths.get(game.platform)
        if executable is None or not executable.is_file():
            raise ValueError(f"runtime-missing: {game.platform}")
        if game.platform in self._retroarch_platforms:
            core = self.core_paths.get(game.platform)
            if core is None or not core.is_file():
                raise ValueError(f"runtime-core-missing: {game.platform}")
            content_path = getattr(game, "content_path", getattr(game, "install_dir", ""))
            arguments = ("-L", str(core), content_path)
        elif game.platform in {"wii", "ps2"}:
            content_path = getattr(game, "content_path", getattr(game, "install_dir", ""))
            arguments = ("-e", content_path) if game.platform == "wii" else (content_path,)
        elif game.platform == "switch":
            content_path = getattr(game, "content_path", getattr(game, "install_dir", ""))
            arguments = (content_path,)
        else:
            raise ValueError(f"unsupported-runtime: {game.platform}")
        return EmulatorLaunchIntent(game.platform, str(executable), arguments)
