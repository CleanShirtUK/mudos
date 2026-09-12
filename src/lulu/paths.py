"""Central paths for packaged Mudos content and mutable user files."""

from dataclasses import dataclass
import os
from pathlib import Path


def _path(variable: str, default: Path | str) -> Path:
    return Path(os.environ.get(variable, str(default))).expanduser()


@dataclass(frozen=True, slots=True)
class MudosPaths:
    """Filesystem contract for Mudos-owned data.

    The individual legacy environment variables remain supported so existing
    development and appliance configuration can use the current locations
    without moving data.
    """

    package_root: Path
    config_root: Path
    data_root: Path
    roms: Path
    bios: Path
    assets: Path
    artwork: Path
    recordings: Path
    captures: Path
    providers: Path
    state: Path
    cache: Path
    steam: Path

    @classmethod
    def from_environment(cls) -> "MudosPaths":
        data = _path("LULU_DATA_ROOT", "/var/lib/lulu")
        assets = _path("LULU_ASSETS_ROOT", data / "assets")
        return cls(
            package_root=_path("LULU_PACKAGE_ROOT", "/opt/lulu/current"),
            config_root=_path("LULU_CONFIG_ROOT", "/etc/lulu"),
            data_root=data,
            roms=_path("LULU_ROM_ROOT", data / "roms"),
            bios=_path("LULU_BIOS_ROOT", data / "bios"),
            assets=assets,
            artwork=_path("LULU_ARTWORK_CACHE", data / ".cache" / "lulu" / "steamgriddb"),
            recordings=_path("LULU_RECORDINGS_ROOT", data / "recordings"),
            captures=_path("LULU_CAPTURES_ROOT", data / "captures"),
            providers=_path("LULU_PROVIDERS_ROOT", data / "providers"),
            state=_path("LULU_STATE_ROOT", data / "state"),
            cache=_path("LULU_CACHE_ROOT", data / "cache"),
            steam=_path("LULU_STEAM_ROOT", data / ".local" / "share" / "Steam"),
        )

    @property
    def catalogue_db(self) -> Path:
        return _path("LULU_CATALOGUE_DB", self.data_root / ".local" / "share" / "lulu" / "catalogue.sqlite3")

    @property
    def metadata_cache(self) -> Path:
        return _path("LULU_METADATA_CACHE", self.data_root / ".cache" / "lulu" / "steamgriddb" / "metadata")

    @property
    def packaged_config(self) -> Path:
        return self.package_root / "config"

    @property
    def provider_config(self) -> Path:
        return self.config_root / "providers"

    @property
    def overrides(self) -> Path:
        return self.config_root / "overrides"


def mudos_paths() -> MudosPaths:
    """Return the current process' path contract."""
    return MudosPaths.from_environment()
