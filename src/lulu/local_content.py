"""Explicit-root local content adapter for bounded emulator validation."""

from dataclasses import dataclass
import hashlib
from pathlib import Path
import re


@dataclass(frozen=True, slots=True)
class LocalContentGame:
    content_id: str
    title: str
    platform: str
    content_path: str
    launchable: bool
    install_state: str
    reason: str


class LocalContentProvider:
    """Scan only a caller-supplied fixture root; never discover host paths."""

    _extensions = {
        "nes": (".nes",),
        "genesis": (".bin",),
        "ps2": (".cue", ".iso"),
        "wii": (".rvz",),
        "switch": (".nsp",),
    }

    def __init__(
        self,
        runtime_paths: dict[str, Path] | None = None,
        bios_paths: dict[str, tuple[Path, ...]] | None = None,
    ) -> None:
        self.runtime_paths = runtime_paths or {}
        self.bios_paths = bios_paths or {}

    def list_installed(self, root: Path) -> list[LocalContentGame]:
        if not root.is_dir():
            return []
        games: list[LocalContentGame] = []
        for platform, extensions in self._extensions.items():
            platform_root = root / platform
            for content in sorted(platform_root.iterdir() if platform_root.is_dir() else ()):
                if content.suffix.lower() not in extensions or not content.is_file():
                    continue
                valid, reason = self._content_status(platform, content)
                runtime_ready = self.runtime_paths.get(platform, Path()).is_file()
                bios_ready = self._bios_ready(platform)
                launchable = valid and runtime_ready and bios_ready
                if valid and not bios_ready:
                    reason = "bios-missing"
                if valid and not runtime_ready:
                    reason = "runtime-missing"
                games.append(
                    LocalContentGame(
                        content_id=self._content_id(platform, content.relative_to(root)),
                        title=self._title(content),
                        platform=platform,
                        content_path=str(content),
                        launchable=launchable,
                        install_state="installed" if valid else "invalid",
                        reason=reason,
                    )
                )
        return sorted(games, key=lambda game: game.title.casefold())

    def _bios_ready(self, platform: str) -> bool:
        if platform != "ps2":
            return True
        return any(path.is_file() for path in self.bios_paths.get(platform, ()))

    @staticmethod
    def _title(content: Path) -> str:
        return re.sub(r"\s+", " ", content.stem.replace("_", " ")).strip()

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
