"""Read-only Questarr metadata association for completed downloader jobs."""

from __future__ import annotations

from dataclasses import dataclass
import json
import time
from typing import Any

from .credential import SecretStore
from .questarr_reconciler import QuestarrApi, QuestarrApiError, QuestarrRateLimited


@dataclass(frozen=True, slots=True)
class QuestarrDownloadMetadata:
    game_id: str
    title: str
    platforms: tuple[str, ...]
    download_id: str
    download_hash: str
    release_title: str
    protocol: str
    status: str
    file_size: int | None = None

    def as_dict(self) -> dict[str, object]:
        return {
            "source": "questarr", "game_id": self.game_id, "title": self.title,
            "platforms": list(self.platforms), "download_id": self.download_id,
            "download_hash": self.download_hash, "release_title": self.release_title,
            "protocol": self.protocol, "status": self.status, "file_size": self.file_size,
        }


class QuestarrMetadataClient:
    """Use Questarr's supported API; never mutate its database or downloads."""

    def __init__(self, base_url: str = "http://127.0.0.1:5002", *, ttl: float = 30.0,
                 transport: Any | None = None) -> None:
        self.ttl = ttl
        self.api = QuestarrApi(base_url=base_url, opener=transport)
        self._expires = 0.0
        self._by_hash: dict[tuple[str, str], QuestarrDownloadMetadata] = {}

    def refresh(self) -> tuple[QuestarrDownloadMetadata, ...]:
        username = SecretStore().get("web/questarr", "username")
        password = SecretStore().get("web/questarr", "password")
        if not username or not password:
            return ()
        try:
            self.api.ensure_authenticated(username, password)
            games = self.api.get("/api/games")
            values: list[QuestarrDownloadMetadata] = []
            for game in games if isinstance(games, list) else ():
                if not isinstance(game, dict):
                    continue
                downloads = self.api.get(f"/api/games/{game.get('id')}/downloads")
                for item in downloads if isinstance(downloads, list) else ():
                    if not isinstance(item, dict):
                        continue
                    values.append(QuestarrDownloadMetadata(
                        str(game.get("id", "")), str(game.get("title", "")),
                        tuple(str(platform) for platform in game.get("platforms", ()) if platform),
                        str(item.get("id", "")), str(item.get("downloadHash", "")),
                        str(item.get("downloadTitle", "")), str(item.get("downloadType", "")),
                        str(item.get("status", "")),
                        int(item["fileSize"]) if item.get("fileSize") is not None else None,
                    ))
            self._by_hash = {(item.protocol, item.download_hash): item for item in values
                             if item.download_hash}
            self._expires = time.monotonic() + self.ttl
            return tuple(values)
        except (QuestarrApiError, OSError, TypeError, ValueError, json.JSONDecodeError):
            return ()

    def find(self, download_hash: str, protocol: str) -> QuestarrDownloadMetadata | None:
        if time.monotonic() >= self._expires:
            self.refresh()
        return self._by_hash.get((protocol.casefold(), str(download_hash)))
