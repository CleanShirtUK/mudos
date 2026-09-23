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
from .plugins.romm.client import RommGame
from .plugins.steam.provider import InstalledSteamGame, SteamProvider
from .plugins.steam.entitlements import SteamEntitlement
from .switch_content import parent_name
from .pc_install import PcInstallSource


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
    local_artwork_path: str = ""
    artwork_override: bool = False
    local_artwork_mode: str = ""
    local_artwork_mtime: int = 0
    automatic_artwork_url: str = ""
    automatic_artwork_source_url: str = ""
    automatic_artwork_provider: str = ""
    automatic_artwork_type: str = ""
    automatic_artwork_width: int | None = None
    automatic_artwork_height: int | None = None
    selected_artwork_source_url: str = ""
    metadata_resolver_version: int = 0
    installed_game_id: str = ""
    summary: str = ""
    game_modes: tuple[str, ...] = ()
    developer: str = ""
    publisher: str = ""
    platforms: tuple[str, ...] = ()
    franchise: str = ""
    collection: str = ""
    igdb_id: str = ""
    igdb_fetched_at: int | None = None
    protondb_tier: str | None = None
    protondb_confidence: str | None = None
    protondb_score: float | None = None
    protondb_trending_tier: str | None = None
    protondb_best_tier: str | None = None
    protondb_report_count: int | None = None
    protondb_fetched_at: int | None = None
    component_paths: tuple[str, ...] = ()
    component_roles: tuple[str, ...] = ()
    component_title_ids: tuple[str, ...] = ()
    mudos_owned: bool = False
    artwork_type: str = ""
    artwork_provider: str = ""
    artwork_width: int | None = None
    artwork_height: int | None = None
    icon_url: str = ""
    canonical_cover_url: str = ""
    canonical_cover_width: int | None = None
    canonical_cover_height: int | None = None

    @classmethod
    def from_steam(cls, game: InstalledSteamGame) -> "CatalogueGame":
        return cls(
            game_id=f"steam:{game.app_id}", provider="steam", provider_id=game.app_id,
            title=game.title, platform="Steam", install_state="installed", launchable=True,
            install_dir=game.install_dir, artwork_url=game.artwork_url, last_played=game.last_played,
            source_title=game.title, normalized_search_title=clean_local_title(game.title),
            catalogue_source="steam", artwork_type="cover", artwork_provider="steam",
            artwork_source_url=game.artwork_url,
        )

    @classmethod
    def from_lutris(cls, registration: dict[str, object], source: PcInstallSource) -> "CatalogueGame":
        slug = str(registration.get("slug") or source.canonical_game_id)
        title = str(registration.get("title") or source.title)
        return cls(
            game_id=f"lutris:{source.lutris_slug or source.canonical_game_id}", provider="lutris", provider_id=str(registration.get("lutris_id", slug)),
            title=title, platform="PC", install_state="installed", launchable=True,
            install_dir=str(registration.get("directory", "")), artwork_url="", last_played=0,
            runtime=str(registration.get("runner", "")), source_title=source.title,
            normalized_search_title=clean_local_title(title), availability_state="installed",
            provider_record_id=str(registration.get("config_id", "")), content_identity=source.source_id,
            catalogue_source=source.provenance,
        )

    @classmethod
    def from_component_app(cls, app: object) -> "CatalogueGame":
        """Normalize an external component application without naming its adapter."""
        value = app if isinstance(app, dict) else {
            key: getattr(app, key, "") for key in (
                "application_id", "name", "summary", "version", "branch", "remote",
                "installed", "icon", "categories",
            )
        }
        application_id = str(value.get("application_id", "")).strip()
        title = str(value.get("name", application_id)).strip() or application_id
        installed = bool(value.get("installed", False))
        categories = tuple(str(item) for item in value.get("categories", ()))
        return cls(
            game_id=f"flatpak:{application_id}", provider="flatpak", provider_id=application_id,
            title=title, platform="Linux", install_state="installed" if installed else "available",
            launchable=installed, install_dir=str(Path.home() / ".var" / "app" / application_id),
            artwork_url="", last_played=0, runtime=str(value.get("branch", "")),
            source_title=title, summary=str(value.get("summary", "")), genres=categories,
            availability_state="installed" if installed else "available", provider_record_id=application_id,
            content_identity=application_id, catalogue_source="flatpak", icon_url=str(value.get("icon", "")),
            artwork_type="icon", artwork_provider="flatpak",
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
            catalogue_source="local", component_paths=getattr(game, "component_paths", ()),
            component_roles=getattr(game, "component_roles", ()),
            component_title_ids=getattr(game, "component_title_ids", ()),
            mudos_owned=bool(getattr(game, "mudos_owned", True)),
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
                 artwork_type="cover", artwork_provider="romm",
                content_identity=game.files[0].name if game.files else game.file_name,
                genres=game.genres, release_date=game.release_date, release_year=game.release_year,
                 total_playtime=game.total_playtime, local_multiplayer=game.local_multiplayer,
                 online_multiplayer=game.online_multiplayer, game_mode=game.game_mode,
                 protondb_rating=game.protondb_rating, artwork_source_url=game.artwork_url,
                 igdb_id=game.igdb_id,
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
             artwork_type="cover", artwork_provider="romm",
            release_year=game.release_year, total_playtime=game.total_playtime,
            local_multiplayer=game.local_multiplayer, online_multiplayer=game.online_multiplayer,
             game_mode=game.game_mode, protondb_rating=game.protondb_rating,
             artwork_source_url=game.artwork_url,
             igdb_id=game.igdb_id,
        )

    def as_dict(self) -> dict[str, object]:
        value = asdict(self)
        value["genres"] = list(self.genres)
        value["game_modes"] = list(self.game_modes)
        value["platforms"] = list(self.platforms)
        value["component_paths"] = list(self.component_paths)
        value["component_roles"] = list(self.component_roles)
        value["component_title_ids"] = list(self.component_title_ids)
        return value


