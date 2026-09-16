"""Consoled-owned normalized catalogue and provider boundary."""

from contextlib import contextmanager
from dataclasses import asdict, dataclass, fields, replace
import json
import os
from pathlib import Path
import sqlite3
import threading
import time

from .local_content import LocalContentGame, LocalContentProvider
from .metadata import MetadataMatch, clean_local_title
from .paths import PATHS
from .romm import RommGame
from .steam_provider import InstalledSteamGame, SteamProvider
from .steam_entitlements import SteamEntitlement


@dataclass(frozen=True, slots=True)
class CatalogueDelta:
    """A provider-neutral change to one authoritative catalogue record.

    Ordering is intentionally absent.  A view decides whether an updated role
    changes its own sort position.
    """

    kind: str
    game_id: str
    before: "CatalogueGame | None" = None
    after: "CatalogueGame | None" = None
    changed_fields: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "game_id": self.game_id,
            "before": self.before.as_dict() if self.before else None,
            "after": self.after.as_dict() if self.after else None,
            "changed_fields": list(self.changed_fields),
        }


@dataclass(frozen=True, slots=True)
class CatalogueGame:
    game_id: str
    provider: str
    provider_id: str
    title: str
    platform: str
    install_state: str
    launchable: bool
    install_dir: str
    artwork_url: str
    last_played: int
    runtime: str = ""
    platform_label: str = ""
    source_title: str = ""
    normalized_search_title: str = ""
    metadata_provider: str = ""
    metadata_game_id: str = ""
    canonical_title: str = ""
    match_status: str = ""
    match_method: str = ""
    match_confidence: float = 0.0
    match_locked: bool = False
    metadata_checked_at: int = 0
    display_title_override: str = ""
    artwork_suppressed: bool = False
    availability_state: str = "installed"
    provider_record_id: str = ""
    content_identity: str = ""
    catalogue_source: str = ""
    genres: tuple[str, ...] = ()
    release_date: str | None = None
    release_year: int | None = None
    total_playtime: int | None = None
    local_multiplayer: bool | None = None
    online_multiplayer: bool | None = None
    game_mode: str | None = None
    protondb_rating: str | None = None
    last_seen_at: int | None = None
    last_synced_at: int | None = None
    artwork_source_url: str = ""
    metadata_resolver_version: int = 0

    @classmethod
    def from_steam(cls, game: InstalledSteamGame) -> "CatalogueGame":
        return cls(
            game_id=f"steam:{game.app_id}", provider="steam", provider_id=game.app_id,
            title=game.title, platform="Steam", install_state="installed", launchable=True,
            install_dir=game.install_dir, artwork_url=game.artwork_url, last_played=game.last_played,
            source_title=game.title, normalized_search_title=clean_local_title(game.title),
            catalogue_source="steam",
        )

    @classmethod
    def from_steam_entitlement(cls, entitlement: SteamEntitlement,
                               installed: InstalledSteamGame | None = None) -> "CatalogueGame":
        return cls(
            game_id=f"steam:{entitlement.app_id}", provider="steam",
            provider_id=entitlement.app_id,
            title=installed.title if installed else entitlement.title,
            platform="Steam", install_state="installed" if installed else "available",
            launchable=installed is not None,
            install_dir=installed.install_dir if installed else "",
            artwork_url=installed.artwork_url if installed else "",
            last_played=installed.last_played if installed else 0,
            platform_label="Steam", source_title=entitlement.title,
            normalized_search_title=clean_local_title(entitlement.title),
            availability_state="installed" if installed else "available",
            catalogue_source="steam",
        )

    @classmethod
    def from_local(cls, game: LocalContentGame) -> "CatalogueGame":
        source_title = game.source_title or game.title
        return cls(
            game_id=game.content_id, provider="local", provider_id=game.content_id,
            title=game.title, platform=game.platform, install_state=game.install_state,
            launchable=game.launchable, install_dir=game.content_path, artwork_url="",
            last_played=0, runtime=game.runtime, platform_label=game.platform_label,
            source_title=source_title, normalized_search_title=clean_local_title(source_title),
            catalogue_source="local",
        )

    @classmethod
    def from_romm(cls, game: RommGame, installed: InstalledSteamGame | None = None,
                  app_id: str | None = None) -> "CatalogueGame":
        if app_id is not None:
            return cls(
                game_id=f"steam:{app_id}", provider="steam", provider_id=app_id,
                title=installed.title if installed else game.title, platform="Steam", platform_label="Steam",
                install_state="installed" if installed else "available", launchable=installed is not None,
                install_dir=installed.install_dir if installed else "", artwork_url=game.artwork_url,
                last_played=installed.last_played if installed else 0, source_title=game.title,
                normalized_search_title=clean_local_title(game.title),
                availability_state="installed" if installed else "available",
                provider_record_id=str(game.rom_id), catalogue_source="romm",
                content_identity=game.files[0].name if game.files else game.file_name,
                genres=game.genres, release_date=game.release_date, release_year=game.release_year,
                total_playtime=game.total_playtime, local_multiplayer=game.local_multiplayer,
                online_multiplayer=game.online_multiplayer, game_mode=game.game_mode,
                protondb_rating=game.protondb_rating, artwork_source_url=game.artwork_url,
            )
        platform = "Steam" if game.platform_slug.casefold() == "steam" else game.platform_slug
        return cls(
            game_id=f"romm:{game.rom_id}", provider="romm", provider_id=str(game.rom_id),
            title=game.title, platform=platform, install_state="available", launchable=False,
            install_dir="", artwork_url=game.artwork_url, last_played=0, runtime="",
            platform_label=game.platform_label, source_title=game.title,
            normalized_search_title=clean_local_title(game.title), availability_state="available",
            provider_record_id=str(game.rom_id),
            content_identity=game.files[0].name if game.files else game.file_name,
            catalogue_source="romm", genres=game.genres, release_date=game.release_date,
            release_year=game.release_year, total_playtime=game.total_playtime,
            local_multiplayer=game.local_multiplayer, online_multiplayer=game.online_multiplayer,
            game_mode=game.game_mode, protondb_rating=game.protondb_rating,
            artwork_source_url=game.artwork_url,
        )

    def as_dict(self) -> dict[str, object]:
        value = asdict(self)
        value["genres"] = list(self.genres)
        return value


