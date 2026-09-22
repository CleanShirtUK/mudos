"""Normalized Nintendo Switch content components.

Providers retain their own records; this module is the small common boundary
used to attach base games, updates, and DLC to one installed title.  A
component is never a catalogue game by itself.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import re
from typing import Mapping


class SwitchContentRole(StrEnum):
    BASE = "base"
    UPDATE = "update"
    DLC = "dlc"


@dataclass(frozen=True, slots=True)
class GameContentComponent:
    game_identity: str
    platform: str
    role: SwitchContentRole
    source: str
    source_id: str
    title_id: str | None = None
    version: str | None = None
    filename: str = ""
    path: str = ""
    installed: bool = False
    parent_game_id: str | None = None
    provider_job_id: str | None = None


def title_id(value: object) -> str | None:
    """Return a canonical Switch title ID, without guessing relationships."""
    match = re.search(r"(?<![0-9a-f])([0-9a-f]{16})(?![0-9a-f])", str(value or ""), re.I)
    return match.group(1).upper() if match else None


def parent_name(value: str) -> str:
    """Normalize a Switch filename for conservative same-title grouping."""
    value = re.sub(r"\.[^.]+$", "", value).replace("_", " ").replace(".", " ")
    value = re.sub(r"\[[^]]*\]", " ", value)
    value = re.sub(r"\b(update|patch|upgrade|dlc|addon|add-on|booster|expansion)\b.*$", "", value,
                   flags=re.I)
    return re.sub(r"\s+", " ", value).strip(" .-_\t").casefold()


def role_from_metadata(metadata: Mapping[str, object]) -> SwitchContentRole | None:
    """Use provider-declared type/category fields before release-name clues."""
    for key in ("role", "downloadType", "download_type", "category", "contentType", "content_type"):
        value = str(metadata.get(key) or "").casefold().strip()
        if value in {"base", "game", "rom", "full"}:
            return SwitchContentRole.BASE
        if value in {"update", "patch", "upgrade"}:
            return SwitchContentRole.UPDATE
        if value in {"dlc", "addon", "add-on", "downloadable-content"}:
            return SwitchContentRole.DLC
    return None


def role_from_unstructured_name(value: str) -> SwitchContentRole | None:
    """Conservative fallback for files whose provider omitted a content role."""
    lowered = value.casefold()
    update = bool(re.search(r"\b(update|patch|upgrade)\b", lowered))
    dlc = bool(re.search(r"\b(dlc|addon|add-on|booster|expansion)\b", lowered))
    # An NSP/XCI suffix identifies a container, not a base role; composite
    # releases commonly contain all three roles in one archive.
    base = bool(re.search(r"\b(base|game)\b", lowered))
    if sum((update, dlc, base)) > 1:
        return None
    if update:
        return SwitchContentRole.UPDATE
    if dlc:
        return SwitchContentRole.DLC
    if base:
        return SwitchContentRole.BASE
    return None


def canonical_identity(*, parent_game_id: object | None = None,
                       base_title_id: object | None = None,
                       fallback: str = "") -> str:
    """Resolve identity from authoritative parent metadata, then base title ID."""
    parent = str(parent_game_id or "").strip()
    if parent:
        return parent
    base = title_id(base_title_id)
    if base:
        return f"switch:{base}"
    if fallback.strip():
        return f"switch:title:{fallback.casefold().strip()}"
    raise ValueError("Switch component has no canonical parent identity")


def component_from_provider(*, source: str, source_id: object, parent_game_id: object,
                            metadata: Mapping[str, object], filename: str = "",
                            path: str = "", installed: bool = False) -> GameContentComponent:
    """Normalize one provider record without confusing downloader protocol with role."""
    role = role_from_metadata(metadata) or role_from_unstructured_name(filename or str(metadata.get("name", "")))
    if role is None:
        raise ValueError("Switch provider record has no unambiguous content role")
    identity = canonical_identity(parent_game_id=parent_game_id)
    return GameContentComponent(
        game_identity=identity, platform="switch", role=role, source=source,
        source_id=str(source_id), title_id=title_id(metadata.get("title_id") or metadata.get("titleId") or filename),
        version=str(metadata.get("version") or metadata.get("releaseVersion") or "") or None,
        filename=filename, path=path, installed=installed,
        parent_game_id=str(parent_game_id), provider_job_id=(
            str(metadata.get("provider_job_id") or metadata.get("downloadHash") or "") or None),
    )
