"""Consoled-owned normalized catalogue and provider boundary."""

from dataclasses import asdict, dataclass
import os
from pathlib import Path
import sqlite3

from .steam_provider import InstalledSteamGame, SteamProvider
from .local_content import LocalContentGame, LocalContentProvider


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

    @classmethod
    def from_steam(cls, game: InstalledSteamGame) -> "CatalogueGame":
        return cls(
            game_id=f"steam:{game.app_id}",
            provider="steam",
            provider_id=game.app_id,
            title=game.title,
            platform="Steam",
            install_state="installed",
            launchable=True,
            install_dir=game.install_dir,
            artwork_url=game.artwork_url,
            last_played=game.last_played,
        )

    @classmethod
    def from_local(cls, game: LocalContentGame) -> "CatalogueGame":
        return cls(
            game_id=game.content_id,
            provider="local",
            provider_id=game.content_id,
            title=game.title,
            platform=game.platform,
            install_state=game.install_state,
            launchable=game.launchable,
            install_dir=game.content_path,
            artwork_url="",
            last_played=0,
        )

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


class CatalogueStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or Path(os.environ.get("LULU_CATALOGUE_DB", "~/.local/share/lulu/catalogue.sqlite3")).expanduser()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.path)
        self.connection.execute(
            """CREATE TABLE IF NOT EXISTS games (
                game_id TEXT PRIMARY KEY,
                provider TEXT NOT NULL,
                provider_id TEXT NOT NULL,
                title TEXT NOT NULL,
                platform TEXT NOT NULL,
                install_state TEXT NOT NULL,
                launchable INTEGER NOT NULL,
                install_dir TEXT NOT NULL,
                artwork_url TEXT NOT NULL,
                last_played INTEGER NOT NULL DEFAULT 0,
                updated_at INTEGER NOT NULL DEFAULT (unixepoch()),
                UNIQUE(provider, provider_id)
            )"""
        )
        self.connection.commit()

    def reconcile_steam(self, provider: SteamProvider) -> list[CatalogueGame]:
        games = [CatalogueGame.from_steam(game) for game in provider.list_installed()]
        self.connection.execute("UPDATE games SET install_state = 'missing', launchable = 0, updated_at = unixepoch() WHERE provider = 'steam'")
        for game in games:
            self.connection.execute(
                """INSERT INTO games
                   (game_id, provider, provider_id, title, platform, install_state,
                    launchable, install_dir, artwork_url, last_played, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, unixepoch())
                   ON CONFLICT(game_id) DO UPDATE SET
                     title=excluded.title, platform=excluded.platform,
                     install_state=excluded.install_state, launchable=excluded.launchable,
                     install_dir=excluded.install_dir, artwork_url=excluded.artwork_url,
                     last_played=MAX(games.last_played, excluded.last_played),
                     updated_at=excluded.updated_at""",
                (*game.as_dict().values(),),
            )
        self.connection.commit()
        return games

    def reconcile_local(self, provider: LocalContentProvider, root: Path) -> list[CatalogueGame]:
        games = [CatalogueGame.from_local(game) for game in provider.list_installed(root)]
        self.connection.execute(
            "UPDATE games SET install_state = 'missing', launchable = 0, updated_at = unixepoch() WHERE provider = 'local'"
        )
        for game in games:
            self.connection.execute(
                """INSERT INTO games
                   (game_id, provider, provider_id, title, platform, install_state,
                    launchable, install_dir, artwork_url, last_played, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, unixepoch())
                   ON CONFLICT(game_id) DO UPDATE SET
                     title=excluded.title, platform=excluded.platform,
                     install_state=excluded.install_state, launchable=excluded.launchable,
                     install_dir=excluded.install_dir, artwork_url=excluded.artwork_url,
                     updated_at=excluded.updated_at""",
                (*game.as_dict().values(),),
            )
        self.connection.commit()
        return games

    def list_games(self, scope: str = "all") -> list[CatalogueGame]:
        query = "SELECT game_id, provider, provider_id, title, platform, install_state, launchable, install_dir, artwork_url, last_played FROM games WHERE launchable = 1"
        parameters: tuple[object, ...] = ()
        if scope == "steam":
            query += " AND provider = ?"
            parameters = ("steam",)
        query += " ORDER BY title COLLATE NOCASE"
        return [CatalogueGame(*row) for row in self.connection.execute(query, parameters)]

    def list_recent(self) -> list[CatalogueGame]:
        return [
            CatalogueGame(*row)
            for row in self.connection.execute(
                "SELECT game_id, provider, provider_id, title, platform, install_state, launchable, install_dir, artwork_url, last_played FROM games WHERE launchable = 1 AND last_played > 0 ORDER BY last_played DESC"
            )
        ]

    def get_game(self, game_id: str) -> CatalogueGame | None:
        row = self.connection.execute(
            "SELECT game_id, provider, provider_id, title, platform, install_state, launchable, install_dir, artwork_url, last_played FROM games WHERE game_id = ?",
            (game_id,),
        ).fetchone()
        return CatalogueGame(*row) if row is not None else None

    def mark_played(self, game_id: str) -> None:
        self.connection.execute("UPDATE games SET last_played = unixepoch(), updated_at = unixepoch() WHERE game_id = ?", (game_id,))
        self.connection.commit()
