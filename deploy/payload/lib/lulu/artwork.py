"""Optional artwork enrichment behind the catalogue boundary."""

from dataclasses import dataclass, field
import hashlib
import json
import logging
import os
from pathlib import Path
import urllib.error
import urllib.parse
import urllib.request


@dataclass(slots=True)
class SteamGridDBArtwork:
    api_key: str | None = None
    cache_dir: Path | None = None
    timeout: float = 4.0
    _logger: logging.Logger = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self.api_key = self.api_key or os.environ.get("LULU_STEAMGRIDDB_API_KEY")
        self.cache_dir = self.cache_dir or Path(os.environ.get(
            "LULU_ARTWORK_CACHE", "~/.cache/lulu/steamgriddb"
        )).expanduser()
        self._logger = logging.getLogger("lulu.artwork")

    def enrich(self, games: list[object]) -> dict[str, str]:
        if not self.api_key:
            return {}
        resolved: dict[str, str] = {}
        for game in games:
            if bool(getattr(game, "artwork_suppressed", False)):
                continue
            game_id = str(getattr(game, "game_id"))
            artwork = self._resolve(
                game_id, str(getattr(game, "provider")),
                str(getattr(game, "provider_id")), str(getattr(game, "title")),
                str(getattr(game, "metadata_provider", "")),
                str(getattr(game, "metadata_game_id", "")),
            )
            if artwork:
                resolved[game_id] = artwork
        return resolved

    def _resolve(self, game_id: str, provider: str, provider_id: str, title: str,
                 metadata_provider: str = "", metadata_game_id: str = "") -> str:
        identity = f"{metadata_provider}:{metadata_game_id}" if metadata_provider and metadata_game_id else game_id
        key = hashlib.sha256(identity.encode()).hexdigest()
        metadata_path = self.cache_dir / f"{key}.json"
        try:
            metadata = json.loads(metadata_path.read_text()) if metadata_path.exists() else {}
            image_url = str(metadata.get("image_url", ""))
            if not image_url:
                image_url = self._find_image(provider, provider_id, title, metadata_provider, metadata_game_id)
                self._write_json(metadata_path, {"image_url": image_url, "identity": identity})
            if not image_url:
                return ""
            image_path = self.cache_dir / f"{key}.jpg"
            if not image_path.exists():
                self._download(image_url, image_path)
            return image_path.as_uri() if image_path.exists() else ""
        except (OSError, ValueError, urllib.error.URLError, TimeoutError) as error:
            self._logger.warning("artwork enrichment failed for %s: %s", game_id, error)
            return ""

    def _find_image(self, provider: str, provider_id: str, title: str,
                    metadata_provider: str = "", metadata_game_id: str = "") -> str:
        if metadata_provider == "steamgriddb" and metadata_game_id:
            path = f"/v2/grids/game/{metadata_game_id}"
        elif provider == "steam" and provider_id.isdecimal():
            path = f"/v2/grids/steam/{provider_id}"
        else:
            return ""
        result = self._request_json(path + "?dimensions=600x900")
        return next((str(item.get("url", "")) for item in result.get("data", []) if item.get("url")), "")

    def _request_json(self, path: str) -> dict[str, object]:
        request = urllib.request.Request(
            "https://www.steamgriddb.com/api" + path,
            headers={"Authorization": f"Bearer {self.api_key}", "User-Agent": "Lulu/1"},
        )
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            return json.loads(response.read())

    def _download(self, url: str, destination: Path) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        request = urllib.request.Request(url, headers={"User-Agent": "Lulu/1"})
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            data = response.read()
        temporary = destination.with_suffix(".tmp")
        temporary.write_bytes(data)
        temporary.replace(destination)

    @staticmethod
    def _write_json(path: Path, value: dict[str, object]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(value, sort_keys=True))
        temporary.replace(path)
