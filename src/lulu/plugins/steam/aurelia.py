"""Opt-in Mudos boundary for Aurelia's JSON CLI.

This module deliberately does not authenticate, change Steam state, or launch
anything during construction. The provider has a distinct identity so it can
never silently take over the production ``steam`` executor.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import json
import os
from pathlib import Path
import shutil
import stat
import time
from typing import Any, Callable

from ...jobs import DownloadJob, ExternalAcquisition, JobState
from ...job_manager import JobCancelled, JobExecutionError, JobReporter
from ...paths import PATHS

PROVIDER_ID = "steam-aurelia"


class AureliaError(RuntimeError):
    def __init__(self, code: str, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.code = code
        self.retryable = retryable


@dataclass(frozen=True, slots=True)
class AureliaCapabilities:
    acquisition_progress: bool = True
    acquisition_cancel: bool = True
    updates: bool = False  # Provider command exists; Acquisitiond update jobs are not wired yet.
    dlc: bool = False  # DLC operations exist upstream; Mudos component jobs are not wired yet.
    launch: bool = False  # Must remain false until Sessiond owns the integrated path.
    running_state: bool = True
    authentication_status: bool = True
    detailed_launch_progress: bool = False


@dataclass(frozen=True, slots=True)
class AureliaInstalledGame:
    provider: str
    app_id: str
    title: str
    installed: bool
    install_path: str | None
    platform: str | None
    update_available: bool | None


class AureliaClient:
    """Secret-free CLI boundary. Credentials are never accepted as arguments."""

    def __init__(self, executable: str | None = None, config_dir: Path | None = None,
                 *, run: Callable[..., Any] | None = None) -> None:
        self.executable = executable or os.environ.get("LULU_AURELIA_EXECUTABLE") or shutil.which("aurelia")
        self.config_dir = config_dir or PATHS.provider_root(PROVIDER_ID) / "aurelia"
        self._run = run
        self._startup_lock = asyncio.Lock()
        self._daemon_ready = False

    @property
    def available(self) -> bool:
        if self._run is not None:
            return True
        if not self.executable:
            return False
        candidate = Path(self.executable)
        resolved = candidate if candidate.is_absolute() or candidate.parent != Path(".") else Path(shutil.which(self.executable) or "")
        return resolved.is_file() and os.access(resolved, os.X_OK)

    def _ensure_config_dir(self) -> None:
        self.config_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        try:
            self.config_dir.chmod(0o700)
        except OSError as error:
            raise AureliaError("session-storage-unavailable", "Aurelia session directory permissions could not be secured", retryable=False) from error
        if self.config_dir.stat().st_mode & 0o077:
            raise AureliaError("session-storage-unavailable", "Aurelia session directory is not private", retryable=False)
        self._ensure_launcher_config()

    def _ensure_launcher_config(self) -> None:
        """Pin Aurelia to Mudos' canonical library without overwriting settings."""
        path = self.config_dir / "config.json"
        canonical = PATHS.steam_library_root
        if path.exists():
            try:
                config = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as error:
                raise AureliaError("invalid-config", "Aurelia configuration is unreadable; refusing to continue") from error
            configured = config.get("steam_library_path") if isinstance(config, dict) else None
            if not isinstance(configured, str) or Path(configured).expanduser().absolute() != canonical.absolute():
                raise AureliaError("library-path-mismatch", "Aurelia is not configured for the canonical Mudos Steam library")
            try:
                path.chmod(0o600)
            except OSError as error:
                raise AureliaError("session-storage-unavailable", "Aurelia configuration permissions could not be secured") from error
            return
        baseline = {
            "steam_library_path": str(canonical),
            "proton_version": "experimental",
            "enable_cloud_sync": False,
            "windows_steam_discovery_enabled": False,
        }
        try:
            with path.open("x", encoding="utf-8") as stream:
                os.chmod(path, 0o600)
                json.dump(baseline, stream, sort_keys=True)
                stream.write("\n")
        except FileExistsError:
            # Another Mudos caller won initialization; validate its result.
            return self._ensure_launcher_config()
        except OSError as error:
            raise AureliaError("session-storage-unavailable", "Aurelia configuration could not be initialized") from error

    def _environment(self) -> dict[str, str]:
        env = os.environ.copy()
        env["AURELIA_CONFIG_DIR"] = str(self.config_dir)
        # Aurelia's daemon endpoint is keyed by XDG_RUNTIME_DIR and uid, not by
        # AURELIA_CONFIG_DIR. Keep Mudos callers on one endpoint even when a
        # caller (for example an offline maintenance shell) omitted XDG_RUNTIME_DIR.
        runtime_dir = Path(env["XDG_RUNTIME_DIR"]) if env.get("XDG_RUNTIME_DIR") else None
        runtime_metadata = None
        if runtime_dir is not None:
            try:
                runtime_metadata = runtime_dir.stat()
            except OSError:
                runtime_metadata = None
        if runtime_metadata is None or not stat.S_ISDIR(runtime_metadata.st_mode) \
                or runtime_metadata.st_uid != os.geteuid():
            runtime_dir = None
            env.pop("XDG_RUNTIME_DIR", None)
            candidate = Path(f"/run/user/{os.geteuid()}")
            try:
                metadata = candidate.stat()
            except OSError:
                metadata = None
            if metadata is not None and stat.S_ISDIR(metadata.st_mode) \
                    and metadata.st_uid == os.geteuid():
                runtime_dir = candidate
                env["XDG_RUNTIME_DIR"] = str(candidate)
        if runtime_dir is not None:
            env["AURELIA_DAEMON_SOCKET"] = str(
                runtime_dir / f"aurelia-{os.geteuid()}.sock")
        else:
            env.pop("AURELIA_DAEMON_SOCKET", None)
        # One persistent daemon is necessary to share the authenticated CM session
        # and active install registry across Acquisitiond and Sessiond calls.
        env.pop("AURELIA_NO_DAEMON", None)
        env.pop("AURELIA_NO_SPAWN", None)
        return env

    async def command(self, *args: str, timeout: float = 120.0) -> Any:
        if not self.available:
            raise AureliaError("unavailable", "Aurelia executable is unavailable", retryable=True)
        self._ensure_config_dir()
        argv = [self.executable, "--json", *map(str, args)]

        async def invoke() -> Any:
            return await self._invoke(argv, timeout)

        # The first CLI request auto-spawns Aurelia's detached daemon. Serialize
        # that one transition inside Acquisitiond: later concurrent health and
        # discovery requests then connect to the same socket rather than racing
        # the upstream CLI's spawn path.
        if self._run is not None or self._daemon_ready:
            return await invoke()
        async with self._startup_lock:
            if self._daemon_ready:
                return await invoke()
            try:
                result = await invoke()
            finally:
                env = self._environment()
                endpoint = env.get("AURELIA_DAEMON_SOCKET")
                if endpoint:
                    try:
                        self._daemon_ready = stat.S_ISSOCK(Path(endpoint).stat().st_mode)
                    except OSError:
                        self._daemon_ready = False
            return result

    async def _invoke(self, argv: list[str], timeout: float) -> Any:
        try:
            if self._run:
                result = self._run(argv, env=self._environment(), timeout=timeout)
                if asyncio.iscoroutine(result):
                    result = await result
                code, stdout, stderr = result
            else:
                process = await asyncio.create_subprocess_exec(
                    *argv, env=self._environment(), stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE)
                stdout_bytes, stderr_bytes = await asyncio.wait_for(process.communicate(), timeout)
                code = process.returncode
                stdout, stderr = stdout_bytes.decode(errors="replace"), stderr_bytes.decode(errors="replace")
        except FileNotFoundError as error:
            raise AureliaError("unavailable", "Aurelia executable is unavailable", retryable=True) from error
        except (TimeoutError, asyncio.TimeoutError) as error:
            raise AureliaError("timeout", "Aurelia command timed out", retryable=True) from error
        except OSError as error:
            raise AureliaError("process-error", f"Aurelia could not run ({type(error).__name__})", retryable=True) from error
        if code:
            # Do not include stderr: upstream diagnostics may contain account identifiers.
            raise AureliaError("command-failed", f"Aurelia command failed (exit {code})", retryable=code in {69, 75})
        try:
            return json.loads(stdout) if stdout.strip() else None
        except json.JSONDecodeError as error:
            raise AureliaError("malformed-output", "Aurelia returned malformed JSON", retryable=True) from error

    async def auth_status(self) -> str:
        try:
            value = await self.command("login", "--health")
        except AureliaError as error:
            if error.code == "unavailable":
                return "unavailable"
            if error.code == "command-failed":
                return "authentication-required"
            raise
        if not isinstance(value, dict):
            raise AureliaError("malformed-output", "Aurelia auth health was not an object")
        if value.get("logged_in") is True:
            return "authenticated"
        if value.get("session_expired") is True:
            return "authentication-expired"
        if value.get("authentication_required") is True:
            return "authentication-required"
        return "unauthenticated"

    async def snapshot(self) -> dict[str, Any]:
        libraries, installed, running, jobs = await asyncio.gather(
            self.command("libraries"), self.command("list", "--installed"),
            self.command("running"), self.command("install", "list"))
        return {"provider": PROVIDER_ID, "libraries": libraries, "installed": installed,
                "running": running, "acquisition": jobs}

    async def installed_games(self) -> tuple[AureliaInstalledGame, ...]:
        """Map Aurelia's installed-library JSON without inventing filesystem facts."""
        rows = await self.command("list", "--installed")
        if not isinstance(rows, list):
            raise AureliaError("malformed-output", "Aurelia installed-game list was not an array")
        result = []
        for row in rows:
            if not isinstance(row, dict) or not str(row.get("app_id", "")).isdecimal():
                continue
            result.append(AureliaInstalledGame(
                provider=PROVIDER_ID, app_id=str(row["app_id"]),
                title=str(row.get("name") or row["app_id"]),
                installed=bool(row.get("is_installed")),
                install_path=row.get("install_path") if isinstance(row.get("install_path"), str) else None,
                platform=row.get("platform") if isinstance(row.get("platform"), str) else None,
                update_available=row.get("update_available")
                if isinstance(row.get("update_available"), bool) else None,
            ))
        return tuple(result)

    async def install_events(self, app_id: str):
        if not self.available:
            raise AureliaError("unavailable", "Aurelia executable is unavailable", retryable=True)
        self._ensure_config_dir()
        process = await asyncio.create_subprocess_exec(
            self.executable, "--json", "install", app_id, env=self._environment(),
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        assert process.stderr is not None
        try:
            async for raw in process.stderr:
                try:
                    value = json.loads(raw)
                except (UnicodeDecodeError, json.JSONDecodeError):
                    continue
                if isinstance(value, dict) and value.get("event") == "progress":
                    yield value
            stdout, _ = await process.communicate()
            if process.returncode:
                raise AureliaError("install-failed", f"Aurelia install failed (exit {process.returncode})", retryable=True)
            if stdout:
                try:
                    json.loads(stdout)
                except json.JSONDecodeError as error:
                    raise AureliaError("malformed-output", "Aurelia install returned malformed JSON") from error
        except asyncio.CancelledError:
            # The executor sends install stop through the shared daemon before
            # cancelling this relay task; cancellation is not inferred from task loss.
            raise
        finally:
            if process.returncode is None:
                process.kill()
                await process.wait()

    async def cancel_install(self, app_id: str, *, timeout: float = 30.0) -> None:
        """Ask Aurelia to stop and wait until its daemon drops the active install.

        `install stop` only sets Aurelia's abort flag and returns immediately.
        The active registry entry remains until the install command unwinds, so
        its disappearance is the provider-side completion acknowledgement.
        """
        result = await self.command("install", "stop", app_id)
        if not isinstance(result, dict) or result.get("event") not in {"stopping", "not_found"}:
            raise AureliaError("cancel-unconfirmed", "Aurelia did not acknowledge the install stop", retryable=True)

        deadline = time.monotonic() + timeout
        stop_acknowledged = result.get("event") == "stopping"
        while time.monotonic() < deadline:
            rows = await self.command("install", "list")
            if not isinstance(rows, list):
                raise AureliaError("malformed-output", "Aurelia install list was not an array", retryable=True)
            active = any(isinstance(row, dict) and str(row.get("app_id")) == app_id
                         for row in rows)
            if not active and stop_acknowledged:
                return
            if not active and not stop_acknowledged:
                installed = await self.installed_games()
                if any(game.app_id == app_id and game.installed for game in installed):
                    # The install completed while the stop request raced its
                    # registration/terminal transition. The executor will
                    # report completion instead of marking it cancelled.
                    return
            if active and not stop_acknowledged:
                result = await self.command("install", "stop", app_id)
                if isinstance(result, dict) and result.get("event") == "stopping":
                    stop_acknowledged = True
            await asyncio.sleep(0.2)
        raise AureliaError("cancel-timeout", "Aurelia did not finish stopping the install", retryable=True)

    async def update(self, app_id: str) -> Any:
        return await self.command("update", app_id)

    async def dlc(self, app_id: str) -> Any:
        return await self.command("dlc", app_id)

    async def launch(self, app_id: str) -> Any:
        return await self.command("play", app_id, "--no-update", "--no-script", timeout=24 * 3600)

    async def running(self) -> Any:
        return await self.command("running")

    async def stop(self, app_id: str) -> Any:
        return await self.command("stop", app_id)


def map_progress(event: dict[str, Any]) -> dict[str, Any]:
    """Map only fields Aurelia actually supplied; unknown quantities remain None."""
    payload = event.get("payload", event)
    if not isinstance(payload, dict):
        return {}
    downloaded = payload.get("bytes_downloaded", payload.get("downloaded_bytes"))
    total = payload.get("total_bytes")
    percent = payload.get("percent")
    phase = payload.get("state") or payload.get("phase") or payload.get("status")
    result: dict[str, Any] = {
        "downloaded_bytes": downloaded if isinstance(downloaded, int) else None,
        "total_bytes": total if isinstance(total, int) else None,
        # Aurelia reports percentage points (0..100); Acquisitiond uses a
        # normalized fraction (0..1).
        "progress": min(1.0, max(0.0, float(percent) / 100.0))
        if isinstance(percent, (int, float)) else None,
        "download_rate": payload.get("speed_bps") if isinstance(payload.get("speed_bps"), int) else None,
        "eta_seconds": payload.get("eta_seconds") if isinstance(payload.get("eta_seconds"), int) else None,
        "stage": str(phase) if phase else "provider-progress",
    }
    return result


def _merge_aurelia_progress(origin_metadata: dict[str, object],
                            event: dict[str, Any]) -> dict[str, object]:
    """Retain Aurelia's useful raw progress fields in the existing job metadata."""
    fields = (
        "event", "state", "phase", "app_id", "bytes_downloaded",
        "downloaded_bytes", "total_bytes", "percent", "speed_bps",
        "eta_seconds", "depot_id", "depot_bytes_downloaded",
        "depot_total_bytes", "depot_percent", "file", "current_file",
    )
    progress = {key: event[key] for key in fields if key in event}
    result = dict(origin_metadata)
    result["aurelia_progress"] = progress
    return result


class AureliaAcquisitionExecutor:
    provider_id = PROVIDER_ID
    supports_pause = False

    def __init__(self, client: AureliaClient | None = None) -> None:
        self.client = client or AureliaClient()
        self.capabilities = AureliaCapabilities()
        self._active: dict[str, str] = {}

    async def run(self, job: DownloadJob, reporter: JobReporter) -> None:
        app_id = job.provider_job_id or job.content_identity.removeprefix("steam-aurelia:")
        if not app_id.isdecimal():
            raise JobExecutionError("invalid-content", "Aurelia acquisition requires a Steam AppID")
        service_recovery = job.recovery_reason == "service-restart"
        self._active[job.job_id] = app_id
        last_downloaded: int | None = job.downloaded_bytes
        last_total: int | None = job.total_bytes
        origin_metadata = dict(job.origin_metadata)
        try:
            await reporter.metadata(provider_job_id=app_id, backend="aurelia",
                                    provider_state="starting")
            await reporter.state(JobState.STARTING, stage="aurelia-starting")
            # Acquisitiond may recover a persisted active job as queued while
            # Aurelia's daemon is still downloading. Adopt its progress instead
            # of submitting a duplicate install for the same AppID.
            live = await self.client.command("install", "list")
            if isinstance(live, list) and any(
                    isinstance(row, dict) and str(row.get("app_id")) == app_id for row in live):
                await reporter.state(JobState.TRANSFERRING, stage="aurelia-recovered-active")
                while True:
                    await asyncio.sleep(2)
                    live = await self.client.command("install", "list")
                    row = next((item for item in live if isinstance(item, dict)
                                and str(item.get("app_id")) == app_id), None) if isinstance(live, list) else None
                    if row is None:
                        break
                    mapped = map_progress(row)
                    last_downloaded = mapped["downloaded_bytes"]
                    last_total = mapped["total_bytes"]
                    await reporter.progress(mapped["progress"],
                                            downloaded_bytes=last_downloaded,
                                            total_bytes=last_total, stage=mapped["stage"])
                    await reporter.metadata(provider_state=mapped["stage"], backend="aurelia",
                                            provider_job_id=app_id,
                                            origin_metadata=_merge_aurelia_progress(origin_metadata, row))
                    if mapped["download_rate"] is not None or mapped["eta_seconds"] is not None:
                        await reporter.metadata(download_rate=mapped["download_rate"],
                                                eta_seconds=mapped["eta_seconds"])
                installed = await self.client.command("list", "--installed")
                installed_rows = installed.get("games", []) if isinstance(installed, dict) else installed
                if isinstance(installed_rows, list) and any(
                        isinstance(item, dict) and str(item.get("app_id")) == app_id
                        for item in installed_rows):
                    await self._record_installed_metadata(app_id, reporter)
                    await reporter.state(JobState.FINALIZING, stage="aurelia-recovered-finalizing")
                    await reporter.progress(1.0, downloaded_bytes=last_downloaded,
                                            total_bytes=last_total,
                                            stage="aurelia-recovered-finalizing")
                    await reporter.state(JobState.COMPLETED, stage="completed")
                    return
                if service_recovery:
                    raise JobExecutionError(
                        "aurelia-recovery-unconfirmed",
                        "Aurelia no longer reports the interrupted install and the title is not installed; refusing to resubmit automatically.",
                        retryable=False,
                    )
            elif service_recovery:
                # AcquisitionStore requeues active jobs at service startup. Only
                # adopt work Aurelia still reports or reconcile an installation
                # Aurelia confirms complete; never start a second install over
                # ambiguous partial files.
                installed = await self.client.installed_games()
                game = next((item for item in installed
                             if item.app_id == app_id and item.installed), None)
                if game is not None:
                    await self._record_installed_metadata(app_id, reporter)
                    await reporter.state(JobState.FINALIZING, stage="aurelia-recovered-finalizing")
                    await reporter.progress(1.0, downloaded_bytes=last_downloaded,
                                            total_bytes=last_total,
                                            stage="aurelia-recovered-finalizing")
                    await reporter.state(JobState.COMPLETED, stage="completed")
                    return
                raise JobExecutionError(
                    "aurelia-recovery-unconfirmed",
                    "Aurelia no longer reports the interrupted install and the title is not installed; refusing to resubmit automatically.",
                    retryable=False,
                )
            async for event in self.client.install_events(app_id):
                value = map_progress(event)
                state = str(event.get("state", "")).lower()
                if state in {"queued", "downloading", "verifying", "moving"}:
                    # Aurelia may alternate downloading/verifying across depots.
                    # Keep the job active until the command's terminal result;
                    # its stage remains precise without illegal state regressions.
                    target = JobState.STARTING if state == "queued" else JobState.TRANSFERRING
                    await reporter.state(target, stage=value["stage"])
                    last_downloaded = value["downloaded_bytes"]
                    last_total = value["total_bytes"]
                    await reporter.progress(value["progress"], downloaded_bytes=value["downloaded_bytes"],
                                            total_bytes=value["total_bytes"], stage=value["stage"])
                    await reporter.metadata(provider_state=state, backend="aurelia",
                                            provider_job_id=app_id,
                                            download_rate=value["download_rate"],
                                            eta_seconds=value["eta_seconds"],
                                            origin_metadata=_merge_aurelia_progress(origin_metadata, event))
                elif state in {"failed", "error"}:
                    raise JobExecutionError("aurelia-install-failed", "Aurelia reported install failure", retryable=True)
                elif state == "cancelled":
                    raise JobCancelled()
            await reporter.state(JobState.FINALIZING, stage="aurelia-finalizing")
            await self._record_installed_metadata(app_id, reporter)
            await reporter.progress(1.0, downloaded_bytes=last_downloaded,
                                    total_bytes=last_total, stage="aurelia-finalizing")
            await reporter.state(JobState.COMPLETED, stage="completed")
        except JobCancelled:
            raise
        except AureliaError as error:
            raise JobExecutionError(error.code, str(error), retryable=error.retryable) from error
        finally:
            self._active.pop(job.job_id, None)

    async def _record_installed_metadata(self, app_id: str, reporter: JobReporter) -> None:
        """Persist only an install path Aurelia itself reports after installation."""
        metadata: dict[str, object] = {
            "provider_job_id": app_id,
            "backend": "aurelia",
            "provider_state": "installed",
        }
        try:
            games = await self.client.installed_games()
        except AureliaError:
            games = ()
        game = next((item for item in games if item.app_id == app_id and item.installed), None)
        if game is not None and game.install_path:
            metadata["destination"] = game.install_path
            metadata["completion_path"] = game.install_path
        await reporter.metadata(**metadata)

    async def cancel(self, job: DownloadJob) -> bool:
        app_id = self._active.get(job.job_id) or job.provider_job_id
        if app_id:
            try:
                await self.client.cancel_install(str(app_id))
            except AureliaError as error:
                raise JobExecutionError(error.code, str(error), retryable=True) from error
            try:
                installed = await self.client.installed_games()
            except AureliaError as error:
                raise JobExecutionError(error.code, str(error), retryable=True) from error
            if any(game.app_id == str(app_id) and game.installed for game in installed):
                # The operation completed before the stop took effect. The run
                # task owns the durable COMPLETED transition and final metadata.
                return False
        return True

    async def discover_external(self) -> tuple[ExternalAcquisition, ...]:
        """Reconcile Aurelia's live daemon jobs after Acquisitiond restart."""
        try:
            rows = await self.client.command("install", "list")
        except AureliaError as error:
            raise JobExecutionError(error.code, str(error), retryable=True) from error
        if not isinstance(rows, list):
            raise JobExecutionError("malformed-output", "Aurelia install list was not an array", retryable=True)
        records: list[ExternalAcquisition] = []
        for row in rows:
            if not isinstance(row, dict) or not str(row.get("app_id", "")).isdecimal():
                continue
            state = JobState.TRANSFERRING if row.get("is_downloading") else JobState.FINALIZING
            records.append(ExternalAcquisition(
                content_identity=f"steam-aurelia:{row['app_id']}",
                title=str(row.get("name") or row["app_id"]), origin="external",
                provenance="Aurelia active job", provider_job_id=str(row["app_id"]),
                state=state,
                progress=min(1.0, max(0.0, float(row["percent"]) / 100.0))
                if isinstance(row.get("percent"), (int, float)) else None,
                downloaded_bytes=row.get("downloaded_bytes") if isinstance(row.get("downloaded_bytes"), int) else None,
                total_bytes=row.get("total_bytes") if isinstance(row.get("total_bytes"), int) else None,
                stage=str(row.get("status") or "provider-active"), rate=None,
                provider_state="active", backend="aurelia",
                metadata={"provider": PROVIDER_ID},
            ))
        return tuple(records)


class AureliaLaunchController:
    """Coarse launch state relay; Sessiond remains the lifecycle authority.

    A play CLI call may block until game exit. This controller observes Aurelia's
    AppID running record independently and exposes only evidence-backed states.
    It intentionally owns no presentation, input, or Gamescope policy.
    """

    STATES = {"requested", "preparing", "launching", "running", "exited", "failed", "cancelled"}

    def __init__(self, client: AureliaClient | None = None) -> None:
        self.client = client or AureliaClient()
        self.state = "exited"
        self.app_id: str | None = None
        self.error: str | None = None
        self._task: asyncio.Task[Any] | None = None

    def can_launch(self, app_id: str) -> bool:
        return bool(app_id.isdecimal() and int(app_id) > 0 and self.client.available)

    async def request(self, app_id: str) -> None:
        if not self.can_launch(app_id):
            raise AureliaError("unavailable", "Aurelia cannot launch this AppID")
        if self._task and not self._task.done():
            raise AureliaError("busy", "Aurelia launch is already active")
        self.app_id, self.error, self.state = app_id, None, "requested"
        self._task = asyncio.create_task(self._play())
        self.state = "preparing"

    async def _play(self) -> None:
        assert self.app_id is not None
        try:
            # The CLI provides no reliable pre-spawn phase signal. `preparing`
            # remains until the AppID appears in the provider running list.
            self.state = "preparing"
            await self.client.launch(self.app_id)
            if self.state != "cancelled":
                self.state = "exited"
        except asyncio.CancelledError:
            self.state = "cancelled"
            raise
        except AureliaError as error:
            self.error = error.code
            self.state = "failed"
        except Exception as error:
            self.error = type(error).__name__
            self.state = "failed"

    async def observe(self) -> str:
        if self.state in {"requested", "preparing", "launching"} and self.app_id:
            try:
                value = await self.client.running()
            except AureliaError:
                # An unavailable observation is not evidence of exit/failure.
                return self.state
            rows = value.get("running", []) if isinstance(value, dict) else []
            if any(str(row.get("app_id")) == self.app_id for row in rows if isinstance(row, dict)):
                self.state = "running"
        return self.state

    async def stop(self) -> str:
        if self.app_id is None:
            return self.state
        try:
            await self.client.stop(self.app_id)
            self.state = "cancelled"
            if self._task and not self._task.done():
                self._task.cancel()
                await asyncio.gather(self._task, return_exceptions=True)
        except AureliaError as error:
            self.error = error.code
            self.state = "failed"
        return self.state

    def snapshot(self) -> dict[str, object]:
        return {"provider": PROVIDER_ID, "app_id": self.app_id,
                "state": self.state, "error": self.error,
                "detailed_launch_progress": False}