# These two provider-observation fields are deliberately excluded from
# meaningful record comparison.  They are synchronization bookkeeping, not
# catalogue state presented to users.  updated_at is not part of
# CatalogueGame: it is written only when this meaningful set changes.
SYNCHRONIZATION_BOOKKEEPING_FIELDS = frozenset({"last_seen_at", "last_synced_at"})
CATALOGUE_GAME_FIELDS = tuple(field.name for field in fields(CatalogueGame))
MEANINGFUL_GAME_FIELDS = tuple(
    name for name in CATALOGUE_GAME_FIELDS
    if name not in SYNCHRONIZATION_BOOKKEEPING_FIELDS
)


IDENTITY_COLUMNS = (
    "source_title", "normalized_search_title", "metadata_provider", "metadata_game_id",
    "canonical_title", "match_status", "match_method", "match_confidence",
    "match_locked", "metadata_checked_at", "display_title_override", "artwork_suppressed",
)
TEMPORARY_METADATA_RETRY_SECONDS = 15 * 60
NORMAL_METADATA_RETRY_SECONDS = 24 * 60 * 60
METADATA_RESOLVER_VERSION = 2
SELECT_COLUMNS = (
    "game_id, provider, provider_id, title, platform, install_state, launchable, install_dir, "
    "artwork_url, last_played, runtime, platform_label, " + ", ".join(IDENTITY_COLUMNS)
    + ", availability_state, provider_record_id, content_identity, catalogue_source, genres, "
      "release_date, release_year, total_playtime, local_multiplayer, online_multiplayer, "
      "game_mode, protondb_rating, last_seen_at, last_synced_at, artwork_source_url"
      ", metadata_resolver_version"
)


class CatalogueStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or PATHS.catalogue_db
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.path, check_same_thread=False)
        self.lock = threading.RLock()
        self._transaction_depth = 0
        self.last_deltas: tuple[CatalogueDelta, ...] = ()
        self.last_write_counts: dict[str, int] = {"insert": 0, "update": 0, "delete": 0}
        self.connection.execute(
            """CREATE TABLE IF NOT EXISTS games (
                game_id TEXT PRIMARY KEY, provider TEXT NOT NULL, provider_id TEXT NOT NULL,
                title TEXT NOT NULL, platform TEXT NOT NULL, install_state TEXT NOT NULL,
                launchable INTEGER NOT NULL, install_dir TEXT NOT NULL, artwork_url TEXT NOT NULL,
                last_played INTEGER NOT NULL DEFAULT 0, updated_at INTEGER NOT NULL DEFAULT (unixepoch()),
                UNIQUE(provider, provider_id)
            )"""
        )
        columns = {row[1] for row in self.connection.execute("PRAGMA table_info(games)")}
        migrations = {"runtime": "TEXT NOT NULL DEFAULT ''", "platform_label": "TEXT NOT NULL DEFAULT ''",
                      "source_title": "TEXT NOT NULL DEFAULT ''", "normalized_search_title": "TEXT NOT NULL DEFAULT ''",
                      "metadata_provider": "TEXT NOT NULL DEFAULT ''", "metadata_game_id": "TEXT NOT NULL DEFAULT ''",
                      "canonical_title": "TEXT NOT NULL DEFAULT ''", "match_status": "TEXT NOT NULL DEFAULT ''",
                      "match_method": "TEXT NOT NULL DEFAULT ''", "match_confidence": "REAL NOT NULL DEFAULT 0",
                       "match_locked": "INTEGER NOT NULL DEFAULT 0", "metadata_checked_at": "INTEGER NOT NULL DEFAULT 0",
                       "display_title_override": "TEXT NOT NULL DEFAULT ''", "artwork_suppressed": "INTEGER NOT NULL DEFAULT 0",
                       "availability_state": "TEXT NOT NULL DEFAULT 'installed'",
                       "provider_record_id": "TEXT NOT NULL DEFAULT ''", "content_identity": "TEXT NOT NULL DEFAULT ''",
                       "catalogue_source": "TEXT NOT NULL DEFAULT ''", "genres": "TEXT NOT NULL DEFAULT '[]'",
                       "release_date": "TEXT", "release_year": "INTEGER", "total_playtime": "INTEGER",
                       "local_multiplayer": "INTEGER", "online_multiplayer": "INTEGER", "game_mode": "TEXT",
                       "protondb_rating": "TEXT", "last_seen_at": "INTEGER", "last_synced_at": "INTEGER",
                       "artwork_source_url": "TEXT NOT NULL DEFAULT ''", "metadata_resolver_version": "INTEGER NOT NULL DEFAULT 0"}
        for name, definition in migrations.items():
            if name not in columns:
                self.connection.execute(f"ALTER TABLE games ADD COLUMN {name} {definition}")
        self.connection.commit()

    @contextmanager
    def atomic(self, *, rollback: bool = False):
        """Group one logical catalogue operation into one SQLite transaction."""
        with self.lock:
            outermost = self._transaction_depth == 0
            if outermost:
                self.connection.execute("BEGIN")
            self._transaction_depth += 1
            try:
                yield
            except Exception:
                self._transaction_depth -= 1
                if outermost:
                    self.connection.rollback()
                raise
            else:
                self._transaction_depth -= 1
                if outermost:
                    if rollback:
                        self.connection.rollback()
                    else:
                        self.connection.commit()

    def _start_operation(self) -> None:
        self.last_deltas = ()
        self.last_write_counts = {"insert": 0, "update": 0, "delete": 0}

    def _finish_operation(self, deltas: list[CatalogueDelta], *, committed: bool = True) -> tuple[CatalogueDelta, ...]:
        self.last_deltas = tuple(deltas) if committed else ()
        return self.last_deltas

    def _record_delta(self, delta: CatalogueDelta, deltas: list[CatalogueDelta] | None) -> None:
        if deltas is not None:
            deltas.append(delta)

    @staticmethod
    def _field_value(game: CatalogueGame, name: str) -> object:
        value = getattr(game, name)
        return list(value) if name == "genres" else value

    @classmethod
    def meaningful_changes(cls, before: CatalogueGame, after: CatalogueGame) -> tuple[str, ...]:
        return tuple(
            name for name in MEANINGFUL_GAME_FIELDS
            if cls._field_value(before, name) != cls._field_value(after, name)
        )

    @staticmethod
    def _sql_value(name: str, value: object) -> object:
        return json.dumps(value, sort_keys=True) if name == "genres" else value

    def _commit_if_direct(self) -> None:
        if self._transaction_depth == 0:
            self.connection.commit()

    def _upsert(self, game: CatalogueGame) -> CatalogueDelta | None:
        with self.lock:
            return self._upsert_locked(game)

    def _merged_game(self, existing: CatalogueGame, incoming: CatalogueGame) -> CatalogueGame:
        installed = existing.install_state == "installed"
        preserve_metadata = bool(existing.metadata_provider)
        preserve_title = bool(existing.display_title_override or existing.match_locked
                              or existing.match_status in {"matched", "manual"})
        return replace(
            existing,
            provider_id=incoming.provider_id,
            platform=incoming.platform,
            install_state=existing.install_state if installed else incoming.install_state,
            launchable=existing.launchable if installed else incoming.launchable,
            install_dir=existing.install_dir if installed else incoming.install_dir,
            platform_label=incoming.platform_label,
            source_title=incoming.source_title,
            availability_state="installed" if installed else incoming.availability_state,
            provider_record_id=incoming.provider_record_id,
            content_identity=incoming.content_identity,
            catalogue_source=incoming.catalogue_source,
            genres=existing.genres if existing.genres else incoming.genres,
            release_date=existing.release_date if existing.release_date is not None else incoming.release_date,
            release_year=existing.release_year if existing.release_year is not None else incoming.release_year,
            total_playtime=existing.total_playtime if existing.total_playtime is not None else incoming.total_playtime,
            local_multiplayer=existing.local_multiplayer if existing.local_multiplayer is not None else incoming.local_multiplayer,
            online_multiplayer=existing.online_multiplayer if existing.online_multiplayer is not None else incoming.online_multiplayer,
            game_mode=existing.game_mode if existing.game_mode is not None else incoming.game_mode,
            protondb_rating=existing.protondb_rating if existing.protondb_rating is not None else incoming.protondb_rating,
            normalized_search_title=incoming.normalized_search_title,
            metadata_resolver_version=existing.metadata_resolver_version if preserve_metadata else incoming.metadata_resolver_version,
            title=existing.title if preserve_title else incoming.title,
            artwork_url=existing.artwork_url if existing.metadata_game_id != incoming.metadata_game_id else incoming.artwork_url,
            last_played=max(existing.last_played, incoming.last_played),
            last_seen_at=existing.last_seen_at,
            last_synced_at=existing.last_synced_at,
        )

    def _upsert_locked(self, game: CatalogueGame, deltas: list[CatalogueDelta] | None = None) -> CatalogueDelta | None:
        existing = self._rows(f"SELECT {SELECT_COLUMNS} FROM games WHERE game_id=?", (game.game_id,))
        before = existing[0] if existing else None
        after = game if before is None else self._merged_game(before, game)
        if before is None:
            values = {name: self._field_value(after, name) for name in CATALOGUE_GAME_FIELDS}
            columns = tuple(name for name in CATALOGUE_GAME_FIELDS if name != "last_seen_at" and name != "last_synced_at")
            # Bookkeeping is retained on inserts for compatibility, but never
            # participates in an update of an otherwise unchanged row.
            columns += ("last_seen_at", "last_synced_at")
            self.connection.execute(
                f"INSERT INTO games ({', '.join(columns)}, updated_at) VALUES "
                f"({', '.join('?' for _ in columns)}, unixepoch())",
                tuple(self._sql_value(name, values[name]) for name in columns),
            )
            self.last_write_counts["insert"] += 1
            delta = CatalogueDelta("insert", after.game_id, after=after)
        else:
            changed = self.meaningful_changes(before, after)
            if not changed:
                return None
            assignments = ", ".join(f"{name}=?" for name in changed)
            self.connection.execute(
                f"UPDATE games SET {assignments}, updated_at=unixepoch() WHERE game_id=?",
                tuple(self._sql_value(name, getattr(after, name)) for name in changed) + (after.game_id,),
            )
            self.last_write_counts["update"] += 1
            delta = CatalogueDelta("update", after.game_id, before=before, after=after,
                                   changed_fields=tuple(sorted(changed)))
        self._record_delta(delta, deltas)
        return delta

    def _apply_existing_locked(self, before: CatalogueGame, after: CatalogueGame,
                               deltas: list[CatalogueDelta] | None = None) -> CatalogueDelta | None:
        changed = self.meaningful_changes(before, after)
        if not changed:
            return None
        assignments = ", ".join(f"{name}=?" for name in changed)
        self.connection.execute(
            f"UPDATE games SET {assignments}, updated_at=unixepoch() WHERE game_id=?",
            tuple(self._sql_value(name, getattr(after, name)) for name in changed) + (after.game_id,),
        )
        self.last_write_counts["update"] += 1
        delta = CatalogueDelta("update", after.game_id, before=before, after=after,
                               changed_fields=tuple(sorted(changed)))
        self._record_delta(delta, deltas)
        return delta

    def diagnostic_update_canonical_title(
            self, game_id: str, expected: str, value: str) -> dict[str, object]:
        """Temporary diagnostic: mutate only canonical_title and commit."""
        with self.lock:
            before = self.connection.execute(
                "SELECT canonical_title FROM games WHERE game_id=?", (game_id,)
            ).fetchone()
            if before is None:
                raise ValueError(f"diagnostic game does not exist: {game_id}")
            before_value = str(before[0])
            if before_value != expected:
                raise RuntimeError(
                    f"diagnostic precondition failed game_id={game_id} "
                    f"expected={expected!r} actual={before_value!r}"
                )
            db_size_before = self.path.stat().st_size if self.path.exists() else 0
            wal_path = Path(str(self.path) + "-wal")
            wal_size_before = wal_path.stat().st_size if wal_path.exists() else 0
            self.connection.execute(
                "UPDATE games SET canonical_title=? WHERE game_id=?",
                (value, game_id),
            )
            rowcount = self.connection.execute("SELECT changes()").fetchone()[0]
            after_update = self.connection.execute(
                "SELECT canonical_title FROM games WHERE game_id=?", (game_id,)
            ).fetchone()[0]
            commit_started_ns = time.monotonic_ns()
            started = time.perf_counter()
            self.connection.commit()
            duration = time.perf_counter() - started
            commit_finished_ns = time.monotonic_ns()
            after_commit = self.connection.execute(
                "SELECT canonical_title FROM games WHERE game_id=?", (game_id,)
            ).fetchone()[0]
            db_size_after = self.path.stat().st_size if self.path.exists() else 0
            wal_size_after = wal_path.stat().st_size if wal_path.exists() else 0
            return {
                "before": before_value,
                "requested": value,
                "after_update": str(after_update),
                "rowcount": rowcount,
                "changes": rowcount,
                "after_commit": str(after_commit),
                "commit_seconds": duration,
                "commit_started_ns": commit_started_ns,
                "commit_finished_ns": commit_finished_ns,
                "journal_mode": self.connection.execute("PRAGMA journal_mode").fetchone()[0],
                "wal_before": wal_size_before,
                "wal_after": wal_size_after,
                "db_before": db_size_before,
                "db_after": db_size_after,
            }

    def diagnostic_set_journal_mode(self, mode: str) -> str:
        with self.lock:
            if self.connection.in_transaction:
                raise RuntimeError("cannot change journal mode during a transaction")
            return str(self.connection.execute(f"PRAGMA journal_mode={mode}").fetchone()[0])

    def diagnostic_checkpoint(self) -> tuple[object, ...]:
        with self.lock:
            if self.connection.in_transaction:
                raise RuntimeError("cannot checkpoint during a transaction")
            return tuple(self.connection.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone())

    def reconcile_steam(self, provider: SteamProvider) -> list[CatalogueGame]:
        games = [CatalogueGame.from_steam(game) for game in provider.list_installed()]
        deltas: list[CatalogueDelta] = []
        self._start_operation()
        with self.atomic():
            # Existing RomM-backed Steam rows may still be present from the
            # migration boundary. Installed manifests supersede that legacy
            # observation without requiring a destructive entitlement sweep.
            existing = self._rows(
                f"SELECT {SELECT_COLUMNS} FROM games WHERE provider='steam'"
            )
            incoming_ids = {game.game_id for game in games}
            for current in existing:
                if current.game_id not in incoming_ids and not current.provider_record_id:
                    self._apply_existing_locked(
                        current, replace(current, install_state="missing", launchable=False), deltas)
                elif current.game_id not in incoming_ids and current.provider_record_id:
                    # Legacy RomM Steam observations remain owned/available;
                    # they are not local-install observations.
                    self._apply_existing_locked(
                        current, replace(current, install_state="available",
                                         launchable=False, install_dir="",
                                         availability_state="available"), deltas)
            for game in games:
                self._upsert_locked(game, deltas)
        self._finish_operation(deltas)
        return games

    def reconcile_steam_entitlements(
            self, entitlements: tuple[SteamEntitlement, ...], provider: SteamProvider
    ) -> list[CatalogueGame]:
        """Join a valid ownership snapshot to local installed manifests.

        The snapshot is additive by design.  A valid refresh never deletes or
        hides an older entitlement; only a separately tested revocation policy
        may do that.  Installed manifests are always included and authoritative
        for installability.
        """
        installed = {game.app_id: game for game in provider.list_installed()}
        normalized = [
            CatalogueGame.from_steam_entitlement(item, installed.get(item.app_id))
            for item in entitlements
        ]
        known = {item.app_id for item in entitlements}
        normalized.extend(
            CatalogueGame.from_steam(game)
            for app_id, game in installed.items() if app_id not in known
        )
        deltas: list[CatalogueDelta] = []
        self._start_operation()
        with self.atomic():
            # A manifest disappearing does not revoke ownership, but it does
            # mean the local install state is no longer installed. Keep the
            # entitlement visible and eligible for acquisition.
            existing = self._rows(
                f"SELECT {SELECT_COLUMNS} FROM games WHERE provider='steam'"
            )
            for current in existing:
                if current.provider_id not in installed and current.install_state == "installed":
                    self._apply_existing_locked(
                        current,
                        replace(current, install_state="available", launchable=False,
                                install_dir="", availability_state="available"),
                        deltas,
                    )
            for game in normalized:
                self._upsert_locked(game, deltas)
        self._finish_operation(deltas)
        return normalized

    def reconcile_local(self, provider: LocalContentProvider, root: Path) -> list[CatalogueGame]:
        games = [CatalogueGame.from_local(game) for game in provider.list_installed(root)]
        deltas: list[CatalogueDelta] = []
        self._start_operation()
        with self.atomic():
            existing = self._rows(f"SELECT {SELECT_COLUMNS} FROM games WHERE provider='local'")
            incoming_ids = {game.game_id for game in games}
            for current in existing:
                if current.game_id not in incoming_ids:
                    self._apply_existing_locked(
                        current, replace(current, install_state="missing", launchable=False), deltas)
            for game in games:
                self._upsert_locked(game, deltas)
            # A staged ROM is represented by both the local provider record
            # and its remote RomM record. Reconcile Store availability by the
            # canonical platform and filename after local discovery.
            installed_files = {
                (game.platform.casefold(), Path(game.source_title).name.casefold()): game
                for game in games if game.install_state == "installed"
            }
            for current in self._rows(f"SELECT {SELECT_COLUMNS} FROM games WHERE provider='romm'"):
                key = (current.platform.casefold(), Path(current.content_identity).name.casefold())
                local = installed_files.get(key)
                if local is not None:
                    self._apply_existing_locked(
                        current,
                        replace(current, install_state="installed", launchable=local.launchable,
                                install_dir=local.install_dir, availability_state="installed"),
                        deltas,
                    )
                elif current.install_state == "installed":
                    self._apply_existing_locked(
                        current,
                        replace(current, install_state="available", launchable=False,
                                install_dir="", availability_state="available"),
                        deltas,
                    )
        self._finish_operation(deltas)
        return games

    def reconcile_romm(self, games: list[CatalogueGame], mode: str = "full") -> list[CatalogueGame]:
        """Apply a complete, already-fetched RomM snapshot atomically."""
        games = list({game.game_id: game for game in games}.values())
        deltas: list[CatalogueDelta] = []
        self._start_operation()
        with self.atomic(rollback=mode == "upsert-rollback"):
            if mode in {"full", "mark"}:
                existing = self._rows(f"SELECT {SELECT_COLUMNS} FROM games WHERE provider='romm'")
                incoming_ids = {game.game_id for game in games}
                for current in existing:
                    if current.game_id not in incoming_ids:
                        self._apply_existing_locked(
                            current, replace(current, install_state="missing", launchable=False,
                                             availability_state="unavailable"), deltas)
            if mode in {"full", "upsert", "upsert-rollback"}:
                for game in games:
                    self._upsert_locked(game, deltas)
        self._finish_operation(deltas, committed=mode != "upsert-rollback")
        return games

    def _rows(self, query: str, parameters: tuple[object, ...] = ()) -> list[CatalogueGame]:
        with self.lock:
            games = []
            for row in self.connection.execute(query, parameters):
                values = list(row)
                try:
                    values[28] = tuple(json.loads(values[28] or "[]"))
                except (TypeError, ValueError, json.JSONDecodeError):
                    values[28] = ()
                games.append(CatalogueGame(*values))
            return games

    def list_games(self, scope: str = "all") -> list[CatalogueGame]:
        query = f"SELECT {SELECT_COLUMNS} FROM games WHERE install_state='installed'"
        parameters: tuple[object, ...] = ()
        if scope == "pc":
            query += " AND provider!='local'"
        elif scope == "steam":
            query += " AND provider=?"; parameters = ("steam",)
        elif scope.startswith("platform:"):
            query += " AND provider='local' AND platform=?"; parameters = (scope.removeprefix("platform:"),)
        return self._rows(query + " ORDER BY title COLLATE NOCASE", parameters)

    def list_catalogue_games(self) -> list[CatalogueGame]:
        return self._rows(f"SELECT {SELECT_COLUMNS} FROM games ORDER BY title COLLATE NOCASE")

    def list_recent(self) -> list[CatalogueGame]:
        return self._rows(f"SELECT {SELECT_COLUMNS} FROM games WHERE install_state='installed' AND last_played>0 ORDER BY last_played DESC")

    def list_available_games(self, provider: str | None = None) -> list[CatalogueGame]:
        query = f"SELECT {SELECT_COLUMNS} FROM games WHERE availability_state='available'"
        parameters: tuple[object, ...] = ()
        if provider is not None:
            if provider == "romm":
                # The existing Store endpoint historically asked for the RomM
                # provider, but also carried transitional Steam rows. Keep that
                # display contract while the Steam rows now come from Valve.
                query += " AND (provider='romm' OR (provider='steam' AND availability_state='available'))"
            else:
                query += " AND provider=?"
                parameters = (provider,)
        return self._rows(query + " ORDER BY title COLLATE NOCASE", parameters)

    def get_game(self, game_id: str) -> CatalogueGame | None:
        rows = self._rows(f"SELECT {SELECT_COLUMNS} FROM games WHERE game_id=?", (game_id,))
        return rows[0] if rows else None

    def list_platforms(self) -> list[tuple[str, str]]:
        platforms = list(self.connection.execute("SELECT platform, MAX(platform_label) FROM games WHERE provider='local' AND install_state='installed' GROUP BY platform"))
        return sorted(platforms, key=lambda item: item[1].casefold())

    def needs_metadata_match(self, game_id: str, now: int | None = None) -> bool:
        row = self.connection.execute(
            "SELECT match_locked, metadata_game_id, match_status, match_method, metadata_checked_at, "
            "catalogue_source, platform, metadata_resolver_version "
            "FROM games WHERE game_id=?", (game_id,)
        ).fetchone()
        if row is None or row[0]:
            return False
        # Existing native Steam matches predate the RomM AppID handoff and
        # must be migrated even though they have a metadata provider ID.
        appid_migration = row[5] == "romm" and row[6] == "Steam" and (
            row[3] != "steam-appid" or row[7] != METADATA_RESOLVER_VERSION
        )
        if appid_migration and row[3] == "steam-appid":
            return True
        if row[1] and not appid_migration:
            return False
        current = int(time.time()) if now is None else now
        cooldown = (
            TEMPORARY_METADATA_RETRY_SECONDS
            if row[3] == "network-error"
            else NORMAL_METADATA_RETRY_SECONDS
        )
        return not row[4] or current - row[4] >= cooldown

    def apply_metadata_match(self, game_id: str, match: MetadataMatch) -> None:
        existing = self.get_game(game_id)
        if existing is None or existing.match_locked:
            return None
        title = existing.display_title_override or (match.canonical_title if match.status == "matched" else match.normalized_search_title)
        presentation = match.presentation
        after = replace(
            existing, title=title, normalized_search_title=match.normalized_search_title,
            metadata_provider=match.provider, metadata_game_id=match.game_id,
            canonical_title=match.canonical_title, match_status=match.status,
            match_method=match.method, match_confidence=match.confidence, match_locked=False,
            metadata_checked_at=int(time.time()),
            genres=tuple(presentation["genres"]) if presentation.get("genres") else existing.genres,
            release_date=presentation.get("release_date") or existing.release_date,
            release_year=presentation.get("release_year") or existing.release_year,
            total_playtime=presentation.get("total_playtime") or existing.total_playtime,
            local_multiplayer=presentation.get("local_multiplayer") if presentation.get("local_multiplayer") is not None else existing.local_multiplayer,
            online_multiplayer=presentation.get("online_multiplayer") if presentation.get("online_multiplayer") is not None else existing.online_multiplayer,
            game_mode=presentation.get("game_mode") or existing.game_mode,
            protondb_rating=presentation.get("protondb_rating") or existing.protondb_rating,
            metadata_resolver_version=METADATA_RESOLVER_VERSION,
            artwork_url="",
        )
        with self.atomic():
            self._start_operation()
            delta = self._apply_existing_locked(existing, after)
        self._finish_operation([delta] if delta else [])
        return delta

    def apply_romm_presentation(self, game_id: str, source: "CatalogueGame") -> CatalogueDelta | None:
        """Fill only missing presentation fields from a matching RomM record."""
        existing = self.get_game(game_id)
        if existing is None:
            return None
        after = replace(
            existing,
            genres=existing.genres or source.genres,
            release_date=existing.release_date or source.release_date,
            release_year=existing.release_year or source.release_year,
            total_playtime=existing.total_playtime or source.total_playtime,
            local_multiplayer=existing.local_multiplayer if existing.local_multiplayer is not None else source.local_multiplayer,
            online_multiplayer=existing.online_multiplayer if existing.online_multiplayer is not None else source.online_multiplayer,
            game_mode=existing.game_mode or source.game_mode,
            protondb_rating=existing.protondb_rating or source.protondb_rating,
        )
        with self.atomic():
            self._start_operation()
            delta = self._apply_existing_locked(existing, after)
        self._finish_operation([delta] if delta else [])
        return delta

    def set_metadata_match(self, game_id: str, provider: str, metadata_game_id: str,
                           canonical_title: str) -> CatalogueDelta | None:
        existing = self.get_game(game_id)
        if existing is None:
            return None
        after = replace(existing, title=existing.display_title_override or canonical_title,
                        metadata_provider=provider, metadata_game_id=metadata_game_id,
                        canonical_title=canonical_title, match_status="manual",
                        match_method="manual", match_confidence=1, match_locked=True,
                        metadata_checked_at=int(time.time()), artwork_url="")
        with self.atomic():
            self._start_operation()
            delta = self._apply_existing_locked(existing, after)
        self._finish_operation([delta] if delta else [])
        return delta

    def clear_metadata_match(self, game_id: str) -> CatalogueDelta | None:
        existing = self.get_game(game_id)
        if existing is None:
            return None
        title = existing.display_title_override or existing.normalized_search_title or clean_local_title(existing.source_title or existing.title)
        after = replace(existing, title=title, metadata_provider="", metadata_game_id="",
                        canonical_title="", match_status="", match_method="manual-cleared",
                        match_confidence=0, match_locked=False, metadata_checked_at=0,
                        artwork_url="", artwork_suppressed=False)
        with self.atomic():
            self._start_operation()
            delta = self._apply_existing_locked(existing, after)
        self._finish_operation([delta] if delta else [])
        return delta

    def mark_played(self, game_id: str) -> CatalogueDelta | None:
        existing = self.get_game(game_id)
        if existing is None:
            return None
        played = int(time.time())
        if played <= existing.last_played:
            return None
        after = replace(existing, last_played=played)
        with self.atomic():
            self._start_operation()
            delta = self._apply_existing_locked(existing, after)
        self._finish_operation([delta] if delta else [])
        return delta

    def set_artwork_url(self, game_id: str, artwork_url: str) -> CatalogueDelta | None:
        existing = self.get_game(game_id)
        if existing is None:
            return None
        with self.atomic():
            self._start_operation()
            delta = self._apply_existing_locked(existing, replace(existing, artwork_url=artwork_url))
        self._finish_operation([delta] if delta else [])
        return delta

    def set_display_title_override(self, game_id: str, title: str) -> CatalogueDelta | None:
        existing = self.get_game(game_id)
        if existing is None:
            return None
        with self.atomic():
            self._start_operation()
            delta = self._apply_existing_locked(existing, replace(existing, title=title, display_title_override=title))
        self._finish_operation([delta] if delta else [])
        return delta

    def clear_display_title_override(self, game_id: str) -> CatalogueDelta | None:
        existing = self.get_game(game_id)
        if existing is None:
            return None
        title = existing.canonical_title or existing.normalized_search_title or clean_local_title(existing.source_title or existing.title)
        with self.atomic():
            self._start_operation()
            delta = self._apply_existing_locked(existing, replace(existing, title=title, display_title_override=""))
        self._finish_operation([delta] if delta else [])
        return delta

    def suppress_artwork(self, game_id: str) -> CatalogueDelta | None:
        existing = self.get_game(game_id)
        if existing is None:
            return None
        with self.atomic():
            self._start_operation()
            delta = self._apply_existing_locked(existing, replace(existing, artwork_url="", artwork_suppressed=True))
        self._finish_operation([delta] if delta else [])
        return delta

    def restore_artwork(self, game_id: str) -> CatalogueDelta | None:
        existing = self.get_game(game_id)
        if existing is None:
            return None
        with self.atomic():
            self._start_operation()
            delta = self._apply_existing_locked(existing, replace(existing, artwork_suppressed=False))
        self._finish_operation([delta] if delta else [])
        return delta
