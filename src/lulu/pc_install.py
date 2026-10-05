"""Provider-neutral PC installation sources and conservative inspection."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
import os
import re
from typing import Iterable

from .paths import PATHS


class PcSourceType(StrEnum):
    WINDOWS_INSTALLER = "windows-installer"
    MSI_INSTALLER = "msi-installer"
    DISC_IMAGE = "disc-image"
    ARCHIVE = "archive"
    DIRECTORY = "directory"
    MULTI_PART_MEDIA = "multi-part-media"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class PcSourceFile:
    path: str
    relative_path: str
    size_bytes: int
    kind: str


@dataclass(frozen=True, slots=True)
class PcInstallSource:
    """A completed, uninstalled PC payload and its provenance."""

    canonical_game_id: str
    title: str
    provenance: str  # acquisition source or manual
    source_type: PcSourceType
    completed_path: str
    files: tuple[PcSourceFile, ...] = ()
    ready_to_install: bool = False
    acquisition_id: str | None = None
    downloader_job_id: str | None = None
    downloader_hash: str | None = None
    lutris_slug: str | None = None
    lutris_installer_slug: str | None = None

    @property
    def source_id(self) -> str:
        if self.acquisition_id:
            return f"acquisition:{self.acquisition_id}"
        if self.lutris_slug and self.lutris_installer_slug:
            return f"lutris-recipe:{self.lutris_slug}:{self.lutris_installer_slug}"
        return f"{self.provenance}:{self.completed_path}"


@dataclass(frozen=True, slots=True)
class RecipeFileRequirement:
    file_id: str
    filename: str
    url: str = ""
    required: bool = True
    label: str = ""

    @property
    def local(self) -> bool:
        return self.url.casefold().startswith("n/a") or not self.url


@dataclass(frozen=True, slots=True)
class RecipeMatch:
    installer_slug: str
    game_slug: str
    title: str
    score: int
    requirements: tuple[RecipeFileRequirement, ...] = ()


_ARCHIVES = {".zip", ".7z", ".rar", ".tar", ".gz", ".bz2", ".xz"}
_DISC_IMAGES = {".iso", ".cue", ".img", ".bin"}
_EXECUTABLES = {".exe", ".msi"}
_PART_RE = re.compile(r"(?:\.part\d+|\.r\d{2,3})\.rar$", re.IGNORECASE)


def canonical_lutris_root(game_slug: str) -> Path:
    """Return the only payload root allowed for Mudos-managed Lutris games."""
    safe = re.sub(r"[^A-Za-z0-9._-]+", "-", game_slug.strip()).strip(".-")
    if not safe:
        raise ValueError("Lutris game slug is empty")
    return PATHS.game_install_root / "Executables" / "lutris" / safe


def _kind(path: Path) -> str:
    suffix = path.suffix.casefold()
    if suffix == ".exe":
        return "exe"
    if suffix == ".msi":
        return "msi"
    if suffix in _DISC_IMAGES:
        return "disc-image"
    if suffix in _ARCHIVES:
        return "archive"
    return "file"


def _files(root: Path, *, limit: int = 4096) -> tuple[PcSourceFile, ...]:
    values: list[PcSourceFile] = []
    candidates = (root.rglob("*") if root.is_dir() else (root,))
    for path in candidates:
        if len(values) >= limit or not path.is_file() or path.is_symlink():
            continue
        try:
            relative = path.relative_to(root if root.is_dir() else path.parent)
            size = path.stat().st_size
        except OSError:
            continue
        values.append(PcSourceFile(str(path), relative.as_posix(), size, _kind(path)))
    return tuple(sorted(values, key=lambda item: item.relative_path.casefold()))


def inspect_pc_source(path: Path, *, canonical_game_id: str, title: str,
                      provenance: str = "manual", acquisition_id: str | None = None,
                      downloader_job_id: str | None = None,
                      downloader_hash: str | None = None) -> PcInstallSource:
    """Inspect a completed payload without executing or mounting anything."""
    path = path.expanduser()
    if not path.exists():
        raise FileNotFoundError(path)
    if path.is_symlink():
        raise ValueError("PC installation sources may not be symlinks")
    files = _files(path)
    suffix = path.suffix.casefold()
    if path.is_dir():
        source_type = PcSourceType.DIRECTORY
    elif _PART_RE.search(path.name):
        source_type = PcSourceType.MULTI_PART_MEDIA
    elif suffix == ".exe":
        source_type = PcSourceType.WINDOWS_INSTALLER
    elif suffix == ".msi":
        source_type = PcSourceType.MSI_INSTALLER
    elif suffix in _DISC_IMAGES:
        source_type = PcSourceType.DISC_IMAGE
    elif suffix in _ARCHIVES:
        source_type = PcSourceType.ARCHIVE
    else:
        source_type = PcSourceType.UNKNOWN
    ready = bool(files) and source_type is not PcSourceType.UNKNOWN
    return PcInstallSource(
        canonical_game_id=canonical_game_id, title=title, provenance=provenance,
        source_type=source_type, completed_path=str(path), files=files,
        ready_to_install=ready, acquisition_id=acquisition_id,
        downloader_job_id=downloader_job_id,
        downloader_hash=downloader_hash,
    )


def recipe_requirements(installer: dict[str, object]) -> tuple[RecipeFileRequirement, ...]:
    script = installer.get("script")
    if not isinstance(script, dict):
        return ()
    result: list[RecipeFileRequirement] = []
    for item in script.get("files", []):
        if not isinstance(item, dict):
            continue
        for file_id, metadata in item.items():
            if isinstance(metadata, dict):
                url = str(metadata.get("url", ""))
                local = url.casefold().startswith("n/a") or not url
                filename = str(metadata.get("filename") or
                                (file_id if local else Path(url.split("?", 1)[0]).name) or file_id)
                label = str(metadata.get("description") or filename)
                required = not bool(metadata.get("optional", False))
            elif isinstance(metadata, str):
                url = metadata
                local = url.casefold().startswith("n/a") or not url
                filename = str(file_id) if local else (Path(url.split("?", 1)[0]).name or str(file_id))
                label = url.partition(":")[2].strip() if local and ":" in url else filename
                required = True
            else:
                continue
            result.append(RecipeFileRequirement(str(file_id), filename, url, required, label))
    return tuple(result)


def match_required_files(source: PcInstallSource,
                         requirements: Iterable[RecipeFileRequirement]) -> dict[str, str]:
    """Map local Lutris requirements only when every mapping is deterministic."""
    mapping: dict[str, str] = {}
    for requirement in requirements:
        if not requirement.local or not requirement.required:
            continue
        wanted = Path(requirement.filename).name.casefold()
        matches = [item for item in source.files
                   if Path(item.relative_path).name.casefold() == wanted]
        if not matches:
            raise ValueError(f"required local file is missing: {requirement.filename}")
        if len(matches) > 1:
            raise ValueError(f"required local file is ambiguous: {requirement.filename}")
        mapping[requirement.file_id] = matches[0].path
    return mapping
