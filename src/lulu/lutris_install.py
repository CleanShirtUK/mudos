"""One-parent Mudos installation transaction for a PC source."""

from __future__ import annotations

import asyncio
import json
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
    uninstall_progress_supported = False

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

    @staticmethod
    def _owned_install_directory(game) -> tuple[Path, bool] | None:
        """Return a verified Lutris directory and whether Mudos owns its files.

        Recipe payloads are deletable only with our install marker. A local
        registration is removable through Lutris but its user's files must be
        preserved. Provider-discovered registrations are not Mudos-owned.
        """
        if (game is None or game.provider != "lutris" or not game.mudos_owned
                or not game.install_dir or game.catalogue_source not in {"lutris-recipe", "mudos-local"}):
            return None
        raw = Path(game.install_dir).expanduser()
        if raw.is_symlink():
            return None
        directory = raw.resolve(strict=False)
        root = (PATHS.game_install_root / "Executables" / "lutris").resolve(strict=False)
        slug = str(game.provider_id)
        if (directory == root or directory.parent != root or directory.name != slug
                or slug in {"", ".", ".."}):
            return None
        recipe_owned = game.catalogue_source == "lutris-recipe"
        if recipe_owned and directory.exists():
            marker = directory / ".mudos-install-owner.json"
            if marker.is_symlink():
                return None
            try:
                value = json.loads(marker.read_text(encoding="utf-8"))
            except (OSError, TypeError, ValueError, json.JSONDecodeError):
                return None
            if (not isinstance(value, dict) or value.get("provider") != "lutris"
                    or value.get("slug") != slug
                    or Path(str(value.get("directory", ""))).resolve(strict=False) != directory):
                return None
        return directory, recipe_owned

    def uninstall_capability(self, game) -> dict[str, object]:
        owned = self._owned_install_directory(game)
        if owned is None:
            return {"supported": False,
                    "reason": "This Lutris entry is not a verified Mudos recipe install or local registration."}
        _directory, recipe_owned = owned
        return {"supported": True, "description": (
            "Remove the Mudos-installed Lutris game and its owned files" if recipe_owned
            else "Remove the Lutris registration only; user files will be kept")}

    def can_uninstall(self, game_id: str) -> bool:
        if self.catalogue is None:
            return False
        game = self.catalogue.get_game(game_id)
        return self._owned_install_directory(game) is not None

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
            recipes: list[LutrisRecipe] = []
            if source.lutris_slug:
                recipes.extend(await asyncio.to_thread(self.adapter.recipes, source.lutris_slug))
            else:
                candidates = await asyncio.to_thread(self.adapter.search, source.title)
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
            if destination.exists():
                raise JobExecutionError(
                    "lutris-destination-exists",
                    "The canonical Lutris destination already exists; refusing to overwrite existing game data.",
                    retryable=False,
                )
            root = destination.parent.resolve(strict=False)
            if destination.resolve(strict=False).parent != root:
                raise JobExecutionError("unsafe-install-path", "Lutris destination escaped canonical root", retryable=False)
            created_by_transaction = True
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
                elif message.startswith("Downloading "):
                    schedule_state(JobState.TRANSFERRING, "downloading-files")
            result = await asyncio.to_thread(self.adapter.execute, source, recipe, destination,
                                             status=status, transaction_id=job.job_id)
            installed_dir = Path(str(result.get("directory", ""))).resolve(strict=False)
            expected_dir = destination.resolve(strict=False)
            if (installed_dir != expected_dir or destination.is_symlink()
                    or not destination.is_dir()):
                raise JobExecutionError("unsafe-install-path",
                                        "Lutris registered a game outside its Mudos transaction directory",
                                        retryable=False)
            ownership_marker = destination / ".mudos-install-owner.json"
            ownership_marker.write_text(json.dumps({
                "schema": 1, "provider": "lutris", "slug": recipe.game_slug,
                "directory": str(expected_dir),
            }, sort_keys=True) + "\n", encoding="utf-8")
            if self.catalogue is not None:
                await asyncio.to_thread(self.catalogue.reconcile_lutris, result, source)
            await reporter.state(JobState.FINALIZING, stage="registering")
            await reporter.metadata(completion_path=str(destination), provider_job_id=str(result["slug"]),
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
        owned = self._owned_install_directory(game)
        if owned is None:
            raise JobExecutionError("unsafe-uninstall-path", "Lutris installation ownership is unverified",
                                     retryable=False)
        directory, recipe_owned = owned
        await reporter.state(JobState.TRANSFERRING, stage="unregistering")
        # Re-check the catalogue-owned path before entering the provider API;
        # never delete first and validate a returned path afterward.
        result = await asyncio.to_thread(
            self.adapter.uninstall, job.provider_job_id,
            delete_files=recipe_owned and directory.is_dir(),
            expected_directory=directory,
        )
        returned_directory = Path(str(result.get("directory", ""))).resolve(strict=False)
        if returned_directory != directory:
            raise JobExecutionError("unsafe-uninstall-path", "Lutris installation ownership is unverified",
                                     retryable=False)
        if recipe_owned and directory.exists():
            # Lutris' model uninstall unregisters the title but, on supported
            # releases, may leave its installation tree in place even when
            # delete_files=True. Complete that provider transaction only after
            # revalidating the per-game marker and canonical direct-child path.
            if self._owned_install_directory(game) != (directory, True) or directory.is_symlink():
                raise JobExecutionError("unsafe-uninstall-path",
                                        "Lutris payload ownership changed during uninstall",
                                        retryable=False)
            try:
                await asyncio.to_thread(shutil.rmtree, directory)
            except OSError as error:
                raise JobExecutionError("lutris-payload-remove-failed",
                                        "Lutris registration was removed but its owned files remain",
                                        retryable=True) from error
        if recipe_owned and directory.exists():
            raise JobExecutionError("lutris-payload-remove-failed",
                                    "Lutris-owned game files remain after uninstall", retryable=True)
        if self.catalogue is not None:
            await asyncio.to_thread(self.catalogue.mark_lutris_uninstalled, job.provider_job_id)
        await reporter.progress(1.0, downloaded_bytes=1, total_bytes=1, stage="completed")
