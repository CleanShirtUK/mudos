"""Unified game catalogue and game/content intent boundary."""

import asyncio
import ast
from dataclasses import replace
import logging
import os
import shutil
from pathlib import Path
from pathlib import Path
import signal
import subprocess
import tempfile
import shlex
import json
import time
import threading
import ctypes
from collections import deque

from dbus_next import BusType, Variant, DBusError
from dbus_next.aio import MessageBus
from dbus_next.service import ServiceInterface, method, signal as dbus_signal

from .catalogue import CatalogueDelta, CatalogueGame, CatalogueStore
from .artwork import LocalArtworkCache, SteamGridDBArtwork
from .contracts import ServiceDescriptor, ServiceName
from .controller_provisioning import ensure_provider_controller_config
from .emulator_runtime import EmulatorRuntimeAdapter
from .emulation import PLATFORMS, current_rom_root, ensure_storage
from .inputplumber import InputPlumberClient
from .local_content import LocalContentProvider
from .metadata import MetadataMatcher, SteamGridDBMetadata, clean_local_title
from .metadata_enrichment import MetadataEnrichmentService
from .network_manager import NetworkManagerAdapter
from .audio_manager import AudioManagerAdapter
from .display_manager import DisplayManagerAdapter
from .storage_manager import StorageManagerAdapter
from .plugins.romm.client import RommApiError, RommClient, RommConfig, RommGame
from .plugins.steam.provider import SteamProvider
from .plugins.steam.entitlements import SteamEntitlementSource
from .system_settings import CATEGORIES as SYSTEM_CATEGORIES, SystemSettingsProvider
from .paths import PATHS
from .platforms import load_platforms
from .providers import GuideAction, NativeConfigAdapter, load_base_guide, load_mudos_guide, load_providers
from .plugins import ComponentRegistry, PluginRegistry
from .credential import (CredentialBroker, CredentialInput, CredentialPresentation,
                          CredentialStatus, SecretStore)
from .web_credentials import WebCredentialStore


DESCRIPTOR = ServiceDescriptor(
    name=ServiceName.CONSOLED,
    authority="unified game catalogue and game/platform intent",
    owned_state=(
        "normalized provider records",
        "content installation metadata",
        "game profiles",
        "compatibility intent",
        "emulator configuration intent",
    ),
    notes=("External runtime configuration is generated output, not authority.",),
)


def _load_plugin_registry() -> PluginRegistry:
    root = PATHS.plugins_root
    installed = PATHS.install_root / "config" / "plugins"
    # The user plugin root also owns per-plugin settings and may therefore
    # exist before any user manifests are installed.  Settings alone must not
    # mask the shipped plugin implementations.
    has_manifests = root.is_dir() and any(root.glob("*/plugin.toml"))
    if not has_manifests and installed.is_dir():
        root = installed
    registry = PluginRegistry(root)
    registry.discover()
    return registry


