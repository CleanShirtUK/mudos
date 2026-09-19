"""Optional artwork enrichment behind the catalogue boundary."""

from dataclasses import dataclass, field
import hashlib
import json
import logging
from pathlib import Path
import urllib.error
import urllib.parse
import urllib.request

from .paths import PATHS
from .provider_config import ProviderConfigurationService


@dataclass(slots=True)
class LocalArtworkCache:
    """Persistent, best-effort cache for provider artwork assets."""

    cache_dir: Path | None = None
    timeout: float = 8.0
    downloader: object | None = None

    def __post_init__(self) -> None:
        self.cache_dir = self.cache_dir or PATHS.romm_artwork_cache

    def cache_remote(self, identity: str, url: str) -> str:
        if not url:
            return ""
        digest = hashlib.sha256(identity.encode()).hexdigest()
        image = self.cache_dir / f"{digest}.img"
        state = self.cache_dir / f"{digest}.json"
        try:
            previous = json.loads(state.read_text()) if state.exists() else {}
            if image.exists() and previous.get("url") == url:
                return image.as_uri()
            if self.downloader is not None:
                payload = self.downloader(url)
            else:
                request = urllib.request.Request(url, headers={"User-Agent": "Mudos/romm"})
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    payload = response.read()
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            temporary = image.with_suffix(".tmp")
            temporary.write_bytes(payload)
            temporary.replace(image)
            state.write_text(json.dumps({"url": url}, sort_keys=True))
            return image.as_uri()
        except (OSError, ValueError, urllib.error.URLError, TimeoutError):
            return image.as_uri() if image.exists() else ""


@dataclass(slots=True)
class SteamGridDBArtwork:
    api_key: str | None = None
    cache_dir: Path | None = None
    timeout: float = 4.0
    _logger: logging.Logger = field(init=False, repr=False)
    endpoint: str = field(init=False, repr=False)

    def __post_init__(self) -> None:
        config = ProviderConfigurationService.from_environment().provider("metadata.steamgriddb")
        if self.api_key is None:
            self.api_key = config.secret("api_key") if config.configured else None
        self.endpoint = str(config.get("endpoint", "https://www.steamgriddb.com/api")).rstrip("/")
        self.cache_dir = self.cache_dir or PATHS.artwork_cache
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
            self.endpoint + path,
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
