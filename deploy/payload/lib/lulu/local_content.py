"""Explicit-root local content adapter for bounded emulator validation."""

from dataclasses import dataclass
import hashlib
from pathlib import Path
import re

from .emulation import PLATFORMS, PlatformDefinition
from .metadata import clean_local_title


@dataclass(frozen=True, slots=True)
class LocalContentGame:
    content_id: str
    title: str
    platform: str
    content_path: str
    launchable: bool
    install_state: str
    reason: str
    runtime: str = ""
    platform_label: str = ""
    source_title: str = ""


class LocalContentProvider:
    """Scan only a caller-supplied fixture root; never discover host paths."""

    def __init__(
        self,
        runtime_paths: dict[str, Path] | None = None,
        bios_paths: dict[str, tuple[Path, ...]] | None = None,
    ) -> None:
        self.runtime_paths = ({key: definition.executable for key, definition in PLATFORMS.items()}
                              if runtime_paths is None else runtime_paths)
        self.bios_paths = {} if bios_paths is None else bios_paths

    def list_installed(self, root: Path) -> list[LocalContentGame]:
        if not root.is_dir():
            return []
        games: list[LocalContentGame] = []
        for platform, definition in PLATFORMS.items():
            platform_root = root / platform
            for content in sorted(platform_root.iterdir() if platform_root.is_dir() else ()):
                if content.suffix.lower() not in definition.extensions or not content.is_file():
                    continue
                valid, reason = self._content_status(platform, content)
                runtime_ready = self.runtime_paths.get(platform, Path()).is_file()
                bios_ready = self._bios_ready(platform, definition)
                launchable = valid and runtime_ready and bios_ready
                if valid and not bios_ready:
                    reason = "bios-missing"
                if valid and not runtime_ready:
                    reason = "runtime-missing"
                games.append(
                    LocalContentGame(
                        content_id=self._content_id(platform, content.relative_to(root)),
                        title=clean_local_title(content.name),
                        platform=platform,
                        content_path=str(content),
                        launchable=launchable,
                        install_state="installed" if valid else "invalid",
                        reason=reason,
                        runtime=definition.runtime,
                        platform_label=definition.label,
                        source_title=content.name,
                    )
                )
        return sorted(games, key=lambda game: game.title.casefold())

    def _bios_ready(self, platform: str, definition: PlatformDefinition) -> bool:
        if definition.bios_subdirectory is None:
            return True
        paths = self.bios_paths.get(platform, ())
        if paths:
            return any(path.is_file() for path in paths)
        return any(path.is_file() for path in definition.bios_root.iterdir()) if definition.bios_root.is_dir() else False

    @staticmethod
    def _content_id(platform: str, content: Path) -> str:
        digest = hashlib.sha256(str(content).encode()).hexdigest()[:16]
        return f"local:{platform}:{digest}"

    @staticmethod
    def _content_status(platform: str, content: Path) -> tuple[bool, str]:
        if platform != "ps2" or content.suffix.lower() != ".cue":
            return True, "ready"
        for line in content.read_text(errors="replace").splitlines():
            match = re.match(r"\s*FILE\s+\"([^\"]+)\"", line, re.IGNORECASE)
            if match:
                referenced = content.parent / match.group(1)
                return (referenced.is_file(), "ready" if referenced.is_file() else "missing-disc-image")
        return False, "malformed-cue"
