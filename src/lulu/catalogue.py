"""Consoled-owned normalized catalogue and provider boundary."""

from dataclasses import asdict, dataclass
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
            provider_record_id=str(game.rom_id), content_identity=game.file_name,
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

    def _upsert(self, game: CatalogueGame) -> None:
        with self.lock:
            self._upsert_locked(game)

    def _upsert_locked(self, game: CatalogueGame) -> None:
        values = game.as_dict()
        values["genres"] = json.dumps(values["genres"], sort_keys=True)
        columns = ("game_id", "provider", "provider_id", "title", "platform", "install_state",
                   "launchable", "install_dir", "artwork_url", "last_played", "runtime",
                   "platform_label", *IDENTITY_COLUMNS, "availability_state", "provider_record_id",
                   "content_identity", "catalogue_source", "genres", "release_date", "release_year",
                   "total_playtime", "local_multiplayer", "online_multiplayer", "game_mode",
                   "protondb_rating", "last_seen_at", "last_synced_at", "artwork_source_url",
                   "metadata_resolver_version")
        placeholders = ", ".join("?" for _ in columns)
        self.connection.execute(
            f"""INSERT INTO games ({', '.join(columns)}, updated_at) VALUES ({placeholders}, unixepoch())
                ON CONFLICT(game_id) DO UPDATE SET
                provider_id=excluded.provider_id, platform=excluded.platform,
                install_state=CASE WHEN games.install_state='installed' THEN 'installed'
                                   ELSE excluded.install_state END,
                launchable=CASE WHEN games.install_state='installed' THEN games.launchable
                                ELSE excluded.launchable END,
                install_dir=CASE WHEN games.install_state='installed' THEN games.install_dir
                                 ELSE excluded.install_dir END,
                platform_label=excluded.platform_label, source_title=excluded.source_title,
                availability_state=CASE WHEN games.install_state='installed' THEN 'installed'
                                       ELSE excluded.availability_state END,
                provider_record_id=excluded.provider_record_id, content_identity=excluded.content_identity,
                catalogue_source=excluded.catalogue_source,
                 genres=CASE WHEN games.genres != '[]' THEN games.genres ELSE excluded.genres END,
                 release_date=COALESCE(games.release_date, excluded.release_date),
                 release_year=COALESCE(games.release_year, excluded.release_year),
                 total_playtime=COALESCE(games.total_playtime, excluded.total_playtime),
                 local_multiplayer=COALESCE(games.local_multiplayer, excluded.local_multiplayer),
                 online_multiplayer=COALESCE(games.online_multiplayer, excluded.online_multiplayer),
                 game_mode=COALESCE(games.game_mode, excluded.game_mode),
                 protondb_rating=COALESCE(games.protondb_rating, excluded.protondb_rating),
                last_seen_at=excluded.last_seen_at,
                last_synced_at=excluded.last_synced_at, artwork_source_url=excluded.artwork_source_url,
                metadata_resolver_version=CASE WHEN games.metadata_provider != ''
                                               THEN games.metadata_resolver_version
                                               ELSE excluded.metadata_resolver_version END,
                normalized_search_title=excluded.normalized_search_title,
                 title=CASE WHEN games.display_title_override != '' THEN games.display_title_override
                            WHEN games.match_locked OR games.match_status='matched' OR games.match_status='manual'
                            THEN games.title ELSE excluded.title END,
                artwork_url=CASE WHEN games.metadata_game_id != excluded.metadata_game_id
                                 THEN games.artwork_url ELSE excluded.artwork_url END,
                last_played=MAX(games.last_played, excluded.last_played), updated_at=excluded.updated_at""",
            tuple(values[column] for column in columns),
        )

    def reconcile_steam(self, provider: SteamProvider) -> list[CatalogueGame]:
        games = [CatalogueGame.from_steam(game) for game in provider.list_installed()]
        with self.lock:
            # RomM-backed Steam entries also use provider=steam for stable
            # Steam identity, but their availability is owned by RomM.
            self.connection.execute(
                "UPDATE games SET install_state='missing', launchable=0, updated_at=unixepoch() "
                "WHERE provider='steam' AND provider_record_id=''"
            )
            for game in games:
                self._upsert_locked(game)
            self.connection.commit()
        return games

    def reconcile_local(self, provider: LocalContentProvider, root: Path) -> list[CatalogueGame]:
        games = [CatalogueGame.from_local(game) for game in provider.list_installed(root)]
        with self.lock:
            self.connection.execute("UPDATE games SET install_state='missing', launchable=0, updated_at=unixepoch() WHERE provider='local'")
            for game in games:
                self._upsert_locked(game)
            self.connection.commit()
        return games

    def reconcile_romm(self, games: list[CatalogueGame]) -> list[CatalogueGame]:
        """Apply a complete, already-fetched RomM snapshot atomically."""
        games = list({game.game_id: game for game in games}.values())
        with self.lock:
            self.connection.execute("BEGIN")
            try:
                self.connection.execute(
                "UPDATE games SET install_state='missing', launchable=0, availability_state='unavailable', "
                "updated_at=unixepoch() WHERE provider='romm'"
            )
                self.connection.execute(
                "UPDATE games SET install_state='missing', launchable=0, availability_state='unavailable' "
                "WHERE provider='steam' AND provider_record_id != '' AND install_state != 'installed'"
            )
                for game in games:
                    self._upsert_locked(game)
                self.connection.commit()
            except Exception:
                self.connection.rollback()
                raise
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
                # Steam-backed RomM records retain runtime provider=steam; their
                # non-empty provider_record_id is the authoritative RomM source.
                query += " AND (provider='romm' OR (provider='steam' AND provider_record_id != ''))"
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
        row = self.connection.execute("SELECT match_locked, display_title_override FROM games WHERE game_id=?", (game_id,)).fetchone()
        if row is None or row[0]:
            return
        title = row[1] or (match.canonical_title if match.status == "matched" else match.normalized_search_title)
        presentation = match.presentation
        with self.lock:
            self.connection.execute(
                """UPDATE games SET title=?, normalized_search_title=?, metadata_provider=?, metadata_game_id=?,
                   canonical_title=?, match_status=?, match_method=?, match_confidence=?, match_locked=0,
                   metadata_checked_at=?, genres=COALESCE(?, genres), release_date=COALESCE(?, release_date),
                   release_year=COALESCE(?, release_year), total_playtime=COALESCE(?, total_playtime),
                   local_multiplayer=COALESCE(?, local_multiplayer), online_multiplayer=COALESCE(?, online_multiplayer),
                   game_mode=COALESCE(?, game_mode), protondb_rating=COALESCE(?, protondb_rating),
                   metadata_resolver_version=?,
                   updated_at=unixepoch() WHERE game_id=? AND match_locked=0""",
                (title, match.normalized_search_title, match.provider, match.game_id, match.canonical_title,
                 match.status, match.method, match.confidence, int(time.time()),
                 json.dumps(presentation["genres"]) if presentation.get("genres") else None,
                 presentation.get("release_date"), presentation.get("release_year"),
                 presentation.get("total_playtime"), presentation.get("local_multiplayer"),
                 presentation.get("online_multiplayer"), presentation.get("game_mode"),
                 presentation.get("protondb_rating"), METADATA_RESOLVER_VERSION, game_id),
            )
            self.connection.commit()

    def apply_romm_presentation(self, game_id: str, source: "CatalogueGame") -> None:
        """Fill only missing presentation fields from a matching RomM record."""
        with self.lock:
            self.connection.execute(
                """UPDATE games SET
                   genres=CASE WHEN games.genres='[]' THEN ? ELSE games.genres END,
                   release_date=COALESCE(release_date, ?), release_year=COALESCE(release_year, ?),
                   total_playtime=COALESCE(total_playtime, ?),
                   local_multiplayer=COALESCE(local_multiplayer, ?),
                   online_multiplayer=COALESCE(online_multiplayer, ?),
                   game_mode=COALESCE(game_mode, ?), protondb_rating=COALESCE(protondb_rating, ?),
                   updated_at=unixepoch() WHERE game_id=?""",
                (json.dumps(list(source.genres)), source.release_date, source.release_year,
                 source.total_playtime, source.local_multiplayer, source.online_multiplayer,
                 source.game_mode, source.protondb_rating, game_id),
            )
            self.connection.commit()

    def set_metadata_match(self, game_id: str, provider: str, metadata_game_id: str,
                           canonical_title: str) -> None:
        self.connection.execute(
            """UPDATE games SET title=CASE WHEN display_title_override != '' THEN display_title_override ELSE ? END,
               metadata_provider=?, metadata_game_id=?, canonical_title=?,
               match_status='manual', match_method='manual', match_confidence=1, match_locked=1,
               metadata_checked_at=unixepoch(), artwork_url='' WHERE game_id=?""",
            (canonical_title, provider, metadata_game_id, canonical_title, game_id),
        )
        self.connection.commit()

    def clear_metadata_match(self, game_id: str) -> None:
        row = self.get_game(game_id)
        if row is None:
            return
        title = row.display_title_override or row.normalized_search_title or clean_local_title(row.source_title or row.title)
        self.connection.execute(
            """UPDATE games SET title=?, metadata_provider='', metadata_game_id='', canonical_title='',
               match_status='', match_method='manual-cleared', match_confidence=0, match_locked=0,
               metadata_checked_at=0, artwork_url='', artwork_suppressed=0 WHERE game_id=?""", (title, game_id),
        )
        self.connection.commit()

    def mark_played(self, game_id: str) -> None:
        self.connection.execute("UPDATE games SET last_played=unixepoch(), updated_at=unixepoch() WHERE game_id=?", (game_id,))
        self.connection.commit()

    def set_artwork_url(self, game_id: str, artwork_url: str) -> None:
        self.connection.execute("UPDATE games SET artwork_url=?, updated_at=unixepoch() WHERE game_id=?", (artwork_url, game_id))
        self.connection.commit()

    def set_display_title_override(self, game_id: str, title: str) -> None:
        self.connection.execute(
            "UPDATE games SET title=?, display_title_override=?, updated_at=unixepoch() WHERE game_id=?",
            (title, title, game_id),
        )
        self.connection.commit()

    def clear_display_title_override(self, game_id: str) -> None:
        row = self.get_game(game_id)
        if row is None:
            return
        title = row.canonical_title or row.normalized_search_title or clean_local_title(row.source_title or row.title)
        self.connection.execute(
            "UPDATE games SET title=?, display_title_override='', updated_at=unixepoch() WHERE game_id=?",
            (title, game_id),
        )
        self.connection.commit()

    def suppress_artwork(self, game_id: str) -> None:
        self.connection.execute(
            "UPDATE games SET artwork_url='', artwork_suppressed=1, updated_at=unixepoch() WHERE game_id=?",
            (game_id,),
        )
        self.connection.commit()

    def restore_artwork(self, game_id: str) -> None:
        self.connection.execute(
            "UPDATE games SET artwork_suppressed=0, updated_at=unixepoch() WHERE game_id=?",
            (game_id,),
        )
        self.connection.commit()
