"""Consoled-owned normalized catalogue and provider boundary."""

from dataclasses import asdict, dataclass
import os
from pathlib import Path
import sqlite3
import time

from .local_content import LocalContentGame, LocalContentProvider
from .metadata import MetadataMatch, clean_local_title
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

    @classmethod
    def from_steam(cls, game: InstalledSteamGame) -> "CatalogueGame":
        return cls(
            game_id=f"steam:{game.app_id}", provider="steam", provider_id=game.app_id,
            title=game.title, platform="Steam", install_state="installed", launchable=True,
            install_dir=game.install_dir, artwork_url=game.artwork_url, last_played=game.last_played,
            source_title=game.title, normalized_search_title=clean_local_title(game.title),
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
        )

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


IDENTITY_COLUMNS = (
    "source_title", "normalized_search_title", "metadata_provider", "metadata_game_id",
    "canonical_title", "match_status", "match_method", "match_confidence",
    "match_locked", "metadata_checked_at",
)
SELECT_COLUMNS = (
    "game_id, provider, provider_id, title, platform, install_state, launchable, install_dir, "
    "artwork_url, last_played, runtime, platform_label, " + ", ".join(IDENTITY_COLUMNS)
)


class CatalogueStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or Path(os.environ.get("LULU_CATALOGUE_DB", "~/.local/share/lulu/catalogue.sqlite3")).expanduser()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.path)
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
                      "match_locked": "INTEGER NOT NULL DEFAULT 0", "metadata_checked_at": "INTEGER NOT NULL DEFAULT 0"}
        for name, definition in migrations.items():
            if name not in columns:
                self.connection.execute(f"ALTER TABLE games ADD COLUMN {name} {definition}")
        self.connection.commit()

    def _upsert(self, game: CatalogueGame) -> None:
        values = game.as_dict()
        columns = ("game_id", "provider", "provider_id", "title", "platform", "install_state",
                   "launchable", "install_dir", "artwork_url", "last_played", "runtime",
                   "platform_label", *IDENTITY_COLUMNS)
        placeholders = ", ".join("?" for _ in columns)
        self.connection.execute(
            f"""INSERT INTO games ({', '.join(columns)}, updated_at) VALUES ({placeholders}, unixepoch())
                ON CONFLICT(game_id) DO UPDATE SET
                provider_id=excluded.provider_id, platform=excluded.platform,
                install_state=excluded.install_state, launchable=excluded.launchable,
                install_dir=excluded.install_dir, runtime=excluded.runtime,
                platform_label=excluded.platform_label, source_title=excluded.source_title,
                normalized_search_title=excluded.normalized_search_title,
                title=CASE WHEN games.match_locked OR games.match_status='matched' OR games.match_status='manual'
                           THEN games.title ELSE excluded.title END,
                artwork_url=CASE WHEN games.metadata_game_id != excluded.metadata_game_id
                                 THEN games.artwork_url ELSE excluded.artwork_url END,
                last_played=MAX(games.last_played, excluded.last_played), updated_at=excluded.updated_at""",
            tuple(values[column] for column in columns),
        )

    def reconcile_steam(self, provider: SteamProvider) -> list[CatalogueGame]:
        games = [CatalogueGame.from_steam(game) for game in provider.list_installed()]
        self.connection.execute("UPDATE games SET install_state='missing', launchable=0, updated_at=unixepoch() WHERE provider='steam'")
        for game in games:
            self._upsert(game)
        self.connection.commit()
        return games

    def reconcile_local(self, provider: LocalContentProvider, root: Path) -> list[CatalogueGame]:
        games = [CatalogueGame.from_local(game) for game in provider.list_installed(root)]
        self.connection.execute("UPDATE games SET install_state='missing', launchable=0, updated_at=unixepoch() WHERE provider='local'")
        for game in games:
            self._upsert(game)
        self.connection.commit()
        return games

    def _rows(self, query: str, parameters: tuple[object, ...] = ()) -> list[CatalogueGame]:
        return [CatalogueGame(*row) for row in self.connection.execute(query, parameters)]

    def list_games(self, scope: str = "all") -> list[CatalogueGame]:
        query = f"SELECT {SELECT_COLUMNS} FROM games WHERE install_state='installed'"
        parameters: tuple[object, ...] = ()
        if scope == "steam":
            query += " AND provider=?"; parameters = ("steam",)
        elif scope.startswith("platform:"):
            query += " AND provider='local' AND platform=?"; parameters = (scope.removeprefix("platform:"),)
        return self._rows(query + " ORDER BY title COLLATE NOCASE", parameters)

    def list_recent(self) -> list[CatalogueGame]:
        return self._rows(f"SELECT {SELECT_COLUMNS} FROM games WHERE install_state='installed' AND last_played>0 ORDER BY last_played DESC")

    def get_game(self, game_id: str) -> CatalogueGame | None:
        rows = self._rows(f"SELECT {SELECT_COLUMNS} FROM games WHERE game_id=?", (game_id,))
        return rows[0] if rows else None

    def list_platforms(self) -> list[tuple[str, str]]:
        platforms = list(self.connection.execute("SELECT platform, MAX(platform_label) FROM games WHERE provider='local' AND install_state='installed' GROUP BY platform"))
        return sorted(platforms, key=lambda item: item[1].casefold())

    def needs_metadata_match(self, game_id: str, now: int | None = None) -> bool:
        row = self.connection.execute("SELECT match_locked, metadata_game_id, metadata_checked_at FROM games WHERE game_id=?", (game_id,)).fetchone()
        if row is None or row[0] or row[1]:
            return False
        current = int(time.time()) if now is None else now
        return not row[2] or current - row[2] >= 86400

    def apply_metadata_match(self, game_id: str, match: MetadataMatch) -> None:
        row = self.connection.execute("SELECT match_locked FROM games WHERE game_id=?", (game_id,)).fetchone()
        if row is None or row[0]:
            return
        title = match.canonical_title if match.status == "matched" else match.normalized_search_title
        self.connection.execute(
            """UPDATE games SET title=?, normalized_search_title=?, metadata_provider=?, metadata_game_id=?,
               canonical_title=?, match_status=?, match_method=?, match_confidence=?, match_locked=0,
               metadata_checked_at=?, artwork_url=artwork_url,
               updated_at=unixepoch() WHERE game_id=? AND match_locked=0""",
            (title, match.normalized_search_title, match.provider, match.game_id, match.canonical_title,
             match.status, match.method, match.confidence, int(time.time()), match.status, game_id),
        )
        self.connection.commit()

    def set_metadata_match(self, game_id: str, provider: str, metadata_game_id: str,
                           canonical_title: str) -> None:
        self.connection.execute(
            """UPDATE games SET title=?, metadata_provider=?, metadata_game_id=?, canonical_title=?,
               match_status='manual', match_method='manual', match_confidence=1, match_locked=1,
               metadata_checked_at=unixepoch(), artwork_url='' WHERE game_id=?""",
            (canonical_title, provider, metadata_game_id, canonical_title, game_id),
        )
        self.connection.commit()

    def clear_metadata_match(self, game_id: str) -> None:
        row = self.get_game(game_id)
        if row is None:
            return
        title = row.normalized_search_title or clean_local_title(row.source_title or row.title)
        self.connection.execute(
            """UPDATE games SET title=?, metadata_provider='', metadata_game_id='', canonical_title='',
               match_status='', match_method='manual-cleared', match_confidence=0, match_locked=0,
               metadata_checked_at=0, artwork_url='' WHERE game_id=?""", (title, game_id),
        )
        self.connection.commit()

    def mark_played(self, game_id: str) -> None:
        self.connection.execute("UPDATE games SET last_played=unixepoch(), updated_at=unixepoch() WHERE game_id=?", (game_id,))
        self.connection.commit()

    def set_artwork_url(self, game_id: str, artwork_url: str) -> None:
        self.connection.execute("UPDATE games SET artwork_url=?, updated_at=unixepoch() WHERE game_id=?", (artwork_url, game_id))
        self.connection.commit()
