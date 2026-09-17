"""Local Valve ownership source for the Steam catalogue.

This replaces the old RomM marker transport.  It deliberately owns only
entitlement membership and the Valve title supplied with each AppID; local
Steam manifests remain authoritative for installation state.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import logging
import os
from pathlib import Path
from typing import Callable
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .paths import PATHS

LOGGER = logging.getLogger("lulu.steam-entitlements")
OWNED_GAMES_URL = "https://api.steampowered.com/IPlayerService/GetOwnedGames/v0001/"


class SteamEntitlementError(RuntimeError):
    """Valve ownership data was unavailable or failed validation."""


@dataclass(frozen=True, slots=True)
class SteamEntitlement:
    app_id: str
    title: str


@dataclass(frozen=True, slots=True)
class SteamEntitlementConfig:
    steam_id: str
    api_key_file: Path
    timeout: float = 8.0

    @classmethod
    def from_file(cls, path: Path | None = None) -> "SteamEntitlementConfig | None":
        path = path or Path(os.environ.get(
            "LULU_STEAM_ENTITLEMENTS_CONFIG", PATHS.plugins_root / "steam" / "steam.json"
        )).expanduser()
        try:
            value = json.loads(path.read_text())
            if not isinstance(value, dict):
                raise ValueError("configuration must be an object")
            steam_id = str(value.get("steam_id", "")).strip()
            key_file = str(value.get("api_key_file", "")).strip()
            timeout = float(value.get("timeout", 8.0))
            if not steam_id.isdecimal() or int(steam_id) < 1:
                raise ValueError("steam_id must be a positive numeric SteamID")
            if not key_file or not 0 < timeout <= 60:
                raise ValueError("api_key_file and a timeout between 0 and 60 seconds are required")
            return cls(steam_id, Path(key_file).expanduser(), timeout)
        except (OSError, TypeError, ValueError, json.JSONDecodeError) as error:
            LOGGER.warning("Steam entitlement configuration unavailable path=%s error=%s", path, error)
            return None

    def api_key(self) -> str:
        try:
            mode = self.api_key_file.stat().st_mode & 0o777
            if mode & 0o077:
                raise SteamEntitlementError("Steam Web API key file must not be group/world accessible")
            value = self.api_key_file.read_text().strip()
        except OSError as error:
            raise SteamEntitlementError("Steam Web API key is unavailable") from error
        if not value:
            raise SteamEntitlementError("Steam Web API key is empty")
        return value


class SteamEntitlementSource:
    """Read Valve-owned AppIDs and retain the last valid snapshot on failure."""

    def __init__(self, config: SteamEntitlementConfig | None = None,
                 request: Callable[[str, float], bytes] | None = None,
                 snapshot_path: Path | None = None) -> None:
        self.config = config or SteamEntitlementConfig.from_file()
        self._request = request or self._http_request
        self._snapshot_path = snapshot_path or (PATHS.data_root / "steam-entitlements.json")
        self._last_good = self._load_snapshot()
        self.last_refresh_succeeded = False
        self.last_error: str = ""

    @property
    def has_snapshot(self) -> bool:
        return bool(self._last_good)

    @property
    def snapshot(self) -> tuple[SteamEntitlement, ...]:
        return self._last_good

    def refresh(self) -> tuple[SteamEntitlement, ...]:
        try:
            if self.config is None:
                raise SteamEntitlementError("Steam entitlement configuration is unavailable")
            payload = self._request(self._url(self.config), self.config.timeout)
            games = self.parse_response(payload)
        except (SteamEntitlementError, OSError, ValueError) as error:
            self.last_refresh_succeeded = False
            self.last_error = str(error)
            LOGGER.warning("Steam entitlement refresh failed; retaining last-known-good snapshot: %s", error)
            return self._last_good
        self._last_good = games
        self._save_snapshot(games)
        self.last_refresh_succeeded = True
        self.last_error = ""
        return games

    @classmethod
    def parse_response(cls, payload: bytes | str | dict[str, object]) -> tuple[SteamEntitlement, ...]:
        try:
            value = json.loads(payload) if isinstance(payload, (bytes, str)) else payload
        except (TypeError, ValueError, json.JSONDecodeError) as error:
            raise SteamEntitlementError("Valve ownership response is not valid JSON") from error
        if not isinstance(value, dict):
            raise SteamEntitlementError("Valve ownership response is not an object")
        response = value.get("response")
        if not isinstance(response, dict) or not isinstance(response.get("games"), list):
            raise SteamEntitlementError("Valve ownership data is private or unavailable")
        if not response["games"]:
            raise SteamEntitlementError("Valve returned an empty ownership list")
        result: list[SteamEntitlement] = []
        seen: set[str] = set()
        for item in response["games"]:
            if not isinstance(item, dict):
                raise SteamEntitlementError("Valve ownership entry is not an object")
            app_id = item.get("appid")
            title = item.get("name")
            if isinstance(app_id, bool) or not isinstance(app_id, int) or not 1 <= app_id <= 9_999_999_999:
                raise SteamEntitlementError("Valve ownership AppID is invalid")
            if not isinstance(title, str) or not title.strip():
                raise SteamEntitlementError("Valve ownership title is invalid")
            identity = str(app_id)
            if identity in seen:
                raise SteamEntitlementError("Valve ownership response contains duplicate AppIDs")
            seen.add(identity)
            result.append(SteamEntitlement(identity, title.strip()))
        return tuple(sorted(result, key=lambda item: (item.title.casefold(), item.app_id)))

    @staticmethod
    def _url(config: SteamEntitlementConfig) -> str:
        return OWNED_GAMES_URL + "?" + urlencode({
            "key": config.api_key(), "steamid": config.steam_id,
            "include_appinfo": 1, "include_played_free_games": 1, "format": "json",
        })

    @staticmethod
    def _http_request(url: str, timeout: float) -> bytes:
        request = Request(url, headers={"Accept": "application/json", "User-Agent": "Lulu/1"})
        with urlopen(request, timeout=timeout) as response:
            if int(response.status) != 200:
                raise SteamEntitlementError(f"Valve ownership request returned HTTP {response.status}")
            return response.read()

    def _load_snapshot(self) -> tuple[SteamEntitlement, ...]:
        try:
            value = json.loads(self._snapshot_path.read_text())
            if not isinstance(value, dict) or value.get("schema") != 1:
                raise ValueError("unsupported entitlement snapshot")
            entries = value.get("games")
            if not isinstance(entries, list):
                raise ValueError("entitlement snapshot games are not a list")
            return self.parse_response({"response": {"games": [
                {"appid": int(item["app_id"]), "name": item["title"]}
                for item in entries if isinstance(item, dict)
            ]}})
        except (OSError, TypeError, ValueError, KeyError, SteamEntitlementError, json.JSONDecodeError):
            return ()

    def _save_snapshot(self, games: tuple[SteamEntitlement, ...]) -> None:
        try:
            self._snapshot_path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self._snapshot_path.with_suffix(".tmp")
            temporary.write_text(json.dumps({
                "schema": 1,
                "games": [{"app_id": game.app_id, "title": game.title} for game in games],
            }, sort_keys=True) + "\n")
            temporary.replace(self._snapshot_path)
        except OSError as error:
            # A cache write failure must never turn a successful Valve refresh
            # into a catalogue failure.
            LOGGER.warning("Could not persist Steam entitlement snapshot: %s", error)
