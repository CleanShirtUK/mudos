"""Small durable registry for completed PC installation sources."""

from __future__ import annotations

from dataclasses import asdict
import json
from pathlib import Path

from .paths import PATHS
from .pc_install import PcInstallSource, PcSourceFile, PcSourceType


class PcInstallSourceStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or (PATHS.provider_root("lutris") / "pc-sources.json")

    def _load(self) -> dict[str, dict[str, object]]:
        try:
            value = json.loads(self.path.read_text())
            return value if isinstance(value, dict) else {}
        except (OSError, ValueError, json.JSONDecodeError):
            return {}

    def put(self, source: PcInstallSource) -> str:
        values = self._load()
        values[source.source_id] = asdict(source)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(values, sort_keys=True) + "\n")
        temporary.replace(self.path)
        return source.source_id

    def get(self, source_id: str) -> PcInstallSource | None:
        value = self._load().get(source_id)
        if not isinstance(value, dict):
            return None
        try:
            return PcInstallSourceStore.from_dict(value)
        except (KeyError, TypeError, ValueError):
            return None

    @staticmethod
    def from_dict(value: dict[str, object]) -> PcInstallSource:
        files = tuple(PcSourceFile(**item) for item in value.get("files", ()) if isinstance(item, dict))
        return PcInstallSource(
            canonical_game_id=str(value["canonical_game_id"]), title=str(value["title"]),
            provenance=str(value["provenance"]), source_type=PcSourceType(str(value["source_type"])),
            completed_path=str(value["completed_path"]), files=files,
            ready_to_install=bool(value.get("ready_to_install", False)),
            questarr_game_id=value.get("questarr_game_id"), questarr_download_id=value.get("questarr_download_id"),
            downloader_job_id=value.get("downloader_job_id"), downloader_hash=value.get("downloader_hash"),
            lutris_slug=value.get("lutris_slug"), lutris_installer_slug=value.get("lutris_installer_slug"),
        )
