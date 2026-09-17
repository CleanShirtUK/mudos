"""Canonical Lulu user, configuration, data, and runtime paths."""

from dataclasses import dataclass
import os
from pathlib import Path
import json


def _xdg(name: str, fallback: Path) -> Path:
    value = os.environ.get(name)
    return Path(value).expanduser() if value else fallback


@dataclass(frozen=True, slots=True)
class MudosPaths:
    """The single path contract shared by Lulu and its providers."""

    home: Path
    config_home: Path
    data_home: Path
    cache_home: Path
    runtime_root: Path

    @classmethod
    def current(cls) -> "MudosPaths":
        home = Path.home()
        return cls(
            home=home,
            config_home=_xdg("XDG_CONFIG_HOME", home / ".config"),
            data_home=_xdg("XDG_DATA_HOME", home / ".local/share"),
            cache_home=_xdg("XDG_CACHE_HOME", home / ".cache"),
            runtime_root=Path(os.environ.get("LULU_RUNTIME_ROOT", "/run/lulu")),
        )

    @property
    def config_root(self) -> Path:
        return self.config_home / "lulu"

    @property
    def data_root(self) -> Path:
        return self.data_home / "lulu"

    def _storage_root(self, kind: str, fallback: Path) -> Path:
        """Resolve a configured mounted target without using /dev names."""
        state_path = self.config_root / "storage-targets.json"
        try:
            state = json.loads(state_path.read_text())
            configured = state.get(f"{kind}_path")
            if configured:
                return Path(configured) / "Mudos"
        except (OSError, ValueError, json.JSONDecodeError):
            pass
        return fallback

    @property
    def game_install_root(self) -> Path:
        return self._storage_root("game", self.home / "Games")

    @property
    def emulation_root(self) -> Path:
        return self._storage_root("emulation", self.home / "Games")

    @property
    def providers_root(self) -> Path:
        return self.config_root / "providers"

    @property
    def plugins_root(self) -> Path:
        return Path(os.environ.get("LULU_PLUGIN_ROOT", self.config_root / "plugins")).expanduser()

    @property
    def platforms_root(self) -> Path:
        return self.config_root / "platforms"

    @property
    def assets_root(self) -> Path:
        return self.config_root / "assets"

    def provider_root(self, provider_id: str) -> Path:
        """Persistent state owned by one provider."""
        return self.providers_root / provider_id

    @property
    def install_root(self) -> Path:
        configured = os.environ.get("LULU_INSTALL_ROOT")
        return Path(configured).expanduser() if configured else Path(__file__).resolve().parents[2]

    def provider_config_root(self, provider_id: str) -> Path:
        return self.provider_root(provider_id) / "config"

    @property
    def rom_root(self) -> Path:
        return self.emulation_root / "ROMs"

    @property
    def bios_root(self) -> Path:
        return self.emulation_root / "BIOS"

    @property
    def steam_library_root(self) -> Path:
        return self.game_install_root / "Executables/steam"

    @property
    def steamcmd_root(self) -> Path:
        """Mudos-owned SteamCMD runtime, separate from user Steam state."""
        return Path(os.environ.get("LULU_STEAMCMD_ROOT", "/var/lib/lulu/steamcmd"))

    @property
    def steamcmd_executable(self) -> Path:
        return self.steamcmd_root / "steamcmd.sh"

    @property
    def recordings(self) -> Path:
        return self.home / "Recordings"

    @property
    def replays(self) -> Path:
        return self.home / "Replays"

    @property
    def screenshots(self) -> Path:
        return self.home / "Screenshots"

    @property
    def artwork_cache(self) -> Path:
        return self.cache_home / "lulu/steamgriddb"

    @property
    def romm_artwork_cache(self) -> Path:
        return self.cache_home / "lulu/romm/artwork"

    @property
    def metadata_cache(self) -> Path:
        return self.cache_home / "lulu/steamgriddb/metadata"

    @property
    def catalogue_db(self) -> Path:
        return self.data_root / "catalogue.sqlite3"


PATHS = MudosPaths.current()
