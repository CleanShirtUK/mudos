"""Canonical, user-overwritable local assets for Library presentation media."""

from __future__ import annotations

import json
import hashlib
from pathlib import Path
import shutil
import subprocess
import time
import urllib.request

from .paths import PATHS

MAX_MEDIA_DOWNLOAD_BYTES = 64 * 1024 * 1024


def media_asset_path(game: object, role: str) -> Path:
    """Return a stable provider/game-ID path, outside provider install folders."""
    suffix = {"icon_square": ".png", "preview_still": ".jpg",
              "preview_animation": ".webp"}.get(role)
    if suffix is None:
        raise ValueError(f"unsupported media role: {role}")
    provider = "".join(c for c in str(getattr(game, "provider", "unknown")).lower()
                       if c.isalnum() or c in "-_") or "unknown"
    identity = str(getattr(game, "game_id", "game"))
    safe_id = "".join(c if c.isalnum() or c in "-_." else "_" for c in identity)
    return PATHS.data_root / "artwork" / provider / safe_id / f"{role}{suffix}"


class LocalMediaAssets:
    """Acquire role assets once; edits to their canonical files become overrides.

    This mirrors the card-art behavior: provider/game ID directories, stable
    named files, atomic writes, and mtime-based detection of user replacement.
    A small sidecar tracks automatic provenance without owning user files.
    """

    def __init__(self, *, timeout: float = 20.0, downloader=None,
                 ffmpeg: str | None = None) -> None:
        self.timeout = timeout
        self.downloader = downloader or self._download
        self.ffmpeg = ffmpeg or shutil.which("ffmpeg") or ""

    @staticmethod
    def _state_path(path: Path) -> Path:
        return path.parent / ".media-assets.json"

    def _read_state(self, path: Path) -> dict[str, object]:
        try:
            value = json.loads(self._state_path(path).read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else {}
        except (OSError, ValueError, TypeError):
            return {}

    def _write_state(self, path: Path, state: dict[str, object]) -> None:
        state_path = self._state_path(path)
        temporary = state_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(state, sort_keys=True), encoding="utf-8")
        temporary.replace(state_path)

    @staticmethod
    def _url(path: Path) -> str:
        return f"{path.as_uri()}?v={path.stat().st_mtime_ns}"

    def _backed_off(self, path: Path, source_url: str) -> bool:
        record = self._read_state(path).get(path.stem)
        return (isinstance(record, dict) and record.get("failure_source_url") == source_url
                and time.time() < float(record.get("retry_after", 0) or 0))

    def _existing(self, path: Path, source_url: str) -> str:
        if not path.is_file():
            return ""
        state = self._read_state(path)
        role = path.stem
        record = state.get(role)
        if not isinstance(record, dict):
            state[role] = {"override": True, "mtime_ns": path.stat().st_mtime_ns}
            self._write_state(path, state)
            return self._url(path)
        mtime = path.stat().st_mtime_ns
        if record.get("override") or int(record.get("mtime_ns", 0) or 0) != mtime:
            record["override"] = True
            record["mtime_ns"] = mtime
            self._write_state(path, state)
            return self._url(path)
        if record.get("source_url") == source_url:
            return self._url(path)
        if not record.get("automatic"):
            return self._url(path)
        return ""

    def present(self, game: object, role: str) -> str:
        """Return an acquired or manually replaced local role asset, if any."""
        path = media_asset_path(game, role)
        if not path.is_file():
            return ""
        state = self._read_state(path)
        record = state.get(path.stem)
        mtime = path.stat().st_mtime_ns
        if not isinstance(record, dict):
            state[path.stem] = {"override": True, "mtime_ns": mtime}
            self._write_state(path, state)
        elif record.get("override") or int(record.get("mtime_ns", 0) or 0) != mtime:
            record["override"] = True
            record["mtime_ns"] = mtime
            self._write_state(path, state)
        return self._url(path)

    def is_override(self, game: object, role: str) -> bool:
        path = media_asset_path(game, role)
        if not path.is_file():
            return False
        record = self._read_state(path).get(path.stem)
        if not isinstance(record, dict):
            return True
        return (bool(record.get("override"))
                or int(record.get("mtime_ns", 0) or 0) != path.stat().st_mtime_ns)

    def install_override(self, game: object, role: str, source_url: str) -> str:
        """Install an explicitly selected integrated candidate as the active override."""
        path = media_asset_path(game, role)
        acquired = self.acquire_image(game, role, source_url, force=True)
        if not acquired:
            return ""
        state = self._read_state(path)
        state[path.stem] = {"automatic": False, "override": True,
                            "source_url": source_url, "mtime_ns": path.stat().st_mtime_ns}
        self._write_state(path, state)
        return self._url(path)

    def acquire_image(self, game: object, role: str, source_url: str, *, force: bool = False) -> str:
        if not source_url:
            return ""
        path = media_asset_path(game, role)
        if not force and self._backed_off(path, source_url):
            return self.present(game, role)
        existing = "" if force else self._existing(path, source_url)
        if existing:
            return existing
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(path.stem + ".part" + path.suffix)
        try:
            self.downloader(source_url, temporary, self.timeout)
            if not temporary.is_file() or temporary.stat().st_size == 0:
                raise OSError("empty image response")
            # Normalize the image once to a stable local file. Preserve alpha
            # for square icons, which commonly contain transparent borders.
            from PIL import Image
            with Image.open(temporary) as image:
                image.verify()
            with Image.open(temporary) as image:
                if role == "icon_square":
                    normalized = temporary.with_suffix(".normalized.png")
                    image.convert("RGBA").save(normalized, format="PNG", optimize=True)
                else:
                    normalized = temporary.with_suffix(".normalized.jpg")
                    image.convert("RGB").save(normalized, format="JPEG", quality=92)
            normalized.replace(path)
            temporary.unlink(missing_ok=True)
            state = self._read_state(path)
            state[path.stem] = {"automatic": True, "override": False,
                                "source_url": source_url,
                                "mtime_ns": path.stat().st_mtime_ns}
            self._write_state(path, state)
            return self._url(path)
        except Exception:
            temporary.unlink(missing_ok=True)
            temporary.with_suffix(".normalized.jpg").unlink(missing_ok=True)
            temporary.with_suffix(".normalized.png").unlink(missing_ok=True)
            state = self._read_state(path)
            old = state.get(path.stem, {})
            old = dict(old) if isinstance(old, dict) else {}
            old.update({"failure_source_url": source_url,
                        "retry_after": int(time.time()) + 86400})
            state[path.stem] = old
            try:
                self._write_state(path, state)
            except OSError:
                pass
            # A failed refresh never removes an already presented local asset.
            return "" if force else (self._url(path) if path.is_file() else "")

    def acquire_animation(self, game: object, source_url: str) -> str:
        if not source_url:
            return ""
        path = media_asset_path(game, "preview_animation")
        if self._backed_off(path, source_url):
            return self.present(game, "preview_animation")
        existing = self._existing(path, source_url)
        if existing:
            return existing
        provider_id = str(getattr(game, "provider_id", ""))
        cache_key = hashlib.sha256(
            "\0".join((str(getattr(game, "provider", "steam")).lower(),
                       provider_id, source_url.strip())).encode("utf-8")).hexdigest()
        legacy = PATHS.cache_home / "lulu" / "media-previews" / "steam" \
            / f"{provider_id}-{cache_key}.webp"
        if legacy.is_file():
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary_copy = path.with_name("preview_animation.migrate.part.webp")
            shutil.copyfile(legacy, temporary_copy)
            if temporary_copy.read_bytes()[:4] == b"RIFF":
                temporary_copy.replace(path)
                state = self._read_state(path)
                state[path.stem] = {"automatic": True, "override": False,
                                    "source_url": source_url,
                                    "generation": "webp-800x450-12fps-q75-v1",
                                    "mtime_ns": path.stat().st_mtime_ns}
                self._write_state(path, state)
                return self._url(path)
            temporary_copy.unlink(missing_ok=True)
        if not self.ffmpeg:
            return self._url(path) if path.is_file() else ""
        path.parent.mkdir(parents=True, exist_ok=True)
        source = path.with_name("preview_animation.source.part.webm")
        output = path.with_name("preview_animation.part.webp")
        try:
            self.downloader(source_url, source, self.timeout)
            if not source.is_file() or source.stat().st_size == 0:
                raise OSError("empty video response")
            nice = shutil.which("nice")
            command = ([nice, "-n", "10", self.ffmpeg] if nice else [self.ffmpeg])
            result = subprocess.run(
                [*command, "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
                 "-hwaccel", "none", "-i", str(source), "-t", "6", "-vf",
                 "fps=12,scale=800:450:force_original_aspect_ratio=increase:flags=lanczos,"
                 "crop=800:450", "-an", "-loop", "0",
                 "-c:v", "libwebp_anim", "-quality", "75", "-compression_level", "4",
                 "-f", "webp", str(output)],
                capture_output=True, timeout=90, check=False,
            )
            if result.returncode or not output.is_file() or not output.stat().st_size:
                raise RuntimeError("animated WebP transcode failed")
            output.replace(path)
            state = self._read_state(path)
            state[path.stem] = {"automatic": True, "override": False,
                                "source_url": source_url,
                                "generation": "webp-800x450-12fps-q75-v1",
                                "mtime_ns": path.stat().st_mtime_ns}
            self._write_state(path, state)
            return self._url(path)
        except Exception:
            output.unlink(missing_ok=True)
            state = self._read_state(path)
            old = state.get(path.stem, {})
            old = dict(old) if isinstance(old, dict) else {}
            old.update({"failure_source_url": source_url,
                        "retry_after": int(time.time()) + 86400})
            state[path.stem] = old
            try:
                self._write_state(path, state)
            except OSError:
                pass
            return self._url(path) if path.is_file() else ""
        finally:
            source.unlink(missing_ok=True)

    def remove_automatic(self, game: object, role: str) -> None:
        path = media_asset_path(game, role)
        state = self._read_state(path)
        record = state.get(path.stem)
        if not path.is_file() or not isinstance(record, dict) or not record.get("automatic"):
            return
        if record.get("override") or int(record.get("mtime_ns", 0) or 0) != path.stat().st_mtime_ns:
            return
        path.unlink(missing_ok=True)
        state.pop(path.stem, None)
        self._write_state(path, state)

    @staticmethod
    def _download(url: str, destination: Path, timeout: float) -> None:
        request = urllib.request.Request(url, headers={"User-Agent": "Lulu/1"})
        with urllib.request.urlopen(request, timeout=timeout) as response, destination.open("wb") as output:
            total = 0
            while True:
                block = response.read(1024 * 1024)
                if not block:
                    break
                total += len(block)
                if total > MAX_MEDIA_DOWNLOAD_BYTES:
                    raise OSError("media source exceeded the acquisition size limit")
                output.write(block)