def canonical_metadata_required(record: CatalogueGame, *, in_library: bool = False,
                                available_to_download: bool = False) -> bool:
    """Return whether a record is on a Mudos presentation surface."""
    return bool(in_library or available_to_download)


# A record is installable only when it came from a source that asserts the
# user's entitlement/access.  Provider catalogue discovery is deliberately
# not enough.  RomM is retained here because it is the user's accessible
# catalogue, while component/Flathub discovery remains storefront-only.
INSTALLABLE_CATALOGUE_SOURCES = frozenset({"steam", "romm", "gog", "epic"})


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
METADATA_RESOLVER_VERSION = 3
SELECT_COLUMNS = (
    "game_id, provider, provider_id, title, platform, install_state, launchable, install_dir, "
    "artwork_url, last_played, runtime, platform_label, " + ", ".join(IDENTITY_COLUMNS)
    + ", availability_state, provider_record_id, content_identity, catalogue_source, genres, "
      "release_date, release_year, total_playtime, local_multiplayer, online_multiplayer, "
        "game_mode, protondb_rating, last_seen_at, last_synced_at, artwork_source_url, local_artwork_path, artwork_override, "
        "local_artwork_mode, local_artwork_mtime, automatic_artwork_url, automatic_artwork_source_url, automatic_artwork_provider, automatic_artwork_type, "
         "automatic_artwork_width, automatic_artwork_height, selected_artwork_source_url"
       ", metadata_resolver_version, installed_game_id, summary, game_modes, developer, publisher, platforms, "
       "franchise, collection, igdb_id, igdb_fetched_at, protondb_tier, protondb_confidence, protondb_score, "
        "protondb_trending_tier, protondb_best_tier, protondb_report_count, protondb_fetched_at, "
         "component_paths, component_roles, component_title_ids, mudos_owned, artwork_type, artwork_provider, "
         "artwork_width, artwork_height, icon_url, canonical_cover_url, canonical_cover_width, canonical_cover_height"
)
SELECT_FIELD_ORDER = (
    "game_id", "provider", "provider_id", "title", "platform", "install_state", "launchable",
    "install_dir", "artwork_url", "last_played", "runtime", "platform_label", *IDENTITY_COLUMNS, "availability_state",
    "provider_record_id", "content_identity", "catalogue_source", "genres", "release_date",
    "release_year", "total_playtime", "local_multiplayer", "online_multiplayer", "game_mode",
     "protondb_rating", "last_seen_at", "last_synced_at", "artwork_source_url", "local_artwork_path",
      "artwork_override", "local_artwork_mode", "local_artwork_mtime", "automatic_artwork_url", "automatic_artwork_source_url", "automatic_artwork_provider",
      "automatic_artwork_type", "automatic_artwork_width", "automatic_artwork_height",
      "selected_artwork_source_url",
    "metadata_resolver_version", "installed_game_id", "summary", "game_modes", "developer",
    "publisher", "platforms", "franchise", "collection", "igdb_id", "igdb_fetched_at", "protondb_tier",
    "protondb_confidence", "protondb_score", "protondb_trending_tier", "protondb_best_tier",
     "protondb_report_count", "protondb_fetched_at", "component_paths", "component_roles",
      "component_title_ids", "mudos_owned", "artwork_type", "artwork_provider", "artwork_width",
      "artwork_height", "icon_url", "canonical_cover_url", "canonical_cover_width", "canonical_cover_height",
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
                         "artwork_source_url": "TEXT NOT NULL DEFAULT ''", "local_artwork_path": "TEXT NOT NULL DEFAULT ''",
                           "artwork_override": "INTEGER NOT NULL DEFAULT 0", "local_artwork_mode": "TEXT NOT NULL DEFAULT ''",
                          "local_artwork_mtime": "INTEGER NOT NULL DEFAULT 0",
                          "automatic_artwork_url": "TEXT NOT NULL DEFAULT ''",
                         "automatic_artwork_source_url": "TEXT NOT NULL DEFAULT ''", "automatic_artwork_provider": "TEXT NOT NULL DEFAULT ''",
                         "automatic_artwork_type": "TEXT NOT NULL DEFAULT ''", "automatic_artwork_width": "INTEGER",
                          "automatic_artwork_height": "INTEGER", "selected_artwork_source_url": "TEXT NOT NULL DEFAULT ''",
                          "metadata_resolver_version": "INTEGER NOT NULL DEFAULT 0",
                       "installed_game_id": "TEXT NOT NULL DEFAULT ''", "summary": "TEXT NOT NULL DEFAULT ''",
                       "game_modes": "TEXT NOT NULL DEFAULT '[]'", "developer": "TEXT NOT NULL DEFAULT ''",
                       "publisher": "TEXT NOT NULL DEFAULT ''", "platforms": "TEXT NOT NULL DEFAULT '[]'",
                       "franchise": "TEXT NOT NULL DEFAULT ''", "collection": "TEXT NOT NULL DEFAULT ''",
                       "igdb_id": "TEXT NOT NULL DEFAULT ''", "igdb_fetched_at": "INTEGER",
                       "protondb_tier": "TEXT", "protondb_confidence": "TEXT", "protondb_score": "REAL",
                       "protondb_trending_tier": "TEXT", "protondb_best_tier": "TEXT",
                        "protondb_report_count": "INTEGER", "protondb_fetched_at": "INTEGER",
                        "component_paths": "TEXT NOT NULL DEFAULT '[]'",
                        "component_roles": "TEXT NOT NULL DEFAULT '[]'",
                        "component_title_ids": "TEXT NOT NULL DEFAULT '[]'",
                         "mudos_owned": "INTEGER NOT NULL DEFAULT 0",
                         "artwork_type": "TEXT NOT NULL DEFAULT ''", "artwork_provider": "TEXT NOT NULL DEFAULT ''",
                         "artwork_width": "INTEGER", "artwork_height": "INTEGER",
                         "icon_url": "TEXT NOT NULL DEFAULT ''", "canonical_cover_url": "TEXT NOT NULL DEFAULT ''",
                         "canonical_cover_width": "INTEGER", "canonical_cover_height": "INTEGER"}
        for name, definition in migrations.items():
            if name not in columns:
                self.connection.execute(f"ALTER TABLE games ADD COLUMN {name} {definition}")
        # One-time compatibility projection for pre-typed records. Flatpak
        # artwork was an AppStream icon; all other legacy populated artwork
        # was card artwork from a provider/enrichment path.
        self.connection.execute(
            "UPDATE games SET artwork_type=CASE WHEN provider='flatpak' THEN 'icon' ELSE 'cover' END, "
            "artwork_provider=CASE WHEN provider='flatpak' THEN 'flatpak' "
            "WHEN metadata_provider='steamgriddb' THEN 'steamgriddb' ELSE provider END "
            "WHERE artwork_url<>'' AND artwork_type=''"
        )
        self.connection.execute(
            "UPDATE games SET automatic_artwork_url=artwork_url, automatic_artwork_source_url=artwork_source_url, "
            "automatic_artwork_provider=artwork_provider, automatic_artwork_type=artwork_type, "
            "automatic_artwork_width=artwork_width, automatic_artwork_height=artwork_height "
            "WHERE artwork_url<>'' AND automatic_artwork_url='' AND artwork_override=0"
        )
        self.connection.execute(
            "UPDATE games SET local_artwork_mode='filesystem' WHERE artwork_override=1 AND local_artwork_path<>'' AND local_artwork_mode=''"
        )
        self.connection.commit()
        self.connection.execute(
            """CREATE TABLE IF NOT EXISTS metadata_enrichment (
                provider TEXT NOT NULL, game_id TEXT NOT NULL, external_id TEXT NOT NULL,
                fetched_at INTEGER NOT NULL, source_updated_at INTEGER, match_method TEXT NOT NULL,
                confidence REAL NOT NULL DEFAULT 0, status TEXT NOT NULL, normalized_json TEXT NOT NULL,
                PRIMARY KEY(provider, game_id),
                FOREIGN KEY(game_id) REFERENCES games(game_id)
            )"""
        )
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
        return list(value) if name in {"genres", "game_modes", "platforms", "component_paths",
                                      "component_roles", "component_title_ids"} else value

    @classmethod
    def meaningful_changes(cls, before: CatalogueGame, after: CatalogueGame) -> tuple[str, ...]:
        return tuple(
            name for name in MEANINGFUL_GAME_FIELDS
            if cls._field_value(before, name) != cls._field_value(after, name)
        )

    @staticmethod
    def _sql_value(name: str, value: object) -> object:
        return json.dumps(value, sort_keys=True) if name in {
            "genres", "game_modes", "platforms", "component_paths", "component_roles",
            "component_title_ids",
        } else value

    def _commit_if_direct(self) -> None:
        if self._transaction_depth == 0:
            self.connection.commit()

    def _upsert(self, game: CatalogueGame) -> CatalogueDelta | None:
        with self.lock:
            return self._upsert_locked(game)

    @staticmethod
    def _romm_filename(game: CatalogueGame) -> str:
        return Path(game.content_identity or game.source_title or game.title).name.casefold()

    def _matching_local_locked(self, game: CatalogueGame) -> CatalogueGame | None:
        """Find the installed local file represented by one RomM record."""
        locals_ = self._rows(
            f"SELECT {SELECT_COLUMNS} FROM games "
            "WHERE provider='local' AND install_state='installed'"
        )
        filename = self._romm_filename(game)
        expected = (PATHS.rom_root / game.platform / filename).resolve()
        for local in locals_:
            try:
                if Path(local.install_dir).resolve() == expected:
                    return local
            except OSError:
                continue
        # Compatibility with records created before canonical destination
        # matching was introduced.  This remains platform/filename based and
        # never uses the displayed title.
        for local in locals_:
            if local.platform.casefold() == game.platform.casefold() and \
                    Path(local.install_dir).name.casefold() == filename:
                return local
        if game.platform.casefold() == "switch":
            expected_parent = parent_name(filename)
            for local in locals_:
                if local.platform.casefold() == "switch" and \
                        parent_name(local.source_title or local.install_dir) == expected_parent:
                    return local
        return None

    def _associate_romm_locked(self, romm: CatalogueGame, local: CatalogueGame,
                               deltas: list[CatalogueDelta]) -> None:
        linked = replace(
            romm,
            install_state="installed", launchable=local.launchable,
            install_dir=local.install_dir, availability_state="installed",
            installed_game_id=local.game_id,
        )
        self._apply_existing_locked(romm, linked, deltas)
        merged_played = max(local.last_played, romm.last_played)
        if merged_played > local.last_played:
            self._apply_existing_locked(local, replace(local, last_played=merged_played), deltas)

    def _unassociate_romm_locked(self, romm: CatalogueGame,
                                 deltas: list[CatalogueDelta]) -> None:
        if not romm.installed_game_id and romm.install_state != "installed":
            return
        self._apply_existing_locked(
            romm,
            replace(romm, installed_game_id="", install_state="available",
                    launchable=False, install_dir="", availability_state="available"),
            deltas,
        )

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
            component_paths=incoming.component_paths or existing.component_paths,
            component_roles=incoming.component_roles or existing.component_roles,
            component_title_ids=incoming.component_title_ids or existing.component_title_ids,
            mudos_owned=incoming.mudos_owned or existing.mudos_owned,
            genres=existing.genres if existing.genres else incoming.genres,
            release_date=existing.release_date if existing.release_date is not None else incoming.release_date,
            release_year=existing.release_year if existing.release_year is not None else incoming.release_year,
            total_playtime=existing.total_playtime if existing.total_playtime is not None else incoming.total_playtime,
            local_multiplayer=existing.local_multiplayer if existing.local_multiplayer is not None else incoming.local_multiplayer,
            online_multiplayer=existing.online_multiplayer if existing.online_multiplayer is not None else incoming.online_multiplayer,
            game_mode=existing.game_mode if existing.game_mode is not None else incoming.game_mode,
            protondb_rating=existing.protondb_rating if existing.protondb_rating is not None else incoming.protondb_rating,
            summary=existing.summary or incoming.summary,
            game_modes=existing.game_modes or incoming.game_modes,
            developer=existing.developer or incoming.developer,
            publisher=existing.publisher or incoming.publisher,
            platforms=existing.platforms or incoming.platforms,
            franchise=existing.franchise or incoming.franchise,
            collection=existing.collection or incoming.collection,
            igdb_id=existing.igdb_id or incoming.igdb_id,
            igdb_fetched_at=existing.igdb_fetched_at or incoming.igdb_fetched_at,
            protondb_tier=existing.protondb_tier or incoming.protondb_tier,
            protondb_confidence=existing.protondb_confidence or incoming.protondb_confidence,
            protondb_score=existing.protondb_score if existing.protondb_score is not None else incoming.protondb_score,
            protondb_trending_tier=existing.protondb_trending_tier or incoming.protondb_trending_tier,
            protondb_best_tier=existing.protondb_best_tier or incoming.protondb_best_tier,
            protondb_report_count=existing.protondb_report_count if existing.protondb_report_count is not None else incoming.protondb_report_count,
            protondb_fetched_at=existing.protondb_fetched_at or incoming.protondb_fetched_at,
            normalized_search_title=incoming.normalized_search_title,
            metadata_resolver_version=existing.metadata_resolver_version if preserve_metadata else incoming.metadata_resolver_version,
            title=existing.title if preserve_title else incoming.title,
             artwork_url=existing.artwork_url if existing.artwork_override or existing.metadata_game_id != incoming.metadata_game_id else incoming.artwork_url,
            last_played=max(existing.last_played, incoming.last_played),
            last_seen_at=existing.last_seen_at,
            last_synced_at=existing.last_synced_at,
             installed_game_id=incoming.installed_game_id,
             artwork_type=existing.artwork_type or incoming.artwork_type,
             artwork_provider=existing.artwork_provider or incoming.artwork_provider,
             artwork_width=existing.artwork_width or incoming.artwork_width,
             artwork_height=existing.artwork_height or incoming.artwork_height,
             icon_url=incoming.icon_url or existing.icon_url,
             canonical_cover_url=existing.canonical_cover_url or incoming.canonical_cover_url,
             canonical_cover_width=existing.canonical_cover_width or incoming.canonical_cover_width,
             canonical_cover_height=existing.canonical_cover_height or incoming.canonical_cover_height,
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
                        current, replace(current, install_state="available", launchable=False,
                                         install_dir="", availability_state="available"), deltas)
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
            for current in self._rows(f"SELECT {SELECT_COLUMNS} FROM games WHERE provider='romm'"):
                local = self._matching_local_locked(current)
                if local is not None:
                    self._associate_romm_locked(current, local, deltas)
                else:
                    self._unassociate_romm_locked(current, deltas)
        self._finish_operation(deltas)
        return games

    def reconcile_lutris(self, registration: dict[str, object], source: PcInstallSource) -> CatalogueGame:
        """Upsert one Mudos-managed Lutris registration without a duplicate source card."""
        game = CatalogueGame.from_lutris(registration, source)
        deltas: list[CatalogueDelta] = []
        self._start_operation()
        with self.atomic():
            self._upsert_locked(game, deltas)
        self._finish_operation(deltas)
        return game

    def reconcile_component_apps(self, provider: str, games: list[CatalogueGame]) -> list[CatalogueGame]:
        """Reconcile a component-owned snapshot by stable provider identity."""
        deltas: list[CatalogueDelta] = []
        incoming = {game.game_id for game in games}
        self._start_operation()
        with self.atomic():
            for current in self._rows("SELECT %s FROM games WHERE provider=?" % SELECT_COLUMNS, (provider,)):
                if current.game_id not in incoming:
                    self._apply_existing_locked(current, replace(current, install_state="available",
                                             launchable=False, install_dir="",
                                             availability_state="available"), deltas)
            for game in games:
                current = self.get_game(game.game_id)
                if current is None:
                    self._upsert_locked(game, deltas)
                    continue
                # Component snapshots explicitly report installed state. Do
                # not let the generic merge preserve a stale installed flag
                # after a provider-native uninstall.
                baseline = replace(current, install_state=game.install_state,
                                   launchable=game.launchable, install_dir=game.install_dir,
                                   availability_state=game.availability_state)
                self._apply_existing_locked(current, self._merged_game(baseline, game), deltas)
        self._finish_operation(deltas)
        return games

    def register_lutris_source(self, source: PcInstallSource) -> CatalogueGame:
        """Expose a completed source as the same canonical install identity."""
        game = replace(CatalogueGame.from_lutris(
            {"slug": source.lutris_slug or source.canonical_game_id,
             "title": source.title, "runner": "wine" if source.source_type.value in
             {"windows-installer", "msi-installer"} else "linux",
             "lutris_id": source.source_id, "directory": ""}, source),
                       install_state="available", launchable=False,
                       availability_state="available", install_dir="",
                       provider_id=source.source_id)
        deltas: list[CatalogueDelta] = []
        self._start_operation()
        with self.atomic():
            self._upsert_locked(game, deltas)
        self._finish_operation(deltas)
        return game

    def mark_lutris_uninstalled(self, provider_id: str) -> CatalogueGame | None:
        rows = self._rows(f"SELECT {SELECT_COLUMNS} FROM games WHERE provider='lutris' AND provider_id=?",
                          (str(provider_id),))
        if not rows:
            return None
        current = rows[0]
        updated = replace(current, install_state="available", launchable=False, install_dir="",
                          availability_state="available")
        deltas: list[CatalogueDelta] = []
        self._start_operation()
        with self.atomic():
            self._apply_existing_locked(current, updated, deltas)
        self._finish_operation(deltas)
        return updated

    def reconcile_romm(self, games: list[CatalogueGame], mode: str = "full") -> list[CatalogueGame]:
        """Apply a complete, already-fetched RomM snapshot atomically."""
        games = list({game.game_id: game for game in games}.values())
        # Switch component records are one provider content set. Keep one
        # catalogue identity while retaining all RomM record IDs as source
        # provenance; component downloads remain provider-level records.
        switch_groups: dict[tuple[str, str], list[CatalogueGame]] = {}
        other_games: list[CatalogueGame] = []
        for game in games:
            if game.platform.casefold() == "switch":
                switch_groups.setdefault((game.platform.casefold(), game.title.casefold()), []).append(game)
            else:
                other_games.append(game)
        collapsed: list[CatalogueGame] = list(other_games)
        for group in switch_groups.values():
            base = next((item for item in group if not any(token in item.content_identity.casefold()
                        for token in ("update", "patch", "dlc", "booster"))), group[0])
            collapsed.append(replace(base, provider_record_id=",".join(item.provider_record_id for item in group),
                                     content_identity=base.content_identity))
        games = collapsed
        deltas: list[CatalogueDelta] = []
        self._start_operation()
        with self.atomic(rollback=mode == "upsert-rollback"):
            associated: list[CatalogueGame] = []
            for game in games:
                local = self._matching_local_locked(game)
                if local is None:
                    associated.append(game)
                else:
                    associated.append(replace(
                        game, install_state="installed", launchable=local.launchable,
                        install_dir=local.install_dir, availability_state="installed",
                        installed_game_id=local.game_id,
                    ))
                    if local.last_played < game.last_played:
                        self._apply_existing_locked(
                            local, replace(local, last_played=game.last_played), deltas)
            games = associated
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
                for name in ("genres", "game_modes", "platforms", "component_paths",
                             "component_roles", "component_title_ids"):
                    index = SELECT_FIELD_ORDER.index(name)
                    try:
                        values[index] = tuple(json.loads(values[index] or "[]"))
                    except (TypeError, ValueError, json.JSONDecodeError):
                        values[index] = ()
                games.append(CatalogueGame(*values))
            return games

    @staticmethod
    def _installed_presentation_where() -> str:
        return (
            "install_state='installed' AND NOT ("
            "provider='romm' AND installed_game_id<>'' AND EXISTS ("
            "SELECT 1 FROM games AS linked_local "
            "WHERE linked_local.game_id=games.installed_game_id "
            "AND linked_local.provider='local' AND linked_local.install_state='installed'"
            "))"
        )

    def list_games(self, scope: str = "all") -> list[CatalogueGame]:
        query = f"SELECT {SELECT_COLUMNS} FROM games WHERE {self._installed_presentation_where()}"
        parameters: tuple[object, ...] = ()
        if scope == "pc":
            # PC Games includes native Linux applications managed by enabled
            # providers (currently Steam and Flatpak), not only Steam rows.
            query += " AND provider IN ('steam', 'flatpak')"
        elif scope == "steam":
            query += " AND provider=?"; parameters = ("steam",)
        elif scope.startswith("platform:"):
            query += " AND provider='local' AND platform=?"; parameters = (scope.removeprefix("platform:"),)
        return self._rows(query + " ORDER BY title COLLATE NOCASE", parameters)

    def list_catalogue_games(self) -> list[CatalogueGame]:
        return self._rows(f"SELECT {SELECT_COLUMNS} FROM games ORDER BY title COLLATE NOCASE")

    def list_recent(self) -> list[CatalogueGame]:
        return self._rows(
            f"SELECT {SELECT_COLUMNS} FROM games WHERE {self._installed_presentation_where()} "
            "AND last_played>0 ORDER BY last_played DESC"
        )

    def list_available_games(self, provider: str | None = None) -> list[CatalogueGame]:
        # Installable is an entitlement/access surface, not provider
        # storefront inventory.  Keep both state columns explicit so stale
        # or partially reconciled rows cannot leak into the UI.
        sources = ",".join("?" for _ in INSTALLABLE_CATALOGUE_SOURCES)
        query = (
            f"SELECT {SELECT_COLUMNS} FROM games WHERE "
            "availability_state='available' AND install_state='available' "
            f"AND catalogue_source IN ({sources})"
        )
        parameters: tuple[object, ...] = tuple(sorted(INSTALLABLE_CATALOGUE_SOURCES))
        if provider is not None:
            if provider == "romm":
                # The existing Store endpoint historically asked for the RomM
                # provider, but also carried transitional Steam rows. Keep that
                # display contract while the Steam rows now come from Valve.
                query += " AND (provider='romm' OR (provider='steam' AND availability_state='available'))"
            else:
                query += " AND provider=?"
                parameters += (provider,)
        query += " AND NOT (provider='romm' AND installed_game_id<>'' AND EXISTS ("
        query += "SELECT 1 FROM games AS linked_local WHERE linked_local.game_id=games.installed_game_id "
        query += "AND linked_local.provider='local' AND linked_local.install_state='installed'))"
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
            "catalogue_source, platform, metadata_resolver_version, metadata_provider "
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
        if row[1] and not appid_migration and (
                (row[8] == "igdb" and row[7] == METADATA_RESOLVER_VERSION)
                or (not row[8] and row[2] == "matched")):
            return False
        current = int(time.time()) if now is None else now
        cooldown = (
            TEMPORARY_METADATA_RETRY_SECONDS
            if row[3] in {"network-error", "igdb-network-error", "igdb-unconfigured"}
            else NORMAL_METADATA_RETRY_SECONDS
        )
        return not row[4] or current - row[4] >= cooldown

    def apply_metadata_match(self, game_id: str, match: MetadataMatch) -> None:
        existing = self.get_game(game_id)
        if existing is None or existing.match_locked:
            return None
        if match.status != "matched":
            # A failed/ambiguous canonical lookup must not erase usable
            # provider presentation metadata or a previously selected cover.
            after = replace(existing, normalized_search_title=match.normalized_search_title,
                            match_status=match.status, match_method=match.method,
                            match_confidence=match.confidence,
                            metadata_checked_at=int(time.time()))
            with self.atomic():
                self._start_operation()
                delta = self._apply_existing_locked(existing, after)
            self._finish_operation([delta] if delta else [])
            return delta
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
            summary=presentation.get("summary") or existing.summary,
            game_modes=tuple(presentation.get("game_modes", ())) or existing.game_modes,
            developer=presentation.get("developer") or existing.developer,
            publisher=presentation.get("publisher") or existing.publisher,
            platforms=tuple(presentation.get("platforms", ())) or existing.platforms,
            franchise=presentation.get("franchise") or existing.franchise,
            collection=presentation.get("collection") or existing.collection,
            igdb_id=str(presentation.get("igdb_id") or existing.igdb_id),
            metadata_resolver_version=METADATA_RESOLVER_VERSION,
            canonical_cover_url=str(presentation.get("cover_url") or existing.canonical_cover_url),
            canonical_cover_width=presentation.get("cover_width") or existing.canonical_cover_width,
            canonical_cover_height=presentation.get("cover_height") or existing.canonical_cover_height,
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

    def enrichment_record(self, provider: str, game_id: str) -> dict[str, object] | None:
        row = self.connection.execute(
            "SELECT external_id, fetched_at, source_updated_at, match_method, confidence, status, normalized_json "
            "FROM metadata_enrichment WHERE provider=? AND game_id=?", (provider, game_id)
        ).fetchone()
        if row is None:
            return None
        try:
            normalized = json.loads(row[6])
        except (TypeError, ValueError, json.JSONDecodeError):
            normalized = {}
        return {"provider": provider, "game_id": game_id, "external_id": row[0],
                "fetched_at": row[1], "source_updated_at": row[2], "match_method": row[3],
                "confidence": row[4], "status": row[5], "normalized": normalized}

    def enrichment_is_fresh(self, provider: str, game_id: str, ttl: int,
                            now: int | None = None) -> bool:
        record = self.enrichment_record(provider, game_id)
        return bool(record and int(record["fetched_at"]) + ttl > (int(time.time()) if now is None else now))

    def apply_enrichment(self, provider: str, game_id: str, external_id: str,
                         normalized: dict[str, object], *, match_method: str,
                         confidence: float, source_updated_at: int | None = None,
                         fetched_at: int | None = None, status: str = "matched") -> CatalogueDelta | None:
        existing = self.get_game(game_id)
        if existing is None:
            return None
        fetched = int(time.time()) if fetched_at is None else fetched_at
        after = replace(
            existing,
            summary=existing.summary or str(normalized.get("summary") or ""),
            release_date=existing.release_date or (str(normalized["release_date"]) if normalized.get("release_date") else None),
            release_year=existing.release_year if existing.release_year is not None else (int(normalized["release_year"]) if normalized.get("release_year") is not None else None),
            genres=existing.genres or tuple(str(item) for item in normalized.get("genres", ())),
            game_modes=existing.game_modes or tuple(str(item) for item in normalized.get("game_modes", ())),
            developer=existing.developer or str(normalized.get("developer") or ""),
             publisher=existing.publisher or str(normalized.get("publisher") or ""),
            platforms=existing.platforms or tuple(str(item) for item in normalized.get("platforms", ())),
            franchise=existing.franchise or str(normalized.get("franchise") or ""),
             collection=existing.collection or str(normalized.get("collection") or ""),
             canonical_cover_url=existing.canonical_cover_url or str(normalized.get("cover_url") or ""),
             canonical_cover_width=existing.canonical_cover_width or normalized.get("cover_width"),
             canonical_cover_height=existing.canonical_cover_height or normalized.get("cover_height"),
            igdb_id=str(external_id) if provider == "igdb" else existing.igdb_id,
            igdb_fetched_at=fetched if provider == "igdb" else existing.igdb_fetched_at,
            protondb_tier=str(normalized.get("tier") or existing.protondb_tier) if provider == "protondb" else existing.protondb_tier,
            protondb_confidence=str(normalized.get("confidence") or existing.protondb_confidence) if provider == "protondb" else existing.protondb_confidence,
            protondb_score=float(normalized["score"]) if provider == "protondb" and normalized.get("score") is not None else existing.protondb_score,
            protondb_trending_tier=str(normalized.get("trending_tier") or existing.protondb_trending_tier) if provider == "protondb" else existing.protondb_trending_tier,
            protondb_best_tier=str(normalized.get("best_tier") or existing.protondb_best_tier) if provider == "protondb" else existing.protondb_best_tier,
            protondb_report_count=int(normalized["report_count"]) if provider == "protondb" and normalized.get("report_count") is not None else existing.protondb_report_count,
            protondb_fetched_at=fetched if provider == "protondb" else existing.protondb_fetched_at,
            protondb_rating=(str(normalized.get("tier")) if provider == "protondb" and normalized.get("tier") else existing.protondb_rating),
        )
        with self.atomic():
            self._start_operation()
            delta = self._apply_existing_locked(existing, after)
            self.connection.execute(
                "INSERT INTO metadata_enrichment(provider, game_id, external_id, fetched_at, source_updated_at, "
                "match_method, confidence, status, normalized_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(provider, game_id) DO UPDATE SET external_id=excluded.external_id, "
                "fetched_at=excluded.fetched_at, source_updated_at=excluded.source_updated_at, "
                "match_method=excluded.match_method, confidence=excluded.confidence, status=excluded.status, "
                "normalized_json=excluded.normalized_json",
                (provider, game_id, external_id, fetched, source_updated_at, match_method, confidence,
                status, json.dumps(normalized, sort_keys=True)),
            )
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

    def set_artwork_selection(self, game_id: str, *, url: str, source_url: str,
                              provider: str, artwork_type: str = "cover",
                              width: int | None = None, height: int | None = None) -> CatalogueDelta | None:
        existing = self.get_game(game_id)
        if existing is None:
            return None
        after = replace(existing, automatic_artwork_url=url, automatic_artwork_source_url=source_url,
                        automatic_artwork_provider=provider, automatic_artwork_type=artwork_type,
                        automatic_artwork_width=width, automatic_artwork_height=height)
        if not existing.artwork_override:
            after = replace(after, artwork_url=url, artwork_source_url=source_url,
                            artwork_provider=provider, artwork_type=artwork_type,
                            artwork_width=width, artwork_height=height)
        with self.atomic():
            self._start_operation()
            delta = self._apply_existing_locked(existing, after)
        self._finish_operation([delta] if delta else [])
        return delta

    def set_local_artwork(self, game_id: str, path: str) -> CatalogueDelta | None:
        existing = self.get_game(game_id)
        if existing is None:
            return None
        resolved = Path(path).resolve()
        try:
            version = resolved.stat().st_mtime_ns
        except OSError:
            version = 0
        after = replace(existing, local_artwork_path=str(resolved), local_artwork_mode="filesystem",
                        local_artwork_mtime=version, artwork_override=True, selected_artwork_source_url="",
                        artwork_url=f"{resolved.as_uri()}?v={version}",
                        artwork_source_url=existing.automatic_artwork_source_url or existing.artwork_source_url,
                        artwork_provider="local", artwork_type="cover")
        with self.atomic():
            self._start_operation()
            delta = self._apply_existing_locked(existing, after)
        self._finish_operation([delta] if delta else [])
        return delta

    def set_selected_artwork(self, game_id: str, path: str, source_url: str,
                             width: int | None = None, height: int | None = None) -> CatalogueDelta | None:
        existing = self.get_game(game_id)
        if existing is None:
            return None
        resolved = Path(path).resolve()
        try:
            version = resolved.stat().st_mtime_ns
        except OSError:
            version = 0
        after = replace(existing, local_artwork_path=str(resolved), local_artwork_mode="sgdb",
                        local_artwork_mtime=version, artwork_override=True,
                        selected_artwork_source_url=source_url,
                        artwork_url=f"{resolved.as_uri()}?v={version}",
                        artwork_source_url=source_url, artwork_provider="local", artwork_type="cover",
                        artwork_width=width, artwork_height=height)
        with self.atomic():
            self._start_operation()
            delta = self._apply_existing_locked(existing, after)
        self._finish_operation([delta] if delta else [])
        return delta

    def clear_local_artwork(self, game_id: str) -> CatalogueDelta | None:
        existing = self.get_game(game_id)
        if existing is None:
            return None
        after = replace(existing, local_artwork_path="", local_artwork_mode="", local_artwork_mtime=0, artwork_override=False,
                        selected_artwork_source_url="",
                        artwork_url=existing.automatic_artwork_url,
                        artwork_source_url=existing.automatic_artwork_source_url,
                        artwork_provider=existing.automatic_artwork_provider,
                        artwork_type=existing.automatic_artwork_type,
                        artwork_width=existing.automatic_artwork_width,
                        artwork_height=existing.automatic_artwork_height)
        with self.atomic():
            self._start_operation()
            delta = self._apply_existing_locked(existing, after)
        self._finish_operation([delta] if delta else [])
        return delta

    def restore_automatic_artwork(self, game_id: str, path: str) -> CatalogueDelta | None:
        """Keep the materialized automatic file while clearing SGDB selection."""
        existing = self.get_game(game_id)
        if existing is None:
            return None
        resolved = Path(path).resolve()
        try:
            version = resolved.stat().st_mtime_ns
        except OSError:
            version = 0
        after = replace(existing, local_artwork_path=str(resolved), local_artwork_mode="automatic",
                        local_artwork_mtime=version, artwork_override=False,
                        selected_artwork_source_url="",
                        artwork_url=f"{resolved.as_uri()}?v={version}",
                        artwork_source_url=existing.automatic_artwork_source_url,
                        artwork_provider="local", artwork_type="cover",
                        artwork_width=existing.automatic_artwork_width,
                        artwork_height=existing.automatic_artwork_height)
        with self.atomic():
            self._start_operation()
            delta = self._apply_existing_locked(existing, after)
        self._finish_operation([delta] if delta else [])
        return delta

    def sync_local_artwork_url(self, game_id: str, path: str) -> CatalogueDelta | None:
        existing = self.get_game(game_id)
        if existing is None:
            return None
        resolved = Path(path).resolve()
        try:
            version = resolved.stat().st_mtime_ns
        except OSError:
            version = existing.local_artwork_mtime
        after = replace(existing, local_artwork_path=str(resolved), local_artwork_mtime=version,
                        artwork_url=f"{resolved.as_uri()}?v={version}")
        with self.atomic():
            self._start_operation()
            delta = self._apply_existing_locked(existing, after)
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
