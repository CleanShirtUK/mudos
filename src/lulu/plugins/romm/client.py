"""Read-only RomM catalogue provider.

Mudos consumes RomM's normal user API.  It does not scan RomM storage or use
administrative endpoints.
"""

from __future__ import annotations

from dataclasses import dataclass
import base64
from io import BytesIO
import json
import logging
import os
from pathlib import Path
import tomllib
from typing import Any, BinaryIO, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from ...paths import PATHS
from ...credential import SecretStore


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
        explicit = path is not None or "LULU_ROMM_CONFIG" in os.environ
        path = path or Path(os.environ.get("LULU_ROMM_CONFIG", PATHS.plugins_root / "romm" / "settings.toml")).expanduser()
        if not path.is_file():
            return None
        try:
            if path.suffix.casefold() == ".toml":
                with path.open("rb") as stream:
                    value = tomllib.load(stream)
                value = value.get("settings", value)
            else:
                value = json.loads(path.read_text())
            if not isinstance(value, dict):
                raise ValueError("configuration must be an object")
            config = cls(
                server_url=str(value.get("server_url", value.get("url", ""))).strip(),
                # API keys are never accepted from TOML. The field is filled
                # from the generic encrypted secret store below.
                client_token=SecretStore().get("romm", "api-key") or "",
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

    @classmethod
    def save_url(cls, server_url: str, path: Path | None = None) -> None:
        server_url = server_url.strip()
        if not server_url.startswith(("http://", "https://")):
            raise ValueError("RomM URL must use http or https")
        path = path or Path(os.environ.get("LULU_ROMM_CONFIG", PATHS.plugins_root / "romm" / "settings.toml")).expanduser()
        path.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
        temporary = path.with_name(f".{path.name}.tmp")
        temporary.write_text("[settings]\nserver_url = " + json.dumps(server_url) + "\n")
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)

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
    category: str | None = None
    title_id: str | None = None
    version: str | None = None
    rom_id: int | None = None


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
    genres: tuple[str, ...] = ()
    release_date: str | None = None
    release_year: int | None = None
    total_playtime: int | None = None
    local_multiplayer: bool | None = None
    online_multiplayer: bool | None = None
    game_mode: str | None = None
    protondb_rating: str | None = None
    igdb_id: str = ""
    summary: str = ""

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
                RommFile(int(item["id"]), str(item.get("file_name", "")), int(item.get("file_size_bytes", 0)),
                         str(item.get("category") or item.get("type") or "") or None,
                         str(item.get("title_id") or item.get("titleId") or "") or None,
                         str(item.get("version") or "") or None, rom_id)
                for item in files_value
                if isinstance(item, dict) and str(item.get("file_name", "")).strip()
            )
            if not file_name and files:
                file_name = files[0].name
            if not file_name or not platform_slug:
                raise ValueError
            # RomM's current response keeps identified IGDB presentation data in
            # ``metadatum`` (and mirrors much of it in ``igdb_metadata``), rather
            # than promoting it to the ROM object.  Prefer the direct ROM fields
            # when present, then use the nested metadata as a presentation fallback.
            metadatum = value.get("metadatum")
            metadatum = metadatum if isinstance(metadatum, dict) else {}
            igdb_metadata = value.get("igdb_metadata")
            igdb_metadata = igdb_metadata if isinstance(igdb_metadata, dict) else {}

            def metadata_value(key: str) -> object:
                if value.get(key) not in (None, "", []):
                    return value[key]
                if metadatum.get(key) not in (None, "", []):
                    return metadatum[key]
                return igdb_metadata.get(key)

            genres_value = metadata_value("genres") or []
            if not isinstance(genres_value, list):
                genres_value = []
            genres = tuple(
                str(item.get("name", "")).strip() if isinstance(item, dict) else str(item).strip()
                for item in genres_value if str(item).strip()
            )
            release_date = metadata_value("first_release_date") or metadata_value("release_date")
            release_date = str(release_date).strip() if release_date else None
            release_year = metadata_value("release_year") or metadata_value("year")
            release_year = int(release_year) if release_year is not None else None

            game_modes = metadata_value("game_modes")
            game_modes = game_modes if isinstance(game_modes, list) else []
            game_mode = ", ".join(str(item).strip() for item in game_modes if str(item).strip()) or None

            # IGDB's multiplayer_modes is the only sampled source that separates
            # offline and online capabilities. A positive max/player value or an
            # explicit cooperative/split-screen flag is sufficient for a boolean;
            # player_count is intentionally not collapsed into this contract.
            multiplayer_modes = igdb_metadata.get("multiplayer_modes", [])
            multiplayer_modes = multiplayer_modes if isinstance(multiplayer_modes, list) else []

            def mode_flag(keys: tuple[str, ...], positive_keys: tuple[str, ...]) -> bool | None:
                observed = False
                for mode in multiplayer_modes:
                    if not isinstance(mode, dict):
                        continue
                    for key in keys:
                        if key in mode and mode[key] is not None:
                            observed = True
                            if bool(mode[key]):
                                return True
                    for key in positive_keys:
                        if key in mode and mode[key] is not None:
                            observed = True
                            try:
                                if int(mode[key]) > 1:
                                    return True
                            except (TypeError, ValueError):
                                pass
                return False if observed else None

            local_multiplayer = mode_flag(
                ("offlinecoop", "splitscreen", "lancoop"),
                ("offlinecoopmax", "offlinemax"),
            )
            online_multiplayer = mode_flag(
                ("onlinecoop", "splitscreenonline"),
                ("onlinecoopmax", "onlinemax"),
            )
            embedded_igdb_id = str(
                (metadatum.get("id") or igdb_metadata.get("id") or "")
            ).strip()
            summary = str(metadata_value("summary") or metadata_value("storyline")
                          or metadata_value("description") or "").strip()
            return cls(
                rom_id, str(value.get("name") or Path(file_name).stem), platform_id,
                platform_slug, platform_label, file_name,
                str(value.get("fs_extension") or Path(file_name).suffix),
                int(value.get("fs_size_bytes", 0)), str(value.get("url_cover") or ""),
                bool(value.get("missing_from_fs", False)), files, genres, release_date, release_year,
                 None, local_multiplayer, online_multiplayer, game_mode,
                 igdb_id=embedded_igdb_id, summary=summary,
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
    def request(self, method: str, url: str, headers: dict[str, str], timeout: float,
                body: bytes | None = None) -> tuple[int, bytes]: ...


class UrlLibTransport:
    def request(self, method: str, url: str, headers: dict[str, str], timeout: float,
                body: bytes | None = None) -> tuple[int, bytes]:
        request = Request(url, data=body, headers=headers, method=method)
        with urlopen(request, timeout=timeout) as response:
            return int(response.status), response.read()

    def open(self, method: str, url: str, headers: dict[str, str], timeout: float,
             offset: int = 0) -> BinaryIO:
        request_headers = dict(headers)
        if offset > 0:
            request_headers["Range"] = f"bytes={offset}-"
        request = Request(url, headers=request_headers, method=method)
        response = urlopen(request, timeout=timeout)
        if not 200 <= int(response.status) < 300:
            response.close()
            raise HTTPError(url, int(response.status), "RomM download failed", response.headers, None)
        return response


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

    def exchange_pairing_code(self, code: str) -> None:
        """Exchange RomM's short-lived device code for an encrypted token."""
        normalized = code.strip().replace("-", "")
        if (len(normalized) != 8 or not normalized.isalnum()
                or not normalized.isascii()):
            raise ValueError("RomM pairing code must be eight characters in XXXX-XXXX format")
        headers = {"Accept": "application/json", "Content-Type": "application/json",
                   "User-Agent": "Mudos/romm"}
        try:
            status, payload = self.transport.request(
                "POST", self.config.api_url + "/client-tokens/exchange", headers,
                self.config.timeout, json.dumps({"code": normalized}).encode(),
            )
        except TypeError as error:
            # Keep older test transports deterministic while production uses the
            # body-capable UrlLibTransport above.
            raise RommApiError("RomM pairing transport does not support POST bodies") from error
        except HTTPError as error:
            if error.code == 404:
                raise RommApiError("RomM pairing code is invalid or expired") from error
            raise RommApiError(f"RomM pairing request returned HTTP {error.code}") from error
        except (URLError, OSError, TimeoutError) as error:
            raise RommApiError("RomM pairing request failed") from error
        if not 200 <= status < 300:
            raise RommApiError(f"RomM pairing returned HTTP {status}")
        try:
            value = json.loads(payload)
            # RomM's ClientTokenCreateSchema calls the one-time plaintext
            # credential ``raw_token``.  Some compatible servers use ``token``.
            token = (value.get("raw_token", value.get("token"))
                     if isinstance(value, dict) else None)
        except (TypeError, ValueError, json.JSONDecodeError) as error:
            raise RommApiError("RomM pairing returned malformed JSON") from error
        if not isinstance(token, str) or not token.startswith("rmm_"):
            raise RommApiError("RomM pairing did not return a client token")
        SecretStore().put("romm", "api-key", token)

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
        path = self._content_path(romm_file)
        return self._request("GET", path, "application/octet-stream")[1]

    @staticmethod
    def _content_path(romm_file: RommFile) -> str:
        """Build RomM 5.x's parent-ROM content route with file selection."""
        if romm_file.rom_id is None:
            raise RommApiError("RomM file is missing its parent ROM ID")
        return (f"/roms/{romm_file.rom_id}/content/{quote(romm_file.name, safe='')}"
                f"?file_ids={romm_file.file_id}")

    def open_file_stream(self, romm_file: RommFile, *, offset: int = 0) -> BinaryIO:
        """Open a RomM content response without materialising it in memory."""
        path = self._content_path(romm_file)
        headers = {"Accept": "application/octet-stream", "User-Agent": "Mudos/romm"}
        if (auth := self.config.auth_header()) is not None:
            headers["Authorization"] = auth
        if isinstance(self.transport, UrlLibTransport):
            try:
                # Large RomM transfers can legitimately be idle for longer
                # than the metadata timeout.  Keep metadata calls bounded,
                # but allow the streaming socket a conservative idle window.
                return self.transport.open("GET", self.config.api_url + path, headers,
                                           max(self.config.timeout, 60.0), offset)
            except HTTPError as error:
                raise RommApiError(f"RomM returned HTTP {error.code} for {path}") from error
            except (URLError, OSError, TimeoutError) as error:
                raise RommApiError(f"RomM request failed: GET {path}") from error
        # Test/custom transports expose only the existing bounded request API.
        # Keep this compatibility fallback; production uses UrlLibTransport.
        return BytesIO(self._request("GET", path, "application/octet-stream")[1])

    def read_steam_manifest(self, romm_file: RommFile) -> SteamManifest:
        path = self._content_path(romm_file)
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
        except HTTPError as error:
            raise RommApiError(f"RomM returned HTTP {error.code} for {path}") from error
        except (URLError, OSError, TimeoutError) as error:
            raise RommApiError(f"RomM request failed: {method} {path}") from error
        if not 200 <= status < 300:
            raise RommApiError(f"RomM returned HTTP {status} for {path}")
        return status, payload
