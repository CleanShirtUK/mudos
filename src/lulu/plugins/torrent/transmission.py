"""Transmission 4.1 JSON-RPC adapter and Mudos torrent executor.

Only this module knows Transmission method names, status integers, or RPC
transport details.  Callers use hashes and normalized TorrentDownload values.
"""

from __future__ import annotations

import asyncio
import base64
from dataclasses import dataclass
import json
import logging
from pathlib import Path
import re
import urllib.error
import urllib.request
from typing import Any, Mapping

from ...credential import SecretStore
from ...jobs import DownloadJob, JobError, JobState
from ...job_manager import JobCancelled, JobExecutionError, JobReporter
from ...paths import MudosPaths, PATHS

LOGGER = logging.getLogger("lulu.plugins.torrent")


class TransmissionError(Exception):
    def __init__(self, code: str, message: str, *, retryable: bool = True) -> None:
        super().__init__(message)
        self.code = code
        self.retryable = retryable


@dataclass(frozen=True, slots=True)
class TransmissionConfig:
    endpoint: str = "http://127.0.0.1:9091/transmission/rpc"
    timeout_seconds: float = 10.0
    username: str = ""
    password: str = ""
    label: str = "mudos"


@dataclass(frozen=True, slots=True)
class TorrentFile:
    index: int
    name: str
    length: int
    completed: int
    wanted: bool
    priority: int


@dataclass(frozen=True, slots=True)
class TorrentDownload:
    hash_string: str
    name: str
    destination: str
    files: tuple[TorrentFile, ...]
    progress: float
    downloaded_bytes: int
    total_bytes: int
    download_rate: int
    upload_rate: int
    eta_seconds: int | None
    state: str
    provider_state: str
    error: str | None
    labels: tuple[str, ...]
    seeding: bool
    finished: bool

    @property
    def completion_path(self) -> str:
        return str(Path(self.destination) / self.name)


def _int(value: object, default: int = 0) -> int:
    try:
        return int(value or default)
    except (TypeError, ValueError):
        return default


