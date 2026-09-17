"""Canonical emulation storage and platform/runtime configuration."""

import os
from dataclasses import dataclass
from pathlib import Path

from .paths import PATHS
from .platforms import load_platforms


ROM_ROOT = PATHS.rom_root
BIOS_ROOT = PATHS.bios_root


def current_rom_root() -> Path:
    return PATHS.rom_root


def current_bios_root() -> Path:
    return PATHS.bios_root


@dataclass(frozen=True, slots=True)
class RuntimePlatformDefinition:
    """Compatibility view; semantic platform data lives in platforms/*.toml."""
    platform_id: str
    label: str
    extensions: tuple[str, ...]
    runtime: str
    executable: Path
    core: Path | None = None
    bios_subdirectory: str | None = None

    @property
    def bios_root(self) -> Path:
        return current_bios_root() / (self.bios_subdirectory or self.platform_id)


# Import compatibility for the pre-registry local content adapter.
PlatformDefinition = RuntimePlatformDefinition


def _path(variable: str, default: str) -> Path:
    return Path(os.environ.get(variable, default)).expanduser()


_RUNTIME = {
    "retroarch": ("LULU_RETROARCH", "/usr/bin/retroarch"),
    "pcsx2": ("LULU_PCSX2", "/usr/bin/pcsx2-qt"),
    "dolphin": ("LULU_DOLPHIN", "/usr/bin/dolphin-emu"),
    "eden": ("LULU_EDEN", "/usr/bin/eden"),
}
_CORES = {"nes": ("LULU_NES_CORE", "/usr/lib/libretro/nestopia_libretro.so"),
          "genesis": ("LULU_GENESIS_CORE", "/usr/lib/libretro/genesis_plus_gx_libretro.so")}
PLATFORMS: dict[str, RuntimePlatformDefinition] = {}
for _id, _definition in load_platforms().items():
    _runtime = _definition.default_provider or ""
    _env, _default = _RUNTIME.get(_runtime, ("", "/usr/bin/false"))
    _core = _CORES.get(_id)
    PLATFORMS[_id] = RuntimePlatformDefinition(
        _id, _definition.name, _definition.content.extensions, _runtime,
        _path(_env, _default) if _env else Path(_default),
        _path(*_core) if _core else None,
        _definition.bios.subdir,
    )


def ensure_storage() -> None:
    """Create the documented roots without touching user firmware files."""
    rom_root, bios_root = current_rom_root(), current_bios_root()
    rom_root.mkdir(parents=True, exist_ok=True)
    bios_root.mkdir(parents=True, exist_ok=True)
    for definition in PLATFORMS.values():
        (rom_root / definition.platform_id).mkdir(exist_ok=True)
        definition.bios_root.mkdir(parents=True, exist_ok=True)
    (bios_root / "switch" / "keys").mkdir(parents=True, exist_ok=True)
    (bios_root / "switch" / "firmware").mkdir(parents=True, exist_ok=True)
