"""Durable, conservative IGDB and ProtonDB reconciliation."""

from __future__ import annotations

import logging
import re
import time

from .catalogue import CatalogueDelta, CatalogueGame, CatalogueStore
from .igdb import IGDBClient, IGDBError, normalize_igdb_game
from .metadata import MetadataMatch, clean_local_title
from .protondb import ProtonDBClient, ProtonDBError


LOGGER = logging.getLogger("lulu.metadata-enrichment")
IGDB_TTL = 30 * 24 * 60 * 60
PROTONDB_TTL = 24 * 60 * 60
PRESENTATION_MEDIA_GENERATION = 1
PLATFORM_IDS = {"nes": 18, "gb": 33, "gbc": 22, "gba": 24, "nds": 20,
                "genesis": 29, "gamecube": 21, "ngc": 21, "wii": 5, "switch": 130,
                "ps1": 7, "psx": 7, "ps2": 8, "ps3": 9, "snes": 19,
                "pc": 6, "linux": 6, "steam": 6}


def _strict_title(value: str) -> str:
    value = clean_local_title(value)
    value = re.sub(r"[\[(](?:USA|Europe|Japan|World|Australia|Korea)[\])]?", "", value, flags=re.IGNORECASE)
    return re.sub(r"[^a-z0-9]+", "", value.casefold())


def _title_tokens(value: str) -> tuple[str, ...]:
    """Normalize punctuation variants while retaining meaningful plus suffixes."""
    cleaned = clean_local_title(value).casefold().replace("+", " plus ")
    return tuple(re.findall(r"[a-z0-9]+", cleaned))


def _exact_candidates(candidates: list[dict[str, object]], query: str) -> list[dict[str, object]]:
    query_tokens = _title_tokens(query)
    direct = []
    aliases = []
    for item in candidates:
        if _title_tokens(str(item.get("name", ""))) == query_tokens:
            direct.append(item)
            continue
        if any(_title_tokens(str(alias.get("name", ""))) == query_tokens
               for alias in item.get("alternative_names", []) or [] if isinstance(alias, dict)):
            aliases.append(item)
    # A game's own exact title outranks another game's regional/legacy alias.
    return direct if direct else aliases


