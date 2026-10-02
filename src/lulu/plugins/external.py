"""Provider-neutral contracts for external PC game clients.

The provider plugins own identity/authentication and command construction;
catalogue and acquisition services consume these small normalized objects.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import asyncio
import json
import logging
import os
import os
from pathlib import Path
import re
import shutil
from typing import Callable, Iterable

from ..job_manager import JobExecutionError, JobReporter
from ..jobs import DownloadJob, JobState


@dataclass(frozen=True, slots=True)
class OwnedProviderGame:
    provider_id: str
    title: str
    install_dir: str = ""
    executable: str = ""
    platform: str = "PC"
    artwork_url: str = ""
    last_played: int = 0
    availability_state: str = "available"


def _record(value: object) -> dict[str, object]:
    return value if isinstance(value, dict) else {}


def normalize_game(value: object, *, provider_id_keys: tuple[str, ...],
                   title_keys: tuple[str, ...]) -> OwnedProviderGame | None:
    item = _record(value)
    identity = next((str(item[key]).strip() for key in provider_id_keys
                     if item.get(key) not in (None, "")), "")
    title = next((str(item[key]).strip() for key in title_keys
                  if item.get(key) not in (None, "")), "")
    if not identity or not title:
        return None
    install_dir = str(item.get("install_dir") or item.get("install_path") or item.get("path") or "")
    executable = str(item.get("executable") or item.get("executable_path") or "")
    return OwnedProviderGame(identity, title, install_dir, executable,
                             str(item.get("platform") or "PC"),
                             str(item.get("artwork_url") or item.get("cover") or ""),
                             int(item.get("last_played") or 0),
                              str(item.get("availability_state") or "available"))


def catalogue_authentication_state(source: object) -> str:
    """Return provider auth state without assuming credentials are local files.

    Providers with daemon/service-owned sessions implement
    ``catalogue_authentication_status()``. Existing file-backed providers keep
    the historical auth-artifact check as the default behavior.
    """
    status = getattr(source, "catalogue_authentication_status", None)
    if callable(status):
        value = str(status()).strip().lower().replace("_", "-")
        return value or "unavailable"
    auth_path = getattr(source, "config_path", None) or getattr(source, "auth_path", None)
    return "authenticated" if auth_path is not None and auth_path.is_file() else "authentication-required"


class SnapshotEntitlementSource:
    """Last-known-good owned/install snapshot used by provider plugins."""

    def __init__(self, provider_id: str, snapshot_path: Path,
                 logger: logging.Logger | None = None) -> None:
        self.provider_id = provider_id
        self.snapshot_path = snapshot_path
        self.logger = logger or logging.getLogger(f"lulu.{provider_id}-entitlements")
        self._owned: tuple[OwnedProviderGame, ...] = ()
        self._installed: tuple[OwnedProviderGame, ...] = ()
        self.last_error = ""
        self._load()

    @property
    def has_snapshot(self) -> bool:
        return bool(self._owned)

    @property
    def snapshot(self) -> tuple[OwnedProviderGame, ...]:
        return self._owned

    def installed(self) -> tuple[OwnedProviderGame, ...]:
        return self._installed

    def _load(self) -> None:
        try:
            value = json.loads(self.snapshot_path.read_text())
            self._owned = tuple(self._parse(item) for item in value.get("owned", []))
            self._installed = tuple(self._parse(item) for item in value.get("installed", []))
        except (OSError, TypeError, ValueError, json.JSONDecodeError, AttributeError):
            self._owned = ()
            self._installed = ()

    def _parse(self, value: object) -> OwnedProviderGame:
        item = _record(value)
        return OwnedProviderGame(str(item.get("provider_id", "")), str(item.get("title", "")),
                                 str(item.get("install_dir", "")), str(item.get("executable", "")),
                                 str(item.get("platform", "PC")), str(item.get("artwork_url", "")),
                                 int(item.get("last_played", 0) or 0),
                                 str(item.get("availability_state", "available")))

    def _save(self) -> None:
        try:
            self.snapshot_path.parent.mkdir(parents=True, exist_ok=True)
            payload = {"schema": 1, "owned": [asdict(game) for game in self._owned],
                       "installed": [asdict(game) for game in self._installed]}
            temporary = self.snapshot_path.with_suffix(".tmp")
            temporary.write_text(json.dumps(payload, sort_keys=True) + "\n")
            temporary.replace(self.snapshot_path)
        except OSError as error:
            self.logger.warning("could not persist %s entitlement snapshot: %s", self.provider_id, error)

    def update(self, owned: Iterable[OwnedProviderGame], installed: Iterable[OwnedProviderGame]) -> None:
        self._owned = tuple(sorted({game.provider_id: game for game in owned}.values(), key=lambda item: item.title.casefold()))
        self._installed = tuple(sorted({game.provider_id: game for game in installed}.values(), key=lambda item: item.title.casefold()))
        self._save()
        self.last_error = ""


class CliAcquisitionExecutor:
    """Run a provider's native install command through JobManager."""

    supports_pause = False
    supports_uninstall = True

    def __init__(self, provider: str, executable: str, install_root: Path,
                 command_builder: Callable[[str, Path], list[str]],
                 uninstall_builder: Callable[[str, Path], list[str]] | None = None) -> None:
        self.provider = provider
        self.executable = executable
        self.install_root = install_root
        self.command_builder = command_builder
        self.uninstall_builder = uninstall_builder
        self._processes: dict[str, asyncio.subprocess.Process] = {}
        self.environment: dict[str, str] | None = None

    def _require(self) -> str:
        resolved = shutil.which(self.executable) or self.executable
        if not Path(resolved).is_file() and shutil.which(resolved) is None:
            raise JobExecutionError(f"{self.provider}-backend-unavailable",
                                     f"{self.provider} backend is not provisioned", retryable=True)
        return resolved

    def _diagnostic_line(self, line: str) -> str:
        return line[-500:]

    def _process_failure(self, returncode: int, provider_message: str) -> JobExecutionError:
        return JobExecutionError(f"{self.provider}-failed", f"{self.provider} exited with status {returncode}",
                                 retryable=True, details={"return_code": returncode})

    def _validation_failure(self, error: JobExecutionError, returncode: int,
                            provider_message: str) -> JobExecutionError:
        return error

    async def run(self, job: DownloadJob, reporter: JobReporter) -> None:
        executable = self._require()
        if job.operation.value == "remove" and self.uninstall_builder is not None:
            command = self.uninstall_builder(job.content_identity, self.install_root)
        elif job.operation.value == "remove":
            # gogdl has no uninstall command.  Its payload is deliberately
            # kept under the provider root, so removal can be performed
            # safely at this boundary without a second download system.
            marker_dir = self._managed_install_directory(job.content_identity)
            await reporter.state(JobState.STARTING, stage="removing")
            import shutil as _shutil
            await asyncio.to_thread(_shutil.rmtree, marker_dir, True)
            await reporter.progress(1.0, stage="completed")
            await reporter.state(JobState.FINALIZING, stage="completed")
            await reporter.state(JobState.COMPLETED, stage="completed")
            return
        else:
            command = self.command_builder(job.content_identity, self.install_root)
        command[0] = executable
        self.install_root.mkdir(parents=True, exist_ok=True)
        process = await asyncio.create_subprocess_exec(
            *command, cwd=str(self.install_root), stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            env=self.environment,
        )
        self._processes[job.job_id] = process
        await reporter.state(JobState.STARTING, stage="starting")
        progress = re.compile(r"(?:progress|complete|completed)\D+([0-9]{1,3})(?:\.|%| percent)", re.I)
        provider_message = ""
        try:
            assert process.stdout is not None
            async for raw in process.stdout:
                line = raw.decode(errors="replace").strip()
                match = progress.search(line)
                diagnostic = self._diagnostic_line(line) if line else ""
                if diagnostic:
                    provider_message = diagnostic
                if match:
                    await reporter.progress(min(1.0, int(match.group(1)) / 100.0), stage="transferring")
                    await reporter.state(JobState.TRANSFERRING, stage="transferring")
                elif line:
                    await reporter.metadata(provider_state=diagnostic)
            code = await process.wait()
            if code != 0:
                raise self._process_failure(code, provider_message)
            await reporter.progress(1.0, stage="finalizing")
            await reporter.state(JobState.FINALIZING, stage="finalizing")
            marker_dir = self.install_root / job.content_identity.removeprefix(f"{self.provider}:")
            if job.operation.value in {"install", "update", "acquire"}:
                try:
                    self._validate_installed_payload(marker_dir)
                except JobExecutionError as error:
                    raise self._validation_failure(error, code, provider_message) from error
                (marker_dir / ".mudos-game.json").write_text(json.dumps({
                    "provider_id": job.content_identity.removeprefix(f"{self.provider}:"),
                    "title": job.title, "install_dir": str(marker_dir),
                }) + "\n")
            elif job.operation.value == "remove":
                marker = marker_dir / ".mudos-game.json"
                marker.unlink(missing_ok=True)
            await reporter.state(JobState.COMPLETED, stage="completed")
        finally:
            self._processes.pop(job.job_id, None)

    def _managed_install_directory(self, identity: str) -> Path:
        root = self.install_root.resolve(strict=False)
        value = self.install_root / identity.removeprefix(f"{self.provider}:")
        if value.is_symlink():
            raise JobExecutionError("unsafe-uninstall-path", "Provider install is a symlink")
        target = value.resolve(strict=False)
        try:
            target.relative_to(root)
        except ValueError as error:
            raise JobExecutionError("unsafe-uninstall-path", "Provider install escaped its managed root") from error
        if target == root or target.parent != root or not (target / ".mudos-game.json").is_file():
            raise JobExecutionError("unmanaged-install", "Provider installation is not Mudos-managed")
        return target

    def _validate_installed_payload(self, directory: Path) -> None:
        """Require the provider's destination to contain real payload before completion."""
        root = self.install_root.resolve(strict=False)
        if directory.is_symlink():
            raise JobExecutionError("unsafe-install-path", "Provider install destination is a symlink")
        target = directory.resolve(strict=False)
        try:
            target.relative_to(root)
        except ValueError as error:
            raise JobExecutionError("unsafe-install-path", "Provider install escaped its managed root") from error
        if target == root or target.parent != root or not target.is_dir():
            raise JobExecutionError("provider-install-incomplete",
                                    "Provider reported success without creating its install directory", retryable=True)
        try:
            has_payload = any(item.is_file() and item.name != ".mudos-game.json"
                              for item in target.rglob("*"))
        except OSError as error:
            raise JobExecutionError("provider-install-incomplete",
                                    "Provider install directory could not be inspected", retryable=True) from error
        if not has_payload:
            raise JobExecutionError("provider-install-incomplete",
                                    "Provider reported success without installing content", retryable=True)

    async def cancel(self, job: DownloadJob) -> None:
        process = self._processes.get(job.job_id)
        if process is not None and process.returncode is None:
            process.terminate()


class CliProviderAuthentication:
    def __init__(self, provider_id: str, executable: str, config_path: Path) -> None:
        self.provider_id = provider_id
        self.executable = executable
        self.config_path = config_path

    def status(self) -> dict[str, object]:
        return {"provider_id": self.provider_id,
                "status": "configured" if self.config_path.exists() else "authentication_required",
                "configured": self.config_path.exists(),
                "authenticated": self.config_path.exists(),
                "authentication_required": not self.config_path.exists(),
                "authentication_in_progress": False, "error": ""}

    def begin(self) -> dict[str, object]:
        return {"provider_id": self.provider_id, "surface": "interactive"}

    def authentication_methods(self) -> tuple[str, ...]:
        return ("auth_browser",)

    def sign_out(self) -> None:
        self.config_path.unlink(missing_ok=True)