class TransmissionClient:
    """Small async wrapper around the current Transmission RPC protocol."""

    def __init__(self, config: TransmissionConfig) -> None:
        self.config = config
        self._session_id: str | None = None
        self._request_id = 0
        self._lock = asyncio.Lock()

    def _request_sync(self, body: bytes, headers: dict[str, str]) -> tuple[int, dict[str, str], bytes]:
        request = urllib.request.Request(self.config.endpoint, data=body, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=self.config.timeout_seconds) as response:
                return response.status, dict(response.headers.items()), response.read()
        except urllib.error.HTTPError as error:
            return error.code, dict(error.headers.items()), error.read()
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            raise TransmissionError("network-error", "Transmission RPC is unavailable") from error

    async def call(self, method: str, params: Mapping[str, object] | None = None) -> dict[str, Any]:
        async with self._lock:
            self._request_id += 1
            payload = json.dumps({"jsonrpc": "2.0", "method": method,
                                  "params": dict(params or {}), "id": self._request_id}).encode()
            headers = {"Content-Type": "application/json", "Accept": "application/json"}
            if self.config.username:
                token = base64.b64encode(f"{self.config.username}:{self.config.password}".encode()).decode()
                headers["Authorization"] = f"Basic {token}"
            for attempt in range(2):
                if self._session_id:
                    headers["X-Transmission-Session-Id"] = self._session_id
                status, response_headers, raw = await asyncio.to_thread(self._request_sync, payload, headers)
                if status == 409:
                    session_id = next((value for key, value in response_headers.items()
                                       if key.casefold() == "x-transmission-session-id"), None)
                    if session_id and attempt == 0:
                        self._session_id = session_id
                        continue
                if status in (401, 403):
                    raise TransmissionError("authentication-failed", "Transmission RPC authentication failed", retryable=False)
                if status < 200 or status >= 300:
                    raise TransmissionError("rpc-http-error", f"Transmission RPC HTTP status {status}")
                try:
                    value = json.loads(raw.decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError) as error:
                    raise TransmissionError("rpc-invalid-response", "Transmission returned invalid JSON") from error
                if value.get("error"):
                    message = str(value["error"].get("message", "Transmission RPC error"))
                    raise TransmissionError("rpc-error", message)
                result = value.get("result")
                if not isinstance(result, dict):
                    raise TransmissionError("rpc-invalid-response", "Transmission RPC result was not an object")
                return result
            raise TransmissionError("session-error", "Transmission RPC session negotiation failed")

    async def health(self) -> dict[str, Any]:
        return await self.call("session_get", {"fields": ["version", "rpc_version_semver", "download_dir"]})

    async def add_magnet(self, magnet: str, destination: str, label: str) -> str:
        result = await self.call("torrent_add", {"filename": magnet, "download_dir": destination,
                                                   "labels": [label], "paused": False})
        item = result.get("torrent_added") or result.get("torrent_duplicate")
        if not isinstance(item, dict) or not item.get("hash_string"):
            raise TransmissionError("add-failed", "Transmission did not return a torrent hash", retryable=False)
        return str(item["hash_string"])

    async def add_torrent(self, metainfo: bytes, destination: str, label: str) -> str:
        encoded = base64.b64encode(metainfo).decode("ascii")
        result = await self.call("torrent_add", {"metainfo": encoded, "download_dir": destination,
                                                   "labels": [label], "paused": False})
        item = result.get("torrent_added") or result.get("torrent_duplicate")
        if not isinstance(item, dict) or not item.get("hash_string"):
            raise TransmissionError("add-failed", "Transmission did not return a torrent hash", retryable=False)
        return str(item["hash_string"])

    async def get(self, hash_string: str) -> TorrentDownload | None:
        fields = ["hash_string", "name", "download_dir", "files", "file_stats", "wanted", "priorities",
                  "percent_done", "left_until_done", "total_size", "size_when_done", "eta", "rate_download",
                  "rate_upload", "status", "error_string", "labels", "is_finished"]
        result = await self.call("torrent_get", {"ids": [hash_string], "fields": fields})
        torrents = result.get("torrents", [])
        if not torrents:
            return None
        return self._normalize(torrents[0])

    async def set_files(self, hash_string: str, *, wanted: list[int] | None = None,
                        unwanted: list[int] | None = None, high: list[int] | None = None,
                        normal: list[int] | None = None, low: list[int] | None = None) -> None:
        values: dict[str, object] = {"ids": [hash_string]}
        for key, value in (("files_wanted", wanted), ("files_unwanted", unwanted),
                           ("priority_high", high), ("priority_normal", normal), ("priority_low", low)):
            if value is not None:
                values[key] = value
        await self.call("torrent_set", values)

    async def pause(self, hash_string: str) -> None:
        await self.call("torrent_stop", {"ids": [hash_string]})

    async def resume(self, hash_string: str) -> None:
        await self.call("torrent_start", {"ids": [hash_string]})

    async def remove(self, hash_string: str, *, delete_local_data: bool = False) -> None:
        await self.call("torrent_remove", {"ids": [hash_string],
                                            "delete_local_data": delete_local_data})

    def _normalize(self, item: Mapping[str, Any]) -> TorrentDownload:
        status = _int(item.get("status"))
        total = _int(item.get("size_when_done")) or _int(item.get("total_size"))
        downloaded = max(0, total - _int(item.get("left_until_done")))
        finished = bool(item.get("is_finished")) or total > 0 and downloaded >= total
        if status in (1, 2): state = "starting"
        elif status in (3,): state = "queued"
        elif status in (4,): state = "transferring"
        elif status in (5, 6): state = "completed"
        else: state = "paused"
        if finished: state = "completed"
        names = item.get("files") if isinstance(item.get("files"), list) else []
        stats = item.get("file_stats") if isinstance(item.get("file_stats"), list) else []
        wanted = item.get("wanted") if isinstance(item.get("wanted"), list) else []
        priorities = item.get("priorities") if isinstance(item.get("priorities"), list) else []
        files = tuple(TorrentFile(i, str(value.get("name", "")), _int(value.get("length")),
                                  _int((stats[i] if i < len(stats) and isinstance(stats[i], dict) else {}).get("bytes_completed")),
                                  bool(wanted[i]) if i < len(wanted) else True,
                                  _int(priorities[i]) if i < len(priorities) else 0)
                      for i, value in enumerate(names) if isinstance(value, dict))
        labels = tuple(str(value) for value in item.get("labels", []) if isinstance(value, str))
        eta = _int(item.get("eta"), -1)
        return TorrentDownload(str(item.get("hash_string", "")), str(item.get("name", "")),
                               str(item.get("download_dir", "")), files, float(item.get("percent_done", 0)),
                               downloaded, total,
                               _int(item.get("rate_download")), _int(item.get("rate_upload")),
                               None if eta < 0 else eta, state, str(status),
                               str(item.get("error_string")) if item.get("error_string") else None,
                               labels, status in (5, 6), finished)


