"""SteamCMD parser and provider-specific acquisition executor.

SteamCMD's progress counters describe its install/staging work.  They are
intentionally exposed through the existing generic byte fields only because
that is the current JobReporter contract; they must not be described as wire
bytes.
"""

from __future__ import annotations

from dataclasses import dataclass
import asyncio
import json
import logging
import os
from pathlib import Path
import pwd
import re
import signal
import shutil
import tomllib
from typing import Callable, Mapping
from urllib.request import Request, urlopen

from ...jobs import DownloadJob, JobState
from ...job_manager import JobExecutionError, JobReporter
from ...paths import PATHS
from ...credential import CredentialBroker, CredentialInput, SecretStore


LOGGER = logging.getLogger("lulu.steamcmd")


class SteamCmdError(JobExecutionError):
    """A normalized failure from the SteamCMD provider boundary."""

    def __init__(self, code: str, message: str, *, details: dict[str, object] | None = None,
                 retryable: bool = False) -> None:
        super().__init__(code, message, details=details, retryable=retryable)


STEAM_APP_DETAILS_URL = "https://store.steampowered.com/api/appdetails"


class SteamPlatformResolver:
    """Resolve Steam's actual depot platform policy, not UI platform labels."""

    def __init__(self, cache_path: Path | None = None,
                 request: Callable[[str, float], bytes] | None = None) -> None:
        self.cache_path = cache_path or (PATHS.config_root / "steam-platforms.json")
        self._request = request or self._http_request

    def resolve(self, app_id: str, timeout: float = 12.0) -> str | None:
        cached = load_platforms(self.cache_path).get(app_id)
        if cached in {"linux", "windows"}:
            return cached
        try:
            payload = json.loads(self._request(
                f"{STEAM_APP_DETAILS_URL}?appids={app_id}&filters=platforms", timeout
            ))
            record = payload.get(app_id) if isinstance(payload, dict) else None
            data = record.get("data") if isinstance(record, dict) and record.get("success") else None
            platforms = data.get("platforms", {}) if isinstance(data, dict) else {}
            if not isinstance(platforms, dict):
                return None
            # Prefer native Linux depots. Windows is intentional for Proton;
            # macOS-only and missing platform data remain unsupported.
            if platforms.get("linux") is True:
                platform = "linux"
            elif platforms.get("windows") is True:
                platform = "windows"
            else:
                return None
            self._persist(app_id, platform)
            return platform
        except (OSError, TypeError, ValueError, json.JSONDecodeError):
            return None

    @staticmethod
    def _http_request(url: str, timeout: float) -> bytes:
        request = Request(url, headers={"Accept": "application/json", "User-Agent": "Lulu/1"})
        with urlopen(request, timeout=timeout) as response:
            if int(response.status) != 200:
                raise OSError(f"Steam app details returned HTTP {response.status}")
            return response.read()

    def _persist(self, app_id: str, platform: str) -> None:
        values = load_platforms(self.cache_path)
        values[app_id] = platform
        try:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.cache_path.with_suffix(".tmp")
            temporary.write_text(json.dumps(values, sort_keys=True) + "\n")
            temporary.replace(self.cache_path)
        except OSError:
            pass


@dataclass(frozen=True, slots=True)
class SteamCmdObservation:
    kind: str
    progress: float | None = None
    staged_bytes: int | None = None
    total_staged_bytes: int | None = None
    message: str = ""


