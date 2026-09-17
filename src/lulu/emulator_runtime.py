"""Provider-neutral emulator launch intent boundary."""

from dataclasses import dataclass
from pathlib import Path

from .local_content import LocalContentGame
from .paths import PATHS
from .platforms import load_platforms
from .providers import ProviderRegistry, launch_arguments, load_providers
from .switch_provider import SwitchProvider


@dataclass(frozen=True, slots=True)
class EmulatorLaunchIntent:
    platform: str
    executable: str
    arguments: tuple[str, ...]
    provider: str = ""
    working_directory: str | None = None


class EmulatorRuntimeAdapter:
    """Build backend launch intent without exposing runtime details to QML."""

    _retroarch_platforms = {"nes", "genesis"}

    def __init__(self, runtime_paths: dict[str, Path], core_paths: dict[str, Path] | None = None,
                 switch_provider: SwitchProvider | None = None,
                 providers: ProviderRegistry | None = None,
                 config_root: Path | None = None) -> None:
        self.runtime_paths = runtime_paths
        self.core_paths = core_paths or {}
        self.switch_provider = switch_provider or SwitchProvider()
        self.providers = providers or load_providers()
        self.platforms = load_platforms()
        self.config_root = config_root

    @staticmethod
    def supports_provider_menu(platform: str) -> bool:
        return platform in EmulatorRuntimeAdapter._retroarch_platforms

    @staticmethod
    def open_provider_menu(platform: str) -> tuple[str, ...]:
        if not EmulatorRuntimeAdapter.supports_provider_menu(platform):
            raise ValueError(f"provider menu is unsupported: {platform}")
        return ("/usr/bin/retroarch", "--command", "MENU_TOGGLE")

    def launch_intent(
        self,
        game: LocalContentGame,
        device_indices: dict[int, int] | None = None,
    ) -> EmulatorLaunchIntent:
        if not game.launchable:
            raise ValueError(f"content is not launchable: {game.reason}")
        executable = self.runtime_paths.get(game.platform)
        if executable is None or not executable.is_file():
            raise ValueError(f"runtime-missing: {game.platform}")
        definition = self.platforms.get(game.platform)
        provider = self.providers.get(definition.default_provider or "")
        arguments = launch_arguments(provider, game, executable, self.core_paths.get(game.platform),
                                     self.config_root / provider.provider_id / "config" if self.config_root else None,
                                     self.switch_provider)
        if provider.provider_id == "eden" and device_indices is not None:
            arguments = self.switch_provider.launch_arguments(
                getattr(game, "content_path", getattr(game, "install_dir", "")),
                device_indices=device_indices,
            )
        return EmulatorLaunchIntent(game.platform, str(executable), arguments, provider.provider_id)
