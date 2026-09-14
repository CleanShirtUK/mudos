"""Read-only RomM catalogue provider.

Mudos consumes RomM's normal user API.  It does not scan RomM storage or use
administrative endpoints.
"""

from __future__ import annotations

from dataclasses import dataclass
import base64
import json
import logging
import os
from pathlib import Path
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from .paths import PATHS


LOGGER = logging.getLogger("lulu.romm")


class RommApiError(RuntimeError):
    """RomM was unavailable or returned an invalid response."""


@dataclass(frozen=True, slots=True)
class RommConfig:
    server_url: str
    client_token: str = ""
    access_token: str = ""
    username: str = ""
    password: str = ""
    timeout: float = 8.0

    @classmethod
    def from_file(cls, path: Path | None = None) -> "RommConfig | None":
        path = path or Path(os.environ.get("LULU_ROMM_CONFIG", PATHS.providers_root / "romm.json")).expanduser()
        if not path.is_file():
            return None
        try:
            value = json.loads(path.read_text())
            if not isinstance(value, dict):
                raise ValueError("configuration must be an object")
            config = cls(
                server_url=str(value.get("server_url", value.get("url", ""))).strip(),
                client_token=str(value.get("client_token", "")),
                access_token=str(value.get("access_token", "")),
                username=str(value.get("username", "")),
                password=str(value.get("password", "")),
                timeout=float(value.get("timeout", 8.0)),
            )
            if not config.server_url or not 0 < config.timeout <= 60:
                raise ValueError("server_url and a timeout between 0 and 60 seconds are required")
            return config
        except (OSError, TypeError, ValueError, json.JSONDecodeError) as error:
            LOGGER.warning("RomM configuration unavailable path=%s error=%s", path, error)
            return None

    @property
    def api_url(self) -> str:
        return self.server_url.rstrip("/") + "/api"

    @property
    def auth_mode(self) -> str:
        if self.client_token:
            return "client_token"
        if self.access_token:
            return "access_token"
        if self.username:
            return "basic"
        return "none"

    def auth_header(self) -> str | None:
        if self.client_token:
            return f"Bearer {self.client_token}"
        if self.access_token:
            return f"Bearer {self.access_token}"
        if self.username:
            value = base64.b64encode(f"{self.username}:{self.password}".encode()).decode()
            return f"Basic {value}"
        return None


@dataclass(frozen=True, slots=True)
class RommPlatform:
    platform_id: int
    slug: str
    label: str


@dataclass(frozen=True, slots=True)
class RommFile:
    file_id: int
    name: str
    size_bytes: int = 0


@dataclass(frozen=True, slots=True)
class RommGame:
    rom_id: int
    title: str
    platform_id: int
    platform_slug: str
    platform_label: str
    file_name: str
    extension: str
    size_bytes: int
    artwork_url: str
    missing_from_fs: bool
    files: tuple[RommFile, ...] = ()

    @classmethod
    def from_json(cls, value: object, platforms: dict[int, RommPlatform]) -> "RommGame":
        if not isinstance(value, dict):
            raise RommApiError("RomM ROM entry is not an object")
        try:
            rom_id = int(value["id"])
            platform_id = int(value["platform_id"])
            if rom_id < 1 or platform_id < 1:
                raise ValueError
            platform = value.get("platform")
            platform = platform if isinstance(platform, dict) else {}
            platform_slug = str(value.get("platform_slug") or platform.get("slug") or "").strip()
            platform_label = str(value.get("platform_display_name") or platform.get("name") or platform_slug).strip()
            known_platform = platforms.get(platform_id)
            platform_slug = platform_slug or (known_platform.slug if known_platform else "")
            platform_label = platform_label or (known_platform.label if known_platform else "")
            file_name = str(value.get("fs_name") or "").strip()
            files_value = value.get("files", [])
            if not isinstance(files_value, list):
                raise ValueError
            files = tuple(
                RommFile(int(item["id"]), str(item.get("file_name", "")), int(item.get("file_size_bytes", 0)))
                for item in files_value
                if isinstance(item, dict) and str(item.get("file_name", "")).strip()
            )
            if not file_name and files:
                file_name = files[0].name
            if not file_name or not platform_slug:
                raise ValueError
            return cls(
                rom_id, str(value.get("name") or Path(file_name).stem), platform_id,
                platform_slug, platform_label, file_name,
                str(value.get("fs_extension") or Path(file_name).suffix),
                int(value.get("fs_size_bytes", 0)), str(value.get("url_cover") or ""),
                bool(value.get("missing_from_fs", False)), files,
            )
        except (KeyError, TypeError, ValueError) as error:
            raise RommApiError("malformed RomM ROM entry") from error