class SteamCmdParser:
    """Turn observed SteamCMD lines into safe provider observations."""

    _progress = re.compile(
        r"Update state \((0x[0-9a-f]+)\)\s+([^,]+),\s+progress:\s*"
        r"([0-9]+(?:\.[0-9]+)?)\s*\(\s*([0-9]+)\s*/\s*([0-9]+)\s*\)",
        re.IGNORECASE,
    )
    _success = re.compile(r"Success! App '([0-9]+)' (fully installed|already up to date)\.", re.I)

    def parse(self, line: str) -> SteamCmdObservation | None:
        clean = line.replace("\x1b[0m", "").replace("\x1b[33;1m", "").replace("\x1b[1m", "")
        clean = clean.replace("\r", "").strip()
        if not clean:
            return None
        match = self._progress.search(clean)
        if match:
            state, label = match.group(1).lower(), match.group(2).strip().lower()
            progress = float(match.group(3)) / 100.0
            staged, total = int(match.group(4)), int(match.group(5))
            if state == "0x3" or label == "reconfiguring":
                return SteamCmdObservation("starting")
            if state == "0x61" or label == "downloading":
                return SteamCmdObservation("transferring", progress, staged, total)
            if state == "0x101" or label == "committing":
                # SteamCMD resets the numerator for this stage.  Do not pass it
                # to JobReporter, where it would look like download progress.
                return SteamCmdObservation("finalizing")
        success = self._success.search(clean)
        if success:
            return SteamCmdObservation("success", message=success.group(2).lower())
        if "Cached credentials not found" in clean:
            return SteamCmdObservation("authentication-required")
        if "not online or not logged in" in clean or "Login Failure" in clean:
            return SteamCmdObservation("authentication-required")
        if "ERROR (Timeout)" in clean or "Retrying..." in clean:
            return SteamCmdObservation("network-error")
        if "Invalid platform" in clean:
            return SteamCmdObservation("invalid-platform")
        if clean.startswith("ERROR!") or "ERROR!" in clean:
            return SteamCmdObservation("failure", message=clean)
        return None


def load_platforms(path: Path | None = None) -> dict[str, str]:
    """Load explicit Steam AppID platform policy without reading credentials."""
    path = path or Path(os.environ.get(
        "LULU_STEAM_PLATFORM_METADATA", PATHS.config_root / "steam-platforms.json"
    ))
    try:
        value = json.loads(path.read_text())
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return {}
    if not isinstance(value, dict):
        return {}
    return {str(key): str(platform).casefold() for key, platform in value.items()
            if str(platform).casefold() in {"windows", "linux"}}


