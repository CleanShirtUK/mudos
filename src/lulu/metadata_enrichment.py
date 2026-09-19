"""Durable, conservative IGDB and ProtonDB reconciliation."""

from __future__ import annotations

import logging
from pathlib import Path
import re
import time

from .catalogue import CatalogueDelta, CatalogueGame, CatalogueStore
from .igdb import IGDBClient, IGDBError, normalize_igdb_game
from .protondb import ProtonDBClient, ProtonDBError


LOGGER = logging.getLogger("lulu.metadata-enrichment")
IGDB_TTL = 30 * 24 * 60 * 60
PROTONDB_TTL = 24 * 60 * 60
PLATFORM_IDS = {"nes": 18, "ps2": 8, "wii": 5, "switch": 130, "genesis": 29}


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
        deltas: list[CatalogueDelta] = []
        for game in games or self.store.list_catalogue_games():
            deltas.extend(self.enrich_game(game, force=force))
        return tuple(deltas)

    def _record_unmatched(self, provider: str, game: CatalogueGame, method: str) -> None:
        self.store.apply_enrichment(provider, game.game_id, "", {}, match_method=method,
                                    confidence=0.0, status="unmatched")
