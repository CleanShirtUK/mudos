"""Provider-owned removal of canonical local emulation content."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

from .catalogue import CatalogueStore
from .emulation import current_rom_root
from .job_manager import JobExecutionError, JobReporter
from .jobs import DownloadJob, JobState


class LocalUninstallExecutor:
    """Delete only an authoritative installed local game boundary."""

    def __init__(self, store: CatalogueStore, root: Path | None = None) -> None:
        self.store = store
        self.root = (root or current_rom_root()).expanduser()

    def _approved_path(self, game_id: str) -> Path:
        game = self.store.get_game(game_id)
        if game is None or game.provider != "local" or game.install_state != "installed":
            raise JobExecutionError("not-installed", "Local game is not installed")
        raw = Path(game.install_dir).expanduser()
        if not raw.is_absolute() or not str(raw).strip():
            raise JobExecutionError("invalid-install-path", "Local install path is invalid")
        root = self.root.resolve(strict=False)
        try:
            candidate = raw.resolve(strict=False)
            candidate.relative_to(root)
        except (OSError, ValueError) as error:
            raise JobExecutionError("unsafe-install-path", "Local install path is outside Mudos storage") from error
        # The platform directory is the immediate child of ROM_ROOT. A file
        # directly under ROM_ROOT and the platform directory itself are not
        # approved installed units.
        if candidate == root or candidate.parent == root:
            raise JobExecutionError("unsafe-install-path", "Refusing to remove a platform root")
        if not os.path.lexists(raw):
            return raw
        if raw.is_symlink() and candidate.parent == root:
            raise JobExecutionError("unsafe-install-path", "Symlink install path is not allowed")
        return raw

    async def run(self, job: DownloadJob, reporter: JobReporter) -> None:
        await reporter.state(JobState.STARTING, stage="removing")
        path = await asyncio.to_thread(self._approved_path, job.content_identity)
        try:
            if os.path.lexists(path):
                # resolve() above proves symlink targets remain within root;
                # rmtree/unlink therefore acts only on the authoritative unit.
                if path.is_dir() and not path.is_symlink():
                    import shutil
                    await asyncio.to_thread(shutil.rmtree, path)
                else:
                    await asyncio.to_thread(path.unlink)
            await reporter.state(JobState.FINALIZING, stage="finalizing")
        except PermissionError as error:
            raise JobExecutionError("permission-denied", "Local content could not be removed") from error
        except OSError as error:
            raise JobExecutionError("remove-failed", "Local content could not be removed", retryable=True) from error

    async def cancel(self, job: DownloadJob) -> None:
        return None
