"""Durable, conservative IGDB and ProtonDB reconciliation."""

from __future__ import annotations

import logging
from pathlib import Path
import re
import time

from .catalogue import CatalogueDelta, CatalogueGame, CatalogueStore
from .igdb import IGDBClient, IGDBError, normalize_igdb_game
from .metadata import MetadataMatch, clean_local_title
from .protondb import ProtonDBClient, ProtonDBError


LOGGER = logging.getLogger("lulu.metadata-enrichment")
IGDB_TTL = 30 * 24 * 60 * 60
PROTONDB_TTL = 24 * 60 * 60
PLATFORM_IDS = {"nes": 18, "gb": 33, "gbc": 22, "gba": 24, "nds": 20,
                "genesis": 29, "gamecube": 21, "ngc": 21, "wii": 5, "switch": 130,
                "ps1": 7, "psx": 7, "ps2": 8, "ps3": 9, "snes": 19,
                "pc": 6, "linux": 6, "steam": 6}


def _strict_title(value: str) -> str:
    value = Path(value).stem.replace("_", " ")
    value = re.sub(r"[\[(](?:USA|Europe|Japan|World|Australia|Korea)[\])]?", "", value, flags=re.IGNORECASE)
    return re.sub(r"[^a-z0-9]+", "", value.casefold())


class MetadataEnrichmentService:
    def __init__(self, store: CatalogueStore, igdb: IGDBClient | None = None,
                 protondb: ProtonDBClient | None = None) -> None:
        self.store = store
        self.igdb = igdb or IGDBClient()
        self.protondb = protondb or ProtonDBClient()

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
                    platform_id = PLATFORM_IDS["steam"]
                    candidates = self.igdb.search_platform(query, platform_id)
                    query_key = _strict_title(query)
                    exact = [item for item in candidates
                             if _strict_title(str(item.get("name", ""))) == query_key
                             or query_key in {
                                 _strict_title(str(alias.get("name", "")))
                                 for alias in item.get("alternative_names", []) or []
                                 if isinstance(alias, dict)}]
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
                exact = []
                for item in candidates:
                    name = _strict_title(str(item.get("name", "")))
                    item_aliases = {_strict_title(str(alias.get("name", "")))
                                    for alias in item.get("alternative_names", []) or []
                                    if isinstance(alias, dict)}
                    if name == query_key or query_key in item_aliases:
                        exact.append(item)
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
            return MetadataMatch(
                "matched", "igdb", str(value.get("id", "")),
                normalized.get("canonical_title", ""), method, confidence,
                query, presentation=normalized,
            )
        except IGDBError as error:
            LOGGER.info("IGDB canonical lookup unavailable game_id=%s reason=%s", game.game_id, error)
            return MetadataMatch("unmatched", normalized_search_title=query,
                                 method="igdb-network-error")

    def enrich_game(self, game: CatalogueGame, *, force: bool = False) -> list[CatalogueDelta]:
        deltas: list[CatalogueDelta] = []
        if game.provider == "steam" and game.provider_id.isdecimal():
            if self.igdb.configured and (force or not self.store.enrichment_is_fresh("igdb", game.game_id, IGDB_TTL)):
                try:
                    value = self.igdb.by_steam_appid(game.provider_id)
                    if value is not None:
                        normalized = normalize_igdb_game(value)
                        delta = self.store.apply_enrichment(
                            "igdb", game.game_id, str(value.get("id", "")), normalized,
                            match_method="steam-appid", confidence=1.0)
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

        if game.provider not in {"local", "romm"} or not game.platform:
            return deltas
        if not self.igdb.configured or (not force and self.store.enrichment_is_fresh("igdb", game.game_id, IGDB_TTL)):
            return deltas
        platform_id = PLATFORM_IDS.get(game.platform.casefold())
        if platform_id is None:
            return deltas
        try:
            candidates = self.igdb.search_platform(game.source_title or game.title, platform_id)
        except IGDBError as error:
            LOGGER.info("IGDB enrichment unavailable provider=igdb game_id=%s reason=%s", game.game_id, error)
            return deltas
        exact = [item for item in candidates
                 if _strict_title(str(item.get("name", ""))) == _strict_title(game.source_title or game.title)]
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
