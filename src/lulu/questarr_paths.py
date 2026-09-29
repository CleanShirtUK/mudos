"""Narrow Questarr container projections for Mudos-owned filesystems."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path

from .paths import PATHS, MudosPaths
from .platforms import load_platforms


QUESTARR_DOWNLOAD_ROOT = Path("/home/lulu/Games/.acquisition/usenet")
QUESTARR_LIBRARY_ROOT = Path("/data")
# Questarr's appliance-owned v1.4.2 patch maps successful NZBGet DestDir to
# downloadDir. Runtime attestation below prevents enabling import on an
# unpatched or unverified container.
QUESTARR_AUTO_IMPORT_SOURCE_SUPPORTED = True
QUESTARR_IMAGE_REF_PATH = Path("/var/lib/lulu-questarr/questarr-image-ref")
QUESTARR_RUNTIME_IMAGE_ATTESTATION = Path("/run/lulu-questarr/verified-image-id")


@dataclass(frozen=True, slots=True)
class QuestarrLibraryMount:
    platform_id: str
    host_path: Path
    container_path: Path


def questarr_library_mounts(paths: MudosPaths = PATHS) -> tuple[QuestarrLibraryMount, ...]:
    """Map configured Mudos platform roots to Questarr's native folder names."""
    definitions = load_platforms()
    mounts: list[QuestarrLibraryMount] = []
    seen: set[str] = set()
    for platform_id, definition in definitions.items():
        library_dir = definition.questarr_library_dir
        if not library_dir:
            continue
        key = library_dir.casefold()
        if key in seen:
            raise ValueError(f"duplicate Questarr library directory: {library_dir}")
        seen.add(key)
        host_path = definition.content_root(paths.rom_root)
        mounts.append(QuestarrLibraryMount(
            platform_id, host_path, QUESTARR_LIBRARY_ROOT / library_dir))
    return tuple(mounts)


def questarr_completed_download_path(
    host_path: str | Path,
    *,
    paths: MudosPaths = PATHS,
    container_download_root: Path = QUESTARR_DOWNLOAD_ROOT,
) -> str | None:
    """Translate an existing successful Usenet output into Questarr's view.

    Only a path beneath the configured completed root is eligible. Active jobs,
    failed jobs, missing output and paths outside the read-only/writable
    completed-output projection are deliberately not projected.
    """
    try:
        complete_root = paths.usenet_complete_root.resolve(strict=True)
        source_root = paths.usenet_root.resolve(strict=True)
        candidate = Path(host_path).resolve(strict=True)
        relative_to_complete = candidate.relative_to(complete_root)
        relative_to_source = candidate.relative_to(source_root)
    except (OSError, ValueError, RuntimeError):
        return None
    if not relative_to_complete.parts or not candidate.exists():
        return None
    return str(container_download_root / relative_to_source)


def questarr_post_processing_readiness(paths: MudosPaths = PATHS) -> tuple[bool, str]:
    """Require real writable projections and an upstream-consumable source path."""
    mounts = questarr_library_mounts(paths)
    if not mounts:
        return False, "no Questarr platform library projections are configured"
    for mount in mounts:
        try:
            if not mount.host_path.is_dir() or not os.access(mount.host_path, os.W_OK):
                return False, f"Questarr library projection is not writable: {mount.platform_id}"
        except OSError:
            return False, f"Questarr library projection cannot be inspected: {mount.platform_id}"
    try:
        if not paths.usenet_complete_root.is_dir():
            return False, "completed Usenet output is not mounted"
        if not os.access(paths.usenet_complete_root, os.R_OK | os.X_OK):
            return False, "completed Usenet output is not readable by Questarr"
    except OSError:
        return False, "completed Usenet output cannot be inspected"
    if not QUESTARR_AUTO_IMPORT_SOURCE_SUPPORTED:
        return False, "Questarr v1.4.2 does not project NZBGet DestDir as downloadDir"
    try:
        image_ref = QUESTARR_IMAGE_REF_PATH.read_text(encoding="ascii").strip()
        running_image = QUESTARR_RUNTIME_IMAGE_ATTESTATION.read_text(encoding="ascii").strip()
    except OSError:
        return False, "patched Questarr image has not passed its runtime path verification"
    expected_digest = image_ref.rsplit("@", 1)[-1] if "@" in image_ref else ""
    if not expected_digest.startswith("sha256:") or expected_digest != running_image:
        return False, "running Questarr image does not match the verified downstream image pin"
    return True, "Questarr library and completed-download projections are ready"
