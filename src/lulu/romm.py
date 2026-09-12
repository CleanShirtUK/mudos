"""Small, typed RomM API adapter for library discovery and installation."""

from dataclasses import dataclass
import base64
import json
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen


@dataclass(frozen=True, slots=True)
class RommConfig:
    """Connection settings; credentials are supplied by the caller, never hard-coded."""

    server_url: str
    client_token: str = ""
    access_token: str = ""
    username: str = ""
    password: str = ""

    @property
    def api_url(self) -> str:
        return self.server_url.rstrip("/") + "/api"

    def auth_header(self) -> str | None:
        if self.client_token:
            return f"Bearer {self.client_token}"
        if self.access_token:
            return f"Bearer {self.access_token}"
        if self.username:
            encoded = base64.b64encode(f"{self.username}:{self.password}".encode()).decode()
            return f"Basic {encoded}"
        return None


@dataclass(frozen=True, slots=True)
class RommPlatform:
    id: int
    slug: str
    fs_slug: str
    name: str
    display_name: str
    rom_count: int
    custom_name: str | None = None

    @classmethod
    def from_json(cls, value: dict[str, Any]) -> "RommPlatform":
        return cls(
            id=int(value["id"]), slug=str(value["slug"]), fs_slug=str(value["fs_slug"]),
            name=str(value["name"]), display_name=str(value["display_name"]),
            rom_count=int(value["rom_count"]), custom_name=value.get("custom_name"),
        )


@dataclass(frozen=True, slots=True)
class RommGame:
    id: int
    name: str | None
    platform_id: int
    platform_slug: str
    platform_display_name: str
    fs_name: str
    fs_extension: str
    fs_size_bytes: int
    url_cover: str | None
    missing_from_fs: bool
    has_multiple_files: bool

    @classmethod
    def from_json(cls, value: dict[str, Any]) -> "RommGame":
        return cls(
            id=int(value["id"]), name=value.get("name"), platform_id=int(value["platform_id"]),
            platform_slug=str(value["platform_slug"]), platform_display_name=str(value["platform_display_name"]),
            fs_name=str(value["fs_name"]), fs_extension=str(value["fs_extension"]),
            fs_size_bytes=int(value["fs_size_bytes"]), url_cover=value.get("url_cover"),
            missing_from_fs=bool(value["missing_from_fs"]),
            has_multiple_files=bool(value["has_multiple_files"]),
        )


@dataclass(frozen=True, slots=True)
class RommLibrary:
    games: tuple[RommGame, ...]
    total: int | None
    limit: int
    offset: int

    @classmethod
    def from_json(cls, value: dict[str, Any]) -> "RommLibrary":
        return cls(
            games=tuple(RommGame.from_json(item) for item in value["items"]),
            total=value.get("total"), limit=int(value["limit"]), offset=int(value["offset"]),
        )


class RommTransport(Protocol):
    def request(self, method: str, url: str, headers: dict[str, str], data: bytes | None = None) -> bytes: ...


class UrlLibTransport:
    def request(self, method: str, url: str, headers: dict[str, str], data: bytes | None = None) -> bytes:
        request = Request(url, data=data, headers=headers, method=method)
        with urlopen(request) as response:
            return response.read()


class RommApiError(RuntimeError):
    """Raised when RomM returns a non-success response."""


class RommClient:
    def __init__(self, config: RommConfig, transport: RommTransport | None = None) -> None:
        if not config.server_url.strip():
            raise ValueError("RomM server URL is required")
        self.config = config
        self.transport = transport or UrlLibTransport()

    def list_platforms(self, updated_after: str | None = None) -> list[RommPlatform]:
        query = {} if updated_after is None else {"updated_after": updated_after}
        return [RommPlatform.from_json(item) for item in self._json("GET", "/platforms", query)]

    def list_games(self, limit: int = 50, offset: int = 0, search_term: str | None = None) -> RommLibrary:
        if not 1 <= limit <= 10000:
            raise ValueError("RomM page limit must be between 1 and 10000")
        if offset < 0:
            raise ValueError("RomM page offset cannot be negative")
        query: dict[str, Any] = {"limit": limit, "offset": offset, "with_files": False}
        if search_term is not None:
            query["search_term"] = search_term
        return RommLibrary.from_json(self._json("GET", "/roms", query))

    def get_game(self, game_id: int) -> RommGame:
        return RommGame.from_json(self._json("GET", f"/roms/{self._positive_id(game_id)}/simple"))

    def download_game(self, game: RommGame, destination: Path, file_name: str | None = None) -> Path:
        """Download one ROM to a caller-owned path; no temporary install is implied."""
        name = file_name or game.fs_name
        if not name or name in {".", ".."} or "/" in name or "\\" in name:
            raise ValueError("RomM download filename must be a single path component")
        payload = self._request("GET", f"/roms/{self._positive_id(game.id)}/content/{quote(name, safe='')}")
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(payload)
        return destination

    def _json(self, method: str, path: str, query: dict[str, Any] | None = None) -> Any:
        if query:
            path += "?" + urlencode(query, doseq=True)
        return json.loads(self._request(method, path))

    def _request(self, method: str, path: str, data: bytes | None = None) -> bytes:
        headers = {"Accept": "application/json"}
        if (auth := self.config.auth_header()) is not None:
            headers["Authorization"] = auth
        try:
            return self.transport.request(method, self.config.api_url + path, headers, data)
        except Exception as error:
            raise RommApiError(f"RomM request failed: {method} {path}") from error

    @staticmethod
    def _positive_id(value: int) -> int:
        if value < 1:
            raise ValueError("RomM id must be positive")
        return value


class RommInstaller:
    """Install boundary that delegates all network behavior to a RomM client."""

    def __init__(self, client: RommClient) -> None:
        self.client = client

    def install(self, game: RommGame, library_root: Path) -> Path:
        return self.client.download_game(game, library_root / game.platform_slug / game.fs_name)
