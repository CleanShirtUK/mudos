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

from ...jobs import DownloadJob, ExternalAcquisition, JobOperation, JobState
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
    updates: bool = True  # Aurelia exposes an update command; progress/cancel are not exposed.
    update_progress: bool = False
    update_cancel: bool = False
    dlc: bool = False  # DLC operations exist upstream; Mudos component jobs are not wired yet.
    launch: bool = True  # Sessiond route exists; still separately gated by explicit opt-in.
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

    @property
    def provider_id(self) -> str:
        return self.app_id

    @property
    def install_dir(self) -> str:
        return self.install_path or ""


@dataclass(frozen=True, slots=True)
class AureliaEntitlement:
    provider_id: str
    title: str
    platform: str = "Steam"
    artwork_url: str = ""
    availability_state: str = "available"


class AureliaEntitlementSource:
    """Authenticated Aurelia library as the authoritative Steam ownership source."""

    provider_id = PROVIDER_ID

    def __init__(self, client: "AureliaClient | None" = None) -> None:
        self.client = client or AureliaClient()
        self.snapshot: tuple[AureliaEntitlement, ...] = ()
        self._installed: tuple[AureliaInstalledGame, ...] = ()
        self.last_error = ""
        self.auth_status = "unauthenticated"

    def refresh(self) -> None:
        async def load() -> None:
            self.auth_status = await self.client.auth_status()
            if self.auth_status != "authenticated":
                self.snapshot, self._installed = (), ()
                self.last_error = self.auth_status
                return
            rows = await self.client.command("list")
            if not isinstance(rows, list):
                raise AureliaError("malformed-output", "Aurelia library was not an array")
            entitlements = []
            installed = []
            for row in rows:
                if not isinstance(row, dict) or row.get("is_owned") is not True:
                    continue
                app_id = str(row.get("app_id", ""))
                if not app_id.isdecimal() or int(app_id) < 1:
                    continue
                name = str(row.get("name") or app_id)
                assets = row.get("assets") if isinstance(row.get("assets"), dict) else {}
                entitlements.append(AureliaEntitlement(
                    app_id, name, "Steam", str(assets.get("header") or assets.get("capsule") or "")))
                if row.get("is_installed") is True:
                    installed.append(AureliaInstalledGame(
                        PROVIDER_ID, app_id, name, True,
                        row.get("install_path") if isinstance(row.get("install_path"), str) else None,
                        row.get("platform") if isinstance(row.get("platform"), str) else None,
                        row.get("update_available") if isinstance(row.get("update_available"), bool) else None))
            self.snapshot, self._installed, self.last_error = tuple(entitlements), tuple(installed), ""
        try:
            asyncio.run(load())
        except Exception as error:
            self.last_error = type(error).__name__
            raise

    def installed(self) -> tuple[AureliaInstalledGame, ...]:
        return self._installed

    def catalogue_authentication_status(self) -> str:
        """Expose the daemon-owned login state to generic catalogue readiness."""
        try:
            return asyncio.run(self.client.auth_status())
        except RuntimeError:
            # Catalogue refresh is synchronous and normally runs on a worker
            # thread. Fail closed if embedded in a running event loop.
            return "unavailable"