@dataclass(frozen=True, slots=True)
class SteamManifest:
    app_id: str

    @classmethod
    def from_bytes(cls, payload: bytes) -> "SteamManifest":
        try:
            value = json.loads(payload)
        except (UnicodeDecodeError, TypeError, ValueError) as error:
            raise RommApiError("invalid Steam manifest JSON") from error
        if not isinstance(value, dict) or value.get("schema") != 1 or value.get("provider") != "steam":
            raise RommApiError("unsupported Steam manifest")
        app_id = value.get("id")
        if not isinstance(app_id, str) or not app_id.isdecimal() or int(app_id) < 1:
            raise RommApiError("Steam manifest AppID is invalid")
        return cls(app_id)


class RommTransport(Protocol):
    def request(self, method: str, url: str, headers: dict[str, str], timeout: float) -> tuple[int, bytes]: ...


class UrlLibTransport:
    def request(self, method: str, url: str, headers: dict[str, str], timeout: float) -> tuple[int, bytes]:
        request = Request(url, headers=headers, method=method)
        with urlopen(request, timeout=timeout) as response:
            return int(response.status), response.read()


class RommClient:
    def __init__(self, config: RommConfig, transport: RommTransport | None = None) -> None:
        if not config.server_url.strip():
            raise ValueError("RomM server URL is required")
        self.config = config
        self.transport = transport or UrlLibTransport()

    def list_platforms(self) -> list[RommPlatform]:
        value = self._json("GET", "/platforms")
        if not isinstance(value, list):
            raise RommApiError("RomM platforms response is not a list")
        result: list[RommPlatform] = []
        try:
            for item in value:
                if not isinstance(item, dict):
                    raise ValueError
                platform_id = int(item["id"])
                slug = str(item["slug"]).strip()
                label = str(item.get("display_name") or item.get("name") or slug).strip()
                if platform_id < 1 or not slug:
                    raise ValueError
                result.append(RommPlatform(platform_id, slug, label))
        except (KeyError, TypeError, ValueError) as error:
            raise RommApiError("malformed RomM platform entry") from error
        return result

    def list_games(self, limit: int = 50, platform_slug: str | None = None) -> list[RommGame]:
        if not 1 <= limit <= 1000:
            raise ValueError("RomM page limit must be between 1 and 1000")
        platforms = {item.platform_id: item for item in self.list_platforms()}
        games: list[RommGame] = []
        offset = 0
        seen_ids: set[int] = set()
        while True:
            value = self._json("GET", "/roms", {"limit": limit, "offset": offset, "with_files": "true", "with_total": "true"})
            if isinstance(value, list):
                items, total = value, None
            elif isinstance(value, dict) and isinstance(value.get("items"), list):
                items, total = value["items"], value.get("total")
            else:
                raise RommApiError("malformed RomM ROM catalogue response")
            page = [RommGame.from_json(item, platforms) for item in items]
            if page and all(game.rom_id in seen_ids for game in page):
                raise RommApiError("RomM pagination repeated a page")
            seen_ids.update(game.rom_id for game in page)
            games.extend(page)
            try:
                reached_total = total is not None and offset + len(page) >= int(total)
            except (TypeError, ValueError) as error:
                raise RommApiError("malformed RomM catalogue total") from error
            if not page or len(page) < limit or reached_total:
                break
            next_offset = offset + len(page)
            if next_offset <= offset:
                raise RommApiError("RomM pagination did not advance")
            offset = next_offset
        if platform_slug is None:
            return games
        expected = platform_slug.casefold()
        return [game for game in games if game.platform_slug.casefold() == expected]

    def download_file(self, romm_file: RommFile) -> bytes:
        path = f"/roms/{romm_file.file_id}/files/content/{quote(romm_file.name, safe='')}"
        return self._request("GET", path, "application/octet-stream")[1]

    def read_steam_manifest(self, romm_file: RommFile) -> SteamManifest:
        path = f"/roms/{romm_file.file_id}/files/content/{quote(romm_file.name, safe='')}"
        return SteamManifest.from_bytes(self._request("GET", path, "application/json")[1])

    def _json(self, method: str, path: str, query: dict[str, object] | None = None) -> object:
        if query:
            path += "?" + urlencode(query)
        try:
            return json.loads(self._request(method, path)[1])
        except (TypeError, ValueError, json.JSONDecodeError) as error:
            raise RommApiError(f"malformed RomM JSON response: {path}") from error

    def _request(self, method: str, path: str, accept: str = "application/json") -> tuple[int, bytes]:
        headers = {"Accept": accept, "User-Agent": "Mudos/romm"}
        if (auth := self.config.auth_header()) is not None:
            headers["Authorization"] = auth
        try:
            status, payload = self.transport.request(method, self.config.api_url + path, headers, self.config.timeout)
        except (HTTPError, URLError, OSError, TimeoutError) as error:
            raise RommApiError(f"RomM request failed: {method} {path}") from error
        if not 200 <= status < 300:
            raise RommApiError(f"RomM returned HTTP {status} for {path}")
        return status, payload