class TorrentProvider:
    """Provider-facing executor; Transmission details stop at this boundary."""

    provider_id = "torrent"
    supports_pause = True

    def __init__(self, client: TransmissionClient, paths: MudosPaths = PATHS,
                 *, label: str = "mudos") -> None:
        self.client, self.paths, self.label = client, paths, label

    def _roots(self) -> tuple[Path, Path]:
        return self.paths.torrent_incomplete_root.resolve(strict=False), self.paths.torrent_complete_root.resolve(strict=False)

    def _ownership_path(self, hash_string: str) -> Path:
        if not re.fullmatch(r"[0-9a-fA-F]{8,64}", hash_string):
            raise JobExecutionError("invalid-torrent-hash", "Transmission torrent hash is invalid", retryable=False)
        return self.paths.torrent_ownership_root / f"{hash_string.lower()}.json"

    def _record_ownership(self, job: DownloadJob, hash_string: str) -> None:
        path = self._ownership_path(hash_string)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".json.tmp")
        temporary.write_text(json.dumps({
            "hash": hash_string.lower(), "label": self.label, "job_id": job.job_id,
            "provider": job.provider, "content_identity": job.content_identity,
        }, sort_keys=True) + "\n")
        temporary.replace(path)

    async def get_download(self, hash_string: str) -> TorrentDownload | None:
        return await self.client.get(hash_string)

    async def add_magnet(self, magnet: str, destination: str | None = None) -> str:
        target = destination or str(self.paths.torrent_complete_root)
        return await self.client.add_magnet(magnet, target, self.label)

    async def add_torrent(self, metainfo: bytes, destination: str | None = None) -> str:
        target = destination or str(self.paths.torrent_complete_root)
        return await self.client.add_torrent(metainfo, target, self.label)

    async def pause(self, hash_string: str) -> None:
        await self.client.pause(hash_string)

    async def resume(self, hash_string: str) -> None:
        await self.client.resume(hash_string)

    async def remove(self, hash_string: str) -> None:
        await self.client.remove(hash_string)

    async def get_files(self, hash_string: str) -> tuple[TorrentFile, ...]:
        download = await self.client.get(hash_string)
        return () if download is None else download.files

    async def set_file_selection(self, hash_string: str, *, wanted: list[int] | None = None,
                                 unwanted: list[int] | None = None, high: list[int] | None = None,
                                 normal: list[int] | None = None, low: list[int] | None = None) -> None:
        await self.client.set_files(hash_string, wanted=wanted, unwanted=unwanted,
                                     high=high, normal=normal, low=low)

    def _owned_path(self, path: str, job: DownloadJob) -> Path:
        candidate = Path(path)
        if candidate.is_symlink():
            raise JobExecutionError("unsafe-path", "download path is a symlink", retryable=False)
        resolved = candidate.resolve(strict=False)
        roots = self._roots()
        if not any(self._within(resolved, root) and resolved != root for root in roots):
            raise JobExecutionError("unsafe-path", "download path is outside the torrent roots", retryable=False)
        if job.provider_job_id is None or not job.ownership_label:
            raise JobExecutionError("ownership-unknown", "download ownership is not authoritative", retryable=False)
        return resolved

    @staticmethod
    def _within(path: Path, root: Path) -> bool:
        try:
            path.relative_to(root)
            return True
        except ValueError:
            return False

    async def run(self, job: DownloadJob, reporter: JobReporter) -> None:
        self.paths.torrent_incomplete_root.mkdir(parents=True, exist_ok=True)
        self.paths.torrent_complete_root.mkdir(parents=True, exist_ok=True)
        torrent = await self.client.get(job.provider_job_id) if job.provider_job_id else None
        if torrent is None and job.provider_job_id:
            if job.state == JobState.QUEUED and job.completion_path and Path(job.completion_path).exists():
                await reporter.metadata(provider_state="missing-after-completion")
                await reporter.progress(1.0, downloaded_bytes=job.total_bytes, total_bytes=job.total_bytes, stage="completed")
                return
            raise JobExecutionError("torrent-missing", "Transmission torrent is no longer present", retryable=True)
        if torrent is not None and self.label not in torrent.labels:
            raise JobExecutionError("ownership-mismatch", "torrent is not labelled as Mudos-owned", retryable=False)
        if torrent is None:
            identity = job.content_identity
            # Transmission's per-torrent destination is the completed root;
            # its daemon-level incomplete-dir setting keeps partial pieces in
            # the separate incomplete root and promotes them on completion.
            destination = str(self.paths.torrent_complete_root)
            if identity.startswith("magnet:"):
                hash_string = await self.client.add_magnet(identity, destination, self.label)
            else:
                raise JobExecutionError("unsupported-source", "torrent acquisition currently requires a magnet URI", retryable=False)
            torrent = await self.client.get(hash_string)
            if torrent is None:
                raise JobExecutionError("add-failed", "added torrent could not be inspected", retryable=True)
            self._record_ownership(job, hash_string)
            await reporter.metadata(provider_job_id=hash_string, backend="transmission", destination=destination,
                                    ownership_label=self.label, deletion_policy="preserve-partial")
        else:
            self._record_ownership(job, torrent.hash_string)
        await reporter.metadata(provider_job_id=torrent.hash_string, backend="transmission",
                                destination=torrent.destination, provider_state=torrent.state,
                                ownership_label=self.label, artifact_files=tuple({"index": f.index, "name": f.name,
                                "length": f.length, "completed": f.completed, "wanted": f.wanted,
                                "priority": f.priority} for f in torrent.files), seeding=torrent.seeding)
        if torrent.state == "paused":
            if job.state == JobState.QUEUED and job.provider_state != "paused":
                await self.client.resume(torrent.hash_string)
                torrent = await self.client.get(torrent.hash_string)
                if torrent is None:
                    raise JobExecutionError("torrent-missing", "Transmission torrent disappeared", retryable=True)
            else:
                await reporter.state(JobState.PAUSED, stage="paused")
                return
        while not torrent.finished:
            if torrent.error:
                raise JobExecutionError("torrent-error", torrent.error, retryable=True)
            await reporter.state(JobState.TRANSFERRING, stage="transferring")
            await reporter.progress(torrent.progress, downloaded_bytes=torrent.downloaded_bytes,
                                    total_bytes=torrent.total_bytes, stage="transferring")
            await reporter.metadata(provider_state=torrent.state, download_rate=torrent.download_rate,
                                    upload_rate=torrent.upload_rate, eta_seconds=torrent.eta_seconds,
                                    seeding=torrent.seeding)
            await asyncio.sleep(1)
            try:
                torrent = await self.client.get(torrent.hash_string)
            except TransmissionError as error:
                # A daemon restart is not an acquisition failure.  Keep the
                # durable job alive and let the next poll reconcile by hash.
                await reporter.metadata(provider_state="daemon-restarting")
                await asyncio.sleep(2)
                continue
            if torrent is None:
                raise JobExecutionError("torrent-missing", "Transmission torrent disappeared", retryable=True)
        completion = torrent.completion_path
        # JobManager promotes a transferring job through its finalizing
        # boundary.  A restart can discover an already-complete torrent while
        # the durable job is still queued/starting, so enter that normalized
        # state explicitly before reporting completion.
        if job.state == JobState.STARTING:
            await reporter.state(JobState.TRANSFERRING, stage="transferring")
        await reporter.metadata(completion_path=completion, provider_state=torrent.state,
                                download_rate=torrent.download_rate, upload_rate=torrent.upload_rate,
                                eta_seconds=0, seeding=torrent.seeding)
        await reporter.progress(1.0, downloaded_bytes=torrent.total_bytes, total_bytes=torrent.total_bytes,
                                stage="completed")

    async def cancel(self, job: DownloadJob) -> None:
        if job.provider_job_id:
            try:
                await self.client.remove(job.provider_job_id)
            except TransmissionError:
                LOGGER.warning("torrent cancellation could not remove hash=%s", job.provider_job_id)

    async def delete_download(self, job: DownloadJob) -> None:
        torrent = await self.client.get(job.provider_job_id) if job.provider_job_id else None
        if torrent is not None and self.label not in torrent.labels:
            raise JobExecutionError("ownership-mismatch", "refusing to delete an unowned torrent", retryable=False)
        if job.ownership_label != self.label:
            raise JobExecutionError("ownership-unknown", "download ownership label is not authoritative", retryable=False)
        if job.provider_job_id:
            await self.client.remove(job.provider_job_id, delete_local_data=True)
        candidates = [job.completion_path or (torrent.completion_path if torrent else None)]
        for value in candidates:
            if not value:
                continue
            path = self._owned_path(value, job)
            if path.exists() and path.is_dir():
                import shutil
                shutil.rmtree(path)
            elif path.exists():
                path.unlink()
        if job.provider_job_id:
            self._ownership_path(job.provider_job_id).unlink(missing_ok=True)
