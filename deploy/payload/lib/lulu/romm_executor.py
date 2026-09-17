"""RomM-to-local-ROM acquisition adapter."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

from .emulation import PLATFORMS, ROM_ROOT, current_rom_root, ensure_storage
from .job_manager import JobExecutionError, JobReporter
from .jobs import DownloadJob, JobState
from .romm import RommApiError, RommClient, RommGame, RommFile


class RommExecutor:
    """Stream one RomM file to a staged canonical ROM path."""

    def __init__(self, client: RommClient | None, *, chunk_size: int = 1024 * 1024) -> None:
        self.client = client
        self.chunk_size = chunk_size

    def _resolve(self, identity: str) -> tuple[RommGame, RommFile]:
        if self.client is None:
            raise JobExecutionError("romm-unavailable", "RomM acquisition is not configured", retryable=True)
        try:
            rom_id = int(identity.removeprefix("romm:"))
        except (TypeError, ValueError) as error:
            raise JobExecutionError("invalid-content-identity", "RomM content identity is invalid") from error
        if rom_id < 1:
            raise JobExecutionError("invalid-content-identity", "RomM content identity is invalid")
        try:
            game = next(game for game in self.client.list_games() if game.rom_id == rom_id)
        except StopIteration as error:
            raise JobExecutionError("romm-content-missing", f"RomM ROM {rom_id} is unavailable", retryable=True) from error
        except RommApiError as error:
            raise JobExecutionError("romm-unavailable", str(error), retryable=True) from error
        if not game.files:
            raise JobExecutionError("romm-file-missing", f"RomM ROM {rom_id} has no downloadable file", retryable=True)
        return game, game.files[0]

    @staticmethod
    def _destination(game: RommGame, romm_file: RommFile) -> Path:
        definition = PLATFORMS.get(game.platform_slug.casefold())
        if definition is None:
            raise JobExecutionError(
                "unsupported-platform", f"RomM platform is unsupported: {game.platform_slug}"
            )
        filename = Path(romm_file.name).name
        if not filename or filename in {".", ".."} or filename != romm_file.name:
            raise JobExecutionError("invalid-filename", "RomM filename is unsafe")
        if Path(filename).suffix.casefold() not in {item.casefold() for item in definition.extensions}:
            raise JobExecutionError("unsupported-file", f"RomM file extension is unsupported: {filename}")
        # ROM_ROOT remains a compatibility seam for fixtures; production uses
        # the canonical policy value at process startup.
        root = Path(os.environ.get("LULU_ROM_ROOT", str(ROM_ROOT))).expanduser()
        return root / definition.platform_id / filename

    async def run(self, job: DownloadJob, reporter: JobReporter) -> None:
        await reporter.state(JobState.STARTING, stage="starting")
        game, romm_file = await asyncio.to_thread(self._resolve, job.content_identity)
        destination = self._destination(game, romm_file)
        ensure_storage()
        destination.parent.mkdir(parents=True, exist_ok=True)
        staging = destination.with_name(f".{destination.name}.{job.job_id}.part")
        stream = None
        try:
            stream = await asyncio.to_thread(self.client.open_file_stream, romm_file)  # type: ignore[union-attr]
            total_header = getattr(stream, "headers", {}).get("Content-Length") if hasattr(stream, "headers") else None
            try:
                total = int(total_header) if total_header is not None else None
            except (TypeError, ValueError):
                total = None
            downloaded = 0
            with staging.open("wb") as output:
                while True:
                    chunk = await asyncio.to_thread(stream.read, self.chunk_size)
                    if not chunk:
                        break
                    output.write(chunk)
                    downloaded += len(chunk)
                    progress = downloaded / total if total and total > 0 else None
                    await reporter.state(JobState.TRANSFERRING, stage="transferring")
                    await reporter.progress(progress, downloaded_bytes=downloaded, total_bytes=total,
                                            stage="transferring")
                output.flush()
                await asyncio.to_thread(os.fsync, output.fileno())
            await reporter.state(JobState.FINALIZING, stage="finalizing")
            await asyncio.to_thread(os.replace, staging, destination)
        except RommApiError as error:
            raise JobExecutionError("romm-failure", str(error), retryable=True) from error
        except OSError as error:
            raise JobExecutionError("local-storage-failure", str(error), retryable=True) from error
        finally:
            if stream is not None:
                await asyncio.to_thread(stream.close)
            try:
                staging.unlink(missing_ok=True)
            except OSError:
                pass
