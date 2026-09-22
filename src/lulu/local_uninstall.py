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

    async def uninstall(self, game_id: str) -> None:
        """Capability marker for Acquisitiond's normal remove boundary."""
        return None

    def _approved_paths(self, game_id: str) -> tuple[Path, ...]:
        game = self.store.get_game(game_id)
        if game is None or game.provider != "local" or game.install_state != "installed":
            raise JobExecutionError("not-installed", "Local game is not installed")
        root = self.root.resolve(strict=False)
        values = (tuple(game.component_paths)
                  if game.platform.casefold() == "switch" and game.component_paths
                  else (game.install_dir,))
        approved: list[Path] = []
        for value in values:
            raw = Path(value).expanduser()
            if not raw.is_absolute() or not str(raw).strip():
                raise JobExecutionError("invalid-install-path", "Local install path is invalid")
            try:
                candidate = raw.resolve(strict=False)
                candidate.relative_to(root)
            except (OSError, ValueError) as error:
                raise JobExecutionError("unsafe-install-path", "Local install path is outside Mudos storage") from error
            # Only canonical platform files are Mudos-owned; staging, Eden
            # NAND, saves, and shader/cache state are outside this boundary.
            if candidate == root or (candidate.parent != root / game.platform
                                     and not (raw.is_dir() and game.platform.casefold() != "switch")):
                raise JobExecutionError("unsafe-install-path", "Component is outside the canonical install boundary")
            if raw.is_symlink():
                raise JobExecutionError("unsafe-install-path", "Symlink install path is not owned")
            approved.append(raw)
        if len(set(approved)) != len(approved):
            raise JobExecutionError("ambiguous-install-set", "Duplicate component path")
        return tuple(approved)

    # Compatibility seam for callers/tests that validate a single legacy path.
    def _approved_path(self, game_id: str) -> Path:
        paths = self._approved_paths(game_id)
        if len(paths) != 1:
            raise JobExecutionError("ambiguous-install-set", "Game has multiple installed components")
        return paths[0]

    async def run(self, job: DownloadJob, reporter: JobReporter) -> None:
        await reporter.state(JobState.STARTING, stage="removing")
        paths = await asyncio.to_thread(self._approved_paths, job.content_identity)
        try:
            for path in paths:
                if os.path.lexists(path):
                    await asyncio.to_thread(path.unlink)
            await reporter.state(JobState.FINALIZING, stage="finalizing")
        except PermissionError as error:
            raise JobExecutionError("permission-denied", "Local content could not be removed") from error
        except OSError as error:
            raise JobExecutionError("remove-failed", "Local content could not be removed", retryable=True) from error

    async def cancel(self, job: DownloadJob) -> None:
        return None