class ConsoleCatalog:
    """Consoled-owned normalized catalogue."""

    descriptor = DESCRIPTOR

    def __init__(self, store: CatalogueStore | None = None, provider: SteamProvider | None = None,
                  local_provider: LocalContentProvider | None = None,
                  metadata: SteamGridDBMetadata | None = None,
                  romm: RommClient | None = None,
                  steam_entitlements: SteamEntitlementSource | None = None,
                  plugin_registry: PluginRegistry | None = None) -> None:
        self.store = store or CatalogueStore()
        self._plugins = plugin_registry or _load_plugin_registry()
        if plugin_registry is None:
            self._plugins.discover()
        self.provider = provider or next((item for item in self._plugins.with_capability("session")
                                          if hasattr(item, "open_main")), None)
        self.local_provider = local_provider or LocalContentProvider()
        self.artwork = SteamGridDBArtwork()
        self.romm_artwork = LocalArtworkCache()
        self.metadata = metadata or SteamGridDBMetadata()
        self.matcher = MetadataMatcher(self.metadata)
        self.enrichment = MetadataEnrichmentService(self.store)
        self.steam_entitlements = steam_entitlements or next(
            (item for item in self._plugins.with_capability("installed_catalogue")
             if hasattr(item, "has_snapshot")), None)
        self._diagnostic_artwork_originals: dict[str, str] = {}
        self._diagnostic_timestamp_originals: dict[str, tuple[int | None, int | None]] = {}
        self._diagnostic_canonical_originals: dict[str, str] = {}
        self.last_delta_batches: list[tuple[object, ...]] = []
        self.romm = romm or next((item for item in self._plugins.with_capability("installed_catalogue")
                                  if hasattr(item, "list_games")), None)
        connection = self.store.connection
        LOGGER.info(
            "catalogue sqlite connection path=%s creator_thread=%s check_same_thread=false "
            "journal_mode=%s locking_mode=%s synchronous=%s busy_timeout=%s "
            "in_transaction=%s",
            self.store.path, threading.get_ident(),
            connection.execute("PRAGMA journal_mode").fetchone()[0],
            connection.execute("PRAGMA locking_mode").fetchone()[0],
            connection.execute("PRAGMA synchronous").fetchone()[0],
            connection.execute("PRAGMA busy_timeout").fetchone()[0],
            connection.in_transaction,
        )

    def refresh(self, stages: set[str] | None = None) -> list[dict[str, object]]:
        all_stages = {"steam", "local", "romm", "components", "romm-artwork", "metadata", "artwork"}
        selected = all_stages if stages is None else set(stages)
        self.last_delta_batches = []
        LOGGER.info("catalogue refresh worker started stages=%s", ",".join(sorted(selected)) or "none")
        LOGGER.info("catalogue refresh worker thread=%s in_transaction=%s",
                    threading.get_ident(), self.store.connection.in_transaction)
        direct_stage = next((stage for stage in selected if stage.startswith(
            ("direct-canonical-alt-game:", "direct-canonical-restore-game:"))), None)
        sqlite_stage = next((stage for stage in selected if stage in {
            "sqlite-wal", "sqlite-checkpoint", "sqlite-delete"}), None)
        if sqlite_stage:
            if sqlite_stage == "sqlite-checkpoint":
                result = self.store.diagnostic_checkpoint()
                LOGGER.info("catalogue sqlite diagnostic checkpoint result=%s", result)
            else:
                mode = "wal" if sqlite_stage == "sqlite-wal" else "delete"
                result = self.store.diagnostic_set_journal_mode(mode)
                LOGGER.info("catalogue sqlite diagnostic journal_mode=%s result=%s", mode, result)
            return [game.as_dict() for game in self.store.list_games()]
        if direct_stage:
            game_id = direct_stage.split("game:", 1)[1]
            existing = self.store.get_game(game_id)
            if existing is None:
                raise ValueError(f"diagnostic game does not exist: {game_id}")
            if direct_stage.startswith("direct-canonical-alt-game:"):
                original = existing.canonical_title
                self._diagnostic_canonical_originals.setdefault(game_id, original)
                expected = self._diagnostic_canonical_originals[game_id]
                value = expected + " [diagnostic]"
            else:
                expected = self._diagnostic_canonical_originals.get(game_id)
                if expected is None:
                    raise RuntimeError("diagnostic restore has no captured original value")
                expected = expected + " [diagnostic]"
                value = self._diagnostic_canonical_originals[game_id]
                if existing.canonical_title != expected:
                    raise RuntimeError(
                        f"diagnostic restore precondition failed game_id={game_id} "
                        f"expected={expected!r} actual={existing.canonical_title!r}"
                    )
            LOGGER.info("catalogue direct diagnostic canonical_title game_id=%s expected=%r requested=%r",
                        game_id, expected, value)
            metrics = self.store.diagnostic_update_canonical_title(game_id, expected, value)
            LOGGER.info("catalogue direct diagnostic canonical_title transaction=%s", metrics)
            result = [game.as_dict() for game in self.store.list_games()]
            return result
        if "steam" in selected and self.steam_entitlements is not None and self.provider is not None:
            LOGGER.info("catalogue stage started name=steam")
            self.steam_entitlements.refresh()
            if self.steam_entitlements.has_snapshot:
                self.store.reconcile_steam_entitlements(
                    self.steam_entitlements.snapshot, self.provider
                )
            else:
                # Before the first successful Valve snapshot, retain existing
                # entitlement rows and only refresh local installed manifests.
                self.store.reconcile_steam(self.provider)
            if self.store.last_deltas:
                self.last_delta_batches.append(self.store.last_deltas)
            LOGGER.info("catalogue stage completed name=steam sqlite_commit=complete")
        if "local" in selected:
            LOGGER.info("catalogue stage started name=local")
            ensure_storage()
            self.store.reconcile_local(self.local_provider, current_rom_root())
            if self.store.last_deltas:
                self.last_delta_batches.append(self.store.last_deltas)
            LOGGER.info("catalogue stage completed name=local sqlite_commit=complete")
        if "components" in selected:
            for source in self._plugins.with_capability("catalogue"):
                if not hasattr(source, "reconcile") or not getattr(source, "provider_id", ""):
                    continue
                try:
                    LOGGER.info("catalogue stage started name=component provider=%s", source.provider_id)
                    applications = asyncio.run(source.reconcile())
                    games = [CatalogueGame.from_component_app(item) for item in applications
                             if bool(getattr(item, "game", False))]
                    self.store.reconcile_component_apps(str(source.provider_id), games)
                    if self.store.last_deltas:
                        self.last_delta_batches.append(self.store.last_deltas)
                    LOGGER.info("catalogue stage completed name=component provider=%s games=%d",
                                source.provider_id, len(games))
                except Exception as error:
                    LOGGER.info("component catalogue unavailable provider=%s error=%s",
                                source.provider_id, type(error).__name__)
        romm_stages = {
            "romm", "romm-readonly", "romm-reconcile-only", "romm-presentation-only",
            "romm-reconcile-mark-only", "romm-reconcile-upsert-only",
            "romm-reconcile-upsert-rollback", "romm-reconcile-upsert-noop",
        }
        single_upsert_stage = next(
            (stage for stage in selected if stage.startswith((
                "romm-reconcile-upsert-game:",
                "romm-reconcile-upsert-rollback-game:",
                "romm-reconcile-upsert-noop-game:",
                "romm-reconcile-upsert-artwork-game:",
                "romm-reconcile-upsert-metadata-game:",
                "romm-reconcile-upsert-timestamps-game:",
                "romm-reconcile-upsert-seen-game:",
                "romm-reconcile-upsert-synced-game:",
                "romm-reconcile-upsert-seen-alt-game:",
                "romm-reconcile-upsert-seen-restore-game:",
                "romm-reconcile-upsert-synced-alt-game:",
                "romm-reconcile-upsert-synced-restore-game:",
                "romm-reconcile-upsert-artwork-alt-game:",
                "romm-reconcile-upsert-artwork-restore-game:",
            ))),
            None,
        )
        if (selected.intersection(romm_stages) or single_upsert_stage) and self.romm is not None:
            romm_readonly = "romm-readonly" in selected and not selected.intersection(
                 {"romm", "romm-reconcile-only", "romm-presentation-only",
                 "romm-reconcile-mark-only", "romm-reconcile-upsert-only",
                 "romm-reconcile-upsert-rollback", "romm-reconcile-upsert-noop"})
            romm_reconcile_only = selected.intersection(
                {"romm-reconcile-only", "romm-reconcile-mark-only", "romm-reconcile-upsert-only",
                 "romm-reconcile-upsert-rollback", "romm-reconcile-upsert-noop"})
            romm_reconcile_only = bool(romm_reconcile_only or single_upsert_stage) and not romm_readonly
            romm_presentation_only = "romm-presentation-only" in selected and not romm_readonly
            romm_stage_name = (
                "romm-readonly" if romm_readonly else
                "romm-reconcile-mark-only" if "romm-reconcile-mark-only" in selected else
                "romm-reconcile-upsert-only" if "romm-reconcile-upsert-only" in selected else
                "romm-reconcile-upsert-rollback" if "romm-reconcile-upsert-rollback" in selected else
                "romm-reconcile-upsert-noop" if "romm-reconcile-upsert-noop" in selected else
                "romm-reconcile-upsert-artwork-game" if single_upsert_stage and "artwork-game:" in single_upsert_stage else
                "romm-reconcile-upsert-metadata-game" if single_upsert_stage and "metadata-game:" in single_upsert_stage else
                "romm-reconcile-upsert-timestamps-game" if single_upsert_stage and "timestamps-game:" in single_upsert_stage else
                "romm-reconcile-upsert-seen-game" if single_upsert_stage and "seen-game:" in single_upsert_stage else
                "romm-reconcile-upsert-synced-game" if single_upsert_stage and "synced-game:" in single_upsert_stage else
                "romm-reconcile-upsert-seen-alt-game" if single_upsert_stage and "seen-alt-game:" in single_upsert_stage else
                "romm-reconcile-upsert-seen-restore-game" if single_upsert_stage and "seen-restore-game:" in single_upsert_stage else
                "romm-reconcile-upsert-synced-alt-game" if single_upsert_stage and "synced-alt-game:" in single_upsert_stage else
                "romm-reconcile-upsert-synced-restore-game" if single_upsert_stage and "synced-restore-game:" in single_upsert_stage else
                "romm-reconcile-upsert-artwork-alt-game" if single_upsert_stage and "artwork-alt-game:" in single_upsert_stage else
                "romm-reconcile-upsert-artwork-restore-game" if single_upsert_stage and "artwork-restore-game:" in single_upsert_stage else
                "romm-reconcile-upsert-game" if single_upsert_stage else
                "romm-reconcile-only" if romm_reconcile_only else
                "romm-presentation-only" if romm_presentation_only else "romm"
            )
            LOGGER.info("catalogue stage started name=%s", romm_stage_name)
            try:
                LOGGER.info("catalogue romm substage started name=network-list")
                romm_games = self.romm.list_games()
                LOGGER.info("catalogue romm substage completed name=network-list items=%d",
                            len(romm_games))
                normalized: dict[str, object] = {}
                for game in romm_games:
                    # RomM's transitional Steam marker platform is no longer a
                    # Steam catalogue input. Steam ownership is sourced locally;
                    # RomM continues to own all non-Steam ROM records below.
                    if game.platform_slug.casefold() == "steam":
                        continue
                    entry = CatalogueGame.from_romm(game)
                    artwork = game.artwork_url
                    if "romm-artwork" in selected:
                        artwork = self.romm_artwork.cache_remote(entry.game_id, game.artwork_url)
                        LOGGER.info("catalogue romm-artwork item game_id=%s cached=%s",
                                    entry.game_id, bool(artwork))
                    entry = replace(
                        entry, artwork_url=artwork, last_seen_at=int(time.time()),
                        last_synced_at=int(time.time())
                    )
                    normalized[entry.game_id] = entry
                LOGGER.info("catalogue romm substage completed name=normalize items=%d",
                            len(normalized))
                romm_commit = "complete"
                if romm_readonly or romm_presentation_only:
                    romm_commit = "skipped"
                else:
                    LOGGER.info("catalogue romm substage started name=sqlite-reconcile")
                    reconcile_mode = (
                        "mark" if "romm-reconcile-mark-only" in selected else
                        "upsert-rollback" if "romm-reconcile-upsert-rollback" in selected
                            or (single_upsert_stage and single_upsert_stage.startswith(
                                "romm-reconcile-upsert-rollback-game:")) else
                        "upsert" if "romm-reconcile-upsert-only" in selected else "full"
                    )
                    reconcile_games = list(normalized.values())
                    if single_upsert_stage:
                        if single_upsert_stage.startswith("romm-reconcile-upsert-rollback-game:"):
                            reconcile_mode = "upsert-rollback"
                            game_id = single_upsert_stage.removeprefix(
                                "romm-reconcile-upsert-rollback-game:")
                        else:
                            reconcile_mode = "upsert"
                            game_id = single_upsert_stage.split("game:", 1)[1]
                        reconcile_games = [game for game in reconcile_games if game.game_id == game_id]
                        LOGGER.info("catalogue romm substage upsert-game target=%s matched=%d",
                                    game_id, len(reconcile_games))
                        variant = single_upsert_stage.split("game:", 1)[0]
                        if reconcile_games and variant.endswith("artwork-"):
                            existing = self.store.get_game(game_id)
                            if existing is not None:
                                reconcile_games = [replace(existing,
                                    artwork_url=reconcile_games[0].artwork_url)]
                        elif reconcile_games and variant.endswith("metadata-"):
                            existing = self.store.get_game(game_id)
                            if existing is not None:
                                incoming = reconcile_games[0]
                                reconcile_games = [replace(existing,
                                    title=incoming.title,
                                    metadata_provider=incoming.metadata_provider,
                                    metadata_game_id=incoming.metadata_game_id,
                                    canonical_title=incoming.canonical_title,
                                    match_status=incoming.match_status,
                                    match_method=incoming.match_method,
                                    match_confidence=incoming.match_confidence,
                                    metadata_checked_at=incoming.metadata_checked_at,
                                    release_date=incoming.release_date,
                                    release_year=incoming.release_year,
                                    metadata_resolver_version=incoming.metadata_resolver_version)]
                        elif reconcile_games and variant.endswith("timestamps-"):
                            existing = self.store.get_game(game_id)
                            if existing is not None:
                                incoming = reconcile_games[0]
                                reconcile_games = [replace(existing,
                                    last_seen_at=incoming.last_seen_at,
                                    last_synced_at=incoming.last_synced_at)]
                        elif reconcile_games and (variant.endswith("seen-") or variant.endswith("synced-")
                                                  or "seen-alt-" in variant or "seen-restore-" in variant
                                                  or "synced-alt-" in variant or "synced-restore-" in variant):
                            existing = self.store.get_game(game_id)
                            if existing is not None:
                                incoming = reconcile_games[0]
                                is_seen = "seen-" in variant
                                is_restore = "restore-" in variant
                                if "alt-" in variant:
                                    self._diagnostic_timestamp_originals.setdefault(
                                        game_id, (existing.last_seen_at, existing.last_synced_at))
                                original = self._diagnostic_timestamp_originals.get(game_id,
                                    (existing.last_seen_at, existing.last_synced_at))
                                reconcile_games = [replace(existing,
                                    last_seen_at=(original[0] if is_restore and is_seen else
                                                  incoming.last_seen_at if is_seen else existing.last_seen_at),
                                    last_synced_at=(original[1] if is_restore and not is_seen else
                                                    incoming.last_synced_at if not is_seen else existing.last_synced_at))]
                        elif reconcile_games and (variant.endswith("artwork-alt-") or variant.endswith("artwork-restore-")):
                            existing = self.store.get_game(game_id)
                            if existing is not None:
                                if variant.endswith("artwork-alt-"):
                                    self._diagnostic_artwork_originals.setdefault(
                                        game_id, existing.artwork_url)
                                    alternate = next((candidate.artwork_url
                                        for candidate in self.store.list_catalogue_games()
                                        if candidate.game_id != game_id and candidate.artwork_url),
                                        existing.artwork_url)
                                    reconcile_games = [replace(existing, artwork_url=alternate)]
                                else:
                                    reconcile_games = [replace(existing,
                                        artwork_url=self._diagnostic_artwork_originals.get(
                                            game_id, existing.artwork_url))]
                    if "romm-reconcile-upsert-noop" in selected or (
                            single_upsert_stage and single_upsert_stage.startswith(
                                "romm-reconcile-upsert-noop-game:")):
                        noop_games = []
                        for game in reconcile_games:
                            existing = self.store.get_game(game.game_id)
                            if existing is not None:
                                LOGGER.info(
                                    "catalogue romm substage upsert-noop game_id=%s "
                                    "source_values_equal=%s bound_values_equal=true",
                                    game.game_id, game.as_dict() == existing.as_dict())
                                noop_games.append(existing)
                        reconcile_games = noop_games
                        reconcile_mode = "upsert"
                    for game in reconcile_games:
                        if game.provider == "steam":
                            existing = self.store.get_game(game.game_id)
                            changed_fields = []
                            if existing is not None:
                                incoming = game.as_dict()
                                stored = existing.as_dict()
                                changed_fields = [
                                    field for field in incoming
                                    if incoming[field] != stored.get(field)
                                ]
                            LOGGER.info("catalogue steam upsert values game_id=%s changed_fields=%s",
                                        game.game_id, ",".join(changed_fields) or "none")
                    LOGGER.info("catalogue romm substage upsert items=%s",
                                ",".join(game.game_id for game in reconcile_games))
                    self.store.reconcile_romm(reconcile_games, mode=reconcile_mode)
                    if self.store.last_deltas:
                        self.last_delta_batches.append(self.store.last_deltas)
                    LOGGER.info("catalogue romm substage completed name=sqlite-reconcile sqlite_commit=complete")
                # Non-Steam local ROMs have their own stable content IDs and
                # cannot be joined by manifest. Use RomM's platform/title pair
                # only as a fallback for missing presentation fields.
                romm_by_title_platform = {}
                for entry in normalized.values():
                    romm_by_title_platform.setdefault(
                        (clean_local_title(entry.title), entry.platform), entry
                    )
                presentation_updates = 0
                if not romm_readonly and not romm_reconcile_only:
                    presentation_deltas = []
                    with self.store.atomic():
                        for existing in self.store.list_games():
                            if existing.provider != "local":
                                continue
                            source = romm_by_title_platform.get(
                                (clean_local_title(existing.title), existing.platform)
                            )
                            if source is not None:
                                delta = self.store.apply_romm_presentation(existing.game_id, source)
                                if delta is not None:
                                    presentation_deltas.append(delta)
                                presentation_updates += 1
                    if presentation_deltas:
                        self.last_delta_batches.append(tuple(presentation_deltas))
                LOGGER.info("catalogue romm substage completed name=local-presentation items=%d",
                            presentation_updates)
                LOGGER.info("catalogue stage completed name=%s items=%d sqlite_commit=%s",
                            romm_stage_name,
                            len(romm_games), romm_commit)
            except RommApiError as error:
                LOGGER.warning("RomM refresh failed; retaining previous snapshot: %s", error)
        if "metadata" in selected:
            LOGGER.info("catalogue stage started name=metadata")
            metadata_count = 0
            metadata_deltas = []
            with self.store.atomic():
                for game in self.store.list_catalogue_games():
                    if self.store.needs_metadata_match(game.game_id):
                        match = self.matcher.match_game(game)
                        delta = self.store.apply_metadata_match(game.game_id, match)
                        if delta is not None:
                            metadata_deltas.append(delta)
                        metadata_count += 1
                        LOGGER.info("catalogue metadata item game_id=%s status=%s method=%s",
                                    game.game_id, match.status, match.method)
            if metadata_deltas:
                self.last_delta_batches.append(tuple(metadata_deltas))
            LOGGER.info("catalogue stage completed name=metadata items=%d sqlite_commit=complete",
                        metadata_count)
        if "metadata-enrichment" in selected:
            LOGGER.info("catalogue stage started name=metadata-enrichment")
            deltas = self.enrichment.enrich_all()
            if deltas:
                self.last_delta_batches.append(deltas)
            LOGGER.info("catalogue stage completed name=metadata-enrichment items=%d",
                        len(deltas))
        if "artwork" in selected:
            LOGGER.info("catalogue stage started name=artwork")
            games = self.store.list_catalogue_games()
            artwork_count = 0
            artwork_deltas = []
            with self.store.atomic():
                for game_id, artwork_url in self.artwork.enrich(games).items():
                    delta = self.store.set_artwork_url(game_id, artwork_url)
                    if delta is not None:
                        artwork_deltas.append(delta)
                    artwork_count += 1
                    LOGGER.info("catalogue artwork item game_id=%s cached=%s",
                            game_id, bool(artwork_url))
            if artwork_deltas:
                self.last_delta_batches.append(tuple(artwork_deltas))
            LOGGER.info("catalogue stage completed name=artwork items=%d sqlite_commit=complete",
                        artwork_count)
        games = self.store.list_catalogue_games()
        result = [game.as_dict() for game in self.store.list_games()]
        LOGGER.info("catalogue refresh worker completed games=%d sqlite_read=complete", len(result))
        return result

    def enrich_metadata(self, game_id: str | None = None, *, force: bool = False) -> int:
        games = [self.store.get_game(game_id)] if game_id else self.store.list_catalogue_games()
        deltas = self.enrichment.enrich_all([game for game in games if game is not None], force=force)
        if deltas:
            self.last_delta_batches.append(deltas)
        return len(deltas)

    def set_metadata_match(self, game_id: str, provider: str, metadata_game_id: str,
                           canonical_title: str) -> CatalogueDelta | None:
        return self.store.set_metadata_match(game_id, provider, metadata_game_id, canonical_title)

    def clear_metadata_match(self, game_id: str) -> CatalogueDelta | None:
        return self.store.clear_metadata_match(game_id)

    def metadata_search(self, game_id: str, query: str) -> list[dict[str, object]]:
        game = self.store.get_game(game_id)
        if game is None:
            raise ValueError("game does not exist")
        search_title = query.strip() or game.canonical_title or game.normalized_search_title or clean_local_title(game.source_title or game.title)
        candidates = self.metadata.search(search_title, game.platform)
        if candidates is None:
            return []
        return [{
            "id": candidate.game_id,
            "title": candidate.title,
            "aliases": list(candidate.aliases),
            "platforms": list(candidate.platforms),
        } for candidate in candidates]

    def _refresh_game_artwork(self, game_id: str) -> CatalogueDelta | None:
        game = self.store.get_game(game_id)
        if game is None:
            raise ValueError("game does not exist")
        for refreshed_id, artwork_url in self.artwork.enrich([game]).items():
            if refreshed_id == game_id:
                return self.store.set_artwork_url(game_id, artwork_url)
        return None

    def apply_metadata_match(self, game_id: str, provider: str, metadata_game_id: str,
                             canonical_title: str) -> tuple[CatalogueDelta, ...]:
        deltas = []
        delta = self.store.set_metadata_match(game_id, provider, metadata_game_id, canonical_title)
        if delta is not None:
            deltas.append(delta)
        artwork_delta = self._refresh_game_artwork(game_id)
        if artwork_delta is not None:
            deltas.append(artwork_delta)
        return tuple(deltas)

    def set_title_override(self, game_id: str, title: str) -> CatalogueDelta | None:
        return self.store.set_display_title_override(game_id, title)

    def clear_title_override(self, game_id: str) -> CatalogueDelta | None:
        return self.store.clear_display_title_override(game_id)

    def suppress_artwork(self, game_id: str) -> CatalogueDelta | None:
        return self.store.suppress_artwork(game_id)

    def restore_artwork(self, game_id: str) -> tuple[CatalogueDelta, ...]:
        deltas = []
        delta = self.store.restore_artwork(game_id)
        if delta is not None:
            deltas.append(delta)
        artwork_delta = self._refresh_game_artwork(game_id)
        if artwork_delta is not None:
            deltas.append(artwork_delta)
        return tuple(deltas)

    def platform_categories(self) -> list[dict[str, str]]:
        return [{"scope": f"platform:{platform}", "platform": platform, "label": label}
                 for platform, label in self.store.list_platforms()]

    def available_games(self, provider: str | None = None) -> list[dict[str, object]]:
        return [game.as_dict() for game in self.store.list_available_games(provider)]

    def resolve_steam_install(self, game_id: str) -> str:
        game = self.store.get_game(game_id)
        if game is None or game.provider != "steam":
            raise ValueError("game is not a Steam catalogue entry")
        if game.install_state != "available" or game.availability_state != "available":
            raise ValueError("game is not available to install")
        if not game.provider_id.isdecimal() or int(game.provider_id) < 1:
            raise ValueError("Steam AppID is invalid")
        return game.provider_id


