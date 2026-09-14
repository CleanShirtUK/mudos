"""Canonical Lulu user, configuration, data, and runtime paths."""

from dataclasses import dataclass
import os
from pathlib import Path


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

    @property
    def providers_root(self) -> Path:
        return self.config_root / "providers"

    @property
    def rom_root(self) -> Path:
        return self.home / "Games/ROMs"

    @property
    def bios_root(self) -> Path:
        return self.home / "Games/BIOS"

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
