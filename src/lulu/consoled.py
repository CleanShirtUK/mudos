"""Unified game catalogue and game/content intent boundary."""

import asyncio
from dataclasses import replace
import logging
import os
from pathlib import Path
import signal
import subprocess
import tempfile
import shlex
import json
import time
import threading
from collections import deque

from dbus_next import BusType, Variant
from dbus_next.aio import MessageBus
from dbus_next.service import ServiceInterface, method, signal as dbus_signal

from .catalogue import CatalogueDelta, CatalogueGame, CatalogueStore
from .artwork import LocalArtworkCache, SteamGridDBArtwork
from .contracts import ServiceDescriptor, ServiceName
from .controller_provisioning import ensure_provider_controller_config
from .emulator_runtime import EmulatorRuntimeAdapter
from .emulation import PLATFORMS, ROM_ROOT, ensure_storage
from .inputplumber import InputPlumberClient
from .local_content import LocalContentProvider
from .metadata import MetadataMatcher, SteamGridDBMetadata, clean_local_title
from .romm import RommApiError, RommClient, RommConfig, RommGame
from .steam_provider import SteamProvider
from .system_settings import CATEGORIES as SYSTEM_CATEGORIES, SystemSettingsProvider


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


class ConsoleCatalog:
    """Consoled-owned normalized catalogue."""

    descriptor = DESCRIPTOR

    def __init__(self, store: CatalogueStore | None = None, provider: SteamProvider | None = None,
                 local_provider: LocalContentProvider | None = None,
                 metadata: SteamGridDBMetadata | None = None,
                 romm: RommClient | None = None) -> None:
        self.store = store or CatalogueStore()
        self.provider = provider or SteamProvider()
        self.local_provider = local_provider or LocalContentProvider()
        self.artwork = SteamGridDBArtwork()
        self.romm_artwork = LocalArtworkCache()
        self.metadata = metadata or SteamGridDBMetadata()
        self.matcher = MetadataMatcher(self.metadata)
        self._diagnostic_artwork_originals: dict[str, str] = {}
        self._diagnostic_timestamp_originals: dict[str, tuple[int | None, int | None]] = {}
        self._diagnostic_canonical_originals: dict[str, str] = {}
        self.last_delta_batches: list[tuple[object, ...]] = []
        config = RommConfig.from_file()
        self.romm = romm or (RommClient(config) if config else None)
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
        all_stages = {"steam", "local", "romm", "romm-artwork", "metadata", "artwork"}
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
        if "steam" in selected:
            LOGGER.info("catalogue stage started name=steam")
            self.store.reconcile_steam(self.provider)
            if self.store.last_deltas:
                self.last_delta_batches.append(self.store.last_deltas)
            LOGGER.info("catalogue stage completed name=steam sqlite_commit=complete")
        if "local" in selected:
            LOGGER.info("catalogue stage started name=local")
            ensure_storage()
            self.store.reconcile_local(self.local_provider, ROM_ROOT)
            if self.store.last_deltas:
                self.last_delta_batches.append(self.store.last_deltas)
            LOGGER.info("catalogue stage completed name=local sqlite_commit=complete")
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
                LOGGER.info("catalogue romm substage started name=installed-lookup")
                installed = {game.app_id: game for game in self.provider.list_installed()}
                LOGGER.info("catalogue romm substage completed name=installed-lookup items=%d",
                            len(installed))
                normalized: dict[str, object] = {}
                for game in romm_games:
                    app_id = self._steam_manifest_app_id(game)
                    entry = CatalogueGame.from_romm(
                        game, installed.get(app_id) if app_id else None, app_id
                    )
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

    def _steam_manifest_app_id(self, game: object) -> str | None:
        if not isinstance(game, RommGame) or game.platform_slug.casefold() != "steam":
            return None
        manifest_files = [item for item in game.files if item.name.casefold().endswith(".json")]
        if not manifest_files or self.romm is None:
            return None
        try:
            return self.romm.read_steam_manifest(manifest_files[0]).app_id
        except RommApiError as error:
            LOGGER.warning("Ignoring invalid RomM Steam manifest rom_id=%s: %s", game.rom_id, error)
            return None

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