BUS_NAME = "org.lulu.Consoled"
OBJECT_PATH = "/org/lulu/Console"
INTERFACE_NAME = "org.lulu.Console"
LOGGER = logging.getLogger("lulu.consoled")


def _keyboard_boundary(action: str) -> bool:
    """Call the provider-neutral Mudos keyboard boundary."""
    root = Path(os.environ.get("LULU_INSTALL_ROOT", "/opt/lulu/current"))
    if action == "status":
        socket_path = Path(os.environ.get("XDG_RUNTIME_DIR", "/run/user/958")) / "mudos-osk-bridge.sock"
        try:
            import socket
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
                client.settimeout(1.0)
                client.connect(str(socket_path))
                client.sendall(b"status\n")
                reply = client.recv(64).decode().strip()
            if reply.startswith("ok "):
                return reply[3:] == "visible"
            raise RuntimeError(reply.removeprefix("error ") or "keyboard status failed")
        except (OSError, TimeoutError) as error:
            raise RuntimeError("Mudos OSK bridge is not available") from error
    command = root / "scripts" / "mudos-keyboard"
    result = subprocess.run([str(command), action], check=False, capture_output=True,
                            text=True, timeout=3)
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or f"keyboard {action} failed")
    return result.stdout.strip() == "visible"


def _mudos_provider_device_indices() -> dict[int, int]:
    """Resolve logical players to current SDL gamepad indices.

    Providers consume the normalized Mudos controller model.  InputPlumber is
    deliberately not part of this contract: a controller may be backed by a
    real composite or by the capability-verified recovery source.
    """
    controllers = _mudos_provider_controller_identities()
    result = {
        player: int(controller["sdl_index"])
        for player, controller in controllers.items()
        if isinstance(controller.get("sdl_index"), int)
    }
    if result:
        return result
    raise RuntimeError("Mudos has no assigned SDL gamepad controllers")