class SteamCmdExecutor:
    """Execute one SteamCMD AppID operation; cancellation is unsupported."""

    def __init__(self, *, executable: str | None = None, account: str | None = None,
                 install_dir: Path | None = None, platforms: Mapping[str, str] | None = None,
                 parser: SteamCmdParser | None = None,
                 platform_resolver: SteamPlatformResolver | None = None,
                 credentials: CredentialBroker | None = None,
                 request_credential: object | None = None) -> None:
        self.executable = executable or os.environ.get("LULU_STEAMCMD") or str(PATHS.steamcmd_executable)
        self.account = account or os.environ.get("LULU_STEAM_ACCOUNT", "")
        if not self.account:
            try:
                path = PATHS.plugins_root / "steam" / "settings.toml"
                with path.open("rb") as stream:
                    self.account = str(tomllib.load(stream).get("settings", {}).get("username", "")).strip()
            except (FileNotFoundError, OSError, tomllib.TOMLDecodeError, AttributeError):
                pass
        configured_library = os.environ.get("LULU_STEAM_LIBRARY")
        self.install_dir = install_dir
        if self.install_dir is None and configured_library:
            self.install_dir = Path(configured_library)
        self.install_dir = self.install_dir or PATHS.steam_library_root
        self.platforms = dict(platforms or load_platforms())
        self.platform_resolver = platform_resolver or SteamPlatformResolver()
        self.parser = parser or SteamCmdParser()
        self.credentials = credentials or CredentialBroker()
        self.request_credential = request_credential
        self.secrets = SecretStore()

    def _require_executable(self) -> str:
        """Resolve only the explicit override or the canonical Mudos path."""
        candidate = self.executable
        path = Path(candidate).expanduser()
        if not path.is_absolute() and os.environ.get("LULU_STEAMCMD"):
            resolved = shutil.which(candidate)
            if resolved:
                candidate, path = resolved, Path(resolved)
        if not path.is_file() or not os.access(path, os.X_OK):
            raise SteamCmdError(
                "steamcmd-unavailable",
                "SteamCMD is not provisioned or executable",
                details={"executable": str(path)},
                retryable=True,
            )
        return candidate

    @staticmethod
    def _metadata(path: Path) -> dict[str, object]:
        """Return filesystem identity only; never read the file."""
        try:
            stat = path.stat()
            return {
                "exists": True,
                "inode": stat.st_ino,
                "size": stat.st_size,
                "mtime_ns": stat.st_mtime_ns,
                "ctime_ns": stat.st_ctime_ns,
                "owner": pwd.getpwuid(stat.st_uid).pw_name,
                "group": str(stat.st_gid),
                "mode": oct(stat.st_mode & 0o7777),
            }
        except (FileNotFoundError, PermissionError, KeyError, OSError):
            return {"exists": False}

    def _cache_snapshot(self) -> dict[str, object]:
        home = Path(os.environ.get("HOME", str(Path.home()))).expanduser()
        steam_root = home / ".steam"
        cache = {
            "steam_root": str(steam_root),
            "steam_root_exists": steam_root.is_dir(),
            "steam_token": self._metadata(steam_root / "steam.token"),
            "registry_vdf": self._metadata(steam_root / "registry.vdf"),
        }
        executable = Path(self.executable).expanduser()
        return {
            "uid": os.geteuid(),
            "user": pwd.getpwuid(os.geteuid()).pw_name,
            "home": str(home),
            "steamcmd_root": str(PATHS.steamcmd_root),
            "executable": str(executable),
            "executable_metadata": self._metadata(executable),
            "cache": cache,
        }

    @staticmethod
    def _cache_events(before: dict[str, object], after: dict[str, object]) -> list[str]:
        events: list[str] = []
        before_cache = before["cache"]
        after_cache = after["cache"]
        assert isinstance(before_cache, dict) and isinstance(after_cache, dict)
        for label, key in (("steam.token", "steam_token"), ("registry.vdf", "registry_vdf")):
            old = before_cache[key]
            new = after_cache[key]
            assert isinstance(old, dict) and isinstance(new, dict)
            if not old.get("exists") and new.get("exists"):
                events.append(f"{label} created")
            elif old.get("exists") and not new.get("exists"):
                events.append(f"{label} deleted")
            elif old.get("inode") != new.get("inode"):
                events.append(f"{label} replaced inode {old.get('inode')} -> {new.get('inode')}")
            elif old.get("mtime_ns") != new.get("mtime_ns"):
                events.append(f"{label} mtime changed")
        return events

    @staticmethod
    def _diagnostic(record: dict[str, object]) -> None:
        # JSON is deliberately limited to metadata and normalized observations.
        def redact(value: object, key: str = "") -> object:
            if any(word in key.casefold() for word in ("password", "secret", "cookie", "credential_value")):
                return "[REDACTED]"
            if isinstance(value, dict):
                return {str(child_key): redact(child_value, str(child_key))
                        for child_key, child_value in value.items()}
            if isinstance(value, list):
                return [redact(child) for child in value]
            return value

        LOGGER.info("steamcmd_lifecycle %s", json.dumps(redact(record), sort_keys=True))

    @staticmethod
    def _app_id(identity: str) -> str:
        value = identity.removeprefix("steam:")
        if not value.isdecimal() or int(value) < 1:
            raise SteamCmdError("invalid-content-identity", "Steam content identity is not a valid AppID")
        return value

    def command(self, app_id: str) -> list[str]:
        platform = self.platforms.get(app_id)
        if platform not in {"windows", "linux"}:
            raise SteamCmdError("unknown-platform", f"Steam platform is unknown for AppID {app_id}")
        if not self.account:
            raise SteamCmdError("authentication-required", "Steam download authentication required")
        command = [self.executable]
        if platform == "windows":
            command += ["+@sSteamCmdForcePlatformType", "windows"]
        command += ["+force_install_dir", str(self.install_dir), "+login", self.account,
                    "+app_update", app_id, "validate", "+quit"]
        return command

    def uninstall_command(self, app_id: str) -> list[str]:
        """Build SteamCMD's provider-native uninstall operation.

        SteamCMD updates the app manifest and owns the Steam library mutation;
        Mudos deliberately never removes Steam files directly.
        """
        platform = self.platforms.get(app_id)
        if platform not in {"windows", "linux"}:
            raise SteamCmdError("unknown-platform", f"Steam platform is unknown for AppID {app_id}")
        if not self.account:
            raise SteamCmdError("authentication-required", "Steam download authentication required")
        command = [self.executable]
        if platform == "windows":
            command += ["+@sSteamCmdForcePlatformType", "windows"]
        command += ["+login", self.account, "+app_uninstall", app_id, "+quit"]
        return command

    async def uninstall(self, job: DownloadJob, reporter: JobReporter) -> None:
        app_id = self._app_id(job.content_identity)
        installed = await asyncio.to_thread(self._installed_owned_app, app_id)
        if installed is None:
            raise SteamCmdError("not-installed", "Steam title is not installed in the Mudos library")
        command = self.uninstall_command(app_id)
        command[0] = self._require_executable()
        await reporter.state(JobState.STARTING, stage="removing")
        process = None
        try:
            process = await asyncio.create_subprocess_exec(
                *command, stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
                start_new_session=True,
            )
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=120)
        except asyncio.TimeoutError as error:
            if process is not None and process.returncode is None:
                process.kill()
            if process is not None:
                await process.wait()
            raise SteamCmdError("provider-timeout", "Steam uninstall timed out", retryable=True) from error
        except OSError as error:
            raise SteamCmdError("provider-failure", "Steam uninstall could not start", retryable=True) from error
        if process.returncode != 0:
            raise SteamCmdError("provider-failure", "Steam uninstall failed", details={"exit_code": process.returncode})
        await reporter.state(JobState.FINALIZING, stage="finalizing")

    def _installed_owned_app(self, app_id: str) -> InstalledSteamGame | None:
        for game in self._provider_installed_games():
            if game.app_id == app_id and Path(game.library_root).resolve() == Path(self.install_dir).resolve():
                return game
        return None

    def _provider_installed_games(self) -> list[InstalledSteamGame]:
        # Import locally to keep the command executor independent of the
        # session Steam client adapter and easy to fixture in tests.
        from .provider import SteamProvider
        return SteamProvider().list_installed(roots=(self.install_dir,))

    async def run(self, job: DownloadJob, reporter: JobReporter) -> None:
        if job.operation.value == "remove":
            await self.uninstall(job, reporter)
            return
        app_id = self._app_id(job.content_identity)
        if app_id not in self.platforms:
            platform = await asyncio.to_thread(self.platform_resolver.resolve, app_id)
            if platform is not None:
                self.platforms[app_id] = platform
        command = self.command(app_id)
        command[0] = self._require_executable()
        self.install_dir.mkdir(parents=True, exist_ok=True)
        before = self._cache_snapshot()
        diagnostic: dict[str, object] = {
            "job_id": job.job_id,
            "app_id": app_id,
            "pid": None,
            "login_mode": "cached candidate",
            "cached_credentials_reported": False,
            "password_prompt_observed": False,
            "guard_prompt_observed": False,
            "login_success": False,
            "exit_code": None,
            "exit_signal": None,
            "quit_requested": True,
            "normal_quit": False,
            "client_version": None,
            "cache_before": before,
        }
        self._diagnostic({"event": "start", **diagnostic})
        process = await asyncio.create_subprocess_exec(
            *command, stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            start_new_session=True,
        )
        diagnostic["pid"] = getattr(process, "pid", None)
        success = False
        finalizing = False

        async def consume(stream: asyncio.StreamReader) -> None:
            nonlocal success, finalizing
            buffer = ""
            prompt_seen = False
            challenge_seen = False
            while (chunk := await stream.read(256)):
                buffer += chunk.decode(errors="replace")
                lower = buffer.casefold()
                version_match = re.search(r"client version:\s*([0-9]+)", lower)
                if version_match:
                    diagnostic["client_version"] = version_match.group(1)
                if "logging in using cached credentials" in lower:
                    diagnostic["cached_credentials_reported"] = True
                    diagnostic["login_success"] = True
                if "logged in ok" in lower:
                    diagnostic["login_success"] = True
                # SteamCMD emits its password prompt without a newline.
                if not prompt_seen and ("password:" in lower or "password " in lower):
                    diagnostic["password_prompt_observed"] = True
                    diagnostic["login_mode"] = "credential supplied"
                    await self._answer(CredentialInput.SECRET, "SteamCMD password", "Password", process)
                    prompt_seen = True
                    buffer = ""
                if not challenge_seen and ("guard code" in lower or "two-factor" in lower or "authenticator" in lower):
                    diagnostic["guard_prompt_observed"] = True
                    diagnostic["login_mode"] = "interactive required"
                    await self._answer(CredentialInput.CODE, "Steam Guard", "Authentication code", process,
                                       min_length=5, max_length=5)
                    challenge_seen = True
                    buffer = ""
                while "\n" in buffer:
                    text, buffer = buffer.split("\n", 1)
                    observation = self.parser.parse(text)
                    lower = text.casefold()
                    if observation is None:
                        continue
                    if observation.kind == "starting":
                        await reporter.state(JobState.STARTING, stage="starting")
                    elif observation.kind == "transferring":
                        await reporter.state(JobState.TRANSFERRING, stage="transferring")
                        await reporter.progress(observation.progress,
                                                downloaded_bytes=observation.staged_bytes,
                                                total_bytes=observation.total_staged_bytes,
                                                stage="transferring")
                    elif observation.kind == "finalizing":
                        finalizing = True
                        await reporter.state(JobState.FINALIZING, stage="finalizing")
                        await reporter.progress(None, downloaded_bytes=None, total_bytes=None,
                                                stage="finalizing")
                    elif observation.kind == "success":
                        success = True
                        if not finalizing:
                            await reporter.state(JobState.FINALIZING, stage="finalizing")
                    elif observation.kind == "authentication-required":
                        raise SteamCmdError("authentication-required", "SteamCMD authentication required")
                    elif observation.kind == "network-error":
                        raise SteamCmdError("network-error", "SteamCMD could not connect to Steam", retryable=True)
                    elif observation.kind == "invalid-platform":
                        raise SteamCmdError("invalid-platform", "SteamCMD rejected the requested platform")
                    elif observation.kind == "failure":
                        raise SteamCmdError("steamcmd-failure", "SteamCMD reported a download failure",
                                            details={"provider_message": observation.message})

        def record_exit(returncode: int | None) -> None:
            diagnostic["exit_code"] = returncode if returncode is not None and returncode >= 0 else None
            diagnostic["exit_signal"] = -returncode if returncode is not None and returncode < 0 else None
            diagnostic["normal_quit"] = returncode == 0 and success
            after = self._cache_snapshot()
            diagnostic["cache_after"] = after
            diagnostic["cache_events"] = self._cache_events(before, after)
            diagnostic["login_success"] = bool(diagnostic["login_success"] or success)
            self._diagnostic({"event": "exit", **diagnostic})

        try:
            await asyncio.wait_for(asyncio.gather(consume(process.stdout), consume(process.stderr)), timeout=120)
        except asyncio.CancelledError:
            if process.returncode is None:
                try:
                    os.killpg(process.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
            await process.wait()
            record_exit(process.returncode)
            raise
        except Exception:
            # Parser/authentication failures are terminal for this operation;
            # do not leave a SteamCMD child behind. This is not job
            # cancellation and makes no claim about user-requested aborts.
            if process.returncode is None:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            await process.wait()
            record_exit(process.returncode)
            raise
        returncode = await process.wait()
        record_exit(returncode)
        if returncode != 0 or not success:
            raise SteamCmdError("steamcmd-failure", "SteamCMD did not complete successfully",
                                details={"exit_code": returncode, "success_result": success,
                                         "finalizing_seen": finalizing})

    async def authenticate(self) -> dict[str, str]:
        """Verify SteamCMD acquisition authentication without secret argv/env."""
        if not self.account:
            raise SteamCmdError("authentication-required", "SteamCMD username is not configured")
        process = await asyncio.create_subprocess_exec(
            self._require_executable(), "+login", self.account, "+quit",
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE, start_new_session=True)
        before = self._cache_snapshot()
        diagnostic: dict[str, object] = {
            "event": "start",
            "operation": "authenticate",
            "pid": getattr(process, "pid", None),
            "login_mode": "cached candidate",
            "cached_credentials_reported": False,
            "password_prompt_observed": False,
            "guard_prompt_observed": False,
            "login_success": False,
            "quit_requested": True,
            "normal_quit": False,
            "cache_before": before,
        }
        self._diagnostic(diagnostic)
        password = self.secrets.get("steam", "password")
        authenticated = False
        challenge = False
        password_sent = False

        async def consume(stream: asyncio.StreamReader) -> None:
            nonlocal authenticated, challenge, password_sent
            while (chunk := await stream.read(256)):
                text = chunk.decode(errors="replace")
                lower = text.casefold()
                if "logging in using cached credentials" in lower:
                    diagnostic["cached_credentials_reported"] = True
                    diagnostic["login_success"] = True
                if "logged in ok" in lower:
                    diagnostic["login_success"] = True
                if ("password:" in lower or "password " in lower) and not password_sent:
                    diagnostic["password_prompt_observed"] = True
                    diagnostic["login_mode"] = "credential supplied"
                    if process.stdin is None or password is None:
                        raise SteamCmdError("authentication-required", "SteamCMD password is required")
                    process.stdin.write((password + "\n").encode())
                    await process.stdin.drain()
                    password_sent = True
                elif "guard code" in lower or "two-factor" in lower or "authenticator" in lower:
                    diagnostic["guard_prompt_observed"] = True
                    diagnostic["login_mode"] = "interactive required"
                    challenge = True
                elif "logged in ok" in lower or "logging in using cached credentials" in lower:
                    authenticated = True

        try:
            await asyncio.wait_for(asyncio.gather(consume(process.stdout), consume(process.stderr)), timeout=45)
            returncode = await process.wait()
        except Exception:
            if process.returncode is None:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            await process.wait()
            returncode = process.returncode
            diagnostic.update({
                "event": "exit",
                "exit_code": returncode if returncode is not None and returncode >= 0 else None,
                "exit_signal": -returncode if returncode is not None and returncode < 0 else None,
                "cache_after": self._cache_snapshot(),
            })
            diagnostic["cache_events"] = self._cache_events(before, diagnostic["cache_after"])
            self._diagnostic(diagnostic)
            raise
        after = self._cache_snapshot()
        diagnostic.update({
            "event": "exit",
            "exit_code": returncode if returncode >= 0 else None,
            "exit_signal": -returncode if returncode < 0 else None,
            "normal_quit": returncode == 0 and bool(authenticated),
            "cache_after": after,
            "cache_events": self._cache_events(before, after),
            "login_success": bool(diagnostic["login_success"] or authenticated),
        })
        self._diagnostic(diagnostic)
        if challenge:
            raise SteamCmdError("challenge-required", "SteamCMD requires a Steam Guard code")
        if returncode != 0 or not authenticated:
            raise SteamCmdError("authentication-failed", "SteamCMD authentication failed")
        if password is not None:
            self.secrets.clear("steam", "password")
        return {"status": "authenticated"}

    async def cancel(self, job: DownloadJob) -> None:
        # JobManager owns the task cancellation boundary.  SteamCMD is placed
        # in its own process group so the executor's cancellation cleanup can
        # terminate the complete provider operation without QML process control.
        return None

    async def _answer(self, input_type: CredentialInput, title: str, prompt: str,
                      process: asyncio.subprocess.Process, *, min_length: int = 0,
                      max_length: int = 4096) -> None:
        if process.stdin is None:
            raise SteamCmdError("auth-backend-unavailable", "SteamCMD input channel unavailable")
        try:
            if self.request_credential is not None:
                value = await self.request_credential(input_type, title, prompt, min_length, max_length)
            elif input_type is CredentialInput.SECRET and self.secrets.configured("steam", "password"):
                value = self.secrets.get("steam", "password") or ""
            else:
                request = await self.credentials.request(title, prompt, input_type,
                                                         secret=input_type is CredentialInput.SECRET,
                                                         min_length=min_length, max_length=max_length)
                value = await self.credentials.wait_for_submission(request.request.request_id)
            process.stdin.write((value + "\n").encode())
            await process.stdin.drain()
            if input_type is CredentialInput.SECRET and value:
                # SteamCMD normally writes its own issued cache after login;
                # do not retain the raw password once it has been supplied.
                self.secrets.clear("steam", "password")
        except (RuntimeError, KeyError, ValueError) as error:
            raise SteamCmdError("authentication-cancelled", "Steam authentication was cancelled") from error
