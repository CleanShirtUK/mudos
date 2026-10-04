"""Canonical emulation storage and platform/runtime configuration."""

import os
from dataclasses import dataclass
from pathlib import Path

from .paths import PATHS
from .platforms import load_platforms
from .platforms.model import SetupFileRequirement
from .eden_runtime import runtime_path


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
    setup_files: tuple[SetupFileRequirement, ...] = ()

    @property
    def bios_root(self) -> Path:
        return current_bios_root() / (self.bios_subdirectory or self.platform_id)


def _path(variable: str, default: str) -> Path:
    return Path(os.environ.get(variable, default)).expanduser()


_RUNTIME = {
    "retroarch": ("LULU_RETROARCH", "/usr/bin/retroarch"),
    # PCSX2 remains a release-owned Flatpak wrapper.
    "pcsx2": ("LULU_PCSX2", str(PATHS.install_root / "packaging" / "pcsx2-qt-flatpak")),
    "dolphin": ("LULU_DOLPHIN", "/usr/bin/dolphin-emu"),
    # Official, checksum-pinned Eden AppImage installed by the Mudos provider.
    "eden": ("LULU_EDEN", str(runtime_path())),
}
_CORES = {
    "nes": ("LULU_NES_CORE", "/usr/lib/libretro/nestopia_libretro.so"),
    "genesis": ("LULU_GENESIS_CORE", "/usr/lib/libretro/genesis_plus_gx_libretro.so"),
    "gba": ("LULU_GBA_CORE", "/usr/lib/libretro/mgba_libretro.so"),
    "gb": ("LULU_GB_CORE", "/usr/lib/libretro/gambatte_libretro.so"),
    "gbc": ("LULU_GBC_CORE", "/usr/lib/libretro/gambatte_libretro.so"),
    "snes": ("LULU_SNES_CORE", "/usr/lib/libretro/snes9x_libretro.so"),
    "nds": ("LULU_NDS_CORE", "/usr/lib/libretro/melonds_libretro.so"),
    "n64": ("LULU_N64_CORE", "/usr/lib/libretro/mupen64plus_next_libretro.so"),
    "psx": ("LULU_PSX_CORE", "/usr/lib/libretro/mednafen_psx_libretro.so"),
    "psp": ("LULU_PSP_CORE", "/usr/lib/libretro/ppsspp_libretro.so"),
    "arcade": ("LULU_ARCADE_CORE", "/usr/lib/libretro/fbneo_libretro.so"),
    "dreamcast": ("LULU_DREAMCAST_CORE", "/usr/lib/libretro/flycast_libretro.so"),
}
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
        _definition.setup_files,
    )

# Provider/platform spellings are normalized at the catalogue boundary. Keep
# aliases here so every consumer (including RomM acquisition) resolves to the
# same canonical runtime and storage identity.
PLATFORM_ALIASES = {
    "ngc": "gamecube", "gc": "gamecube", "nintendo-gamecube": "gamecube",
    "ps1": "psx", "playstation": "psx", "playstation-1": "psx",
    "sfc": "snes", "super-famicom": "snes",
    "megadrive": "genesis", "mega-drive": "genesis",
    "game-boy": "gb", "game-boy-color": "gbc", "game-boy-advance": "gba",
    "ds": "nds", "nintendo-ds": "nds",
}


def canonical_platform_id(platform_id: str) -> str:
    value = str(platform_id or "").strip().casefold().replace("_", "-")
    canonical = PLATFORM_ALIASES.get(value, value)
    return canonical if canonical in PLATFORMS else value


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