def _mudos_controller_state() -> dict[int, dict[str, object]]:
    """Return connected, assigned normalized controllers keyed by player."""
    state = subprocess.run(
        [
            "busctl",
            "--user",
            "call",
            "org.lulu.ConsoleSessiond",
            "/org/lulu/ConsoleSession",
            "org.lulu.ConsoleSession",
            "GetState",
        ],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    # busctl prints a D-Bus string using C-style quoting, not JSON quoting.
    # JSON embedded in that string can contain apostrophes and escaped quotes.
    state_json = _parse_busctl_json_string(state)
    assignments = state_json.get("controller", {}).get("controllers", {})
    result: dict[int, dict[str, object]] = {}
    if isinstance(assignments, dict):
        for controller in assignments.values():
            if not isinstance(controller, dict) or not controller.get("connected"):
                continue
            player = controller.get("player")
            if isinstance(player, int) and player in range(1, 5):
                result[player] = dict(controller)
    return result


def _mudos_provider_controller_identities() -> dict[int, dict[str, object]]:
    """Return live SDL identity for each assigned logical player."""
    result = _mudos_controller_state()
    # SDL is the provider boundary.  Read its current list at launch time so
    # a replacement device cannot inherit the previous device's GUID/name.
    try:
        library = ctypes.CDLL("libSDL3.so")
        library.SDL_Init.argtypes = [ctypes.c_uint32]
        library.SDL_Init.restype = ctypes.c_bool
        library.SDL_GetGamepads.argtypes = [ctypes.POINTER(ctypes.c_int)]
        library.SDL_GetGamepads.restype = ctypes.POINTER(ctypes.c_uint32)
        library.SDL_GetGamepadNameForID.argtypes = [ctypes.c_uint32]
        library.SDL_GetGamepadNameForID.restype = ctypes.c_char_p
        class SDLGuid(ctypes.Structure):
            _fields_ = [("data", ctypes.c_ubyte * 16)]
        library.SDL_GetGamepadGUIDForID.argtypes = [ctypes.c_uint32]
        library.SDL_GetGamepadGUIDForID.restype = SDLGuid
        library.SDL_GUIDToString.argtypes = [SDLGuid, ctypes.c_char_p, ctypes.c_int]
        if library.SDL_Init(0x2000):
            count = ctypes.c_int()
            ids = library.SDL_GetGamepads(ctypes.byref(count))
            for index in range(count.value):
                instance = ids[index]
                guid = ctypes.create_string_buffer(33)
                library.SDL_GUIDToString(library.SDL_GetGamepadGUIDForID(instance), guid, 33)
                # Match the normalized assignment to the current SDL list.
                # The live index is the only provider-facing device identity.
                for player, controller in result.items():
                    if controller.get("sdl_index") in (None, index):
                        result[player] = {
                            **controller,
                            "sdl_index": index,
                            "sdl_guid": guid.value.decode("ascii"),
                            "sdl_name": (library.SDL_GetGamepadNameForID(instance) or b"").decode(),
                        }
            library.SDL_Quit()
    except (OSError, AttributeError, RuntimeError):
        LOGGER.warning("SDL inventory unavailable; provider launch will report missing live identity")
    return result


def _parse_busctl_json_string(output: str) -> dict[str, object]:
    """Decode the JSON string returned by ``busctl call ... GetState``."""
    value = ast.literal_eval(output.removeprefix("s ").strip())
    decoded = json.loads(value if isinstance(value, str) else value)
    if not isinstance(decoded, dict):
        raise ValueError("ConsoleSessiond state is not an object")
    return decoded


def _retroarch_child_config(device_indices: dict[int, int]) -> str:
    directory = Path(os.environ.get("XDG_RUNTIME_DIR", "/tmp"))
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="ascii",
        prefix="lulu-retroarch-",
        suffix=".cfg",
        dir=directory,
        delete=False,
    ) as config:
        config.write(
            "".join(
                f'input_player{player}_joypad_index = "{device_indices[player]}"\n'
                for player in range(1, 5)
                if player in device_indices
            ) + 'network_cmd_enable = "true"\n'
            'network_cmd_port = "55355"\n'
            'quit_on_close_content = "true"\n'
            'config_save_on_exit = "false"\n'
        )
        return config.name


