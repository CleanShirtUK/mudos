"""RomM-to-local-ROM acquisition adapter."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from dataclasses import replace
import shutil
import stat
import zipfile

from ...emulation import PLATFORMS, ROM_ROOT, canonical_platform_id, current_rom_root, ensure_storage
from ...job_manager import JobExecutionError, JobReporter
from ...jobs import DownloadJob, JobState
from .client import RommApiError, RommClient, RommConfig, RommGame, RommFile


class RommExecutor:
    """Stream one RomM file to a staged canonical ROM path."""

    def __init__(self, client: RommClient | None, *, chunk_size: int = 1024 * 1024) -> None:
        self.client = client
        self.chunk_size = chunk_size

    supports_pause = True

    def _refresh_saved_client(self) -> None:
        """Observe OOBE-saved configuration without restarting Acquisitiond."""
        if self.client is None or isinstance(self.client, RommClient):
            config = RommConfig.from_file()
            self.client = RommClient(config) if config else None

    def _resolve(self, identity: str) -> tuple[RommGame, RommFile]:
        if self.client is None:
            raise JobExecutionError("romm-unavailable", "RomM acquisition is not configured", retryable=True)
        file_id: int | None = None
        raw_identity = identity.removeprefix("romm-file:") if identity.startswith("romm-file:") else identity.removeprefix("romm:")
        if identity.startswith("romm-file:"):
            try:
                raw_rom, raw_file = raw_identity.split(":", 1)
                rom_id, file_id = int(raw_rom), int(raw_file)
            except (TypeError, ValueError):
                raise JobExecutionError("invalid-content-identity", "RomM file identity is invalid")
        else:
            try:
                rom_id = int(raw_identity)
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
        if file_id is not None:
            try:
                return game, next(item for item in game.files if item.file_id == file_id)
            except StopIteration as error:
                raise JobExecutionError("romm-file-missing", "RomM file is unavailable", retryable=True) from error
        return game, game.files[0]

    @staticmethod
    def _destination(game: RommGame, romm_file: RommFile) -> Path:
        definition = PLATFORMS.get(canonical_platform_id(game.platform_slug))
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

    @staticmethod
    def _disc_destination(game: RommGame, romm_file: RommFile) -> Path:
        """Keep PS1 descriptors/tracks together without making BIN a ROM type."""
        definition = PLATFORMS.get(canonical_platform_id(game.platform_slug))
        filename = Path(romm_file.name).name
        suffix = Path(filename).suffix.casefold()
        if definition is None or definition.platform_id != "psx" or filename != romm_file.name:
            raise JobExecutionError("unsupported-file", "Invalid PS1 disc-set file")
        if suffix not in {".cue", ".bin", ".zip"}:
            raise JobExecutionError("unsupported-file", f"Unsupported PS1 disc-set member: {filename}")
        root = Path(os.environ.get("LULU_ROM_ROOT", str(ROM_ROOT))).expanduser()
        return root / "psx" / f"romm-{game.rom_id}" / filename

    @staticmethod
    def _extract_psx_zip(archive: Path, destination: Path) -> None:
        """Extract CUE/BIN members without allowing traversal or symlinks."""
        try:
            with zipfile.ZipFile(archive) as bundle:
                for member in bundle.infolist():
                    if member.is_dir():
                        continue
                    mode = member.external_attr >> 16
                    if stat.S_ISLNK(mode):
                        raise JobExecutionError("unsafe-archive", "PS1 archive contains a symbolic link")
                    target = (destination / member.filename).resolve()
                    try:
                        target.relative_to(destination.resolve())
                    except ValueError as error:
                        raise JobExecutionError("unsafe-archive", "PS1 archive member escapes its disc folder") from error
                    if Path(member.filename).suffix.casefold() not in {".cue", ".bin"}:
                        continue
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with bundle.open(member) as source, target.open("wb") as output:
                        shutil.copyfileobj(source, output)
        except zipfile.BadZipFile as error:
            raise JobExecutionError("invalid-archive", "RomM PS1 archive is not a valid ZIP file") from error

    async def run(self, job: DownloadJob, reporter: JobReporter) -> None:
        self._refresh_saved_client()
        if job.content_identity.startswith("romm:") and not job.content_identity.startswith("romm-file:"):
            game, _ = await asyncio.to_thread(self._resolve, job.content_identity)
            if canonical_platform_id(game.platform_slug) == "psx":
                files = [item for item in game.files if item.category in {None, "", "game", "update", "dlc"}
                         and not item.name.startswith(".")]
                archives = [item for item in files if Path(item.name).suffix.casefold() == ".zip"]
                cues = [item for item in files if Path(item.name).suffix.casefold() == ".cue"]
                if archives:
                    files = archives
                elif cues:
                    files = cues + [item for item in files
                                    if Path(item.name).suffix.casefold() == ".bin"]
                if len(files) > 1 or archives:
                    await self._run_disc_files(job, game, files, reporter)
                    return
        if job.content_identity.startswith("romm-set:"):
            identities = [item for item in job.content_identity.removeprefix("romm-set:").split(",") if item]
            if not identities:
                raise JobExecutionError("invalid-content-set", "RomM content set is empty")
            expanded: list[tuple[str, bool, RommGame, RommFile]] = []
            selected_files: list[tuple[RommGame, RommFile]] = []
            for identity in identities:
                game, _ = await asyncio.to_thread(self._resolve, f"romm:{identity}")
                selected = [item for item in game.files if item.category in {None, "", "game", "update", "dlc"}
                            and not item.name.startswith(".")]
                disc_layout = canonical_platform_id(game.platform_slug) == "psx"
                if disc_layout:
                    archives = [item for item in selected if Path(item.name).suffix.casefold() == ".zip"]
                    cues = [item for item in selected if Path(item.name).suffix.casefold() == ".cue"]
                    if archives:
                        selected = archives
                    elif cues:
                        selected = cues + [item for item in selected
                                           if Path(item.name).suffix.casefold() == ".bin"]
                selected_files.extend((game, item) for item in selected)
                expanded.extend((f"{game.rom_id}:{item.file_id}", disc_layout, game, item)
                                for item in selected)
            if not expanded:
                raise JobExecutionError("romm-file-missing", "RomM content set has no installable files")
            await reporter.metadata(artifact_files=tuple({
                "rom_id": game.rom_id,
                "file_id": item.file_id,
                "name": item.name,
                "category": item.category,
                "title_id": item.title_id,
                "version": item.version,
            } for game, item in selected_files))
            # A content set is one acquisition transaction.  Its component
            # transfers must not drive the parent through FINALIZING until
            # every component has been installed; otherwise the manager
            # attempts STARTING for the next component after FINALIZING.
            await reporter.state(JobState.STARTING, stage="starting")
            disc_cues: list[Path] = []
            for identity, disc_layout, game, item in expanded:
                await self._run_one(replace(job, content_identity=f"romm-file:{identity}"), reporter,
                                    transition_states=False, disc_layout=disc_layout)
                if disc_layout and Path(item.name).suffix.casefold() == ".zip":
                    archive = self._disc_destination(game, item)
                    await asyncio.to_thread(self._extract_psx_zip, archive, archive.parent)
                    disc_cues.extend(archive.parent.rglob("*.cue"))
                    disc_cues.extend(archive.parent.rglob("*.CUE"))
                elif disc_layout and Path(item.name).suffix.casefold() == ".cue":
                    disc_cues.append(self._disc_destination(game, item))
            if len(disc_cues) > 1:
                platform_root = Path(os.environ.get("LULU_ROM_ROOT", str(ROM_ROOT))).expanduser() / "psx"
                title = "".join(character if character.isalnum() or character in " -_" else "_"
                                for character in job.title).strip(" ._")
                playlist = platform_root / f"{title or 'PlayStation Set'} [{job.job_id[:8]}].m3u"
                playlist.write_text("\n".join(
                    path.relative_to(platform_root).as_posix()
                    for path in dict.fromkeys(disc_cues)) + "\n")
            await reporter.progress(1.0, stage="finalizing")
            await reporter.state(JobState.FINALIZING, stage="finalizing")
            return
        await self._run_one(job, reporter)

    async def _run_disc_files(self, job: DownloadJob, game: RommGame,
                              files: list[RommFile], reporter: JobReporter) -> None:
        if not files:
            raise JobExecutionError("romm-file-missing", "PS1 disc set has no CUE or archive")
        await reporter.metadata(artifact_files=tuple({
            "rom_id": game.rom_id, "file_id": item.file_id, "name": item.name,
            "category": item.category,
        } for item in files))
        await reporter.state(JobState.STARTING, stage="starting")
        for item in files:
            await self._run_one(replace(job, content_identity=f"romm-file:{game.rom_id}:{item.file_id}"),
                                reporter, transition_states=False, disc_layout=True)
        for item in files:
            if Path(item.name).suffix.casefold() == ".zip":
                archive = self._disc_destination(game, item)
                await asyncio.to_thread(self._extract_psx_zip, archive, archive.parent)
        cues = [self._disc_destination(game, item) for item in files
                if Path(item.name).suffix.casefold() == ".cue"]
        for item in files:
            if Path(item.name).suffix.casefold() == ".zip":
                archive = self._disc_destination(game, item)
                cues.extend(archive.parent.rglob("*.cue"))
                cues.extend(archive.parent.rglob("*.CUE"))
        cues = list(dict.fromkeys(cues))
        if len(cues) > 1:
            title = "".join(character if character.isalnum() or character in " -_" else "_"
                             for character in game.title).strip(" ._")
            platform_root = Path(os.environ.get("LULU_ROM_ROOT", str(ROM_ROOT))).expanduser() / "psx"
            playlist = platform_root / f"{title or 'PlayStation Set'} [{job.job_id[:8]}].m3u"
            playlist.write_text("\n".join(
                path.relative_to(platform_root).as_posix() for path in cues) + "\n")
        await reporter.progress(1.0, stage="finalizing")
        await reporter.state(JobState.FINALIZING, stage="finalizing")

    async def _run_one(self, job: DownloadJob, reporter: JobReporter, *,
                       transition_states: bool = True, disc_layout: bool = False) -> None:
        # Pairing replaces the encrypted token while acquisitiond remains
        # alive. Refresh production clients per job; injected test doubles are
        # intentionally left untouched.
        self._refresh_saved_client()
        if transition_states:
            await reporter.state(JobState.STARTING, stage="starting")
        game, romm_file = await asyncio.to_thread(self._resolve, job.content_identity)
        destination = (self._disc_destination(game, romm_file) if disc_layout
                       else self._destination(game, romm_file))
        ensure_storage()
        destination.parent.mkdir(parents=True, exist_ok=True)
        # Retries carry the failed attempt as parent_job_id.  Reusing that
        # transaction key makes the provider-owned partial resumable without
        # placing staging data in the RomM library.
        transaction_id = job.parent_job_id or job.job_id
        staging = destination.with_name(f".{destination.name}.{transaction_id}.part")
        stream = None
        preserve_staging = True
        try:
            downloaded = staging.stat().st_size if staging.exists() else 0
            try:
                stream = await asyncio.to_thread(self.client.open_file_stream, romm_file, offset=downloaded)  # type: ignore[union-attr]
            except TypeError as error:
                # Preserve compatibility with injected provider doubles from
                # older integrations; production RomMClient supports Range.
                if "offset" not in str(error):
                    raise
                stream = await asyncio.to_thread(self.client.open_file_stream, romm_file)  # type: ignore[union-attr]
            headers = getattr(stream, "headers", {})
            status = int(getattr(stream, "status", 206 if downloaded else 200))
            # A server that ignores Range must not append a second copy.
            if downloaded and status != 206:
                staging.unlink(missing_ok=True)
                downloaded = 0
            total_header = headers.get("Content-Range", "").rsplit("/", 1)[-1] if headers.get("Content-Range") else headers.get("Content-Length")
            try:
                total = int(total_header) if total_header is not None else None
            except (TypeError, ValueError):
                total = None
            mode = "ab" if downloaded else "wb"
            with staging.open(mode) as output:
                if downloaded:
                    progress = downloaded / total if total and total > 0 else None
                    await reporter.state(JobState.TRANSFERRING, stage="transferring")
                    await reporter.progress(progress, downloaded_bytes=downloaded,
                                            total_bytes=total, stage="transferring")
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
            if transition_states:
                await reporter.state(JobState.FINALIZING, stage="finalizing")
            await asyncio.to_thread(os.replace, staging, destination)
            preserve_staging = False
        except asyncio.CancelledError:
            # A paused job keeps its provider-owned staging file so resume can
            # continue from the reported byte offset. Cancellation still
            # removes the active job; the hidden partial is harmless and is
            # replaced/cleaned on a later acquisition according to RomM's
            # staging policy.
            preserve_staging = True
            raise
        except RommApiError as error:
            raise JobExecutionError("romm-failure", str(error), retryable=True) from error
        except OSError as error:
            raise JobExecutionError("local-storage-failure", str(error), retryable=True) from error
        finally:
            if stream is not None:
                await asyncio.to_thread(stream.close)
            if not preserve_staging:
                try:
                    staging.unlink(missing_ok=True)
                except OSError:
                    pass
