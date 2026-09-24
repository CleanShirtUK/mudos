"""Canonical game identity and deterministic metadata matching."""

from dataclasses import dataclass
from dataclasses import field
import difflib
from datetime import datetime, timezone
import hashlib
import json
import logging
import re
import time
from pathlib import Path
import urllib.error
import urllib.parse
import urllib.request

from .paths import PATHS
from .provider_config import ProviderConfigurationService


NOISE_WORDS = {
    "a", "b", "beta", "cart", "demo", "dump", "e", "en", "eng", "f", "fr",
    "fra", "g", "german", "i", "it", "j", "jpn", "japan", "k", "proto",
    "base", "cart", "dlc", "game", "nsp", "rev", "revision", "sample", "spanish",
    "t", "translation", "u", "usa", "v", "version",
}
NOISE_REGION_WORDS = {"australia", "europe", "japan", "korea", "usa", "world"}
PLATFORM_ALIASES = {
    "nes": {"nes", "famicom", "nintendo entertainment system"},
    "genesis": {"genesis", "mega drive", "sega genesis", "sega mega drive"},
    "ps2": {"ps2", "playstation 2", "sony playstation 2"},
    "wii": {"wii", "nintendo wii"},
    "switch": {"switch", "nintendo switch"},
    "steam": {"steam", "pc", "windows", "linux"},
}


def _is_noise_token(value: str) -> bool:
    value = value.casefold().strip()
    return (
        value in NOISE_WORDS
        # Region words are noise only inside explicit ROM decoration groups;
        # meaningful title words such as "World" must survive bare titles.
        or bool(re.fullmatch(r"[0-9a-f]{8,20}", value))
        or bool(re.fullmatch(r"\d+(?:\.\d+)+", value))
        or bool(re.fullmatch(r"\d{1,3}", value))
        or bool(re.fullmatch(r"[a-z]{1,3}\d+(?:\.\d+)*", value))
        or bool(re.fullmatch(r"[a-z]{2,3}", value) and value not in {"the", "and"})
        or bool(re.fullmatch(r"(?:rev|revision|v|version)\s*\d+[a-z]?", value))
        or bool(re.fullmatch(r"(?:disc|disk|cd|side)[ _-]*[0-9a-z]+", value))
        or bool(re.fullmatch(r"[a-z]{2,5}[0-9]{2,6}", value))
        or bool(re.fullmatch(r"[!bhtuvx\-+]+", value))
        or bool(re.fullmatch(r"(?:[a-z]{2,3}[,_ /-]?){2,5}", value))
    )


def clean_local_title(value: str) -> str:
    """Remove common ROM-set decoration while retaining meaningful punctuation."""
    title = Path(value).name
    known_extensions = {
        ".7z", ".bin", ".cue", ".gb", ".gba", ".gbc", ".gen", ".iso", ".md",
        ".nds", ".nes", ".n64", ".nsp", ".pak", ".ps1", ".ps2", ".rom", ".rvz",
        ".sfc", ".smc", ".snes", ".z64", ".zip",
    }
    if Path(title).suffix.casefold() in known_extensions:
        title = Path(title).stem
    title = title.replace("_", " ")
    title = re.sub(r"(?<!\d)\.|\.(?!\d)", " ", title)
    title = re.sub(r"\bDLC\b.*$", "", title, flags=re.IGNORECASE)

    def remove_group(match: re.Match[str]) -> str:
        contents = re.sub(r"\s+", " ", (match.group(1) or match.group(2) or "").strip())
        parts = [part.strip() for part in re.split(r"[,;/]+", contents) if part.strip()]
        return "" if parts and all(_is_noise_token(part) for part in parts) else match.group(0)

    previous = None
    while previous != title:
        previous = title
        title = re.sub(r"\(([^()]*)\)|\[([^\[\]]*)\]", lambda m: remove_group(m), title)

    title = re.sub(r"(?:\s|[-_.])+(?:[A-Z]{2,5}\d{2,6})$", "", title)
    title = re.sub(r"\s+", " ", title)
    # ROM sets commonly put a leading article at the end of the title.
    # Normalize that reversible presentation form without fuzzy matching.
    title = re.sub(r"^(.+),\s*the(\s+-|$)", r"The \1\2", title, flags=re.IGNORECASE)
    tokens = title.split()
    while tokens and _is_trailing_noise_token(tokens[-1]):
        tokens.pop()
    title = " ".join(tokens)
    title = re.sub(r"\s+", " ", title).strip(" ._-\t")
    return title


def _is_trailing_noise_token(value: str) -> bool:
    value = value.casefold().strip()
    return (
        value in NOISE_WORDS
        or bool(re.fullmatch(r"[0-9a-f]{8,20}", value))
        or bool(re.fullmatch(r"[a-z]{1,3}\d+(?:\.\d+)*", value))
    )


@dataclass(frozen=True, slots=True)
class MetadataCandidate:
    game_id: str
    title: str
    aliases: tuple[str, ...] = ()
    platforms: tuple[str, ...] = ()
    raw: dict[str, object] | None = None