class ConsoleInterface(ServiceInterface):
    def __init__(self, catalogue: ConsoleCatalog, local_runtime: EmulatorRuntimeAdapter | None = None,
                 system_settings: SystemSettingsProvider | None = None,
                 sessiond: object | None = None,
                 network_manager: NetworkManagerAdapter | None = None,
                 audio_manager: AudioManagerAdapter | None = None,
                 storage_manager: StorageManagerAdapter | None = None,
                 display_manager: DisplayManagerAdapter | None = None,
                 credentials: CredentialBroker | None = None) -> None:
        super().__init__(INTERFACE_NAME)
        self.catalogue = catalogue
        self.local_runtime = local_runtime
        self.system_settings = system_settings or SystemSettingsProvider()
        self.sessiond = sessiond
        self.network_manager = network_manager or NetworkManagerAdapter()
        self.audio_manager = audio_manager or AudioManagerAdapter()
        self.storage_manager = storage_manager or StorageManagerAdapter()
        self.display_manager = display_manager or DisplayManagerAdapter()
        self.credentials = credentials or CredentialBroker()
        self.secrets = SecretStore()
        self.web_credentials = WebCredentialStore(self.secrets)
        self._local_process: asyncio.subprocess.Process | None = None
        self._local_token: str | None = None
        self._refresh_task: asyncio.Task[list[dict[str, object]]] | None = None
        self._catalogue_generation = 0
        self._delta_history: deque[tuple[int, list[dict[str, object]]]] = deque(maxlen=256)
        self._providers = load_providers()
        plugin_root = PATHS.plugins_root
        installed_plugins = PATHS.install_root / "config" / "plugins"
        # A user plugin-settings directory may exist before the shipped
        # manifests are copied there. In that case still discover the bundled
        # plugin definitions, while retaining the user-owned settings path for
        # normal configuration and secrets.
        if (not plugin_root.is_dir() or not any(plugin_root.glob("*/plugin.toml"))) and installed_plugins.is_dir():
            plugin_root = installed_plugins
        self._plugins = PluginRegistry(plugin_root)
        self._plugins.discover()
        self._components = ComponentRegistry(self._plugins)
        self._components.discover()
        self._base_guide = load_base_guide()
        self._mudos_guide = load_mudos_guide()
        self._platforms = load_platforms()

    def _provider_for_game_id(self, game_id: str):
        game = self.catalogue.store.get_game(game_id)
        if game is None or game.provider != "local":
            return None

    def _guide_context(self, state: dict[str, object]) -> tuple[str, object | None]:
        if str(state.get("delegated_surface", "")) == "browser":
            return "browser", None
        lifecycle = str(state.get("lifecycle", "shell"))
        if lifecycle == "shell":
            return "shell", None
        provider_id = state.get("provider_id")
        if not provider_id and str(state.get("session_kind")) == "game":
            game = self.catalogue.store.get_game(str(state.get("primary_id", "")))
            if game is not None:
                try:
                    provider_id = game.provider
                    if provider_id == "local":
                        platform = self._platforms.get(game.platform)
                        provider_id = platform.default_provider
                except KeyError:
                    provider_id = None
        if not provider_id:
            return "game", None
        surface = state.get("delegated_surface")
        context = str(surface) if surface else (
            "standalone" if state.get("session_kind") == "provider_standalone" else "game")
        try:
            return context, self._providers.get(str(provider_id))
        except KeyError:
            return context, None

    @method()
    async def GetGuideActions(self) -> "s":
        """Return the composed, normalized Guide model for the active context."""
        state = json.loads(await self.sessiond.call_get_state()) if self.sessiond is not None else {"lifecycle": "shell"}
        context, provider = self._guide_context(state)
        provider_actions = self._providers.guide_actions(provider.provider_id, context) if provider is not None else ()
        # Provider actions lead, including Quit; Mudos-owned actions follow.
        actions = list(provider_actions)
        if context == "game" and not actions and state.get("active_identity"):
            # Generic launch-capable components need not be copied into the
            # legacy provider TOML tree just to expose process-group Quit.
            actions.append(GuideAction("process-group-quit", "Quit", "quit",
                                       "process-group-terminate", ("game",), False, 90))
        if context == "browser":
            actions.append(GuideAction("browser-quit", "Quit", "quit", "browser:quit", ("browser",), False, 1))
        actions.extend(action for action in self._base_guide if context in action.contexts)
        actions.extend(action for action in self._mudos_guide if context in action.contexts)
        return json.dumps([{
            "id": action.action_id, "label": action.label, "role": action.role,
            "target": action.target, "confirm": action.confirm, "order": action.order,
        } for action in actions], separators=(",", ":"))

    @method()
    def GetComponentRegistry(self) -> "s":
        """Expose one safe descriptor API for future OOBE/Admin setup flows."""
        return json.dumps(self._components.setup_records(self.secrets), sort_keys=True, separators=(",", ":"))

    @method()
    async def ExecuteGuideAction(self, action_id: "s") -> "s":
        """Execute system-owned Guide actions; return provider targets to the helper."""
        if action_id == "browser-quit":
            state = json.loads(await self.sessiond.call_get_state())
            if str(state.get("delegated_surface", "")) != "browser":
                raise ValueError("browser is not active")
            await self.sessiond.call_set_delegated_surface("")
            return "executed"
        if action_id == "process-group-quit":
            state = json.loads(await self.sessiond.call_get_state())
            if not state.get("active_identity"):
                raise ValueError("no owned process is active")
            return "process-group-terminate"
        action = next((item for item in self._base_guide if item.action_id == action_id), None)
        if action is None:
            action = next((item for item in self._mudos_guide if item.action_id == action_id), None)
        if action is not None:
            if action.target == "session:set-input-mode":
                await self.sessiond.call_set_input_mode("compat")
            elif action.target == "session:reset-mudos":
                await self.sessiond.call_reset_mudos()
            elif action.target == "system:reboot":
                await self.sessiond.call_reboot()
            elif action.target == "system:shutdown":
                await self.sessiond.call_shutdown()
            elif action.target == "mudos:downloads":
                await self.sessiond.call_request_mudos_downloads()
            elif action.target == "process-group-terminate":
                return action.target
            elif action.target == "browser:quit":
                await self.sessiond.call_set_delegated_surface("")
            else:
                raise ValueError(f"unsupported base Guide target: {action.target}")
            return "executed"
        state = json.loads(await self.sessiond.call_get_state())
        context, provider = self._guide_context(state)
        if provider is None:
            raise ValueError("no provider owns the active Guide context")
        actions = self._providers.guide_actions(provider.provider_id, context)
        selected = next((item for item in actions if item.action_id == action_id), None)
        if selected is None:
            raise ValueError("Guide action is not valid in the active context")
        if selected.target == "mudos:downloads":
            await self.sessiond.call_request_mudos_downloads()
            return "executed"
        return selected.target
        try:
            platform = self._platforms.get(game.platform)
            return self._providers.get(platform.default_provider or "")
        except KeyError:
            return None

    def _provider_setting(self, provider_id: str) -> NativeConfigAdapter | None:
        if provider_id != "retroarch":
            return None
        return NativeConfigAdapter(PATHS.provider_config_root("retroarch") / "retroarch.cfg")

    @method()
    def ListMudosProviders(self) -> "s":
        """Registry-owned provider menu declarations for the Mudos Menu."""
        return json.dumps([
            {"id": provider.provider_id, "name": provider.name,
             "controller_mode": provider.standalone_launch.controller_mode}
            for provider in self._providers.standalone()
        ], sort_keys=False)

    @method()
    async def LaunchProviderStandalone(self, provider_id: "s", timeout_ms: "u") -> "s":
        return await self._launch_provider_standalone(provider_id, timeout_ms)

    async def _launch_provider_standalone(self, provider_id: str, timeout_ms: int) -> str:
        provider = self._providers.get(provider_id)
        launch = provider.standalone_launch
        if launch is None or not launch.command:
            raise ValueError("provider has no standalone launch")
        command = list(launch.command)
        executable = command[0]
        if not os.path.isabs(executable):
            executable = shutil.which(executable) or ""
            command[0] = executable
        if not executable or not os.path.isfile(executable):
            raise ValueError(f"standalone runtime missing: {provider.provider_id}")
        if self.sessiond is None:
            raise ValueError("session lifecycle unavailable")
        environment = os.environ.copy()
        environment["XDG_CONFIG_HOME"] = str(PATHS.provider_config_root(provider.provider_id))
        child_config_path: str | None = None
        if provider.provider_id in {"retroarch", "pcsx2"}:
            environment.pop("WAYLAND_DISPLAY", None)
        if provider.provider_id == "retroarch":
            device_indices = await asyncio.to_thread(_mudos_provider_device_indices)
            child_config_path = await asyncio.to_thread(_retroarch_child_config, device_indices)
            command[1:1] = ["--appendconfig", child_config_path]
            environment["LIBRETRO_AUTOCONFIG_DIRECTORY"] = "/opt/lulu/config/retroarch/autoconfig"
        steam_delegated = provider.provider_id == "steam"
        if steam_delegated:
            await asyncio.to_thread(self.catalogue.provider.open_main)
            # Steam is already resident and the URI helper exits immediately.
            # Keep a lifecycle-owned sentinel until the user leaves Steam.
            process = await asyncio.create_subprocess_exec(
                "sleep", "2147483647", stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL,
                start_new_session=True,
            )
        else:
            process = await asyncio.create_subprocess_exec(
                *command, stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL,
                env=environment, start_new_session=True,
            )
        try:
            token = await self.sessiond.call_begin_provider_session(
                provider.provider_id, launch.controller_mode, process.pid,
                os.getpgid(process.pid), os.path.realpath(f"/proc/{process.pid}/exe"), command)
        except Exception:
            try:
                os.killpg(os.getpgid(process.pid), signal.SIGTERM)
            except (ProcessLookupError, OSError):
                pass
            await process.wait()
            raise
        self._local_process = process
        self._local_token = token

        async def apply_provider_controller_mode() -> None:
            # Apply ownership only after the provider has had time to present.
            # Verify that this standalone session is still current first.
            await asyncio.sleep(1)
            try:
                state = json.loads(await self.sessiond.call_get_state())
                if (state.get("launch_token") == token
                        and state.get("session_kind") == "provider_standalone"
                        and state.get("lifecycle") == "game"):
                    if not steam_delegated:
                        await self.sessiond.call_set_input_mode(launch.controller_mode)
                        LOGGER.info("standalone provider controller mode applied provider=%s mode=%s",
                                    provider.provider_id, launch.controller_mode)
            except Exception:
                LOGGER.exception("standalone provider controller mode failed provider=%s",
                                 provider.provider_id)
        asyncio.create_task(apply_provider_controller_mode())

        async def reap() -> None:
            exit_code = await process.wait()
            if child_config_path is not None:
                try:
                    os.unlink(child_config_path)
                except FileNotFoundError:
                    pass
            if steam_delegated:
                await asyncio.to_thread(self.catalogue.provider.hide_main)
            try:
                await self.sessiond.call_end_local_session(token, exit_code)
            except Exception:
                LOGGER.exception("standalone provider session end failed provider=%s", provider.provider_id)
            LOGGER.info("standalone provider exit provider=%s pid=%s exit_code=%s", provider.provider_id, process.pid, exit_code)
            if self._local_token == token:
                self._local_process = None
                self._local_token = None
        if steam_delegated:
            async def watch_steam_window() -> None:
                # Steam's URI helper and update/web bootstrap can take several
                # seconds before the final main window is mapped. Do not
                # interpret that startup gap as a user closing Steam.
                for _ in range(20):
                    if await asyncio.to_thread(self.catalogue.provider.main_window_visible):
                        break
                    await asyncio.sleep(1)
                while process.returncode is None:
                    state = json.loads(await self.sessiond.call_get_state())
                    if state.get("lifecycle") == "game":
                        focused = await asyncio.to_thread(self.catalogue.provider.main_window_focused)
                        desired = "compat" if focused else "gamepad"
                        if state.get("input_mode") != desired:
                            await self.sessiond.call_set_input_mode(desired)
                            LOGGER.info("focused provider controller mode applied provider=steam mode=%s", desired)
                    visible = await asyncio.to_thread(self.catalogue.provider.main_window_visible)
                    if not visible:
                        process.terminate()
                        return
                    await asyncio.sleep(1)
            asyncio.create_task(watch_steam_window())
        asyncio.create_task(reap())
        LOGGER.info("standalone provider started provider=%s command=%r token=%s", provider.provider_id, command, token)
        return token

    @method()
    def GetProviderGuide(self, game_id: "s") -> "s":
        """Return registry-resolved, Guide-safe settings metadata."""
        provider = self._provider_for_game_id(game_id)
        if provider is None or not provider.capabilities.settings:
            return json.dumps({"available": False})
        adapter = self._provider_setting(provider.provider_id)
        if adapter is None:
            return json.dumps({"available": False})
        return json.dumps({
            "available": True,
            "provider_id": provider.provider_id,
            "provider_name": provider.name,
            "setting_key": "fps_show",
            "setting_label": "Show FPS",
            "setting_value": (adapter.get("", "fps_show", "false") or "false").strip('"'),
        })

    @method()
    def SetProviderSetting(self, provider_id: "s", key: "s", value: "s") -> "s":
        LOGGER.info("provider setting mutation requested provider=%s key=%s value=%s", provider_id, key, value)
        if provider_id != "retroarch" or key != "fps_show" or value not in {"true", "false"}:
            raise DBusError("org.lulu.Console.Error.InvalidProviderSetting", "unsupported provider setting")
        adapter = self._provider_setting(provider_id)
        assert adapter is not None
        # RetroArch uses a global sectionless config, represented by an empty
        # section in the line-preserving native adapter.
        adapter.set("", key, value)
        result = (adapter.get("", key, value) or value).strip('"')
        LOGGER.info("provider setting mutation applied provider=%s key=%s value=%s", provider_id, key, result)
        return result

    def _publish_delta_batches(self, batches: object) -> None:
        for batch in batches:
            deltas = [delta for delta in batch if isinstance(delta, CatalogueDelta)]
            if not deltas:
                continue
            self._catalogue_generation += 1
            self._delta_history.append(
                (self._catalogue_generation, [delta.as_dict() for delta in deltas])
            )
            self.CatalogueGenerationChanged(self._catalogue_generation)

    def _publish_delta(self, delta: CatalogueDelta | None) -> None:
        self._publish_delta_batches([(delta,)] if delta is not None else [])

    
    @staticmethod
    def _variant(key: str, value: object) -> Variant:
        if isinstance(value, bool):
            return Variant("b", value)
        if isinstance(value, str):
            return Variant("s", value)
        if isinstance(value, int):
            return Variant("x", value)
        if isinstance(value, float):
            return Variant("d", value)
        if isinstance(value, list) and all(isinstance(item, str) for item in value):
            return Variant("as", value)
        if value is None:
            raise TypeError(f"catalogue field {key!r} cannot be None in D-Bus output")
        raise TypeError(f"unsupported catalogue field {key!r} type: {type(value).__name__}")

    
    @classmethod
    def _variants(cls, game: dict[str, object]) -> dict[str, Variant]:
        # D-Bus has no nullable primitive signature; omission represents an
        # unknown optional metadata field while SQLite/JSON retain NULL.
        return {key: cls._variant(key, value) for key, value in game.items() if value is not None}


    @method()
    async def Refresh(self) -> "u":
        count = await self.refresh_catalogue()
        return count

    @method()
    async def ShowKeyboard(self) -> "b":
        return await asyncio.to_thread(_keyboard_boundary, "show")

    @method()
    async def HideKeyboard(self) -> "b":
        return await asyncio.to_thread(_keyboard_boundary, "hide")

    @method()
    async def KeyboardVisible(self) -> "b":
        return await asyncio.to_thread(_keyboard_boundary, "status")

    @method()
    async def GetNetworkState(self) -> "s":
        return json.dumps(await self.network_manager.snapshot(), sort_keys=True)

    @method()
    async def SetWifiEnabled(self, enabled: "b") -> "s":
        return json.dumps(await self.network_manager.set_enabled(enabled), sort_keys=True)

    @method()
    async def ConnectWifi(self, ssid: "s", password: "s") -> "s":
        return json.dumps(await self.network_manager.connect_network(ssid, password), sort_keys=True)

    @method()
    async def DisconnectWifi(self) -> "s":
        return json.dumps(await self.network_manager.disconnect(), sort_keys=True)

    @method()
    async def ForgetWifi(self, ssid: "s") -> "s":
        return json.dumps(await self.network_manager.forget(ssid), sort_keys=True)

    @method()
    async def GetAudioState(self) -> "s":
        return json.dumps(await self.audio_manager.snapshot(), sort_keys=True)

    @method()
    async def SetAudioOutput(self, device_id: "s") -> "s":
        return json.dumps(await self.audio_manager.set_default_output(device_id), sort_keys=True)

    @method()
    async def SetAudioInput(self, device_id: "s") -> "s":
        return json.dumps(await self.audio_manager.set_default_input(device_id), sort_keys=True)

    @method()
    async def SetAudioVolume(self, device_id: "s", volume: "u", input_device: "b") -> "s":
        return json.dumps(await self.audio_manager.set_volume(device_id, volume, input_device), sort_keys=True)

    @method()
    async def SetAudioMute(self, device_id: "s", muted: "b", input_device: "b") -> "s":
        return json.dumps(await self.audio_manager.set_mute(device_id, muted, input_device), sort_keys=True)

    @method()
    async def GetStorageState(self) -> "s":
        return json.dumps(await self.storage_manager.snapshot(), sort_keys=True)

    @method()
    async def MountStorage(self, device_id: "s") -> "s":
        return json.dumps(await self.storage_manager.mount(device_id), sort_keys=True)

    @method()
    async def UnmountStorage(self, device_id: "s") -> "s":
        return json.dumps(await self.storage_manager.unmount(device_id), sort_keys=True)

    @method()
    async def EjectStorage(self, device_id: "s") -> "s":
        return json.dumps(await self.storage_manager.eject(device_id), sort_keys=True)

    @method()
    async def SelectStorageTarget(self, kind: "s", device_id: "s") -> "s":
        return json.dumps(await self.storage_manager.select_target(kind, device_id), sort_keys=True)

    @method()
    async def GetDisplayState(self) -> "s":
        state = await asyncio.to_thread(self.display_manager.snapshot)
        return json.dumps(state, sort_keys=True)

    @method()
    async def ApplyDisplay(self, output: "s", width: "u", height: "u", refresh: "d") -> "s":
        state = await asyncio.to_thread(self.display_manager.apply, output, width, height, refresh)
        return json.dumps(state, sort_keys=True)

    @method()
    async def RefreshStages(self, stages: "as") -> "u":
        count = await self.refresh_catalogue(set(stages))
        return count

    @method()
    async def RefreshMetadata(self, game_id: "s", force: "b") -> "u":
        """Run optional external enrichment in the catalogue worker boundary."""
        count = await asyncio.to_thread(self.catalogue.enrich_metadata, game_id or None, force=force)
        self._publish_delta_batches(getattr(self.catalogue, "last_delta_batches", []))
        self.CatalogueChanged()
        return count

    async def refresh_catalogue(self, stages: set[str] | None = None, source: str = "api") -> int:
        """Run one refresh at a time and share it across callers."""
        LOGGER.info("catalogue refresh requested source=%s", source)
        if self._refresh_task is None or self._refresh_task.done():
            if stages is None:
                self._refresh_task = asyncio.create_task(
                    asyncio.to_thread(self.catalogue.refresh), name="catalogue-refresh")
            else:
                self._refresh_task = asyncio.create_task(
                    asyncio.to_thread(lambda: self.catalogue.refresh(stages)),
                    name="catalogue-refresh")
        refresh_task = self._refresh_task
        try:
            result = await asyncio.shield(refresh_task)
        finally:
            if self._refresh_task is refresh_task and refresh_task.done():
                self._refresh_task = None
        self._publish_delta_batches(getattr(self.catalogue, "last_delta_batches", []))
        self.CatalogueChanged()
        LOGGER.info("catalogue refresh applied games=%d", len(result))
        return len(result)

    @method()
    def ListGames(self, scope: "s") -> "aa{sv}":
        if scope == "recent":
            games = self.catalogue.store.list_recent()
        else:
            games = self.catalogue.store.list_games(scope)
        return [self._variants(game.as_dict()) for game in games]

    @method()
    def GetCatalogueSnapshot(self) -> "(ts)":
        return self._get_catalogue_snapshot()

    def _get_catalogue_snapshot(self) -> list[object]:
        games = [game.as_dict() for game in self.catalogue.store.list_catalogue_games()]
        # The D-Bus signature is a single STRUCT (ts).  dbus-next requires
        # struct values to be represented by lists, not Python tuples.
        return [self._catalogue_generation, json.dumps(games, sort_keys=True)]

    @method()
    def GetCatalogueChanges(self, since_generation: "t") -> "(bs)":
        return self._get_catalogue_changes(since_generation)

    def _get_catalogue_changes(self, since_generation: int) -> list[object]:
        if since_generation == self._catalogue_generation:
            return [False, "[]"]
        if not self._delta_history:
            return [True, "[]"]
        first_generation = self._delta_history[0][0]
        if since_generation < first_generation - 1:
            return [True, "[]"]
        batches = [
            {"generation": generation, "deltas": deltas}
            for generation, deltas in self._delta_history
            if generation > since_generation
        ]
        return [False, json.dumps(batches, sort_keys=True)]

    @method()
    def ListPlatformCategories(self) -> "aa{sv}":
        return [self._variants(category) for category in self.catalogue.platform_categories()]

    @method()
    def ListAvailableGames(self, provider: "s") -> "aa{sv}":
        return [self._variants(game) for game in self.catalogue.available_games(provider or None)]

    @method()
    def ResolveSteamInstall(self, game_id: "s") -> "s":
        try:
            return self.catalogue.resolve_steam_install(game_id)
        except ValueError as error:
            raise DBusError("org.lulu.Console.Error.InvalidGame", str(error)) from error

    @method()
    def ListSystemSettings(self, category: "s") -> "aa{sv}":
        return [self._variants(item) for item in self.system_settings.list_settings(category)]

    @method()
    def ListSystemCategories(self) -> "as":
        return list(SYSTEM_CATEGORIES)

    @method()
    def SearchMetadata(self, game_id: "s", query: "s") -> "aa{sv}":
        return [self._variants(item) for item in self.catalogue.metadata_search(game_id, query)]

    @method()
    def SetMetadataMatch(self, game_id: "s", provider: "s", metadata_game_id: "s",
                         canonical_title: "s") -> "":
        self._publish_delta_batches([
            (delta,) for delta in self.catalogue.apply_metadata_match(
                game_id, provider, metadata_game_id, canonical_title)
        ])

    @method()
    def GetPluginStatus(self) -> "s":
        """Return normalized plugin health without exposing plugin internals."""
        return json.dumps(self._plugins.status(), separators=(",", ":"))

    @method()
    def GetPluginAuthStatus(self, plugin_id: "s") -> "s":
        auth = self._plugins.for_plugin(plugin_id, "authentication")
        if not auth:
            return json.dumps({"status": "unavailable"}, separators=(",", ":"))
        provider = auth[0]
        try:
            return json.dumps(provider.status(), separators=(",", ":"))
        except Exception as error:
            LOGGER.exception("plugin auth status failed plugin=%s", plugin_id)
            return json.dumps({"status": "degraded", "error": str(error)}, separators=(",", ":"))

    @method()
    async def BeginPluginAuthentication(self, plugin_id: "s") -> "s":
        auth = self._plugins.for_plugin(plugin_id, "authentication")
        if not auth:
            raise DBusError("org.lulu.Console.Error.PluginUnavailable", "plugin authentication unavailable")
        result = auth[0].begin()
        provider_id = str(result.get("provider_id", "")) if isinstance(result, dict) else ""
        if provider_id:
            return json.dumps({"status": "surface_requested",
                               "launch": await self._launch_provider_standalone(provider_id, 15000)},
                              separators=(",", ":"))
        return json.dumps(result, separators=(",", ":"))

    @method()
    async def BeginCredentialRequest(self, title: "s", prompt: "s", input_type: "s",
                                     secret: "b", min_length: "u", max_length: "u",
                                     multiline: "b", presentation: "s") -> "s":
        try:
            request = await self.credentials.request(title, prompt, CredentialInput(input_type),
                                                       secret=secret, min_length=min_length,
                                                       max_length=max_length, multiline=multiline,
                                                       presentation=CredentialPresentation(presentation or "prompted"))
            return json.dumps(request.public_state(), separators=(",", ":"))
        except (RuntimeError, ValueError) as error:
            raise DBusError("org.lulu.Console.Error.CredentialUnavailable", str(error)) from error

    @method()
    def GetWebCredential(self, profile_id: "s", origin: "s") -> "s":
        try:
            return json.dumps(self.web_credentials.get(profile_id, origin), separators=(",", ":"))
        except ValueError as error:
            raise DBusError("org.lulu.Console.Error.WebCredentialUnavailable", str(error)) from error

    @method()
    def SaveWebCredential(self, profile_id: "s", origin: "s", username: "s", password: "s") -> "s":
        try:
            result = self.web_credentials.save(profile_id, origin, username, password)
            if profile_id == "questarr":
                # Credential persistence is complete before this asynchronous
                # trigger is submitted.  The UI does not wait for Questarr's
                # network reconciliation.
                subprocess.Popen(
                    ["systemctl", "start", "lulu-questarr-reconcile.service"],
                    stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL, close_fds=True,
                )
            return json.dumps(result, separators=(",", ":"))
        except ValueError as error:
            raise DBusError("org.lulu.Console.Error.WebCredentialUnavailable", str(error)) from error

    @method()
    def ClearWebCredential(self, profile_id: "s", origin: "s") -> "s":
        try:
            return json.dumps(self.web_credentials.clear(profile_id, origin), separators=(",", ":"))
        except ValueError as error:
            raise DBusError("org.lulu.Console.Error.WebCredentialUnavailable", str(error)) from error

    @method()
    async def BeginOwnedCredentialRequest(self, title: "s", prompt: "s", input_type: "s",
                                          secret: "b", min_length: "u", max_length: "u",
                                          owner_id: "s", owner_json: "s",
                                           choices_json: "s", multiline: "b", presentation: "s") -> "s":
        try:
            owner = json.loads(owner_json) if owner_json else {}
            if not isinstance(owner, dict):
                raise ValueError("credential owner metadata must be an object")
            choices = json.loads(choices_json) if choices_json else []
            if not isinstance(choices, list) or not all(isinstance(item, str) for item in choices):
                raise ValueError("credential choices must be a string list")
            request = await self.credentials.request(
                title, prompt, CredentialInput(input_type), secret=secret,
                min_length=min_length, max_length=max_length, owner_id=owner_id,
                 owner=owner, choices=tuple(choices), multiline=multiline,
                 presentation=CredentialPresentation(presentation or "prompted"),
            )
            return json.dumps(request.public_state(), separators=(",", ":"))
        except (RuntimeError, ValueError, TypeError) as error:
            raise DBusError("org.lulu.Console.Error.CredentialUnavailable", str(error)) from error

    @method()
    def GetCredentialState(self) -> "s":
        return json.dumps(self.credentials.state(), separators=(",", ":"))

    @method()
    async def WithdrawOwnedCredentialRequest(self, request_id: "s", owner_id: "s",
                                             message: "s") -> "s":
        try:
            await self.credentials.withdraw(request_id, owner_id, message)
            return json.dumps(self.credentials.state(), separators=(",", ":"))
        except (KeyError, PermissionError, ValueError) as error:
            raise DBusError("org.lulu.Console.Error.CredentialUnavailable", str(error)) from error

    @method()
    def GetPluginSecretStatus(self, plugin_id: "s", name: "s") -> "s":
        return json.dumps({"configured": self.secrets.configured(plugin_id, name),
                           "backend": self.secrets.backend(plugin_id, name)}, separators=(",", ":"))

    @method()
    def SetPluginSecret(self, plugin_id: "s", name: "s", value: "s") -> "s":
        self.secrets.put(plugin_id, name, value)
        return json.dumps({"configured": True}, separators=(",", ":"))

    @method()
    def PairRommDevice(self, code: "s") -> "s":
        from .plugins.romm import RommClient, RommConfig
        config = RommConfig.from_file()
        if config is None:
            raise DBusError("org.lulu.Console.Error.InvalidPluginSetting", "RomM URL is not configured")
        try:
            RommClient(config).exchange_pairing_code(code)
        except (ValueError, RommApiError) as error:
            raise DBusError("org.lulu.Console.Error.CredentialInvalid", str(error)) from error
        return json.dumps({"configured": True}, separators=(",", ":"))

    @method()
    async def VerifyPluginAcquisition(self, plugin_id: "s") -> "s":
        auth = self._plugins.for_plugin(plugin_id, "authentication")
        if not auth or not hasattr(auth[0], "verify_acquisition"):
            return json.dumps({"status": "unavailable"}, separators=(",", ":"))
        try:
            return json.dumps(await auth[0].verify_acquisition(), separators=(",", ":"))
        except Exception as error:
            # Deliberately return only the normalized backend code/message.
            code = getattr(error, "code", "authentication-failed")
            return json.dumps({"status": str(code)}, separators=(",", ":"))

    @method()
    def ClearPluginSecret(self, plugin_id: "s", name: "s") -> "s":
        self.secrets.clear(plugin_id, name)
        return json.dumps({"configured": False}, separators=(",", ":"))

    @method()
    def SetPluginSetting(self, plugin_id: "s", name: "s", value: "s") -> "s":
        if plugin_id == "romm" and name == "url":
            from .plugins.romm import RommConfig
            RommConfig.save_url(value)
        elif plugin_id == "steam" and name == "username":
            if not value.strip():
                raise DBusError("org.lulu.Console.Error.InvalidPluginSetting", "Steam username cannot be empty")
            # Steam credentials are plugin-owned SecretStore slots. Guard
            # codes continue through CredentialBroker and never reach here.
            self.secrets.put("steam", "username", value.strip())
        else:
            raise DBusError("org.lulu.Console.Error.InvalidPluginSetting", "unsupported plugin setting")
        return json.dumps({"saved": True}, separators=(",", ":"))

    @method()
    async def SubmitCredential(self, request_id: "s", value: "s") -> "s":
        try:
            session = await self.credentials.submit(request_id, value)
            return json.dumps(session.public_state(), separators=(",", ":"))
        except (KeyError, ValueError) as error:
            raise DBusError("org.lulu.Console.Error.CredentialInvalid", str(error)) from error

    @method()
    async def TakeCredentialValue(self, request_id: "s") -> "s":
        try:
            return await self.credentials.take_value(request_id)
        except KeyError as error:
            raise DBusError("org.lulu.Console.Error.CredentialUnknown", str(error)) from error

    @method()
    async def CancelCredential(self, request_id: "s") -> "s":
        try:
            await self.credentials.cancel(request_id)
            return json.dumps(self.credentials.state(), separators=(",", ":"))
        except KeyError as error:
            raise DBusError("org.lulu.Console.Error.CredentialUnknown", str(error)) from error
        self.CatalogueChanged()

    @method()
    def ClearMetadataMatch(self, game_id: "s") -> "":
        self._publish_delta(self.catalogue.clear_metadata_match(game_id))
        self.CatalogueChanged()

    @method()
    def SetTitleOverride(self, game_id: "s", title: "s") -> "":
        self._publish_delta(self.catalogue.set_title_override(game_id, title))
        self.CatalogueChanged()

    @method()
    def ClearTitleOverride(self, game_id: "s") -> "":
        self._publish_delta(self.catalogue.clear_title_override(game_id))
        self.CatalogueChanged()

    @method()
    def SuppressArtwork(self, game_id: "s") -> "":
        self._publish_delta(self.catalogue.suppress_artwork(game_id))
        self.CatalogueChanged()

    @method()
    def RestoreArtwork(self, game_id: "s") -> "":
        self._publish_delta_batches([
            (delta,) for delta in self.catalogue.restore_artwork(game_id)
        ])
        self.CatalogueChanged()

    @method()
    async def LaunchGame(self, game_id: "s", timeout_ms: "u") -> "s":
        games = {game.game_id: game for game in self.catalogue.store.list_games()}
        game = games.get(game_id)
        if game is None or not game.launchable:
            raise ValueError("game is not installed and launchable")
        LOGGER.info("launch dispatch game_id=%s provider=%s provider_id=%s", game_id, game.provider, game.provider_id)
        for launcher in self._plugins.with_capability("launch"):
            provider_ids = tuple(getattr(launcher, "provider_ids", ()))
            if game.provider not in provider_ids or not hasattr(launcher, "launch_command"):
                continue
            command = launcher.launch_command(game.provider_id)
            if self.sessiond is None:
                raise ValueError("console session is unavailable")
            context = {
                key: os.environ[key] for key in (
                    "DISPLAY", "WAYLAND_DISPLAY", "XDG_RUNTIME_DIR", "XDG_SESSION_TYPE",
                    "DBUS_SESSION_BUS_ADDRESS", "XAUTHORITY", "HOME", "USER",
                ) if os.environ.get(key)
            }
            await self.sessiond.call_set_delegated_launch_context(json.dumps(context, sort_keys=True))
            token = await self.sessiond.call_request_game_launch(game.game_id, command, timeout_ms)
            delta = self.catalogue.store.mark_played(game.game_id)
            self._publish_delta(delta)
            self.CatalogueChanged()
            return token
        if game.provider == "steam":
            details_uri = self.catalogue.provider.open_game_details(game.provider_id)
            launch_uri = self.catalogue.provider.launch_gamepad_title(game.provider_id)
            LOGGER.info(
                "Steam contextual launch submitted game_id=%s details=%s launch=%s",
                game_id,
                details_uri,
                launch_uri,
            )
            return details_uri
        if game.provider == "lutris":
            from .lutris_adapter import LutrisAdapter
            script = PATHS.cache_home / "lutris" / f"mudos-{game.provider_id}.sh"
            await asyncio.to_thread(LutrisAdapter().output_script, game.provider_id, script)
            if self.sessiond is None:
                raise ValueError("console session is unavailable")
            context = {
                key: os.environ[key] for key in (
                    "DISPLAY", "WAYLAND_DISPLAY", "XDG_RUNTIME_DIR", "XDG_SESSION_TYPE",
                    "DBUS_SESSION_BUS_ADDRESS", "XAUTHORITY", "HOME", "USER",
                ) if os.environ.get(key)
            }
            await self.sessiond.call_set_delegated_launch_context(json.dumps(context, sort_keys=True))
            token = await self.sessiond.call_request_game_launch(
                game.game_id, ["/usr/bin/env", "bash", str(script)], timeout_ms
            )
            delta = self.catalogue.store.mark_played(game.game_id)
            self._publish_delta(delta)
            self.CatalogueChanged()
            return token
        if game.provider == "local" and self.local_runtime is not None:
            device_indices = None
            if game.platform == "switch":
                device_indices = await asyncio.to_thread(_mudos_provider_device_indices)
            controller_identities = None
            if game.platform in {"switch", "ps2", "wii", "nes", "genesis"}:
                controller_identities = await asyncio.to_thread(_mudos_provider_controller_identities)
            intent = self.local_runtime.launch_intent(
                game, device_indices=device_indices,
                controller_identities=controller_identities,
            )
            command = [intent.executable, *intent.arguments]
            is_pcsx2 = intent.provider == "pcsx2"
            if is_pcsx2:
                LOGGER.info("[PCSX2] selected game=%s path=%s", game_id, game.install_dir)
                LOGGER.info("[PCSX2] resolved executable=%s", intent.executable)
            child_config_path: str | None = None
            if intent.provider in {"pcsx2", "dolphin"}:
                controller_provider = intent.provider
                device_indices = await asyncio.to_thread(_mudos_provider_device_indices)
                controller_config_path = await asyncio.to_thread(
                    ensure_provider_controller_config,
                    controller_provider,
                    PATHS.provider_config_root(controller_provider),
                    max(device_indices),
                    device_indices,
                    PATHS.provider_config_root(controller_provider)
                    if controller_provider == "dolphin" else None,
                    controller_identities,
                )
                LOGGER.info(
                    "local runtime controller profile provider=%s path=%s",
                    controller_provider,
                    controller_config_path,
                )
            if intent.provider == "retroarch":
                device_indices = await asyncio.to_thread(_mudos_provider_device_indices)
                child_config_path = await asyncio.to_thread(_retroarch_child_config, device_indices)
                command[1:1] = [
                    "--appendconfig",
                    child_config_path,
                ]
                LOGGER.info(
                    "local runtime controller game_id=%s device_indices=%s",
                    game_id,
                    device_indices,
                )
            LOGGER.info(
                "local runtime dispatch game_id=%s runtime=%s core=%s rom=%s command=%r",
                game_id,
                intent.executable,
                intent.arguments[-3] if intent.provider == "retroarch" else "",
                intent.arguments[-1],
                command,
            )
            if is_pcsx2:
                LOGGER.info("[PCSX2] command line=%s", shlex.join(command))
            child_environment = os.environ.copy()
            if intent.provider in {"retroarch", "pcsx2"}:
                child_environment.pop("WAYLAND_DISPLAY", None)
            if intent.provider:
                child_environment["XDG_CONFIG_HOME"] = str(
                    PATHS.provider_config_root(intent.provider)
                )
            if intent.provider == "retroarch":
                child_environment["LIBRETRO_AUTOCONFIG_DIRECTORY"] = (
                    "/opt/lulu/config/retroarch/autoconfig"
                )
                child_environment["MUDOS_PROVIDER_MENU_COMMAND"] = shlex.join(
                    self.local_runtime.open_provider_menu(intent.platform)
                )
                child_environment["MUDOS_PROVIDER_MENU_LABEL"] = "Provider"
            process = await asyncio.create_subprocess_exec(
                *command,
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
                env=child_environment,
                cwd="/home/lulu" if intent.provider == "eden" else None,
                start_new_session=True,
            )
            if is_pcsx2:
                LOGGER.info("[PCSX2] process PID=%s", process.pid)
            try:
                if self.sessiond is not None:
                    self._local_token = await self.sessiond.call_begin_local_session(
                        game_id,
                        process.pid,
                        os.getpgid(process.pid),
                        os.path.realpath(f"/proc/{process.pid}/exe"),
                        command,
                    )
                self._local_process = process
            except Exception:
                try:
                    os.killpg(os.getpgid(process.pid), signal.SIGTERM)
                except (ProcessLookupError, OSError):
                    pass
                await process.wait()
                raise

            async def reap() -> None:
                exit_code = await process.wait()
                if child_config_path is not None:
                    try:
                        os.unlink(child_config_path)
                    except FileNotFoundError:
                        pass
                if self.sessiond is not None and self._local_token is not None:
                    try:
                        await self.sessiond.call_end_local_session(self._local_token, exit_code)
                    except Exception as error:
                        LOGGER.error("local session end failed game_id=%s token=%s error=%s", game_id, self._local_token, error)
                self._local_process = None
                self._local_token = None
                LOGGER.info("local runtime exit game_id=%s pid=%s exit_code=%s", game_id, process.pid, exit_code)
                if is_pcsx2:
                    LOGGER.info("[PCSX2] process exit pid=%s exit_code=%s", process.pid, exit_code)
                    LOGGER.info("[PCSX2] lifecycle return game_id=%s", game_id)

            asyncio.create_task(reap())
            token = self._local_token or f"local:{process.pid}"
            LOGGER.info("local runtime started game_id=%s pid=%s token=%s", game_id, process.pid, token)
        else:
            raise ValueError(f"provider launch is unavailable: {game.provider}")
        delta = self.catalogue.store.mark_played(game.game_id)
        LOGGER.info("launch returned game_id=%s token=%s", game_id, token)
        self._publish_delta(delta)
        self.CatalogueChanged()
        return token

    @method()
    async def CancelLocalLaunch(self) -> "":
        process = self._local_process
        if process is None:
            return
        try:
            os.killpg(os.getpgid(process.pid), signal.SIGTERM)
        except (ProcessLookupError, OSError):
            pass
        await process.wait()

    @dbus_signal()
    def CatalogueChanged(self) -> "":
        LOGGER.info("catalogue changed signal emitted")
        return

    @dbus_signal()
    def CatalogueGenerationChanged(self, generation: "t") -> "t":
        return generation


