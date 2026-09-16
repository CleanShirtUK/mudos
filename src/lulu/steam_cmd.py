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
import os
from pathlib import Path
import re
from typing import Callable, Mapping
from urllib.request import Request, urlopen

from .jobs import DownloadJob, JobState
from .job_manager import JobExecutionError, JobReporter
from .paths import PATHS


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
                 platform_resolver: SteamPlatformResolver | None = None) -> None:
        self.executable = executable or os.environ.get("LULU_STEAMCMD", "steamcmd")
        self.account = account or os.environ.get("LULU_STEAM_ACCOUNT", "")
        if not self.account:
            try:
                # This file contains only the account name, never a password,
                # token, Guard data, or a SteamCMD cache.
                self.account = (PATHS.config_root / "steam-account").read_text().strip()
            except (FileNotFoundError, OSError):
                pass
        configured_library = os.environ.get("LULU_STEAM_LIBRARY")
        self.install_dir = install_dir
        if self.install_dir is None and configured_library:
            self.install_dir = Path(configured_library)
        self.install_dir = self.install_dir or (PATHS.data_home / "Steam")
        self.platforms = dict(platforms or load_platforms())
        self.platform_resolver = platform_resolver or SteamPlatformResolver()
        self.parser = parser or SteamCmdParser()

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
        command = [self.executable, "+@NoPromptForPassword", "1"]
        if platform == "windows":
            command += ["+@sSteamCmdForcePlatformType", "windows"]
        command += ["+force_install_dir", str(self.install_dir), "+login", self.account,
                    "+app_update", app_id, "validate", "+quit"]
        return command

    async def run(self, job: DownloadJob, reporter: JobReporter) -> None:
        app_id = self._app_id(job.content_identity)
        if app_id not in self.platforms:
            platform = await asyncio.to_thread(self.platform_resolver.resolve, app_id)
            if platform is not None:
                self.platforms[app_id] = platform
        command = self.command(app_id)
        self.install_dir.mkdir(parents=True, exist_ok=True)
        process = await asyncio.create_subprocess_exec(
            *command, stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        success = False
        finalizing = False

        async def consume(stream: asyncio.StreamReader) -> None:
            nonlocal success, finalizing
            while (line := await stream.readline()):
                observation = self.parser.parse(line.decode(errors="replace"))
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
                        # A no-op update has no transfer stage.  FINALIZING is
                        # the provider-neutral completion bridge used by the
                        # manager; it does not fabricate transfer progress.
                        await reporter.state(JobState.FINALIZING, stage="finalizing")
                elif observation.kind == "authentication-required":
                    raise SteamCmdError("authentication-required", "Steam download authentication required")
                elif observation.kind == "invalid-platform":
                    raise SteamCmdError("invalid-platform", "SteamCMD rejected the requested platform")
                elif observation.kind == "failure":
                    raise SteamCmdError("steamcmd-failure", "SteamCMD reported a download failure",
                                        details={"provider_message": observation.message})

        try:
            await asyncio.gather(consume(process.stdout), consume(process.stderr))
        except Exception:
            # Parser/authentication failures are terminal for this operation;
            # do not leave a SteamCMD child behind. This is not job
            # cancellation and makes no claim about user-requested aborts.
            if process.returncode is None:
                process.kill()
            await process.wait()
            raise
        returncode = await process.wait()
        if returncode != 0 or not success:
            raise SteamCmdError("steamcmd-failure", "SteamCMD did not complete successfully",
                                details={"exit_code": returncode, "success_result": success,
                                         "finalizing_seen": finalizing})

    async def cancel(self, job: DownloadJob) -> None:
        raise SteamCmdError("cancellation-unsupported", "Steam acquisition cancellation is unavailable")
