"""Small, rate-limited IGDB client used by metadata reconciliation."""

from __future__ import annotations

from dataclasses import dataclass
import json
import logging
import threading
import time
from typing import Callable
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .provider_config import ProviderConfigurationService


LOGGER = logging.getLogger("lulu.igdb")
IGDB_FIELDS = (
    "id,name,summary,first_release_date,genres.name,game_modes.name,platforms.name,"
    "involved_companies.company.name,involved_companies.developer,involved_companies.publisher,"
    "franchises.name,collections.name,multiplayer_modes.*,cover.url,cover.width,cover.height,cover.image_id,"
    "screenshots.url,screenshots.width,screenshots.height,screenshots.image_id,"
    "alternative_names.name,external_games.*"
)


class IGDBError(RuntimeError):
    pass


@dataclass(slots=True)
class _Token:
    value: str
    expires_at: float


class IGDBClient:
    """Client-credentials IGDB adapter; no user token or Twitch scopes."""

    def __init__(self, config: ProviderConfigurationService | None = None,
                 request: Callable[[Request, bytes | None, float], tuple[int, bytes]] | None = None,
                 clock: Callable[[], float] = time.time) -> None:
        self.config = (config or ProviderConfigurationService.from_environment()).provider("metadata.igdb")
        self.endpoint = str(self.config.get("endpoint", "https://api.igdb.com/v4")).rstrip("/")
        self.auth_endpoint = str(self.config.get("auth_endpoint", "https://id.twitch.tv/oauth2/token"))
        try:
            self.timeout = float(self.config.get("timeout", 5.0))
        except (TypeError, ValueError):
            self.timeout = 5.0
        self._request = request or self._http_request
        self._clock = clock
        self._token: _Token | None = None
        self._token_lock = threading.Lock()
        self._rate_lock = threading.Lock()
        self._request_times: list[float] = []
        self._semaphore = threading.BoundedSemaphore(8)

    @property
    def configured(self) -> bool:
        return self.config.enabled and bool(self.config.get("client_id", "")) and self.config.secret_available("client_secret")

    def test_connection(self) -> str:
        """Validate credentials through the same token/query boundary as enrichment."""
        if not self.config.enabled:
            return "disabled"
        if not str(self.config.get("client_id", "")).strip() or not self.config.secret_available("client_secret"):
            return "incomplete"
        self.query("fields id; limit 1;")
        return "connected"

    def reload_configuration(self) -> None:
        """Pick up Admin changes without restarting the catalogue daemon."""
        service = ProviderConfigurationService.from_environment()
        self.config = service.provider("metadata.igdb")
        self.endpoint = str(self.config.get("endpoint", "https://api.igdb.com/v4")).rstrip("/")
        self.auth_endpoint = str(self.config.get("auth_endpoint", "https://id.twitch.tv/oauth2/token"))
        self._token = None

    def _token_value(self, *, force: bool = False) -> str:
        if not self.config.enabled:
            raise IGDBError("disabled")
        client_id = str(self.config.get("client_id", "")).strip()
        secret = self.config.secret("client_secret")
        if not client_id or not secret:
            raise IGDBError("unconfigured")
        now = self._clock()
        with self._token_lock:
            if not force and self._token is not None and self._token.expires_at - 60 > now:
                return self._token.value
            body = urlencode({"client_id": client_id, "client_secret": secret,
                              "grant_type": "client_credentials"}).encode()
            try:
                status, payload = self._request(Request(self.auth_endpoint, method="POST"), body, self.timeout)
            except (OSError, TimeoutError) as error:
                raise IGDBError("token-unavailable") from error
            if status < 200 or status >= 300:
                raise IGDBError(f"token-http-{status}")
            try:
                value = json.loads(payload)
                token = str(value["access_token"])
                expires = float(value["expires_in"])
            except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
                raise IGDBError("token-malformed") from error
            self._token = _Token(token, now + max(60.0, expires))
            return token

    def _throttle(self) -> None:
        while True:
            now = self._clock()
            with self._rate_lock:
                self._request_times = [stamp for stamp in self._request_times if now - stamp < 1.0]
                if len(self._request_times) < 4:
                    self._request_times.append(now)
                    return
                wait = 1.0 - (now - self._request_times[0])
            if wait > 0:
                time.sleep(wait)

    def query(self, body: str, *, retry_auth: bool = True) -> list[dict[str, object]]:
        token = self._token_value()
        client_id = str(self.config.get("client_id", "")).strip()
        with self._semaphore:
            self._throttle()
            request = Request(self.endpoint.rstrip("/") + "/games", data=body.encode(), method="POST",
                              headers={"Client-ID": client_id, "Authorization": f"Bearer {token}",
                                       "Content-Type": "text/plain"})
            try:
                status, payload = self._request(request, body.encode(), self.timeout)
            except (OSError, TimeoutError) as error:
                raise IGDBError("unavailable") from error
        if status == 401 and retry_auth:
            self._token_value(force=True)
            return self.query(body, retry_auth=False)
        if status == 429:
            raise IGDBError("rate-limited")
        if status < 200 or status >= 300:
            raise IGDBError(f"http-{status}")
        try:
            value = json.loads(payload)
        except (TypeError, ValueError, json.JSONDecodeError) as error:
            raise IGDBError("malformed-response") from error
        if not isinstance(value, list):
            raise IGDBError("malformed-response")
        return [item for item in value if isinstance(item, dict)]

    def by_steam_appid(self, app_id: str) -> dict[str, object] | None:
        if not app_id.isdecimal() or int(app_id) < 1 or not self.configured:
            return None
        body = f'fields {IGDB_FIELDS}; where external_games.external_game_source = 1 & external_games.uid = "{app_id}"; limit 2;'
        rows = self.query(body)
        return rows[0] if len(rows) == 1 else None

    def by_id(self, game_id: str) -> dict[str, object] | None:
        """Resolve a previously supplied IGDB identity without title searching."""
        if not str(game_id).isdecimal() or int(game_id) < 1 or not self.configured:
            return None
        rows = self.query(f"fields {IGDB_FIELDS}; where id = {int(game_id)}; limit 1;")
        return rows[0] if rows else None

    def search_platform(self, title: str, platform_id: int) -> list[dict[str, object]]:
        if not title.strip() or not self.configured:
            return []
        escaped = title.replace('"', '\\"')
        body = f'fields {IGDB_FIELDS}; search "{escaped}"; where platforms = ({platform_id}); limit 10;'
        return self.query(body)

    @staticmethod
    def _http_request(request: Request, body: bytes | None, timeout: float) -> tuple[int, bytes]:
        try:
            with urlopen(request, data=body, timeout=timeout) as response:
                return int(response.status), response.read()
        except Exception as error:
            status = getattr(error, "code", None)
            if status is not None:
                return int(status), getattr(error, "read", lambda: b"")()
            raise


