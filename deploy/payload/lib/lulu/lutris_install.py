"""One-parent Mudos installation transaction for a PC source."""

from __future__ import annotations

import asyncio
from pathlib import Path
import shutil

from .job_manager import JobExecutionError, JobReporter
from .jobs import DownloadJob, JobState
from .lutris_adapter import LutrisAdapter, LutrisAdapterError, LutrisInstallCancelled, LutrisRecipe
from .job_manager import JobCancelled
from .pc_install import PcInstallSource, canonical_lutris_root
from .pc_install_store import PcInstallSourceStore
from .paths import PATHS


class LutrisInstallExecutor:
    provider_id = "lutris"
    supports_pause = False
    supports_uninstall = True

    def __init__(self, sources: PcInstallSourceStore | None = None,
                 adapter: LutrisAdapter | None = None, catalogue=None) -> None:
        self.sources = sources or PcInstallSourceStore()
        self.adapter = adapter or LutrisAdapter()
        self.catalogue = catalogue

    def register_source(self, source: PcInstallSource) -> str:
        if not source.ready_to_install:
            raise ValueError("PC source is not ready to install")
        return self.sources.put(source)

    def uninstall(self, _job: DownloadJob) -> None:
        """Marker for Acquisitiond's supported uninstall capability."""
        return None

    def can_uninstall(self, game_id: str) -> bool:
        if self.catalogue is None:
            return False
        game = self.catalogue.get_game(game_id)
        if game is None or game.provider != "lutris" or not game.mudos_owned or not game.install_dir:
            return False
        directory = Path(game.install_dir).resolve(strict=False)
        root = (PATHS.game_install_root / "Executables" / "lutris").resolve(strict=False)
        try:
            directory.relative_to(root)
        except ValueError:
            return False
        return directory != root

    async def cancel(self, _job: DownloadJob) -> None:
        # Guide/sessiond owns termination of the interactive process group.
        return None

    async def run(self, job: DownloadJob, reporter: JobReporter) -> None:
        if job.operation.value == "remove":
            await self._uninstall(job, reporter)
            return
        source = self.sources.get(job.content_identity)
        if source is None or not source.ready_to_install:
            raise JobExecutionError("pc-source-unavailable", "PC installation source is not ready", retryable=False)
        await reporter.state(JobState.STARTING, stage="resolving-recipe")
        destination: Path | None = None
        created_by_transaction = False
        try:
            candidates = await asyncio.to_thread(self.adapter.search, source.title)
            recipes: list[LutrisRecipe] = []
            for candidate in candidates:
                slug = str(candidate.get("slug", ""))
                if slug:
                    recipes.extend(await asyncio.to_thread(self.adapter.recipes, slug))
            recipe = await asyncio.to_thread(self.adapter.match, source, tuple(recipes))
            await reporter.metadata(artifact_files=({"source_id": source.source_id,
                                                      "recipe": recipe.installer_slug,
                                                      "game_slug": recipe.game_slug},))
            await reporter.state(JobState.TRANSFERRING, stage="preparing-runner")
            destination = canonical_lutris_root(recipe.game_slug)
            # An interrupted/retryable transaction may leave a partial
            # canonical directory behind.  This path is Mudos-owned and the
            # source is still explicitly Ready to Install, so remove only
            # that stale payload before retrying; never infer installation from
            # its mere presence.
            created_by_transaction = True
            if destination.exists():
                await asyncio.to_thread(shutil.rmtree, destination)
            root = destination.parent.resolve(strict=False)
            if destination.resolve(strict=False).parent != root:
                raise JobExecutionError("unsafe-install-path", "Lutris destination escaped canonical root", retryable=False)
            await reporter.state(JobState.TRANSFERRING, stage="installing")
            loop = asyncio.get_running_loop()
            def schedule_state(state: JobState, stage: str) -> None:
                async def apply() -> None:
                    try:
                        await reporter.state(state, stage=stage)
                    except ValueError:
                        # An explicit Guide cancellation may race the worker's
                        # completion callback; CANCELLING is already terminal
                        # for this transaction and must not become a failure.
                        return
                loop.call_soon_threadsafe(asyncio.create_task, apply())
            def status(message: str) -> None:
                if message == "awaiting_interaction":
                    schedule_state(JobState.AWAITING_INTERACTION, "awaiting_interaction")
                elif message == "interaction_complete":
                    schedule_state(JobState.TRANSFERRING, "installing")
            result = await asyncio.to_thread(self.adapter.execute, source, recipe, destination,
                                             status=status, transaction_id=job.job_id)
            if self.catalogue is not None:
                await asyncio.to_thread(self.catalogue.reconcile_lutris, result, source)
            await reporter.state(JobState.FINALIZING, stage="registering")
            await reporter.metadata(completion_path=str(destination), provider_job_id=str(result["lutris_id"]),
                                    backend="lutris", destination=str(destination), provider_state="installed",
                                    ownership_label="mudos")
            await reporter.progress(1.0, downloaded_bytes=1, total_bytes=1, stage="completed")
        except asyncio.CancelledError:
            if created_by_transaction and destination is not None and destination.is_dir():
                await asyncio.to_thread(shutil.rmtree, destination)
            raise
        except LutrisInstallCancelled:
            if created_by_transaction and destination is not None and destination.is_dir():
                await asyncio.to_thread(shutil.rmtree, destination)
            raise JobCancelled()
        except LutrisAdapterError as error:
            if created_by_transaction and destination is not None and destination.is_dir():
                await asyncio.to_thread(shutil.rmtree, destination)
            raise JobExecutionError("lutris-install-failed", str(error), retryable=True) from error
        except OSError as error:
            if created_by_transaction and destination is not None and destination.is_dir():
                await asyncio.to_thread(shutil.rmtree, destination)
            raise JobExecutionError("lutris-storage-failure", str(error), retryable=True) from error

    async def _uninstall(self, job: DownloadJob, reporter: JobReporter) -> None:
        if not job.provider_job_id:
            raise JobExecutionError("lutris-registration-missing", "Lutris game registration is missing", retryable=False)
        game = self.catalogue.get_game_by_provider_id("lutris", job.provider_job_id) if self.catalogue else None
        if not game or not self.can_uninstall(game.game_id):
            raise JobExecutionError("unsafe-uninstall-path", "Lutris installation ownership is unverified",
                                     retryable=False)
        await reporter.state(JobState.TRANSFERRING, stage="unregistering")
        result = await asyncio.to_thread(self.adapter.uninstall, job.provider_job_id, delete_files=False)
        directory = Path(str(result.get("directory", ""))).resolve(strict=False)
        canonical_parent = (PATHS.game_install_root / "Executables" / "lutris").resolve(strict=False)
        try:
            directory.relative_to(canonical_parent)
        except ValueError as error:
            raise JobExecutionError("unsafe-uninstall-path", "Lutris payload is outside the canonical root",
                                     retryable=False) from error
        if not game or not game.mudos_owned or Path(game.install_dir).resolve(strict=False) != directory:
            raise JobExecutionError("unsafe-uninstall-path", "Lutris installation ownership is unverified",
                                     retryable=False)
        if directory != canonical_parent and directory.is_dir():
            await asyncio.to_thread(shutil.rmtree, directory)
        if self.catalogue is not None:
            await asyncio.to_thread(self.catalogue.mark_lutris_uninstalled, job.provider_job_id)
        await reporter.progress(1.0, downloaded_bytes=1, total_bytes=1, stage="completed")
