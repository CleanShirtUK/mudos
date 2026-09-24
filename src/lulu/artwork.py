"""Optional artwork enrichment behind the catalogue boundary."""

from dataclasses import dataclass, field
import hashlib
import json
import logging
from pathlib import Path
import urllib.error
import urllib.parse
import urllib.request
import shutil
import re
import time
from threading import Lock

from .paths import PATHS
from .provider_config import ProviderConfigurationService


IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}


def local_artwork_path(game: object) -> Path:
    """Return the stable, user-visible artwork path for a catalogue record."""
    provider = str(getattr(game, "provider", ""))
    install_dir = Path(str(getattr(game, "install_dir", "") or "")).expanduser()
    game_id = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(getattr(game, "game_id", "game")))
    if provider == "flatpak":
        return PATHS.data_root / "artwork" / "flatpak" / game_id / "cover.jpg"
    if provider == "romm":
        return PATHS.data_root / "artwork" / "romm" / game_id / "cover.jpg"
    if install_dir.is_file():
        return install_dir.with_name(install_dir.name + ".cover.jpg")
    if install_dir:
        return install_dir / "cover.jpg"
    return PATHS.data_root / "artwork" / provider / game_id / "cover.jpg"


def materialize_artwork(source_url: str, destination: Path, *, overwrite: bool = False) -> bool:
    """Materialize a decoded image once, without replacing user files."""
    if destination.exists() and not overwrite:
        return True
    if not source_url:
        return destination.exists()
    parsed = urllib.parse.urlparse(source_url)
    source = Path(urllib.request.url2pathname(parsed.path)) if parsed.scheme == "file" else None
    if source is None or not source.exists():
        return False
    try:
        from PIL import Image
        with Image.open(source) as image:
            image.verify()
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_suffix(".tmp")
        with Image.open(source) as image:
            image.convert("RGB").save(temporary, format="JPEG", quality=94)
        temporary.replace(destination)
        return True
    except (OSError, ValueError):
        return False


@dataclass(frozen=True, slots=True)
class ArtworkSelection:
    url: str
    source_url: str
    provider: str
    artwork_type: str
    width: int | None = None
    height: int | None = None


@dataclass(slots=True)
class LocalArtworkCache:
    """Persistent, best-effort cache for provider artwork assets."""

    cache_dir: Path | None = None
    timeout: float = 8.0
    downloader: object | None = None

    def __post_init__(self) -> None:
        self.cache_dir = self.cache_dir or PATHS.romm_artwork_cache

    def cache_remote(self, identity: str, url: str) -> str:
        if not url:
            return ""
        digest = hashlib.sha256(identity.encode()).hexdigest()
        image = self.cache_dir / f"{digest}.img"
        state = self.cache_dir / f"{digest}.json"
        try:
            previous = json.loads(state.read_text()) if state.exists() else {}
            if image.exists() and previous.get("url") == url:
                return image.as_uri()
            if self.downloader is not None:
                payload = self.downloader(url)
            else:
                request = urllib.request.Request(url, headers={"User-Agent": "Mudos/romm"})
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    payload = response.read()
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            temporary = image.with_suffix(".tmp")
            temporary.write_bytes(payload)
            temporary.replace(image)
            state.write_text(json.dumps({"url": url}, sort_keys=True))
            return image.as_uri()
        except (OSError, ValueError, urllib.error.URLError, TimeoutError):
            return image.as_uri() if image.exists() else ""


