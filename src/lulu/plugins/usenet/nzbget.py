"""Normalized NZBGet JSON-RPC adapter and Usenet JobManager executor."""

from __future__ import annotations

import asyncio
import base64
from dataclasses import dataclass
import json
import logging
import os
from pathlib import Path
import urllib.error
import urllib.request
from typing import Any, Mapping

from ...jobs import DownloadJob, ExternalAcquisition, JobError, JobState
from ...job_manager import JobCancelled, JobExecutionError, JobReporter
from ...paths import MudosPaths, PATHS
from ...questarr_metadata import QuestarrMetadataClient

LOGGER = logging.getLogger("lulu.plugins.usenet")


class NzbGetError(Exception):
    def __init__(self, code: str, message: str, *, retryable: bool = True) -> None:
        super().__init__(message)
        self.code = code
        self.retryable = retryable


@dataclass(frozen=True, slots=True)
class NzbGetConfig:
    endpoint: str = "http://127.0.0.1:6789/jsonrpc"
    username: str = "mudos"
    password: str = ""
    timeout_seconds: float = 10.0
    category: str = "mudos"
    dupe_prefix: str = "mudos:"


@dataclass(frozen=True, slots=True)
class UsenetServerConfig:
    """Secret-backed news-server boundary, applied when credentials exist."""

    host: str = ""
    port: int = 563
    tls: bool = True
    username: str = ""
    password: str = ""
    connections: int = 8


@dataclass(frozen=True, slots=True)
class NzbDownload:
    nzbid: int
    name: str
    category: str
    dupe_key: str
    status: str
    total_bytes: int
    remaining_bytes: int
    downloaded_bytes: int
    rate: int
    destination: str
    final_directory: str
    post_progress: float | None
    post_info: str
    error: str | None = None
    source_name: str = ""

    @property
    def progress(self) -> float:
        if self.total_bytes <= 0:
            return self.post_progress or 0.0
        return max(0.0, min(1.0, self.downloaded_bytes / self.total_bytes))


@dataclass(frozen=True, slots=True)
class NzbHistory:
    nzbid: int
    name: str
    category: str
    dupe_key: str
    status: str
    destination: str
    final_directory: str
    error: str | None = None
    source_name: str = ""
    par_status: str = ""
    unpack_status: str = ""
    failed_articles: int = 0
    total_articles: int = 0
    extra_par_blocks: int = 0


def _external_state(status: str, *, history: bool = False) -> tuple[JobState, str]:
    value = status.upper()
    if history:
        if value.startswith(("FAILURE", "WARNING")): return JobState.FAILED, "failed"
        if value.startswith("DELETED"): return JobState.CANCELLED, "cancelled"
        return JobState.COMPLETED, "completed"
    if value == "PAUSED": return JobState.PAUSED, "paused"
    if value in {"QUEUED", "FETCHING"}: return JobState.QUEUED, "queued"
    if value in {"DOWNLOADING"}: return JobState.TRANSFERRING, "transferring"
    return JobState.FINALIZING, value.lower()


def _int(value: object, default: int = 0) -> int:
    try:
        return int(value or default)
    except (TypeError, ValueError):
        return default


def _u64(item: Mapping[str, Any], name: str) -> int:
    return (_int(item.get(f"{name}Hi")) << 32) + (_int(item.get(f"{name}Lo")) & 0xFFFFFFFF)