@dataclass(frozen=True, slots=True)
class MetadataMatch:
    status: str
    provider: str = ""
    game_id: str = ""
    canonical_title: str = ""
    method: str = ""
    confidence: float = 0.0
    normalized_search_title: str = ""
    candidates: tuple[MetadataCandidate, ...] = ()
    presentation: dict[str, object] = field(default_factory=dict)


class SteamGridDBMetadata:
    """Small cached SteamGridDB metadata client; credentials never enter cache data."""

    provider_name = "steamgriddb"

    def __init__(self, api_key: str | None = None, cache_dir: Path | None = None,
                 timeout: float = 4.0, now: callable = time.time) -> None:
        config = ProviderConfigurationService.from_environment().provider("metadata.steamgriddb")
        self.api_key = api_key if api_key is not None else (config.secret("api_key") if config.configured else None)
        self.endpoint = str(config.get("endpoint", "https://www.steamgriddb.com/api")).rstrip("/")
        self.cache_dir = cache_dir or PATHS.metadata_cache
        self.timeout = timeout
        self.now = now
        self._logger = logging.getLogger("lulu.metadata")

    def search(self, query: str, platform: str) -> list[MetadataCandidate] | None:
        if not self.api_key:
            return None
        key = hashlib.sha256(f"search:{platform}:{query.casefold()}".encode()).hexdigest()
        payload = self._cached(key)
        if payload is None:
            try:
                encoded = urllib.parse.quote(query, safe="")
                payload = self._request_json(f"/v2/search/autocomplete/{encoded}")
                self._write_cache(key, payload)
            except (OSError, ValueError, urllib.error.URLError, TimeoutError) as error:
                self._logger.warning("metadata search failed: %s", error)
                return None
        candidates = [self._candidate(item) for item in payload.get("data", []) if isinstance(item, dict)]
        hydrated: list[MetadataCandidate] = []
        for candidate in candidates[:10]:
            if candidate.platforms or not candidate.game_id:
                hydrated.append(candidate)
                continue
            details = self._game(candidate.game_id)
            if details:
                merged = dict(candidate.raw or {})
                merged.update(details)
                hydrated.append(self._candidate(merged))
            else:
                hydrated.append(candidate)
        return hydrated + candidates[10:]

    def search_steam_app(self, app_id: str) -> MetadataCandidate | None:
        """Resolve Steam presentation metadata by its canonical AppID."""
        if not self.api_key or not app_id.isdecimal() or int(app_id) < 1:
            return None
        key = hashlib.sha256(f"steam-app:{app_id}".encode()).hexdigest()
        payload = self._cached(key)
        if payload is None:
            try:
                payload = self._request_json(f"/v2/games/steam/{app_id}")
                self._write_cache(key, payload)
            except (OSError, ValueError, urllib.error.URLError, TimeoutError) as error:
                self._logger.warning("Steam metadata failed for %s: %s", app_id, error)
                return None
        data = payload.get("data") if isinstance(payload, dict) else None
        return self._candidate(data) if isinstance(data, dict) else None

    def _game(self, game_id: str) -> dict[str, object] | None:
        key = hashlib.sha256(f"game:{game_id}".encode()).hexdigest()
        payload = self._cached(key)
        if payload is not None:
            return payload
        try:
            payload = self._request_json(f"/v2/games/id/{urllib.parse.quote(game_id, safe='')}")
            data = payload.get("data")
            if isinstance(data, dict):
                self._write_cache(key, data)
                return data
        except (OSError, ValueError, urllib.error.URLError, TimeoutError) as error:
            self._logger.warning("metadata details failed for %s: %s", game_id, error)
        return None

    def _request_json(self, path: str) -> dict[str, object]:
        request = urllib.request.Request(
            self.endpoint + path,
            headers={"Authorization": f"Bearer {self.api_key}", "User-Agent": "Lulu/1"},
        )
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            return json.loads(response.read())

    def _cached(self, key: str) -> dict[str, object] | None:
        path = self.cache_dir / f"{key}.json"
        try:
            if not path.exists():
                return None
            value = json.loads(path.read_text())
            return value.get("payload") if isinstance(value, dict) else None
        except (OSError, ValueError, TypeError):
            return None

    def _write_cache(self, key: str, payload: dict[str, object]) -> None:
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        path = self.cache_dir / f"{key}.json"
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps({"cached_at": self.now(), "payload": payload}, sort_keys=True))
        temporary.replace(path)

    @staticmethod
    def _candidate(item: dict[str, object]) -> MetadataCandidate:
        def strings(value: object) -> tuple[str, ...]:
            if not isinstance(value, list):
                return ()
            return tuple(str(entry.get("name", entry)) if isinstance(entry, dict) else str(entry) for entry in value)

        return MetadataCandidate(
            game_id=str(item.get("id", "")),
            title=str(item.get("name", "")),
            aliases=strings(item.get("aliases", item.get("alternative_names", []))),
            platforms=strings(item.get("platforms", [])),
            raw=item,
        )


def _platform_match(platform: str, candidate: MetadataCandidate) -> bool | None:
    if not candidate.platforms:
        return None
    expected = PLATFORM_ALIASES.get(platform, {platform.casefold()})
    actual = {item.casefold() for item in candidate.platforms}
    return any(alias in actual or any(alias in actual_item for actual_item in actual) for alias in expected)