@dataclass(slots=True)
class SteamGridDBArtwork:
    api_key: str | None = None
    cache_dir: Path | None = None
    timeout: float = 4.0
    _logger: logging.Logger = field(init=False, repr=False)
    endpoint: str = field(init=False, repr=False)
    _request_lock: Lock = field(init=False, repr=False)
    _last_request_at: float = field(init=False, default=0.0, repr=False)

    def __post_init__(self) -> None:
        self.reload_configuration()
        self.cache_dir = self.cache_dir or PATHS.artwork_cache
        self._logger = logging.getLogger("lulu.artwork")
        self._request_lock = Lock()

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    def reload_configuration(self) -> None:
        config = ProviderConfigurationService.from_environment().provider("metadata.steamgriddb")
        if config.configured:
            self.api_key = config.secret("api_key")
        elif self.api_key is None:
            self.api_key = None
        self.endpoint = str(config.get("endpoint", "https://www.steamgriddb.com/api")).rstrip("/")

    def test_connection(self) -> str:
        self.reload_configuration()
        if not self.configured:
            return "incomplete"
        self._request_json("/v2/search/autocomplete/SuperTux")
        return "connected"

    def enrich(self, games: list[object]) -> dict[str, str]:
        if not self.api_key:
            return {}
        resolved: dict[str, str] = {}
        for game in games:
            if bool(getattr(game, "artwork_suppressed", False)):
                continue
            game_id = str(getattr(game, "game_id"))
            artwork = self._resolve(
                game_id, str(getattr(game, "provider")),
                str(getattr(game, "provider_id")), str(getattr(game, "title")),
                str(getattr(game, "metadata_provider", "")),
                str(getattr(game, "metadata_game_id", "")),
            )
            if artwork:
                resolved[game_id] = artwork
        return resolved

    def resolve_typed(self, game: object) -> ArtworkSelection | None:
        """Resolve a cover without collapsing icons and arbitrary images into it."""
        self.reload_configuration()
        if bool(getattr(game, "artwork_suppressed", False)):
            return None
        existing_url = str(getattr(game, "artwork_url", "") or "")
        existing_type = str(getattr(game, "artwork_type", "") or "")
        existing_provider = str(getattr(game, "artwork_provider", "") or "")
        if existing_url and existing_type == "icon":
            existing_url = ""
        # Existing validated/legacy SGDB covers remain usable during migration.
        legacy_selection = None
        if existing_url and existing_type == "cover" and existing_provider == "steamgriddb":
            legacy_selection = ArtworkSelection(
                existing_url, str(getattr(game, "artwork_source_url", "") or ""),
                "steamgriddb", "cover", getattr(game, "artwork_width", None),
                getattr(game, "artwork_height", None))
        provider = str(getattr(game, "provider", ""))
        provider_id = str(getattr(game, "provider_id", ""))
        canonical_title = str(getattr(game, "canonical_title", "") or getattr(game, "title", ""))
        igdb_id = str(getattr(game, "metadata_game_id", "")) if \
            str(getattr(game, "metadata_provider", "")) == "igdb" else ""
        image_url = ""
        if self.api_key and igdb_id:
            image_url = self._find_canonical_image(canonical_title, igdb_id)
        elif self.api_key and provider == "steam" and provider_id.isdecimal():
            image_url = self._find_image("steam", provider_id, canonical_title)
        if image_url:
            key = hashlib.sha256(f"sgdb-cover:{igdb_id or provider_id}:{image_url}".encode()).hexdigest()
            image_path = self.cache_dir / f"{key}.jpg"
            if not image_path.exists():
                self._download(image_url, image_path)
            if image_path.exists():
                return ArtworkSelection(image_path.as_uri(), image_url, "steamgriddb", "cover")
        canonical_cover = str(getattr(game, "canonical_cover_url", "") or "")
        if canonical_cover:
            key = hashlib.sha256(f"igdb-cover:{igdb_id}:{canonical_cover}".encode()).hexdigest()
            image_path = self.cache_dir / f"{key}.jpg"
            if not image_path.exists():
                self._download(canonical_cover, image_path)
            if image_path.exists():
                return ArtworkSelection(
                    image_path.as_uri(), canonical_cover, "igdb", "cover",
                    getattr(game, "canonical_cover_width", None),
                    getattr(game, "canonical_cover_height", None),
                )
        if existing_url and existing_type == "cover":
            return ArtworkSelection(existing_url, str(getattr(game, "artwork_source_url", "") or existing_url),
                                    existing_provider or provider, "cover",
                                    getattr(game, "artwork_width", None), getattr(game, "artwork_height", None))
        return legacy_selection

    def resolve_square_icon(self, game: object) -> ArtworkSelection | None:
        """Resolve a stable square list icon, independently of cover artwork."""
        if bool(getattr(game, "artwork_suppressed", False)):
            return None
        self.reload_configuration()
        game_id = str(getattr(game, "game_id", ""))
        existing_url = str(getattr(game, "icon_square_url", "") or "")
        existing_provider = str(getattr(game, "icon_square_provider", "") or "")
        existing_source = str(getattr(game, "icon_square_source_url", "") or existing_url)
        if existing_url and existing_provider == "steamgriddb":
            return ArtworkSelection(existing_url, existing_source, existing_provider, "icon")

        provider = str(getattr(game, "provider", ""))
        provider_id = str(getattr(game, "provider_id", ""))
        title = str(getattr(game, "canonical_title", "") or getattr(game, "title", ""))
        sgdb_game_id = ""
        endpoints: list[tuple[str, str]] = []
        if (self.api_key and str(getattr(game, "metadata_provider", "")) == "igdb"
              and str(getattr(game, "metadata_game_id", ""))):
            sgdb_game_id = self._search_sgdb_game_id(
                title, str(getattr(game, "metadata_game_id")))
            if sgdb_game_id:
                endpoints = [(f"/v2/grids/game/{sgdb_game_id}", "grid"),
                             (f"/v2/icons/game/{sgdb_game_id}", "icon")]
        elif self.api_key and provider == "steam" and provider_id.isdecimal():
            sgdb_game_id = provider_id
            endpoints = [(f"/v2/grids/steam/{provider_id}", "grid"),
                         (f"/v2/icons/steam/{provider_id}", "icon")]

        if sgdb_game_id:
            cache_key = hashlib.sha256(f"sgdb-square:{sgdb_game_id}".encode()).hexdigest()
            cache_path = self.cache_dir / f"{cache_key}.json"
            cached: dict[str, object] = {}
            try:
                cached = json.loads(cache_path.read_text()) if cache_path.exists() else {}
                if cached.get("checked_at", 0) and time.time() - float(cached["checked_at"]) < 30 * 86400:
                    cached_url = str(cached.get("url", ""))
                    if cached_url:
                        return ArtworkSelection(cached_url, cached_url, "steamgriddb", "icon")
                    endpoints = []
            except (OSError, ValueError, TypeError):
                pass
            selected = ""
            for endpoint, role in endpoints:
                try:
                    data = self._request_json(endpoint).get("data", [])
                except (OSError, ValueError, urllib.error.URLError, TimeoutError):
                    continue
                selected = self._choose_square_asset(data) if role == "grid" else self._choose_icon_asset(data)
                if selected:
                    break
            try:
                self._write_json(cache_path, {"checked_at": time.time(), "url": selected})
            except OSError:
                pass
            if selected:
                return ArtworkSelection(selected, selected, "steamgriddb", "icon")

        if existing_url:
            return ArtworkSelection(existing_url, existing_source,
                                    existing_provider or "native", "icon")
        fallback = str(getattr(game, "icon_url", "") or "")
        if fallback:
            return ArtworkSelection(fallback, fallback,
                                    str(getattr(game, "provider", "native")), "icon")
        return None

    def _search_sgdb_game_id(self, title: str, igdb_id: str) -> str:
        key = hashlib.sha256(f"sgdb-game-id:{igdb_id}:{title.casefold()}".encode()).hexdigest()
        path = self.cache_dir / f"{key}.json"
        try:
            state = json.loads(path.read_text()) if path.exists() else {}
            if state.get("igdb_id") == igdb_id and time.time() - float(state.get("checked_at", 0)) < 30 * 86400:
                return str(state.get("game_id", ""))
        except (OSError, ValueError, TypeError):
            pass
        game_id = ""
        try:
            escaped = urllib.parse.quote(title, safe="")
            candidates = self._request_json(f"/v2/search/autocomplete/{escaped}").get("data", [])
            key_title = re.sub(r"[^a-z0-9]+", "", title.casefold())
            ranked: set[str] = set()
            for item in candidates if isinstance(candidates, list) else []:
                if not isinstance(item, dict) or not item.get("id"):
                    continue
                name_key = re.sub(r"[^a-z0-9]+", "", str(item.get("name", "")).casefold())
                if name_key == key_title:
                    ranked.add(str(item["id"]))
            game_id = next(iter(ranked)) if len(ranked) == 1 else ""
        except (OSError, ValueError, urllib.error.URLError, TimeoutError):
            return ""
        try:
            self._write_json(path, {"igdb_id": igdb_id, "checked_at": time.time(), "game_id": game_id})
        except OSError:
            pass
        return game_id

    @staticmethod
    def _choose_square_asset(items: object) -> str:
        if not isinstance(items, list):
            return ""
        ranked: list[tuple[float, str]] = []
        for item in items:
            if not isinstance(item, dict) or not item.get("url"):
                continue
            try:
                width, height = int(item.get("width", 0) or 0), int(item.get("height", 0) or 0)
            except (TypeError, ValueError):
                continue
            if width < 256 or height < 256 or not 0.85 <= width / height <= 1.15:
                continue
            ranked.append((min(width, height) - abs(width - height), str(item["url"])))
        return max(ranked, default=(0, ""))[1]

    @staticmethod
    def _choose_icon_asset(items: object) -> str:
        if not isinstance(items, list):
            return ""
        ranked: list[tuple[int, str]] = []
        for item in items:
            if not isinstance(item, dict) or not item.get("url"):
                continue
            try:
                width, height = int(item.get("width", 0) or 0), int(item.get("height", 0) or 0)
            except (TypeError, ValueError):
                width = height = 0
            if width and height and not 0.7 <= width / height <= 1.3:
                continue
            ranked.append((width * height, str(item["url"])))
        return max(ranked, default=(0, ""))[1]

    def square_gallery(self, game: object) -> list[dict[str, object]]:
        """Return only near-square SGDB grid/icon candidates for list artwork."""
        self.reload_configuration()
        if not self.api_key or bool(getattr(game, "artwork_suppressed", False)):
            return []
        provider = str(getattr(game, "provider", ""))
        provider_id = str(getattr(game, "provider_id", ""))
        if (str(getattr(game, "metadata_provider", "")) == "igdb"
              and str(getattr(game, "metadata_game_id", ""))):
            sgdb_id = self._find_canonical_game_id(
                str(getattr(game, "canonical_title", "") or getattr(game, "title", "")),
                str(getattr(game, "metadata_game_id")))
            if not sgdb_id:
                return []
            endpoints = (f"/v2/grids/game/{sgdb_id}", f"/v2/icons/game/{sgdb_id}")
        elif provider == "steam" and provider_id.isdecimal():
            endpoints = (f"/v2/grids/steam/{provider_id}", f"/v2/icons/steam/{provider_id}")
        else:
            return []
        current = str(getattr(game, "icon_square_source_url", "") or "")
        candidates: list[dict[str, object]] = []
        seen: set[str] = set()
        for endpoint in endpoints:
            try:
                rows = self._request_json(endpoint).get("data", [])
            except (OSError, ValueError, urllib.error.URLError, TimeoutError):
                continue
            if not isinstance(rows, list):
                continue
            for item in rows:
                if not isinstance(item, dict) or not item.get("url"):
                    continue
                try:
                    width, height = int(item.get("width", 0) or 0), int(item.get("height", 0) or 0)
                except (TypeError, ValueError):
                    continue
                if width < 128 or height < 128 or not 0.85 <= width / height <= 1.15:
                    continue
                url = str(item["url"])
                if url in seen:
                    continue
                seen.add(url)
                candidates.append({"id": str(item.get("id", url)), "url": url,
                                   "thumbnail": str(item.get("thumb", "") or url),
                                   "width": width, "height": height,
                                   "provider": "steamgriddb", "current": url == current})
        return candidates

    def resolve_landscape(self, game: object) -> str:
        """Resolve an SGDB hero image independently from portrait cover art."""
        existing = str(getattr(game, "landscape_artwork_url", "") or "")
        if existing:
            return existing
        self.reload_configuration()
        if not self.api_key or bool(getattr(game, "artwork_suppressed", False)):
            return ""
        provider = str(getattr(game, "provider", ""))
        provider_id = str(getattr(game, "provider_id", ""))
        if provider == "steam" and provider_id.isdecimal():
            endpoint = f"/v2/heroes/steam/{provider_id}"
        elif (str(getattr(game, "metadata_provider", "")) == "steamgriddb"
              and str(getattr(game, "metadata_game_id", "")).isdecimal()):
            endpoint = f"/v2/heroes/game/{getattr(game, 'metadata_game_id')}"
        elif str(getattr(game, "metadata_provider", "")) == "igdb" and str(
                getattr(game, "metadata_game_id", "")):
            sgdb_id = self._find_canonical_game_id(
                str(getattr(game, "canonical_title", "") or getattr(game, "title", "")),
                str(getattr(game, "metadata_game_id")))
            if not sgdb_id:
                return ""
            endpoint = f"/v2/heroes/game/{sgdb_id}"
        else:
            return ""
        cache_key = hashlib.sha256(f"sgdb-landscape:{endpoint}".encode()).hexdigest()
        cache_path = self.cache_dir / f"{cache_key}.json"
        try:
            cached = json.loads(cache_path.read_text()) if cache_path.exists() else {}
            if (isinstance(cached, dict) and cached.get("endpoint") == endpoint
                    and time.time() - float(cached.get("checked_at", 0)) < 86400):
                return str(cached.get("url", ""))
        except (OSError, ValueError, TypeError):
            pass
        result = self._request_json(endpoint)
        items = result.get("data", []) if isinstance(result, dict) else []
        ranked: list[tuple[float, str]] = []
        if not isinstance(items, list):
            return ""
        for item in items:
            if not isinstance(item, dict) or not item.get("url"):
                continue
            try:
                width, height = int(item.get("width", 0) or 0), int(item.get("height", 0) or 0)
            except (TypeError, ValueError):
                continue
            if width < 600 or height <= 0 or width / height < 1.4:
                continue
            ratio = width / height
            ranked.append((abs(ratio - 2.4), str(item["url"])))
        selected = min(ranked)[1] if ranked else ""
        try:
            self._write_json(cache_path, {"endpoint": endpoint, "checked_at": time.time(),
                                          "url": selected})
        except OSError:
            pass
        return selected

    def gallery(self, game: object) -> list[dict[str, object]]:
        """Return validated portrait grids for an established IGDB identity."""
        igdb_id = str(getattr(game, "metadata_game_id", "") or "")
        if str(getattr(game, "metadata_provider", "")) != "igdb" or not igdb_id:
            return []
        title = str(getattr(game, "canonical_title", "") or getattr(game, "title", ""))
        sgdb_id = self._find_canonical_game_id(title, igdb_id)
        if not sgdb_id:
            return []
        result = self._request_json(f"/v2/grids/game/{sgdb_id}")
        current = str(getattr(game, "automatic_artwork_source_url", "") or "")
        selected = str(getattr(game, "selected_artwork_source_url", "") or "")
        candidates = []
        for item in result.get("data", []) if isinstance(result, dict) else []:
            if not isinstance(item, dict) or not self._valid_portrait(item):
                continue
            url = str(item.get("url", ""))
            if not url:
                continue
            candidates.append({
                "id": str(item.get("id", "")), "url": url,
                "thumbnail": str(item.get("thumb", "") or item.get("url", "")),
                "width": int(item.get("width", 0) or 0),
                "height": int(item.get("height", 0) or 0),
                "provider": "steamgriddb", "source": "SteamGridDB",
                "title": "SteamGridDB card artwork",
                "current": url == current or url == selected,
            })
        return candidates

    def select_gallery_artwork(self, game: object, source_url: str) -> tuple[Path, str, int, int] | None:
        """Download and validate one candidate, returning its cached image."""
        candidate = next((item for item in self.gallery(game) if item["url"] == source_url), None)
        if candidate is None:
            return None
        key = hashlib.sha256(f"sgdb-selected:{source_url}".encode()).hexdigest()
        image_path = self.cache_dir / f"{key}.jpg"
        if not image_path.exists():
            self._download(source_url, image_path)
        if not image_path.exists():
            return None
        return image_path, source_url, int(candidate["width"]), int(candidate["height"])

    def _resolve(self, game_id: str, provider: str, provider_id: str, title: str,
                 metadata_provider: str = "", metadata_game_id: str = "") -> str:
        identity = f"{metadata_provider}:{metadata_game_id}" if metadata_provider and metadata_game_id else game_id
        key = hashlib.sha256(identity.encode()).hexdigest()
        metadata_path = self.cache_dir / f"{key}.json"
        try:
            metadata = json.loads(metadata_path.read_text()) if metadata_path.exists() else {}
            image_url = str(metadata.get("image_url", ""))
            if not image_url:
                image_url = self._find_image(provider, provider_id, title, metadata_provider, metadata_game_id)
                self._write_json(metadata_path, {"image_url": image_url, "identity": identity})
            if not image_url:
                return ""
            image_path = self.cache_dir / f"{key}.jpg"
            if not image_path.exists():
                self._download(image_url, image_path)
            return image_path.as_uri() if image_path.exists() else ""
        except (OSError, ValueError, urllib.error.URLError, TimeoutError) as error:
            self._logger.warning("artwork enrichment failed for %s: %s", game_id, error)
            return ""

    def _find_image(self, provider: str, provider_id: str, title: str,
                    metadata_provider: str = "", metadata_game_id: str = "") -> str:
        if metadata_provider == "igdb" and metadata_game_id:
            return self._find_canonical_image(title, metadata_game_id)
        if metadata_provider == "steamgriddb" and metadata_game_id:
            path = f"/v2/grids/game/{metadata_game_id}"
        elif provider == "steam" and provider_id.isdecimal():
            path = f"/v2/grids/steam/{provider_id}"
        else:
            return ""
        result = self._request_json(path + "?dimensions=600x900")
        return self._choose_cover(result.get("data", []))

    def _find_canonical_image(self, title: str, igdb_id: str) -> str:
        # SGDB has no universal IGDB foreign-key endpoint. Resolve the SGDB
        # identity from the canonical IGDB title, then validate its grids.
        identity = hashlib.sha256(f"sgdb-identity:{igdb_id}:{title.casefold()}".encode()).hexdigest()
        state_path = self.cache_dir / f"{identity}.json"
        try:
            state = json.loads(state_path.read_text()) if state_path.exists() else None
            if isinstance(state, dict) and state.get("identity") == f"igdb:{igdb_id}" and state.get("sgdb_game_id"):
                return str(state.get("image_url", ""))
        except (OSError, ValueError, TypeError):
            pass
        escaped = urllib.parse.quote(title, safe="")
        result = self._request_json(f"/v2/search/autocomplete/{escaped}")
        candidates = [item for item in result.get("data", []) if isinstance(item, dict)]
        normalized = " ".join(title.casefold().split())
        candidates.sort(key=lambda item: 0 if " ".join(str(item.get("name", "")).casefold().split()) == normalized else 1)
        for candidate in candidates[:5]:
            game_id = str(candidate.get("id", ""))
            if not game_id:
                continue
            grids = self._request_json(f"/v2/grids/game/{game_id}?dimensions=600x900")
            selected = self._choose_cover(grids.get("data", []))
            if selected:
                self._write_json(state_path, {"identity": f"igdb:{igdb_id}",
                                               "sgdb_game_id": game_id, "image_url": selected})
                return selected
        self._write_json(state_path, {"identity": f"igdb:{igdb_id}", "image_url": ""})
        return ""

    def _find_canonical_game_id(self, title: str, igdb_id: str) -> str:
        identity = hashlib.sha256(f"sgdb-identity:{igdb_id}:{title.casefold()}".encode()).hexdigest()
        state_path = self.cache_dir / f"{identity}.json"
        try:
            state = json.loads(state_path.read_text()) if state_path.exists() else {}
            if isinstance(state, dict) and state.get("identity") == f"igdb:{igdb_id}" and state.get("sgdb_game_id"):
                return str(state["sgdb_game_id"])
        except (OSError, ValueError, TypeError):
            pass
        self._find_canonical_image(title, igdb_id)
        try:
            state = json.loads(state_path.read_text())
            return str(state.get("sgdb_game_id", ""))
        except (OSError, ValueError, TypeError):
            return ""

    @staticmethod
    def _valid_portrait(item: dict[str, object]) -> bool:
        try:
            width, height = int(item.get("width", 0) or 0), int(item.get("height", 0) or 0)
        except (TypeError, ValueError):
            return False
        if not width or not height or height < 500:
            return False
        ratio = width / height
        return 0.52 <= ratio <= 0.78

    @staticmethod
    def _choose_cover(items: object) -> str:
        if not isinstance(items, list):
            return ""
        ranked: list[tuple[int, str]] = []
        for item in items:
            if not isinstance(item, dict) or not item.get("url"):
                continue
            try:
                width = int(item.get("width", 0) or 0)
                height = int(item.get("height", 0) or 0)
            except (TypeError, ValueError):
                width = height = 0
            # When dimensions are supplied, reject square/wide assets. Older
            # SGDB responses omit them, so those remain eligible but rank last.
            if width and height:
                ratio = width / height
                if ratio < 0.52 or ratio > 0.78 or height < 500:
                    continue
                score = 1000 - abs(width / height - 2 / 3) * 1000 + min(height, 900) / 10
            else:
                score = 1
            ranked.append((int(score), str(item["url"])))
        return max(ranked, default=(0, ""))[1]

    def _request_json(self, path: str) -> dict[str, object]:
        # SteamGridDB's public API is rate limited. Backfill is intentionally
        # serial and capped at one request per second per client instance.
        with self._request_lock:
            wait = 1.0 - (time.monotonic() - self._last_request_at)
            if wait > 0:
                time.sleep(wait)
            self._last_request_at = time.monotonic()
        request = urllib.request.Request(
            self.endpoint + path,
            headers={"Authorization": f"Bearer {self.api_key}", "User-Agent": "Lulu/1"},
        )
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            return json.loads(response.read())

    def _download(self, url: str, destination: Path) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        request = urllib.request.Request(url, headers={"User-Agent": "Lulu/1"})
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            data = response.read()
        temporary = destination.with_suffix(".tmp")
        temporary.write_bytes(data)
        temporary.replace(destination)

    @staticmethod
    def _write_json(path: Path, value: dict[str, object]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(value, sort_keys=True))
        temporary.replace(path)