class MetadataEnrichmentService:
    def __init__(self, store: CatalogueStore, igdb: IGDBClient | None = None,
                 protondb: ProtonDBClient | None = None) -> None:
        self.store = store
        self.igdb = igdb or IGDBClient()
        self.protondb = protondb or ProtonDBClient()

    def presentation_media_backfill_needed(self, game_id: str) -> bool:
        record = self.store.enrichment_record("presentation-media", game_id)
        normalized = record.get("normalized", {}) if record else {}
        try:
            return int(normalized.get("generation", 0)) < PRESENTATION_MEDIA_GENERATION
        except (AttributeError, TypeError, ValueError):
            return True

    def mark_presentation_media_backfill_attempted(self, game_id: str) -> None:
        self.store.apply_enrichment(
            "presentation-media", game_id, str(PRESENTATION_MEDIA_GENERATION),
            {"generation": PRESENTATION_MEDIA_GENERATION},
            match_method="media-backfill-v1", confidence=1.0, status="attempted")

    def search_games(self, game: CatalogueGame, query: str) -> list[dict[str, object]]:
        """Search IGDB for explicit user mapping choices; never writes a match."""
        if not self.igdb.configured or not query.strip():
            return []
        platform_id = PLATFORM_IDS.get(game.platform.casefold())
        matches = self.igdb.search(query.strip(), platform_id)
        results: list[dict[str, object]] = []
        seen: set[str] = set()
        for match in matches:
            normalized = normalize_igdb_game(match)
            game_id = str(normalized.get("igdb_id", ""))
            title = str(normalized.get("canonical_title", ""))
            if not game_id or not title or game_id in seen:
                continue
            seen.add(game_id)
            results.append({
                "provider": "igdb", "source": "IGDB", "id": game_id, "title": title,
                "year": normalized.get("release_year"),
                "platforms": normalized.get("platforms", []),
                "thumbnail": normalized.get("icon_square_url") or normalized.get("cover_url", ""),
                "subtitle": " · ".join(filter(None, (
                    str(normalized.get("release_year") or ""),
                    ", ".join(str(item) for item in normalized.get("platforms", [])),
                ))),
            })
        return results

    def canonical_match(self, game: CatalogueGame) -> MetadataMatch:
        """Resolve provider identity through IGDB without changing operational state."""
        reload_config = getattr(self.igdb, "reload_configuration", None)
        if callable(reload_config):
            reload_config()
        query = clean_local_title(game.title if game.provider == "steam" else
                                  (game.source_title or game.title))
        if not self.igdb.configured:
            return MetadataMatch("unmatched", normalized_search_title=query, method="igdb-unconfigured")
        try:
            value = None
            method = ""
            confidence = 0.0
            if game.provider == "steam" and game.provider_id.isdecimal():
                value = self.igdb.by_steam_appid(game.provider_id)
                method, confidence = "steam-appid", 1.0
                if value is None:
                    cached_id = (game.metadata_game_id if game.metadata_provider == "igdb"
                                 else game.igdb_id)
                    if cached_id:
                        value = self.igdb.by_id(cached_id)
                        if value is not None:
                            method, confidence = "cached-igdb-association", 1.0
                if value is None:
                    platform_id = PLATFORM_IDS["steam"]
                    candidates = self.igdb.search_platform(query, platform_id)
                    exact = _exact_candidates(candidates, query)
                    if len(exact) == 1:
                        value = exact[0]
                        method, confidence = "steam-title-platform", 0.95
                    elif len(exact) > 1:
                        return MetadataMatch("ambiguous", normalized_search_title=query,
                                             method="steam-title-platform-ambiguous")
            elif game.igdb_id:
                value = self.igdb.by_id(game.igdb_id)
                method, confidence = "provider-igdb-id", 1.0
            else:
                platform_id = PLATFORM_IDS.get(game.platform.casefold())
                if platform_id is None:
                    return MetadataMatch("unmatched", normalized_search_title=query,
                                         method="unsupported-platform")
                candidates = self.igdb.search_platform(query, platform_id)
                query_key = _strict_title(query)
                exact = _exact_candidates(candidates, query)
                if len(exact) != 1:
                    return MetadataMatch("ambiguous" if len(exact) > 1 else "unmatched",
                                         normalized_search_title=query,
                                         method="title-platform-ambiguous" if len(exact) > 1
                                         else "title-platform-no-exact")
                value = exact[0]
                method, confidence = "title-platform" if query == clean_local_title(
                    str(value.get("name", ""))) else "alias-platform", 0.95
            if not value:
                return MetadataMatch("unmatched", normalized_search_title=query,
                                     method=method + "-not-found")
            normalized = normalize_igdb_game(value)
            LOGGER.info(
                "metadata match provider=%s title=%r candidate=%r method=%s confidence=%.3f igdb_id=%s",
                game.provider, query, normalized.get("canonical_title", ""),
                method, confidence, value.get("id", ""),
            )
            return MetadataMatch(
                "matched", "igdb", str(value.get("id", "")),
                normalized.get("canonical_title", ""), method, confidence,
                query, presentation=normalized,
            )
        except IGDBError as error:
            LOGGER.info("IGDB canonical lookup unavailable game_id=%s reason=%s", game.game_id, error)
            return MetadataMatch("unmatched", normalized_search_title=query,
                                 method="igdb-network-error")

    def enrich_game(self, game: CatalogueGame, *, force: bool = False,
                    force_igdb: bool = False) -> list[CatalogueDelta]:
        deltas: list[CatalogueDelta] = []
        if game.provider == "steam" and game.provider_id.isdecimal():
            if self.igdb.configured and (force or force_igdb
                                         or not self.store.enrichment_is_fresh("igdb", game.game_id, IGDB_TTL)):
                try:
                    if game.match_locked and game.metadata_provider == "igdb" and game.metadata_game_id:
                        value = self.igdb.by_id(game.metadata_game_id)
                        match_method = "manual-igdb-id"
                        confidence = 1.0
                    else:
                        value = self.igdb.by_steam_appid(game.provider_id)
                        match_method = "steam-appid"
                        confidence = 1.0
                        cached_id = (game.metadata_game_id if game.metadata_provider == "igdb"
                                     else game.igdb_id)
                        if value is None and cached_id:
                            value = self.igdb.by_id(cached_id)
                            if value is not None:
                                match_method = "cached-igdb-association"
                    if value is None and not (game.match_locked and game.metadata_provider == "igdb"):
                        query = clean_local_title(game.title)
                        matches = _exact_candidates(
                            self.igdb.search_platform(query, PLATFORM_IDS["steam"]), query)
                        if len(matches) == 1:
                            value = matches[0]
                            match_method = "steam-title-platform"
                            confidence = 0.95
                    if value is not None:
                        normalized = normalize_igdb_game(value)
                        delta = self.store.apply_enrichment(
                            "igdb", game.game_id, str(value.get("id", "")), normalized,
                            match_method=match_method, confidence=confidence)
                        if delta:
                            deltas.append(delta)
                    else:
                        self._record_unmatched("igdb", game, "steam-appid-not-found")
                except IGDBError as error:
                    LOGGER.info("IGDB enrichment unavailable provider=igdb game_id=%s reason=%s", game.game_id, error)
            current = self.store.get_game(game.game_id) or game
            if self.protondb.enabled and (force or not self.store.enrichment_is_fresh("protondb", game.game_id, PROTONDB_TTL)):
                try:
                    value = self.protondb.summary(game.provider_id)
                    if value is not None:
                        delta = self.store.apply_enrichment(
                            "protondb", game.game_id, game.provider_id, value,
                            match_method="steam-appid", confidence=1.0)
                        if delta:
                            deltas.append(delta)
                except ProtonDBError as error:
                    LOGGER.info("ProtonDB enrichment unavailable game_id=%s reason=%s", game.game_id, error)
            return deltas

        if not game.platform:
            return deltas
        if not self.igdb.configured or (not force and not force_igdb
                                        and self.store.enrichment_is_fresh("igdb", game.game_id, IGDB_TTL)):
            return deltas
        canonical_id = (
            game.metadata_game_id if game.metadata_provider == "igdb" else game.igdb_id
        )
        if canonical_id:
            try:
                value = self.igdb.by_id(canonical_id)
            except IGDBError as error:
                LOGGER.info("IGDB enrichment unavailable provider=%s title=%r reason=%s",
                            game.provider, game.source_title or game.title, error)
                return deltas
            if value is not None:
                normalized = normalize_igdb_game(value)
                delta = self.store.apply_enrichment(
                    "igdb", game.game_id, str(value.get("id", canonical_id)), normalized,
                    match_method="canonical-igdb-id", confidence=1.0)
                if delta:
                    deltas.append(delta)
                return deltas
        platform_id = PLATFORM_IDS.get(game.platform.casefold())
        if platform_id is None:
            return deltas
        try:
            query = clean_local_title(game.source_title or game.title)
            candidates = self.igdb.search_platform(query, platform_id)
        except IGDBError as error:
            LOGGER.info("IGDB enrichment unavailable provider=igdb game_id=%s reason=%s", game.game_id, error)
            return deltas
        exact = _exact_candidates(candidates, query)
        if len(exact) != 1:
            self._record_unmatched("igdb", game, "ambiguous" if len(exact) > 1 else "no-exact-platform-match")
            return deltas
        value = exact[0]
        normalized = normalize_igdb_game(value)
        delta = self.store.apply_enrichment("igdb", game.game_id, str(value.get("id", "")), normalized,
                                            match_method="platform-title", confidence=0.95)
        if delta:
            deltas.append(delta)
        return deltas

    def enrich_all(self, games: list[CatalogueGame] | None = None, *, force: bool = False) -> tuple[CatalogueDelta, ...]:
        reload_config = getattr(self.igdb, "reload_configuration", None)
        if callable(reload_config):
            reload_config()
        deltas: list[CatalogueDelta] = []
        for game in games or self.store.list_catalogue_games():
            deltas.extend(self.enrich_game(game, force=force))
        return tuple(deltas)

    def enrich_protondb(self, games: list[CatalogueGame], *, force: bool = False) -> tuple[CatalogueDelta, ...]:
        """Refresh ProtonDB only for eligible installed Steam Library games."""
        if not self.protondb.enabled:
            return ()
        deltas: list[CatalogueDelta] = []
        for game in games:
            if game.provider != "steam" or not game.provider_id.isdecimal():
                continue
            if not force and self.store.enrichment_is_fresh("protondb", game.game_id, PROTONDB_TTL):
                continue
            try:
                value = self.protondb.summary(game.provider_id)
                if value is None:
                    continue
                delta = self.store.apply_enrichment(
                    "protondb", game.game_id, game.provider_id, value,
                    match_method="steam-appid", confidence=1.0)
                if delta:
                    deltas.append(delta)
            except ProtonDBError as error:
                LOGGER.info("ProtonDB enrichment unavailable game_id=%s reason=%s", game.game_id, error)
        return tuple(deltas)

    def _record_unmatched(self, provider: str, game: CatalogueGame, method: str) -> None:
        self.store.apply_enrichment(provider, game.game_id, "", {}, match_method=method,
                                    confidence=0.0, status="unmatched")