def _similarity(query: str, candidate: MetadataCandidate) -> float:
    values = (candidate.title, *candidate.aliases)
    def token_sort(value: str) -> str:
        return " ".join(sorted(re.findall(r"[a-z0-9]+", value.casefold())))

    return max(
        max(
            difflib.SequenceMatcher(None, query.casefold(), value.casefold()).ratio(),
            difflib.SequenceMatcher(None, token_sort(query), token_sort(value)).ratio(),
        )
        for value in values if value
    )


def _title_key(value: str) -> str:
    return " ".join(sorted(re.findall(r"[a-z0-9]+", value.casefold())))


class MetadataMatcher:
    def __init__(self, provider: SteamGridDBMetadata, minimum: float = 0.84, margin: float = 0.10) -> None:
        self.provider = provider
        self.minimum = minimum
        self.margin = margin

    def match(self, source_title: str, platform: str) -> MetadataMatch:
        query = clean_local_title(source_title)
        candidates = self.provider.search(query, platform)
        if candidates is None:
            return MetadataMatch("unmatched", normalized_search_title=query, method="network-error")
        ranked: list[tuple[float, MetadataCandidate]] = []
        for candidate in candidates:
            if not candidate.game_id or not candidate.title:
                continue
            platform_match = _platform_match(platform, candidate)
            if platform_match is False:
                continue
            score = _similarity(query, candidate)
            if platform_match is True:
                score = min(1.0, score + 0.08)
            ranked.append((score, candidate))
        ranked.sort(key=lambda item: (-item[0], item[1].game_id))
        if not ranked:
            return MetadataMatch("unmatched", normalized_search_title=query, method="no-result")
        score, candidate = ranked[0]
        next_score = ranked[1][0] if len(ranked) > 1 else 0.0
        if score < self.minimum:
            status = "unmatched"
            method = "low-confidence"
        elif (
            len(ranked) > 1
            and score == next_score
            and _title_key(query) == _title_key(candidate.title)
            and _title_key(candidate.title) == _title_key(ranked[1][1].title)
        ):
            status = "ambiguous"
            method = "equal-title-results"
        else:
            status = "matched"
            method = "platform-exact" if _platform_match(platform, candidate) else "title"
        return MetadataMatch(
            status, self.provider.provider_name if status == "matched" else "", 
            candidate.game_id if status == "matched" else "", candidate.title if status == "matched" else "",
            method, round(score, 4), query, tuple(item[1] for item in ranked[:5]),
            presentation_metadata(candidate) if status == "matched" else {},
        )

    def match_game(self, game: object) -> MetadataMatch:
        provider = str(getattr(game, "provider", ""))
        app_id = str(getattr(game, "provider_id", ""))
        if provider == "steam" and app_id.isdecimal():
            candidate = self.provider.search_steam_app(app_id)
            if candidate is not None and candidate.game_id and candidate.title:
                return MetadataMatch(
                    "matched", self.provider.provider_name, candidate.game_id, candidate.title,
                    "steam-appid", 1.0, str(getattr(game, "normalized_search_title", "")),
                    (candidate,), presentation_metadata(candidate),
                )
        return self.match(str(getattr(game, "source_title", "") or getattr(game, "title", "")),
                          str(getattr(game, "platform", "")))


def presentation_metadata(candidate: MetadataCandidate) -> dict[str, object]:
    """Extract only unambiguous canonical presentation fields from provider data."""
    raw = candidate.raw or {}
    genres = raw.get("genres", [])
    if isinstance(genres, list):
        genres = [str(item.get("name", "")).strip() if isinstance(item, dict) else str(item).strip()
                  for item in genres if str(item).strip()]
    else:
        genres = []
    release_date = raw.get("release_date", raw.get("first_release_date"))
    numeric_release = release_date
    if isinstance(release_date, str) and release_date.strip().isdigit():
        numeric_release = int(release_date.strip())
    if isinstance(numeric_release, (int, float)) and numeric_release > 0:
        release_date = datetime.fromtimestamp(numeric_release, timezone.utc).date().isoformat()
    else:
        release_date = str(release_date).strip() if release_date else None
    year = raw.get("release_year", raw.get("year"))
    try:
        release_year = int(year) if year is not None else (int(release_date[:4]) if release_date and release_date[:4].isdigit() else None)
    except (TypeError, ValueError):
        release_year = None
    result: dict[str, object] = {"genres": genres, "release_date": release_date, "release_year": release_year}
    for key in ("summary", "developer", "publisher", "franchise", "collection", "igdb_id",
                "total_playtime", "local_multiplayer", "online_multiplayer", "game_mode", "protondb_rating",
                "cover_url", "cover_width", "cover_height", "aliases"):
        if key in raw and raw[key] is not None:
            result[key] = raw[key]
    for key in ("game_modes", "platforms"):
        values = raw.get(key, [])
        if isinstance(values, list):
            result[key] = [str(item.get("name", "")).strip() if isinstance(item, dict) else str(item).strip()
                           for item in values if str(item).strip()]
    return result