def normalize_igdb_game(value: dict[str, object]) -> dict[str, object]:
    def names(key: str) -> list[str]:
        raw = value.get(key, [])
        return [str(item.get("name", "")).strip() for item in raw if isinstance(item, dict) and item.get("name")]

    companies = value.get("involved_companies", [])
    developer = publisher = ""
    if isinstance(companies, list):
        for item in companies:
            if not isinstance(item, dict) or not isinstance(item.get("company"), dict):
                continue
            name = str(item["company"].get("name", "")).strip()
            if item.get("developer") and not developer:
                developer = name
            if item.get("publisher") and not publisher:
                publisher = name
    release = value.get("first_release_date")
    release_date = time.strftime("%Y-%m-%d", time.gmtime(int(release))) if isinstance(release, (int, float)) and release > 0 else None
    result: dict[str, object] = {
        "igdb_id": str(value.get("id", "")), "canonical_title": str(value.get("name", "")).strip(),
        "summary": str(value.get("summary", "")).strip(), "release_date": release_date,
        "release_year": int(release_date[:4]) if release_date else None, "genres": names("genres"),
        "game_modes": names("game_modes"), "platforms": names("platforms"),
        "developer": developer, "publisher": publisher,
        "franchise": (names("franchises") or [""])[0], "collection": (names("collections") or [""])[0],
    }
    cover = value.get("cover") if isinstance(value.get("cover"), dict) else {}
    cover_url = str(cover.get("url", "")).strip()
    image_id = str(cover.get("image_id", "")).strip()
    if image_id:
        cover_url = f"https://images.igdb.com/igdb/image/upload/t_1080p/{image_id}.jpg"
    if cover_url.startswith("//"):
        cover_url = "https:" + cover_url
    result["cover_url"] = cover_url
    if image_id:
        result["icon_square_url"] = f"https://images.igdb.com/igdb/image/upload/t_thumb/{image_id}.jpg"
        result["icon_square_provider"] = "igdb"
        result["icon_square_source_url"] = result["icon_square_url"]
    screenshots = value.get("screenshots")
    if isinstance(screenshots, list):
        widescreen: list[str] = []
        for screenshot in screenshots:
            if not isinstance(screenshot, dict):
                continue
            try:
                width = int(screenshot.get("width", 0) or 0)
                height = int(screenshot.get("height", 0) or 0)
            except (TypeError, ValueError):
                continue
            screenshot_id = str(screenshot.get("image_id", "")).strip()
            url = str(screenshot.get("url", "")).strip()
            if width >= 600 and height > 0 and width / height >= 1.4:
                if screenshot_id:
                    url = f"https://images.igdb.com/igdb/image/upload/t_screenshot_big/{screenshot_id}.jpg"
                if url.startswith("//"):
                    url = "https:" + url
                if url:
                    widescreen.append(url)
        if widescreen:
            # IGDB preserves its canonical screenshot order; choosing the first
            # valid landscape image keeps the preview stable between refreshes.
            result["preview_still_url"] = widescreen[0]
            result["preview_still_provider"] = "igdb"
            result["preview_still_source_url"] = result["preview_still_url"]
    result["cover_width"] = int(cover["width"]) if str(cover.get("width", "")).isdigit() else None
    result["cover_height"] = int(cover["height"]) if str(cover.get("height", "")).isdigit() else None
    result["aliases"] = names("alternative_names")
    multiplayer = value.get("multiplayer_modes")
    if isinstance(multiplayer, list) and multiplayer:
        mode = multiplayer[0] if isinstance(multiplayer[0], dict) else {}
        if "offlinecoop" in mode:
            result["local_multiplayer"] = bool(mode["offlinecoop"])
        if "onlinemultiplayer" in mode:
            result["online_multiplayer"] = bool(mode["onlinemultiplayer"])
    return result
