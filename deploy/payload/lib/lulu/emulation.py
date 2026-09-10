"""Canonical emulation storage and platform/runtime configuration."""

from dataclasses import dataclass
import os
from pathlib import Path


ROM_ROOT = Path(os.environ.get("LULU_ROM_ROOT", "/var/lib/lulu/roms")).expanduser()
BIOS_ROOT = Path(os.environ.get("LULU_BIOS_ROOT", "/var/lib/lulu/bios")).expanduser()


@dataclass(frozen=True, slots=True)
class PlatformDefinition:
    platform_id: str
    label: str
    extensions: tuple[str, ...]
    runtime: str
    executable: Path
    core: Path | None = None
    bios_subdirectory: str | None = None

    @property
    def bios_root(self) -> Path:
        return BIOS_ROOT / (self.bios_subdirectory or self.platform_id)


def _path(variable: str, default: str) -> Path:
    return Path(os.environ.get(variable, default)).expanduser()


PLATFORMS: dict[str, PlatformDefinition] = {
    "nes": PlatformDefinition(
        "nes", "Nintendo Entertainment System", (".nes",), "retroarch",
        _path("LULU_RETROARCH", "/usr/bin/retroarch"),
        _path("LULU_NES_CORE", "/usr/lib/libretro/nestopia_libretro.so"),
    ),
    "genesis": PlatformDefinition(
        "genesis", "Sega Genesis", (".bin",), "retroarch",
        _path("LULU_RETROARCH", "/usr/bin/retroarch"),
        _path("LULU_GENESIS_CORE", "/usr/lib/libretro/genesis_plus_gx_libretro.so"),
    ),
    "ps2": PlatformDefinition(
        "ps2", "PlayStation 2", (".cue", ".iso"), "pcsx2",
        _path("LULU_PCSX2", "/usr/bin/pcsx2-qt"), bios_subdirectory="ps2",
    ),
    "wii": PlatformDefinition(
        "wii", "Wii", (".rvz",), "dolphin",
        _path("LULU_DOLPHIN", "/usr/bin/dolphin-emu"),
    ),
    "switch": PlatformDefinition(
        "switch", "Nintendo Switch", (".nsp",), "yuzu",
        _path("LULU_YUZU", "/usr/bin/yuzu"),
    ),
}


def ensure_storage() -> None:
    """Create the documented roots without touching user firmware files."""
    ROM_ROOT.mkdir(parents=True, exist_ok=True)
    BIOS_ROOT.mkdir(parents=True, exist_ok=True)
    for definition in PLATFORMS.values():
        (ROM_ROOT / definition.platform_id).mkdir(exist_ok=True)
        definition.bios_root.mkdir(parents=True, exist_ok=True)
