"""Explicit-root local content adapter for bounded emulator validation."""

from dataclasses import dataclass
import hashlib
from pathlib import Path
import re

from .emulation import PLATFORMS, RuntimePlatformDefinition, current_bios_root
from .metadata import clean_local_title
from .switch_content import SwitchContentRole, parent_name, role_from_unstructured_name, title_id


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
    component_paths: tuple[str, ...] = ()
    component_roles: tuple[str, ...] = ()
    component_title_ids: tuple[str, ...] = ()
    mudos_owned: bool = True


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
            candidates = (platform_root.rglob("*") if platform == "psx" and platform_root.is_dir()
                          else platform_root.iterdir() if platform_root.is_dir() else ())
            contents = [content for content in sorted(candidates)
                        if content.suffix.lower() in definition.extensions and content.is_file()]
            playlist_members: set[Path] = set()
            if platform == "psx":
                for playlist in (path for path in contents if path.suffix.casefold() == ".m3u"):
                    try:
                        playlist_members.update((playlist.parent / line.strip()).resolve()
                                                for line in playlist.read_text(errors="replace").splitlines()
                                                if line.strip() and not line.lstrip().startswith("#"))
                    except OSError:
                        continue
                contents = [path for path in contents
                            if path.suffix.casefold() == ".m3u" or path.resolve() not in playlist_members]
            if platform == "switch":
                games.extend(self._list_switch(contents, root, definition))
                continue
            for content in contents:
                valid, reason = self._content_status(platform, content)
                runtime_ready = self.runtime_paths.get(platform, Path()).is_file()
                bios_ready = self._bios_ready(platform, definition)
                launchable = valid and runtime_ready and bios_ready
                if valid and not bios_ready:
                    reason = "bios-missing" if definition.bios_subdirectory is not None else "setup-files-missing"
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

    def _list_switch(self, contents: list[Path], root: Path,
                     definition: RuntimePlatformDefinition) -> list[LocalContentGame]:
        groups: dict[str, list[Path]] = {}
        for content in contents:
            key = parent_name(content.name)
            # A missing/ambiguous parent is deliberately left as its own game;
            # it must not be destructively merged with an unrelated title.
            groups.setdefault(key or content.name.casefold(), []).append(content)
        result: list[LocalContentGame] = []
        for key, members in groups.items():
            members.sort(key=lambda path: 0 if (role_from_unstructured_name(path.name) or SwitchContentRole.BASE)
                         == SwitchContentRole.BASE else 1)
            base = next((path for path in members
                         if (role_from_unstructured_name(path.name) or SwitchContentRole.BASE)
                         == SwitchContentRole.BASE), members[0])
            valid, reason = self._content_status("switch", base)
            runtime_ready = self.runtime_paths.get("switch", Path()).is_file()
            files_ready = self._bios_ready("switch", definition)
            launchable = valid and runtime_ready and files_ready
            if valid and not runtime_ready:
                reason = "runtime-missing"
            elif valid and not files_ready:
                reason = "setup-files-missing"
            roles = tuple((role_from_unstructured_name(path.name) or SwitchContentRole.BASE).value
                          for path in members)
            ids = tuple(value for value in (title_id(path.name) for path in members) if value)
            result.append(LocalContentGame(
                content_id=self._content_id("switch", Path(base).relative_to(root)),
                title=clean_local_title(base.name), platform="switch", content_path=str(base),
                launchable=launchable, install_state="installed" if valid else "invalid",
                reason=reason, runtime=definition.runtime, platform_label=definition.label,
                source_title=base.name, component_paths=tuple(str(path) for path in members),
                component_roles=roles, component_title_ids=ids, mudos_owned=True,
            ))
        return result

    def _bios_ready(self, platform: str, definition: RuntimePlatformDefinition) -> bool:
        if definition.bios_subdirectory is not None:
            paths = self.bios_paths.get(platform, ())
            if paths:
                if not any(path.is_file() for path in paths):
                    return False
            elif not (any(path.is_file() for path in definition.bios_root.iterdir())
                      if definition.bios_root.is_dir() else False):
                return False
        for requirement in definition.setup_files:
            if not requirement.required:
                continue
            target = current_bios_root() / requirement.destination
            files = {path.name.casefold() for path in target.rglob("*") if path.is_file()} if target.is_dir() else set()
            if (not files or any(name not in files for name in requirement.required_names)):
                return False
        return True

    @staticmethod
    def _content_id(platform: str, content: Path) -> str:
        digest = hashlib.sha256(str(content).encode()).hexdigest()[:16]
        return f"local:{platform}:{digest}"

    @staticmethod
    def _content_status(platform: str, content: Path) -> tuple[bool, str]:
        if platform == "psx" and content.suffix.casefold() == ".m3u":
            try:
                members = [(content.parent / line.strip()).resolve()
                           for line in content.read_text(errors="replace").splitlines()
                           if line.strip() and not line.lstrip().startswith("#")]
                if not members:
                    return False, "malformed-disc-playlist"
                root = content.parent.resolve()
                for member in members:
                    member.relative_to(root)
                    if member.suffix.casefold() != ".cue" or not member.is_file():
                        return False, "missing-disc-image"
                    valid, reason = LocalContentProvider._cue_status(member)
                    if not valid:
                        return False, reason
                return True, "ready"
            except (OSError, ValueError):
                return False, "malformed-disc-playlist"
        if platform not in {"ps1", "psx", "ps2"} or content.suffix.lower() != ".cue":
            return True, "ready"
        if platform == "ps2":
            for line in content.read_text(errors="replace").splitlines():
                match = re.match(r"\s*FILE\s+\"([^\"]+)\"", line, re.IGNORECASE)
                if match:
                    referenced = content.parent / match.group(1)
                    return (referenced.is_file(), "ready" if referenced.is_file() else "missing-disc-image")
            return False, "malformed-cue"
        return LocalContentProvider._cue_status(content)

    @staticmethod
    def _cue_status(content: Path) -> tuple[bool, str]:
        if content.suffix.lower() != ".cue":
            return True, "ready"
        references = []
        for line in content.read_text(errors="replace").splitlines():
            match = re.match(r"\s*FILE\s+(?:\"([^\"]+)\"|([^\s]+))", line, re.IGNORECASE)
            if match:
                references.append(content.parent / (match.group(1) or match.group(2)))
        if not references:
            return False, "malformed-cue"
        return (all(path.is_file() for path in references),
                "ready" if all(path.is_file() for path in references) else "missing-disc-image")
