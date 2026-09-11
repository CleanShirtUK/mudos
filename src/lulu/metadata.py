"""Canonical game identity and deterministic metadata matching."""

from dataclasses import dataclass
import difflib
import hashlib
import json
import logging
import re
import time
from pathlib import Path
import urllib.error
import urllib.parse
import urllib.request


NOISE_WORDS = {
    "a", "b", "beta", "cart", "demo", "dump", "e", "en", "eng", "f", "fr",
    "fra", "g", "german", "i", "it", "j", "jpn", "japan", "k", "proto",
    "rev", "revision", "sample", "spanish", "t", "translation", "u", "usa",
    "v", "version", "world",
}
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
        or bool(re.fullmatch(r"(?:rev|revision|v|version)\s*\d+[a-z]?", value))
        or bool(re.fullmatch(r"(?:disc|disk|cd|side)[ _-]*[0-9a-z]+", value))
        or bool(re.fullmatch(r"[a-z]{2,5}[0-9]{2,6}", value))
        or bool(re.fullmatch(r"[!bhtuvx\-+]+", value))
        or bool(re.fullmatch(r"(?:[a-z]{2,3}[,_ /-]?){2,5}", value))
    )


def clean_local_title(value: str) -> str:
    """Remove common ROM-set decoration while retaining meaningful punctuation."""
    title = Path(value).stem
    title = title.replace("_", " ")
    title = re.sub(r"(?<!\d)\.(?!\d)", " ", title)

    def remove_group(match: re.Match[str]) -> str:
        contents = re.sub(r"\s+", " ", match.group(1).strip())
        parts = [part.strip() for part in re.split(r"[,;/]+", contents) if part.strip()]
        return "" if parts and all(_is_noise_token(part) for part in parts) else match.group(0)

    previous = None
    while previous != title:
        previous = title
        title = re.sub(r"\(([^()]*)\)|\[([^\[\]]*)\]", lambda m: remove_group(m), title)

    title = re.sub(r"(?:\s|[-_.])+(?:[A-Z]{2,5}\d{2,6})$", "", title)
    title = re.sub(r"\s+", " ", title).strip(" ._-\t")
    return title


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


class SteamGridDBMetadata:
    """Small cached SteamGridDB metadata client; credentials never enter cache data."""

    provider_name = "steamgriddb"

    def __init__(self, api_key: str | None = None, cache_dir: Path | None = None,
                 timeout: float = 4.0, now: callable = time.time) -> None:
        import os
        self.api_key = api_key or os.environ.get("LULU_STEAMGRIDDB_API_KEY")
        self.cache_dir = cache_dir or Path(os.environ.get(
            "LULU_METADATA_CACHE", "~/.cache/lulu/steamgriddb/metadata"
        )).expanduser()
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
        return [self._candidate(item) for item in payload.get("data", []) if isinstance(item, dict)]

    def _request_json(self, path: str) -> dict[str, object]:
        request = urllib.request.Request(
            "https://www.steamgriddb.com/api" + path,
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
    return any(alias in actual or any(alias in item for alias in actual) for alias in expected)


def _similarity(query: str, candidate: MetadataCandidate) -> float:
    values = (candidate.title, *candidate.aliases)
    return max(difflib.SequenceMatcher(None, query.casefold(), value.casefold()).ratio() for value in values if value)


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
        elif len(ranked) > 1 and score - next_score < self.margin:
            status = "ambiguous"
            method = "close-results"
        else:
            status = "matched"
            method = "platform-exact" if _platform_match(platform, candidate) else "title"
        return MetadataMatch(
            status, self.provider.provider_name if status == "matched" else "", 
            candidate.game_id if status == "matched" else "", candidate.title if status == "matched" else "",
            method, round(score, 4), query, tuple(item[1] for item in ranked[:5]),
        )