class AureliaClient:
    """Secret-free CLI boundary. Credentials are never accepted as arguments."""

    def __init__(self, executable: str | None = None, config_dir: Path | None = None,
                 *, run: Callable[..., Any] | None = None) -> None:
        self.executable = executable or os.environ.get("LULU_AURELIA_EXECUTABLE") or shutil.which("aurelia")
        self.config_dir = config_dir or PATHS.provider_root(PROVIDER_ID) / "aurelia"
        self._run = run
        self._startup_lock = asyncio.Lock()
        self._daemon_ready = False
        self._update_cache: dict[str, tuple[float, dict[str, Any]]] = {}
        self._update_lock = asyncio.Lock()

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

    async def available_platforms(self, app_id: str) -> tuple[str, ...]:
        """Return platforms explicitly represented in Aurelia depot metadata.

        Store-facing OS support is deliberately not used here: only depots with
        an explicit ``config.oslist`` are considered verified acquisition
        choices. An empty result means unknown, not Linux or Windows by default.
        """
        if not app_id.isdecimal() or int(app_id) < 1:
            raise AureliaError("invalid-app-id", "Steam AppID is invalid")
        value = await self.command("depots", app_id)
        if not isinstance(value, dict) or not isinstance(value.get("depots"), list):
            raise AureliaError("malformed-output", "Aurelia depot metadata was not an array")
        found: set[str] = set()
        for depot in value["depots"]:
            if not isinstance(depot, dict) or not str(depot.get("id", "")).isdecimal():
                continue
            config = depot.get("config")
            if isinstance(config, dict):
                oslist = config.get("oslist")
            elif isinstance(config, str):
                # Official Aurelia 0.1.37 and 0.1.38 emit the compatible
                # `depots --json` string form (`"os: windows, lang: ..."`);
                # tolerate a structured OS list as well when supplied.
                oslist = next((part.split(":", 1)[1].strip()
                               for part in config.split(",")
                               if part.strip().casefold().startswith("os:")), None)
            else:
                oslist = None
            if not isinstance(oslist, str):
                continue
            normalized = {part.strip().casefold() for part in oslist.split(",")}
            if "windows" in normalized:
                found.add("windows")
            if "linux" in normalized:
                found.add("linux")
        return tuple(platform for platform in ("windows", "linux") if platform in found)

    async def install_events(self, app_id: str, platform: str):
        if not self.available:
            raise AureliaError("unavailable", "Aurelia executable is unavailable", retryable=True)
        if platform not in {"windows", "linux"}:
            raise AureliaError("unknown-platform", "Aurelia install requires an explicit verified platform")
        self._ensure_config_dir()
        process = await asyncio.create_subprocess_exec(
            self.executable, "--json", "install", app_id, "--platform", platform,
            env=self._environment(),
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
        if not app_id.isdecimal() or int(app_id) < 1:
            raise AureliaError("invalid-app-id", "Aurelia update requires a positive Steam AppID")
        # Updates can be multi-hour depot operations. The JSON command reports a
        # terminal result only; keep it alive until Aurelia confirms its outcome.
        return await self.command("update", app_id, timeout=8 * 60 * 60)

    async def update_availability(self, app_id: str, *, force: bool = False,
                                  cache_seconds: float = 90.0) -> dict[str, Any]:
        """Compare this appmanifest's installed depots with official Aurelia targets.

        `aurelia manifests APPID` is read-only and reports current per-branch
        manifests. Only depot IDs present in the installed appmanifest are
        compared. Steam's StateUpdateRequired flag is kept as independent local
        evidence because Aurelia treats it as update-pending even when manifests
        match. This is manifest-state evidence, not byte-level verification.
        """
        if not app_id.isdecimal() or int(app_id) < 1:
            raise AureliaError("invalid-app-id", "Steam update check requires a positive AppID")
        async with self._update_lock:
            cached = self._update_cache.get(app_id)
            if not force and cached is not None and time.monotonic() - cached[0] < cache_seconds:
                return dict(cached[1])
            try:
                evidence = await self._collect_update_evidence(app_id)
            except AureliaError as error:
                evidence = {
                    "app_id": app_id, "status": "unverifiable", "available": False,
                    "reason": str(error), "provider_error_code": error.code,
                    "branch": None, "state_flags": None, "state_update_required": None,
                    "installed_depots": {}, "target_depots": {}, "changed_depots": {},
                    "checked_at": time.time(), "source": "steam-appmanifest+aurelia-manifests",
                    "evidence_level": "depot-manifest-state-not-file-integrity",
                }
                if error.code in {"invalid-app-id"}:
                    raise
                # Do not cache incomplete or failed evidence as though it were
                # a durable game state; callers may retry a read-only check.
                return evidence
            self._update_cache[app_id] = (time.monotonic(), evidence)
            return dict(evidence)

    async def _collect_update_evidence(self, app_id: str) -> dict[str, Any]:
        games = await self.installed_games()
        matches = [game for game in games if game.app_id == app_id and game.installed]
        if len(matches) != 1 or not matches[0].install_path:
            raise AureliaError(
                "update-unverifiable",
                "Aurelia did not identify exactly one installed path for this AppID.",
                retryable=False,
            )
        install_path = Path(matches[0].install_path)
        appmanifest = install_path.parent.parent / f"appmanifest_{app_id}.acf"
        try:
            manifest_stat = appmanifest.stat()
            raw = appmanifest.read_text(encoding="utf-8", errors="strict")
        except OSError as error:
            raise AureliaError(
                "update-unverifiable", "The installed Steam appmanifest is unavailable.",
                retryable=False,
            ) from error
        try:
            from .provider import SteamProvider
            app = SteamProvider._parse_vdf(raw).get("AppState")
        except (UnicodeError, ValueError, IndexError) as error:
            raise AureliaError("update-unverifiable", "The installed Steam appmanifest is malformed.",
                               retryable=False) from error
        if not isinstance(app, dict) or str(app.get("appid", "")) != app_id:
            raise AureliaError("update-unverifiable", "The appmanifest AppID does not match.", retryable=False)
        try:
            state_flags = int(str(app["StateFlags"]), 10)
        except (KeyError, TypeError, ValueError) as error:
            raise AureliaError("update-unverifiable", "The appmanifest StateFlags value is missing or malformed.",
                               retryable=False) from error
        if not (state_flags & 4):
            raise AureliaError("update-unverifiable", "Steam does not mark this installation fully installed.",
                               retryable=False)
        user_config = app.get("UserConfig", {})
        branch = str(user_config.get("BetaKey") or "public").strip() if isinstance(user_config, dict) else "public"
        if not branch or any(character.isspace() for character in branch):
            raise AureliaError("update-unverifiable", "The appmanifest active branch is malformed.", retryable=False)
        installed_block = app.get("InstalledDepots")
        if not isinstance(installed_block, dict) or not installed_block:
            raise AureliaError("update-unverifiable", "The appmanifest has no installed depot manifests.",
                               retryable=False)
        installed: dict[str, str] = {}
        for depot_id, row in installed_block.items():
            if not str(depot_id).isdecimal() or not isinstance(row, dict):
                raise AureliaError("update-unverifiable", "An installed depot record is malformed.", retryable=False)
            manifest_id = row.get("manifest")
            if not isinstance(manifest_id, str) or not manifest_id.isdecimal():
                raise AureliaError("update-unverifiable",
                                   f"Installed depot {depot_id} has no valid manifest ID.", retryable=False)
            installed[str(depot_id)] = manifest_id

        rows = await self.command("manifests", app_id, timeout=35.0)
        if not isinstance(rows, list):
            raise AureliaError("malformed-manifests", "Aurelia manifests output was not an array.", retryable=True)
        remote: dict[str, str] = {}
        for row in rows:
            if not isinstance(row, dict):
                raise AureliaError("malformed-manifests", "Aurelia returned a malformed depot manifest row.",
                                   retryable=True)
            if str(row.get("branch", "")) != branch:
                continue
            depot_id, manifest_id = str(row.get("depot_id", "")), str(row.get("manifest_id", ""))
            if not depot_id.isdecimal() or not manifest_id.isdecimal():
                raise AureliaError("malformed-manifests", "Aurelia returned invalid depot or manifest IDs.",
                                   retryable=True)
            if depot_id in remote and remote[depot_id] != manifest_id:
                raise AureliaError("malformed-manifests", "Aurelia returned conflicting target manifests.",
                                   retryable=True)
            remote[depot_id] = manifest_id
        missing = sorted(set(installed) - set(remote))
        if missing:
            status, reason = "unverifiable", "Aurelia has no target manifest for installed depot(s): " + ", ".join(missing)
            targets: dict[str, str] = {depot: remote[depot] for depot in installed if depot in remote}
            changed: dict[str, dict[str, str]] = {}
        else:
            targets = {depot: remote[depot] for depot in installed}
            changed = {depot: {"installed": installed[depot], "target": targets[depot]}
                       for depot in installed if installed[depot] != targets[depot]}
            if changed:
                status, reason = "update-available", "Installed depot manifests differ from the active branch targets."
            elif state_flags & 2:
                status, reason = "inconsistent", "Depot manifests match, but Steam still sets StateUpdateRequired."
            else:
                status, reason = "current", "Installed depot manifests match the active branch targets."
        return {
            "app_id": app_id, "status": status, "available": status == "update-available",
            "reason": reason, "branch": branch, "state_flags": state_flags,
            "state_update_required": bool(state_flags & 2), "installed_depots": installed,
            "target_depots": targets, "changed_depots": changed,
            "appmanifest_mtime_ns": manifest_stat.st_mtime_ns,
            "appmanifest_size": manifest_stat.st_size,
            "checked_at": time.time(), "source": "steam-appmanifest+aurelia-manifests",
            "evidence_level": "depot-manifest-state-not-file-integrity",
        }

    async def dlc(self, app_id: str) -> Any:
        return await self.command("dlc", app_id)

    async def spawn_play(self, app_id: str) -> asyncio.subprocess.Process:
        """Start blocking `play` without blocking Sessiond's event loop."""
        if not app_id.isdecimal() or int(app_id) < 1:
            raise AureliaError("invalid-app-id", "Aurelia launch requires a positive AppID")
        if not self.available:
            raise AureliaError("unavailable", "Aurelia executable is unavailable", retryable=True)
        self._ensure_config_dir()
        wrapper = Path(__file__).resolve().parents[4] / "scripts" / "aurelia-graphical-launch.py"
        if not wrapper.is_file():
            raise AureliaError("launch-wrapper-unavailable", "Mudos Aurelia graphical launch wrapper is unavailable")
        return await asyncio.create_subprocess_exec(
            self.executable, "--json", "play", app_id, "--steam", "--no-update", "--script", str(wrapper),
            env=self._environment(), stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL,
            start_new_session=True,
        )

    def launch_failure_detail(self, app_id: str, started_at: float) -> str | None:
        """Return Aurelia's concise structured failure for this launch, if present."""
        logs = self.config_dir / "logs"
        try:
            sessions = sorted(
                (path for path in logs.iterdir() if path.is_dir()),
                key=lambda path: path.stat().st_mtime,
                reverse=True,
            )
        except OSError:
            return None
        for session in sessions:
            try:
                summary = json.loads((session / "summary.json").read_text(encoding="utf-8"))
                if (not isinstance(summary, dict)
                        or str(summary.get("app_id")) != app_id
                        or float(summary.get("timestamp", 0)) < started_at - 2):
                    continue
                events = (session / "events.jsonl").read_text(encoding="utf-8").splitlines()
            except (OSError, ValueError, TypeError, json.JSONDecodeError):
                continue
            for line in reversed(events):
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(event, dict):
                    continue
                if event.get("event_type") != "stage_failure":
                    continue
                metadata = event.get("metadata")
                metadata = metadata if isinstance(metadata, dict) else {}
                stage = str(event.get("stage") or "Launch")
                detail = str(metadata.get("error_message") or event.get("message") or "").strip()
                if detail:
                    return f"{stage}: {detail}"[:320]
            # Aurelia versions have emitted a terminal Failure summary without
            # a stage_failure event. Preserve the structured verification detail
            # so an early CLI exit is actionable instead of silently generic.
            verification = summary.get("verification")
            if isinstance(verification, dict):
                status = str(verification.get("detailed_status") or "").strip()
                result = str(summary.get("result") or "").strip()
                if status and (result == "Failure" or status not in {"verified", "game_executable_not_found"}):
                    exit_code = verification.get("exit_code")
                    suffix = f" (exit code {exit_code})" if isinstance(exit_code, int) else ""
                    return f"Launch verification {status.replace('_', ' ')}{suffix}"[:320]
        return None

    async def running_record(self, app_id: str) -> dict[str, Any] | None:
        """Read Aurelia's per-AppID record while its blocking play command runs.

        Asking the daemon to execute `running` can contend with a long-running
        `play` request in some Aurelia builds. The record is Aurelia's own source
        of truth for stop/running and is atomically refreshed by its launch code.
        """
        def read_record() -> dict[str, Any] | None:
            path = self.config_dir / "running" / f"{app_id}.json"
            try:
                value = json.loads(path.read_text(encoding="utf-8"))
            except FileNotFoundError:
                return None
            except (OSError, json.JSONDecodeError) as error:
                raise AureliaError("malformed-running-state", "Aurelia running record is unreadable") from error
            if (not isinstance(value, dict) or str(value.get("app_id")) != app_id
                    or not isinstance(value.get("pid"), int) or value["pid"] < 2):
                raise AureliaError("malformed-running-state", "Aurelia running record has invalid AppID/PID fields")
            return value

        return await asyncio.to_thread(read_record)

    def daemon_alive(self) -> bool:
        """Check the selected Aurelia daemon endpoint without issuing a CLI call."""
        environment = self._environment()
        endpoint = environment.get("AURELIA_DAEMON_SOCKET")
        if not endpoint:
            return False
        socket_path = Path(endpoint)
        try:
            if not stat.S_ISSOCK(socket_path.stat().st_mode):
                return False
            marker = json.loads(socket_path.with_suffix(".info").read_text(encoding="utf-8"))
            pid = marker.get("pid") if isinstance(marker, dict) else None
            return isinstance(pid, int) and pid > 1 and Path(f"/proc/{pid}").exists()
        except (OSError, json.JSONDecodeError):
            return False

    async def stop(self, app_id: str) -> Any:
        if not app_id.isdecimal() or int(app_id) < 1:
            raise AureliaError("invalid-app-id", "Aurelia stop requires a positive AppID")
        if not self.available:
            raise AureliaError("unavailable", "Aurelia executable is unavailable", retryable=True)
        self._ensure_config_dir()
        environment = self._environment()
        # Aurelia's stop command terminates the tracked process tree locally, but
        # normally forwards through its daemon. During `play`, that daemon may be
        # occupied; bypass it rather than waiting behind the blocking play request.
        environment["AURELIA_NO_DAEMON"] = "1"
        process: asyncio.subprocess.Process | None = None
        try:
            process = await asyncio.create_subprocess_exec(
                self.executable, "--json", "stop", app_id, env=environment,
                stdin=asyncio.subprocess.DEVNULL, stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
            stdout, _stderr = await asyncio.wait_for(process.communicate(), timeout=30)
        except (OSError, TimeoutError, asyncio.TimeoutError) as error:
            if process is not None and process.returncode is None:
                process.terminate()
                try:
                    await asyncio.wait_for(process.wait(), timeout=2)
                except TimeoutError:
                    process.kill()
                    await process.wait()
            raise AureliaError("stop-failed", "Aurelia could not complete the game stop", retryable=True) from error
        if process.returncode:
            raise AureliaError("stop-failed", f"Aurelia game stop failed (exit {process.returncode})", retryable=True)
        try:
            return json.loads(stdout) if stdout.strip() else None
        except json.JSONDecodeError as error:
            raise AureliaError("malformed-output", "Aurelia stop returned malformed JSON") from error


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
    # Aurelia owns both the Steam-library configuration and per-AppID removal.
    # Never substitute SteamCMD or direct Steam-library deletion here.
    supports_uninstall = True
    uninstall_progress_supported = False

    def __init__(self, client: AureliaClient | None = None) -> None:
        self.client = client or AureliaClient()
        self.capabilities = AureliaCapabilities()
        self._active: dict[str, str] = {}
        from .provider import SteamProvider
        self._steam_provider = SteamProvider()

    def uninstall_capability(self, game) -> dict[str, object]:
        app_id = str(getattr(game, "provider_id", ""))
        if not app_id.isdecimal() or int(app_id) < 1:
            return {"supported": False,
                    "reason": "Aurelia uninstall requires a valid Steam AppID."}
        return {"supported": True,
                "description": "Uninstall this Steam game through Aurelia."}

    async def run(self, job: DownloadJob, reporter: JobReporter) -> None:
        app_id = job.provider_job_id or job.content_identity.removeprefix("steam-aurelia:").removeprefix("steam:")
        if not app_id.isdecimal():
            raise JobExecutionError("invalid-content", "Aurelia acquisition requires a Steam AppID")
        if job.operation is JobOperation.REMOVE:
            if job.recovery_reason and job.recovery_reason.startswith("service-restart"):
                raise JobExecutionError(
                    "orphaned-removal-incomplete",
                    "An interrupted Aurelia removal is never replayed automatically; provider outcome requires reconciliation.",
                    retryable=False,
                )
            await self._uninstall(app_id, reporter)
            return
        if job.operation is JobOperation.UPDATE:
            await self._update(app_id, job, reporter)
            return
        service_recovery = job.recovery_reason == "service-restart"
        selected_platform = job.origin_metadata.get("steam_platform")
        if selected_platform not in {"windows", "linux"}:
            raise JobExecutionError(
                "steam-platform-unknown",
                "This Steam installation job has no persisted, verified platform selection.",
                retryable=False,
            )
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
                    await self._record_installed_metadata(app_id, reporter,
                                                         expected_platform=str(selected_platform))
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
                    await self._record_installed_metadata(app_id, reporter,
                                                         expected_platform=str(selected_platform))
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
            async for event in self.client.install_events(app_id, str(selected_platform)):
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
            await self._record_installed_metadata(app_id, reporter,
                                                 expected_platform=str(selected_platform))
            await reporter.progress(1.0, downloaded_bytes=last_downloaded,
                                    total_bytes=last_total, stage="aurelia-finalizing")
            await reporter.state(JobState.COMPLETED, stage="completed")
        except JobCancelled:
            raise
        except AureliaError as error:
            raise JobExecutionError(error.code, str(error), retryable=error.retryable) from error
        finally:
            self._active.pop(job.job_id, None)

    async def _uninstall(self, app_id: str, reporter: JobReporter) -> None:
        await reporter.metadata(provider_job_id=app_id, backend="aurelia",
                                provider_state="uninstalling")
        await reporter.state(JobState.STARTING, stage="aurelia-uninstall-starting")
        try:
            await self.client.command("uninstall", app_id)
            installed = await self.client.installed_games()
        except AureliaError as error:
            raise JobExecutionError(
                f"aurelia-{error.code}",
                f"Aurelia could not uninstall this Steam game ({error.code}).",
                retryable=error.retryable,
            ) from error
        if any(game.app_id == app_id and game.installed for game in installed):
            raise JobExecutionError(
                "aurelia-uninstall-unconfirmed",
                "Aurelia completed the uninstall command but still reports the game installed.",
                retryable=True,
            )
        await reporter.state(JobState.FINALIZING, stage="aurelia-uninstall-finalizing")
        await reporter.progress(1.0, stage="aurelia-uninstall-complete")
        await reporter.state(JobState.COMPLETED, stage="completed")

    async def _update(self, app_id: str, job: DownloadJob, reporter: JobReporter) -> None:
        """Run one Aurelia update; the CLI exposes terminal status, not safe controls/progress."""
        if self._steam_provider.presentation_pids(app_id):
            raise JobExecutionError("steam-game-running",
                                    "Close this game before updating its installed files.",
                                    retryable=True)
        origin_metadata = dict(job.origin_metadata)
        if job.recovery_reason == "service-restart":
            # Continuation is shell-memory only. Recovery must never rehydrate
            # Update & Launch authority from the persisted job row.
            origin_metadata.update({"launch_intent": "none", "launch_policy": "background-only"})
            await reporter.metadata(origin="steam-update-background",
                                    origin_metadata=origin_metadata,
                                    recovery_reason="service-restart")
        await reporter.metadata(provider_job_id=app_id, backend="aurelia",
                                provider_state="checking-update")
        await reporter.state(JobState.STARTING, stage="aurelia-update-check")
        try:
            selected_platform = job.origin_metadata.get("steam_platform")
            live = await self.client.command("install", "list", timeout=15.0)
            if isinstance(live, list) and any(
                    isinstance(row, dict) and str(row.get("app_id")) == app_id for row in live):
                # Aurelia may use its install registry while applying an update.
                # Adopt but never submit another operation during service recovery.
                await reporter.state(JobState.TRANSFERRING, stage="aurelia-update-recovered")
                deadline = time.monotonic() + 6 * 60 * 60
                while time.monotonic() < deadline:
                    await asyncio.sleep(2)
                    live = await self.client.command("install", "list", timeout=15.0)
                    row = next((item for item in live if isinstance(item, dict)
                                and str(item.get("app_id")) == app_id), None) if isinstance(live, list) else None
                    if row is None:
                        break
                    mapped = map_progress(row)
                    await reporter.progress(mapped["progress"],
                                             downloaded_bytes=mapped["downloaded_bytes"],
                                             total_bytes=mapped["total_bytes"],
                                             stage="aurelia-update-recovered")
                else:
                    raise JobExecutionError("aurelia-update-timeout",
                                            "Aurelia's recovered update did not finish in time.",
                                            retryable=True)
                availability = await self.client.update_availability(app_id, force=True)
                await self._confirm_updated(app_id, availability, reporter)
                return

            availability = await self.client.update_availability(app_id, force=True)
            if availability.get("status") == "current":
                # A recovered operation may have completed before Acquisitiond
                # or another client completed it before user confirmation.
                await self._confirm_updated(app_id, availability, reporter)
                return
            if availability.get("status") != "update-available":
                raise self._verification_failure(availability, phase="before")
            if job.recovery_reason == "service-restart":
                raise JobExecutionError(
                    "aurelia-update-recovery-ambiguous",
                    "Aurelia still reports an update after restart; it was not restarted automatically. Retry from Mudos.",
                    retryable=False,
                )
            if availability.get("pinned"):
                raise JobExecutionError("aurelia-update-pinned",
                                        "This Steam game is pinned and Aurelia will not update it.",
                                        retryable=False)
            if self._steam_provider.presentation_pids(app_id):
                raise JobExecutionError("steam-game-running",
                                        "Close this game before updating its installed files.",
                                        retryable=True)
            await reporter.metadata(provider_state="updating")
            await reporter.state(JobState.TRANSFERRING, stage="aurelia-updating")
            update_task = asyncio.create_task(self.client.update(app_id))
            while not update_task.done():
                await asyncio.sleep(1.5)
                if update_task.done():
                    break
                try:
                    live = await self.client.command("install", "list", timeout=12.0)
                except AureliaError:
                    # Update remains authoritative; lack of optional live
                    # telemetry leaves an indeterminate state, not failure.
                    continue
                row = next((item for item in live if isinstance(item, dict)
                            and str(item.get("app_id")) == app_id), None) if isinstance(live, list) else None
                if row is not None:
                    mapped = map_progress(row)
                    stage_text = str(mapped.get("stage") or "").casefold()
                    stage = ("downloading" if "download" in stage_text else
                             "verifying" if "verif" in stage_text else
                             "applying" if any(word in stage_text for word in ("moving", "apply", "install")) else
                             "aurelia-updating")
                    await reporter.state(JobState.TRANSFERRING, stage=stage)
                    await reporter.progress(mapped.get("progress"),
                                            downloaded_bytes=mapped.get("downloaded_bytes"),
                                            total_bytes=mapped.get("total_bytes"), stage=stage)
            await update_task
            await reporter.state(JobState.FINALIZING, stage="aurelia-update-verifying")
            verified = await self.client.update_availability(app_id, force=True)
            await self._confirm_updated(app_id, verified, reporter)
        except JobExecutionError:
            raise
        except AureliaError as error:
            raise JobExecutionError(f"aurelia-{error.code}",
                                    ("Aurelia's update result is uncertain after a timeout; check the Downloads view "
                                     "and Steam status before retrying." if error.code == "timeout" else
                                     f"Aurelia could not update this Steam game ({error.code})."),
                                    # A timed-out CLI may have left the daemon
                                    # operation running. Do not offer Retry and
                                    # risk a duplicate depot operation.
                                     retryable=False if error.code == "timeout" else error.retryable) from error

    @staticmethod
    def _verification_failure(evidence: dict[str, Any], *, phase: str) -> JobExecutionError:
        status = str(evidence.get("status", "unverifiable"))
        code = ("steam-update-unapplied" if status == "update-available" else
                "steam-update-inconsistent" if status == "inconsistent" else
                "steam-update-unverifiable")
        return JobExecutionError(
            code,
            f"Steam update verification was {status} {phase} the Aurelia command: "
            f"{evidence.get('reason', 'required manifest evidence is missing')}",
            retryable=False,
            details={"phase": phase, "evidence": evidence},
        )

    async def _confirm_updated(self, app_id: str, availability: dict[str, Any],
                               reporter: JobReporter) -> None:
        if availability.get("status") != "current":
            raise self._verification_failure(availability, phase="after")
        installed = await self.client.installed_games()
        game = next((item for item in installed if item.app_id == app_id and item.installed), None)
        if game is None:
            raise JobExecutionError("aurelia-update-install-missing",
                                    "Aurelia no longer confirms this game is installed.", retryable=False)
        await reporter.metadata(provider_state="update-verified-current", backend="aurelia",
                                destination=game.install_path,
                                completion_path=game.install_path)
        await reporter.progress(None, stage="aurelia-update-verified")
        await reporter.state(JobState.FINALIZING, stage="aurelia-update-verified")
        await reporter.state(JobState.COMPLETED, stage="completed")

    async def _record_installed_metadata(self, app_id: str, reporter: JobReporter,
                                         *, expected_platform: str | None = None) -> None:
        """Persist Aurelia's install path and reject a known platform mismatch."""
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
        if expected_platform is not None:
            actual = game.platform.casefold() if game and isinstance(game.platform, str) else ""
            if actual not in {"windows", "linux"}:
                raise JobExecutionError(
                    "steam-installed-platform-unknown",
                    "Aurelia cannot verify the installed platform; this installation was not confirmed.",
                    retryable=False,
                )
            if actual != expected_platform:
                raise JobExecutionError(
                    "steam-installed-platform-mismatch",
                    f"Aurelia reports {actual} content but this job selected {expected_platform}; no platform switch was accepted.",
                    retryable=False,
                )
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