class NzbGetClient:
    def __init__(self, config: NzbGetConfig) -> None:
        self.config = config
        self._request_id = 0
        self._lock = asyncio.Lock()

    def _request_sync(self, payload: bytes) -> bytes:
        auth = base64.b64encode(f"{self.config.username}:{self.config.password}".encode()).decode()
        request = urllib.request.Request(
            self.config.endpoint, data=payload,
            headers={"Content-Type": "application/json", "Authorization": f"Basic {auth}"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.config.timeout_seconds) as response:
                return response.read()
        except urllib.error.HTTPError as error:
            if error.code in (401, 403):
                raise NzbGetError("authentication-failed", "NZBGet RPC authentication failed", retryable=False)
            raise NzbGetError("rpc-http-error", f"NZBGet RPC HTTP status {error.code}")
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            raise NzbGetError("network-error", "NZBGet RPC is unavailable") from error

    async def call(self, method: str, params: list[object] | None = None) -> Any:
        async with self._lock:
            self._request_id += 1
            payload = json.dumps({"jsonrpc": "2.0", "method": method,
                                  "params": params or [], "id": self._request_id}).encode()
            try:
                raw = await asyncio.to_thread(self._request_sync, payload)
                value = json.loads(raw.decode("utf-8"))
            except NzbGetError:
                raise
            except (UnicodeDecodeError, json.JSONDecodeError) as error:
                raise NzbGetError("rpc-invalid-response", "NZBGet returned invalid JSON") from error
            if not isinstance(value, dict) or "error" in value:
                error = value.get("error", {}) if isinstance(value, dict) else {}
                message = error.get("message", "NZBGet RPC error") if isinstance(error, dict) else str(error)
                raise NzbGetError("rpc-error", str(message))
            return value.get("result")

    async def health(self) -> dict[str, Any]:
        version = await self.call("version")
        status = await self.call("status")
        return {"version": str(version), "status": status}

    async def append(self, content: bytes | str, filename: str, *, category: str,
                     dupe_key: str, paused: bool = False) -> int:
        if isinstance(content, bytes):
            value = base64.b64encode(content).decode("ascii")
        else:
            value = content
        result = await self.call("append", [filename, value, category, 0, False, paused,
                                              dupe_key, 0, "SCORE", [{"Name": "*unpack:", "Value": "yes"}]])
        nzbid = _int(result)
        if nzbid <= 0:
            raise NzbGetError("submit-failed", "NZBGet rejected the NZB", retryable=False)
        return nzbid

    async def groups(self) -> tuple[NzbDownload, ...]:
        result = await self.call("listgroups", [0]) or []
        return tuple(self._group(item) for item in result if isinstance(item, dict))

    async def history(self) -> tuple[NzbHistory, ...]:
        result = await self.call("history", [False]) or []
        return tuple(self._history(item) for item in result if isinstance(item, dict))

    async def find(self, dupe_key: str) -> tuple[NzbDownload | None, NzbHistory | None]:
        groups = await self.groups()
        group = next((item for item in groups if item.dupe_key == dupe_key), None)
        if group is not None:
            return group, None
        history = await self.history()
        return None, next((item for item in history if item.dupe_key == dupe_key), None)

    async def pause(self, nzbid: int) -> None:
        if not await self.call("editqueue", ["GroupPause", "", [nzbid]]):
            raise NzbGetError("pause-failed", "NZBGet could not pause the group")

    async def resume(self, nzbid: int) -> None:
        if not await self.call("editqueue", ["GroupResume", "", [nzbid]]):
            raise NzbGetError("resume-failed", "NZBGet could not resume the group")

    async def remove(self, nzbid: int, *, preserve_history: bool = True) -> None:
        command = "GroupDelete" if preserve_history else "GroupFinalDelete"
        if not await self.call("editqueue", [command, "", [nzbid]]):
            raise NzbGetError("remove-failed", "NZBGet could not remove the group")

    @staticmethod
    def _group(item: Mapping[str, Any]) -> NzbDownload:
        post = _int(item.get("PostStageProgress")) / 1000 if "PostStageProgress" in item else None
        return NzbDownload(_int(item.get("NZBID")), str(item.get("NZBName", item.get("Name", ""))),
                           str(item.get("Category", "")), str(item.get("DupeKey", "")),
                           str(item.get("Status", "")), _u64(item, "FileSize"),
                           _u64(item, "RemainingSize"), _u64(item, "DownloadedSize"),
                           _int(item.get("DownloadRate")), str(item.get("DestDir", "")),
                           str(item.get("FinalDir", "")), post, str(item.get("PostInfoText", "")),
                           str(item.get("NZBFilename", "")))

    @staticmethod
    def _history(item: Mapping[str, Any]) -> NzbHistory:
        return NzbHistory(_int(item.get("NZBID")), str(item.get("Name", item.get("NZBName", ""))),
                          str(item.get("Category", "")), str(item.get("DupeKey", "")),
                          str(item.get("Status", "")), str(item.get("DestDir", "")),
                          str(item.get("FinalDir", "")), None, str(item.get("NZBFilename", "")),
                          str(item.get("ParStatus", "")), str(item.get("UnpackStatus", "")),
                          _int(item.get("FailedArticles")), _int(item.get("TotalArticles")),
                          _int(item.get("ExtraParBlocks")))


def _history_failure_message(item: NzbHistory) -> str:
    """Produce a user-facing reason from NZBGet's authoritative terminal fields."""
    if item.par_status.upper() == "FAILURE":
        reason = f"NZBGet PAR verification/repair failed ({item.status})"
        if item.total_articles:
            reason += f"; {item.failed_articles} of {item.total_articles} articles failed"
        if item.extra_par_blocks == 0:
            reason += "; no additional recovery blocks were available"
        return reason
    if item.unpack_status.upper() == "FAILURE":
        return f"NZBGet unpack failed ({item.status})"
    return f"NZBGet reported {item.status}"


class UsenetProvider:
    provider_id = "usenet"
    supports_pause = True

    def __init__(self, client: NzbGetClient, paths: MudosPaths = PATHS, *, category: str = "mudos",
                 dupe_prefix: str = "mudos:", questarr_metadata: QuestarrMetadataClient | None = None) -> None:
        self.client, self.paths, self.category, self.dupe_prefix = client, paths, category, dupe_prefix
        self.questarr_metadata = questarr_metadata

    def _dupe_key(self, job: DownloadJob) -> str:
        return f"{self.dupe_prefix}{job.job_id}"

    def _ownership_path(self, job: DownloadJob) -> Path:
        return self.paths.usenet_ownership_root / f"{job.job_id}.json"

    def _external_key(self, item: NzbDownload | NzbHistory) -> str:
        import hashlib
        source = item.source_name or item.name
        for sidecar in sorted((self.paths.usenet_ownership_root / "external").glob("*.json")):
            try:
                value = json.loads(sidecar.read_text())
            except (OSError, ValueError, json.JSONDecodeError):
                continue
            if value.get("source_name") == source or (not item.source_name and value.get("name") == item.name):
                return str(value["content_identity"])
        # Status, category, destination and FinalDir are mutable. The sidecar
        # created on first observation is the durable identity anchor.
        stable = "|".join((source, item.dupe_key))
        digest = hashlib.sha256(stable.encode()).hexdigest()[:24]
        return f"nzbget:external:{digest}"

    def _external_origin(self, item: NzbDownload | NzbHistory) -> tuple[str, str]:
        if item.category.casefold() == "questarr" or item.dupe_key.casefold().startswith("questarr:"):
            return "questarr", "questarr"
        return "external", "external/manual"

    def _remember_external(self, key: str, item: NzbDownload | NzbHistory,
                           origin: str, provenance: str) -> None:
        path = self.paths.usenet_ownership_root / "external" / f"{key.rsplit(':', 1)[-1]}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.write_text(json.dumps({"content_identity": key, "provider": "usenet",
                                        "origin": origin, "provenance": provenance,
                                        "name": item.name, "category": item.category,
                                        "dupe_key": item.dupe_key,
                                        "source_name": item.source_name,
                                        "provider_job_id": item.nzbid}, sort_keys=True) + "\n")

    async def discover_external(self) -> tuple[ExternalAcquisition, ...]:
        """Discover all non-Mudos queue/history entries for global Downloads."""
        records: list[ExternalAcquisition] = []
        groups = await self.client.groups()
        history = await self.client.history()
        for item in groups:
            if item.dupe_key.startswith(self.dupe_prefix):
                continue
            origin, provenance = self._external_origin(item)
            key = self._external_key(item); self._remember_external(key, item, origin, provenance)
            state, stage = _external_state(item.status)
            metadata = self.questarr_metadata.find(item.dupe_key, "usenet") \
                if origin == "questarr" and self.questarr_metadata else None
            records.append(ExternalAcquisition(
                key, item.name, origin, provenance, str(item.nzbid), state,
                item.progress, item.downloaded_bytes, item.total_bytes, stage, item.rate,
                item.status, item.destination, "nzbget", metadata.as_dict() if metadata else {}))
        for item in history:
            if item.dupe_key.startswith(self.dupe_prefix):
                continue
            origin, provenance = self._external_origin(item)
            key = self._external_key(item); self._remember_external(key, item, origin, provenance)
            state, stage = _external_state(item.status, history=True)
            metadata = self.questarr_metadata.find(item.dupe_key, "usenet") \
                if origin == "questarr" and self.questarr_metadata else None
            records.append(ExternalAcquisition(
                key, item.name, origin, provenance, str(item.nzbid), state,
                1.0 if state == JobState.COMPLETED else None, None, None, stage, None,
                item.status, item.final_directory or item.destination, "nzbget",
                metadata.as_dict() if metadata else {},
                JobError("usenet-provider-failure", _history_failure_message(item), retryable=True)
                if state == JobState.FAILED else None))
        return tuple(records)

    def _record(self, job: DownloadJob, nzbid: int, destination: str) -> None:
        path = self._ownership_path(job)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps({"job_id": job.job_id, "provider": "usenet",
                                         "dupe_key": self._dupe_key(job), "nzbid": nzbid,
                                         "destination": destination}, sort_keys=True) + "\n")
        temporary.replace(path)

    async def _submit(self, job: DownloadJob) -> int:
        identity = job.content_identity
        if identity.startswith(("http://", "https://")):
            return await self.client.append(identity, "", category=self.category, dupe_key=self._dupe_key(job))
        source = Path(identity.removeprefix("file://"))
        if not source.is_file():
            raise JobExecutionError("unsupported-source", "Usenet acquisition requires an NZB file or URL", retryable=False)
        return await self.client.append(source.read_bytes(), source.name, category=self.category,
                                        dupe_key=self._dupe_key(job))

    def _completion(self, download: NzbDownload | NzbHistory) -> str:
        """Normalize NZBGet's terminal directory without appending the job twice."""
        raw = download.final_directory or download.destination
        root = Path(os.path.normpath(str(self.paths.usenet_complete_root)))
        path = Path(raw) if raw else root
        if not path.is_absolute():
            path = root / path
        path = Path(os.path.normpath(str(path)))

        # FinalDir is NZBGet's explicit post-processing result location. DestDir
        # is also commonly already the per-job directory (as in history RPC).
        if download.final_directory:
            return str(path)
        if path == root:
            path /= download.name
        elif not path.exists() and download.name not in path.parts:
            path /= download.name
        return str(path)

    @staticmethod
    def _require_completion(path: str, provider_job_id: str) -> str:
        if not Path(path).exists():
            raise JobExecutionError(
                "usenet-output-missing", "NZBGet reported success but its output directory is missing",
                retryable=True, details={"provider_job_id": provider_job_id, "completion_path": path})
        return path

    async def reconcile_completion_path(self, job: DownloadJob) -> str | None:
        """Re-read an owned successful history item to repair stale path metadata."""
        if job.provider != self.provider_id or job.state != JobState.COMPLETED \
                or job.backend != "nzbget" or not job.provider_job_id:
            return None
        dupe_key = job.ownership_label or self._dupe_key(job)
        _, history = await self.client.find(dupe_key)
        if history is None or history.status.upper() not in {"SUCCESS/ALL", "SUCCESS/UNPACK"} \
                or str(history.nzbid) != str(job.provider_job_id):
            return None
        completion = self._completion(history)
        return completion if Path(completion).exists() else None

    async def run(self, job: DownloadJob, reporter: JobReporter) -> None:
        self.paths.usenet_incomplete_root.mkdir(parents=True, exist_ok=True)
        self.paths.usenet_complete_root.mkdir(parents=True, exist_ok=True)
        group, history = await self.client.find(self._dupe_key(job))
        if group is None and history is None:
            nzbid = await self._submit(job)
            destination = str(self.paths.usenet_complete_root)
            self._record(job, nzbid, destination)
            for _ in range(10):
                group, history = await self.client.find(self._dupe_key(job))
                if group is not None or history is not None:
                    break
                await asyncio.sleep(0.2)
        if group is not None:
            await reporter.metadata(provider_job_id=str(group.nzbid), backend="nzbget",
                                    destination=group.destination, ownership_label=self._dupe_key(job),
                                    provider_state=group.status)
            if group.status == "PAUSED":
                await reporter.state(JobState.PAUSED, stage="paused")
                return
            if group.status in {"QUEUED", "FETCHING"}:
                await reporter.state(JobState.QUEUED, stage="queued")
            while group.status not in {"PP_FINISHED"}:
                if group.status in {"DOWNLOADING", "FETCHING"}:
                    await reporter.state(JobState.TRANSFERRING, stage="transferring")
                elif group.status in {"PP_QUEUED", "LOADING_PARS", "VERIFYING_SOURCES", "REPAIRING",
                                      "VERIFYING_REPAIRED", "RENAMING", "UNPACKING", "MOVING",
                                      "POST_UNPACK_RENAMING", "POST_DOWNLOAD_RENAMING", "EXECUTING_SCRIPT"}:
                    await reporter.state(JobState.FINALIZING, stage=group.status.lower())
                elif group.status == "PAUSED":
                    await reporter.state(JobState.PAUSED, stage="paused")
                    return
                await reporter.progress(group.progress, downloaded_bytes=group.downloaded_bytes,
                                        total_bytes=group.total_bytes, stage=group.status.lower())
                await reporter.metadata(provider_state=group.status, download_rate=group.rate)
                await asyncio.sleep(1)
                group, history = await self.client.find(self._dupe_key(job))
                if group is None:
                    break
            if group is not None and group.status != "PP_FINISHED":
                _, history = await self.client.find(self._dupe_key(job))
        if history is None and group is None:
            raise JobExecutionError("nzbget-missing", "owned NZB disappeared from queue and history", retryable=True)
        if history is None and group is not None and group.status != "PP_FINISHED":
            raise JobExecutionError("nzbget-missing", "owned NZB disappeared before post-processing completed", retryable=True)
        if history is None and group is not None:
            completion = self._require_completion(self._completion(group), str(group.nzbid))
            await reporter.metadata(provider_job_id=str(group.nzbid), backend="nzbget",
                                    provider_state=group.status, completion_path=completion,
                                    ownership_label=self._dupe_key(job))
            await reporter.progress(1.0, downloaded_bytes=group.total_bytes, total_bytes=group.total_bytes,
                                    stage="completed")
            return
        status = history.status.upper()
        await reporter.metadata(provider_job_id=str(history.nzbid), backend="nzbget",
                                destination=history.destination, provider_state=status,
                                ownership_label=self._dupe_key(job))
        if status.startswith("FAILURE") or status.startswith("WARNING"):
            reason = _history_failure_message(history)
            raise JobExecutionError("usenet-post-processing", reason, retryable=True,
                                    details={"provider_status": status,
                                             "failed_articles": history.failed_articles,
                                             "total_articles": history.total_articles,
                                             "par_status": history.par_status,
                                             "unpack_status": history.unpack_status})
        if status.startswith("DELETED"):
            if status.startswith("DELETED/COPY"):
                raise JobExecutionError(
                    "usenet-duplicate", "NZBGet refused this Mudos submission as a duplicate",
                    retryable=False, details={"provider_status": status, "nzbid": history.nzbid,
                                              "dupe_key": history.dupe_key})
            raise JobCancelled()
        await reporter.metadata(provider_job_id=str(history.nzbid), backend="nzbget",
                                provider_state=status,
                                completion_path=self._require_completion(
                                    self._completion(history), str(history.nzbid)),
                                ownership_label=self._dupe_key(job))
        await reporter.progress(1.0, downloaded_bytes=job.total_bytes, total_bytes=job.total_bytes, stage="completed")

    async def pause(self, provider_job_id: str) -> None:
        await self.client.pause(int(provider_job_id))

    async def resume(self, provider_job_id: str) -> None:
        await self.client.resume(int(provider_job_id))

    async def cancel(self, job: DownloadJob) -> None:
        if job.provider_job_id:
            await self.client.remove(int(job.provider_job_id), preserve_history=True)

    async def cleanup_cancelled(self, job: DownloadJob) -> None:
        """Remove a still-queued provider job for a terminal owned job.

        A numeric NZBGet ID is not proof of ownership: verify the durable
        Acquisitiond ownership sidecar, dupe key, and live queue record before
        issuing the provider's normal owned-job removal operation.
        """
        if job.provider != self.provider_id or job.state != JobState.CANCELLED \
                or job.backend != "nzbget" or not job.provider_job_id:
            return
        dupe_key = self._dupe_key(job)
        if job.ownership_label != dupe_key:
            return
        ownership_path = self._ownership_path(job)
        if ownership_path.is_symlink() or not ownership_path.is_file():
            return
        try:
            ownership = json.loads(ownership_path.read_text())
        except (OSError, ValueError, json.JSONDecodeError):
            return
        if not isinstance(ownership, dict) or ownership.get("job_id") != job.job_id \
                or ownership.get("provider") != self.provider_id \
                or ownership.get("dupe_key") != dupe_key \
                or str(ownership.get("nzbid", "")) != str(job.provider_job_id):
            return
        group, _history = await self.client.find(dupe_key)
        if group is None or group.dupe_key != dupe_key \
                or str(group.nzbid) != str(job.provider_job_id):
            return
        await self.client.remove(group.nzbid, preserve_history=True)
