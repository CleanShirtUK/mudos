"""Provider launch adapters.

This module is deliberately small: core asks a provider for a launch shape;
provider-specific command-line knowledge stays here rather than in consoled.
"""

from pathlib import Path
from typing import Protocol

from ..local_content import LocalContentGame
from ..switch_provider import SwitchProvider
from .model import ProviderDefinition


class LaunchAdapter(Protocol):
    def arguments(self, game: LocalContentGame, executable: Path, core: Path | None,
                  config_root: Path | None, switch: SwitchProvider) -> tuple[str, ...]: ...


def launch_arguments(provider: ProviderDefinition, game: LocalContentGame,
                     executable: Path, core: Path | None, config_root: Path | None,
                     switch: SwitchProvider) -> tuple[str, ...]:
    content = getattr(game, "content_path", getattr(game, "install_dir", ""))
    if provider.provider_id == "retroarch":
        if core is None or not core.is_file():
            raise ValueError(f"runtime-core-missing: {game.platform}")
        prefix = ("--config", str(config_root / "retroarch.cfg")) if config_root else ()
        return (*prefix, "-L", str(core), content)
    if provider.provider_id == "dolphin":
        prefix = ("--user", str(config_root)) if config_root else ()
        # Dolphin 2606 removed the former -f CLI switch. --batch keeps the
        # normal Dolphin UI hidden while -e launches the selected game.
        return (*prefix, "--batch", "-e", content)
    if provider.provider_id == "pcsx2":
        # PCSX2 honors XDG_CONFIG_HOME; consoled supplies the provider's
        # persistent config directory in the child environment.
        prefix = ()
        return (*prefix, "-batch", "-fullscreen", "--", content)
    if provider.provider_id == "eden":
        return switch.launch_arguments(content)
    raise ValueError(f"provider has no local launch adapter: {provider.provider_id}")