def _mudos_provider_device_indices() -> dict[int, int]:
    """Resolve logical players to current InputPlumber gamepad target indices."""
    client = InputPlumberClient("/org/shadowblip/InputPlumber/CompositeDevice0", {})
    slots = client.runtime_gamepad_slots()
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
    state_json = json.loads(state.removeprefix("s ").strip())
    if isinstance(state_json, str):
        state_json = json.loads(state_json)
    assignments = state_json.get("controller", {}).get("controllers", {})
    result: dict[int, int] = {}
    for runtime_path, _persistent_id, target_index in slots:
        player = assignments.get(runtime_path, {}).get("player")
        if isinstance(player, int) and player in range(1, 5):
            result[player] = target_index
    if not result:
        raise RuntimeError("Mudos has no assigned InputPlumber gamepad slots")
    return result


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
                 sessiond: object | None = None) -> None:
        super().__init__(INTERFACE_NAME)
        self.catalogue = catalogue
        self.local_runtime = local_runtime
        self.system_settings = system_settings or SystemSettingsProvider()
        self.sessiond = sessiond
        self._local_process: asyncio.subprocess.Process | None = None
        self._local_token: str | None = None
        self._refresh_task: asyncio.Task[list[dict[str, object]]] | None = None
        self._catalogue_generation = 0
        self._delta_history: deque[tuple[int, list[dict[str, object]]]] = deque(maxlen=256)

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
    async def RefreshStages(self, stages: "as") -> "u":
        count = await self.refresh_catalogue(set(stages))
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
            raise self._error(error) from error

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
        if game.provider == "local" and self.local_runtime is not None:
            device_indices = None
            if game.platform == "switch":
                device_indices = await asyncio.to_thread(_mudos_provider_device_indices)
            intent = self.local_runtime.launch_intent(game, device_indices=device_indices)
            command = [intent.executable, *intent.arguments]
            is_pcsx2 = intent.platform == "ps2"
            if is_pcsx2:
                LOGGER.info("[PCSX2] selected game=%s path=%s", game_id, game.install_dir)
                LOGGER.info("[PCSX2] resolved executable=%s", intent.executable)
            child_config_path: str | None = None
            if intent.platform in {"ps2", "wii"}:
                controller_provider = {"ps2": "pcsx2", "wii": "dolphin"}[intent.platform]
                device_indices = await asyncio.to_thread(_mudos_provider_device_indices)
                controller_config_path = await asyncio.to_thread(
                    ensure_provider_controller_config,
                    controller_provider,
                    None,
                    max(device_indices),
                    device_indices,
                )
                LOGGER.info(
                    "local runtime controller profile provider=%s path=%s",
                    controller_provider,
                    controller_config_path,
                )
            if intent.platform in {"nes", "genesis"}:
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
                intent.arguments[1] if intent.platform in {"nes", "genesis"} else "",
                intent.arguments[-1],
                command,
            )
            if is_pcsx2:
                LOGGER.info("[PCSX2] command line=%s", shlex.join(command))
            child_environment = os.environ.copy()
            if intent.platform in {"nes", "genesis", "ps2"}:
                child_environment.pop("WAYLAND_DISPLAY", None)
            if intent.platform in {"nes", "genesis"}:
                child_environment["LIBRETRO_AUTOCONFIG_DIRECTORY"] = (
                    "/opt/lulu/config/retroarch/autoconfig"
                )
                child_environment["MUDOS_PROVIDER_MENU_COMMAND"] = shlex.join(
                    self.local_runtime.open_provider_menu(intent.platform)
                )
            process = await asyncio.create_subprocess_exec(
                *command,
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
                env=child_environment,
                cwd="/home/lulu" if intent.platform == "switch" else None,
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