ROMM_SYNC_INTERVAL = 15 * 60


async def serve() -> None:
    catalogue = ConsoleCatalog()
    runtime = EmulatorRuntimeAdapter(
        {platform: definition.executable for platform, definition in PLATFORMS.items()},
        {platform: definition.core for platform, definition in PLATFORMS.items() if definition.core is not None},
        config_root=PATHS.providers_root,
    )
    bus = await MessageBus(bus_type=BusType.SESSION).connect()
    session_introspection = await bus.introspect("org.lulu.ConsoleSessiond", "/org/lulu/ConsoleSession")
    session_proxy = bus.get_proxy_object(
        "org.lulu.ConsoleSessiond", "/org/lulu/ConsoleSession", session_introspection
    )
    sessiond = session_proxy.get_interface("org.lulu.ConsoleSession")
    interface = ConsoleInterface(catalogue, runtime, sessiond=sessiond)
    bus.export(OBJECT_PATH, interface)
    await bus.request_name(BUS_NAME)
    # Publish the D-Bus boundary before the potentially slow provider refresh.
    # sessiond starts the shell during bootstrap, and the bridge must be able to
    # discover Consoled while the catalogue is being populated.
    # Publish the boundary and cached catalogue immediately. Provider sync is
    # deliberately background work so RomM cannot delay shell startup.
    async def synchronize() -> None:
        while True:
            try:
                await interface.refresh_catalogue()
            except Exception:
                LOGGER.exception("background catalogue synchronization failed")
            await asyncio.sleep(ROMM_SYNC_INTERVAL)

    asyncio.create_task(synchronize(), name="catalogue-sync")
    await asyncio.Event().wait()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    asyncio.run(serve())


if __name__ == "__main__":
    main()
