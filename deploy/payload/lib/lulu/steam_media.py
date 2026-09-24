"""Cached, optional Steam presentation media metadata."""

from __future__ import annotations

import json
from pathlib import Path
import time
from threading import Lock
from typing import Callable
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .paths import PATHS


class SteamStoreMedia:
    """Resolve public Steam hover media without downloading video assets."""

    endpoint = "https://store.steampowered.com/apphoverpublic"

    def __init__(self, cache_dir: Path | None = None, timeout: float = 5.0,
                 request: Callable[[str, float], bytes] | None = None,
                 clock: Callable[[], float] = time.time) -> None:
        self.cache_dir = cache_dir or PATHS.metadata_cache / "steam-media"
        self.timeout = timeout
        self._request = request or self._http_request
        self._clock = clock
        self._request_lock = Lock()
        self._last_request_at = 0.0

    def resolve(self, app_id: str) -> dict[str, str]:
        if not app_id.isdecimal() or int(app_id) < 1:
            return {}
        path = self.cache_dir / f"{app_id}.json"
        try:
            cached = json.loads(path.read_text()) if path.exists() else {}
            age = self._clock() - float(cached.get("checked_at", 0))
            ttl = 6 * 60 * 60 if cached.get("failed") else 30 * 86400
            if cached.get("app_id") == app_id and age < ttl:
                value = cached.get("media", {})
                return value if isinstance(value, dict) else {}
        except (OSError, ValueError, TypeError):
            pass
        url = f"{self.endpoint}/{app_id}/?" + urlencode({"l": "english", "json": 1})
        try:
            with self._request_lock:
                wait = 0.25 - (self._clock() - self._last_request_at)
                if wait > 0:
                    time.sleep(wait)
                self._last_request_at = self._clock()
            payload = json.loads(self._request(url, self.timeout))
        except (OSError, URLError, TimeoutError, ValueError, TypeError):
            self._save(app_id, {}, failed=True)
            return {}
        if not isinstance(payload, dict):
            return {}
        video = str(payload.get("strMicroTrailerURL") or "").strip()
        if video and ".webm" not in video.casefold():
            video = ""
        still = ""
        screenshots = payload.get("rgScreenshots", [])
        if isinstance(screenshots, list):
            for screenshot in screenshots:
                if not isinstance(screenshot, dict):
                    continue
                filename = str(screenshot.get("filename", "")).strip().lstrip("/")
                if filename and not filename.startswith(("http://", "https://")):
                    still = (f"https://shared.akamai.steamstatic.com/store_item_assets/"
                             f"steam/apps/{app_id}/{filename}")
                    break
        media = {"preview_video_url": video, "preview_video_provider": "steam" if video else "",
                 "preview_video_source_url": video, "preview_still_url": still,
                 "preview_still_provider": "steam" if still else "",
                 "preview_still_source_url": still}
        try:
            self._save(app_id, media)
        except OSError:
            pass
        return media

    def _save(self, app_id: str, media: dict[str, str], *, failed: bool = False) -> None:
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        path = self.cache_dir / f"{app_id}.json"
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps({"app_id": app_id, "checked_at": self._clock(),
                                         "failed": failed, "media": media}, sort_keys=True))
        temporary.replace(path)

    @staticmethod
    def _http_request(url: str, timeout: float) -> bytes:
        request = Request(url, headers={"Accept": "application/json", "User-Agent": "Lulu/1"})
        with urlopen(request, timeout=timeout) as response:
            return response.read()
