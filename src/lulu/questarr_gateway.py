"""Minimal NZBGet XML-RPC facade whose jobs are owned by Acquisitiond."""

from __future__ import annotations

from concurrent.futures import Future, TimeoutError
import base64
import asyncio
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import logging
import os
from pathlib import Path
import sqlite3
import threading
from typing import Any
from urllib.parse import urlsplit
import xml.etree.ElementTree as ElementTree
from xmlrpc.client import Fault, dumps, loads

from .jobs import DownloadJob, JobState
from .job_manager import JobManager
from .paths import PATHS

LOGGER = logging.getLogger("lulu.questarr-gateway")
GATEWAY_HOST = "127.0.0.1"
GATEWAY_PORT = 5001
NZBGET_VERSION = "24.0-mudos-gateway"
MAX_NZB_BYTES = 24 * 1024 * 1024


class QuestarrGateway:
    """Expose only Questarr v1.4.2's required NZBGet XML-RPC operations."""

    def __init__(self, manager: JobManager, loop: Any, *, database: Path | None = None,
                 nzb_root: Path | None = None, watched_nzb_root: Path | None = None) -> None:
        self.manager = manager
        self.loop = loop
        self.database = database or PATHS.data_root / "questarr-gateway.sqlite3"
        # NZBGet recursively scans its configured NzbDir. Gateway-owned files
        # must stay in Acquisitiond-private storage, never in that watched tree.
        self.watched_nzb_root = Path(watched_nzb_root or PATHS.usenet_nzb_root).resolve()
        self.nzb_root = Path(nzb_root or PATHS.data_root / "questarr-nzb-staging").resolve()
        if self.nzb_root == self.watched_nzb_root or self.watched_nzb_root in self.nzb_root.parents:
            raise ValueError("Questarr NZB staging must be outside NZBGet's watched NzbDir")
        self._lock = threading.RLock()
        self.database.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.nzb_root.mkdir(parents=True, exist_ok=True)
        os.chmod(self.nzb_root, 0o700)
        if self.nzb_root.stat().st_mode & 0o077:
            raise PermissionError("Questarr NZB staging must be private to its owner")
        self._db = sqlite3.connect(self.database, check_same_thread=False)
        os.chmod(self.database, 0o600)
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.execute("""CREATE TABLE IF NOT EXISTS nzb_requests (
            client_id INTEGER PRIMARY KEY AUTOINCREMENT,
            fingerprint TEXT NOT NULL UNIQUE,
            content_identity TEXT NOT NULL UNIQUE,
            title TEXT NOT NULL,
            job_id TEXT NOT NULL DEFAULT '',
            category TEXT NOT NULL DEFAULT 'questarr',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )""")
        columns = {str(row[1]) for row in self._db.execute("PRAGMA table_info(nzb_requests)")}
        if "category" not in columns:
            self._db.execute("ALTER TABLE nzb_requests ADD COLUMN category TEXT NOT NULL DEFAULT 'questarr'")
        self._db.commit()

    def close(self) -> None:
        self._db.close()

    def _on_loop(self, coroutine: Any) -> Any:
        future: Future[Any] = asyncio.run_coroutine_threadsafe(coroutine, self.loop)
        try:
            return future.result(timeout=20)
        except TimeoutError as error:
            future.cancel()
            raise RuntimeError("Acquisitiond did not respond in time") from error

    def _jobs(self) -> tuple[DownloadJob, ...]:
        async def snapshot() -> tuple[DownloadJob, ...]:
            return self.manager.snapshot()
        return self._on_loop(snapshot())

    @staticmethod
    def _validated_url(source: str) -> str:
        if len(source) > 8192 or any(ord(char) < 32 or ord(char) == 127 for char in source):
            raise Fault(400, "NZB source URL is invalid")
        try:
            parsed = urlsplit(source)
            _port = parsed.port
        except ValueError as error:
            raise Fault(400, "NZB source URL is invalid") from error
        if (parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname
                or parsed.username is not None or parsed.password is not None
                or parsed.fragment):
            raise Fault(400, "NZB source URL is unsupported")
        return source

    @staticmethod
    def _validate_document(content: bytes) -> str:
        if not content or len(content) > MAX_NZB_BYTES:
            raise Fault(400, "NZB content size is invalid")
        try:
            document = content.decode("utf-8-sig")
        except UnicodeDecodeError as error:
            raise Fault(400, "NZB content must be UTF-8 XML") from error
        # Standard NZB files use an external DOCTYPE. ElementTree does not
        # retrieve that external DTD; reject entity declarations so parsing
        # cannot expand attacker-controlled internal entities.
        if "<!ENTITY" in document.upper():
            raise Fault(400, "NZB entity declarations are unsupported")
        try:
            root = ElementTree.fromstring(document)
        except ElementTree.ParseError as error:
            raise Fault(400, "decoded NZB content is malformed XML") from error
        root_name = str(root.tag).rsplit("}", 1)[-1].casefold()
        if root_name != "nzb":
            raise Fault(400, "decoded XML root must be nzb")
        return root_name

    def _submit(self, source: bytes | str, title: str, category: str,
                rpc_metadata: dict[str, object]) -> int:
        import hashlib
        if isinstance(source, str):
            source = self._validated_url(source)
            digest = hashlib.sha256(source.encode("utf-8")).hexdigest()
            content_identity = source
            path = None
        else:
            digest = hashlib.sha256(source).hexdigest()
            content_identity = f"file://{self.nzb_root / (digest + '.nzb')}"
            path = self.nzb_root / f"{digest}.nzb"
        fingerprint = digest
        with self._lock:
            row = self._db.execute(
                "SELECT client_id, job_id FROM nzb_requests WHERE fingerprint=?", (fingerprint,)
            ).fetchone()
            if row:
                client_id, job_id = int(row[0]), str(row[1])
                current_jobs = self._jobs()
                if job_id and any(job.job_id == job_id for job in current_jobs):
                    return client_id
                # A stale mapping is not permission to resubmit: Acquisitiond
                # may have pruned old terminal history. Keep its external ID
                # stable rather than silently creating a second acquisition.
                if job_id:
                    return client_id
                matching = next((job for job in current_jobs
                                 if job.content_identity == content_identity and job.origin == "questarr"), None)
                if matching is not None:
                    self._db.execute("UPDATE nzb_requests SET job_id=? WHERE client_id=?",
                                     (matching.job_id, client_id))
                    self._db.commit()
                    return client_id
            else:
                self._db.execute(
                    "INSERT INTO nzb_requests(fingerprint,content_identity,title,category) VALUES(?,?,?,?)",
                    (fingerprint, content_identity, title[:500] or "download.nzb", category[:128] or "questarr"),
                )
                self._db.commit()
                client_id = int(self._db.execute(
                    "SELECT client_id FROM nzb_requests WHERE fingerprint=?", (fingerprint,)
                ).fetchone()[0])

            if isinstance(source, bytes):
                assert path is not None
                path.parent.mkdir(parents=True, exist_ok=True)
                if not path.exists():
                    temporary = path.with_suffix(".tmp")
                    temporary.write_bytes(source)
                    temporary.chmod(0o600)
                    temporary.replace(path)
                default_title = path.name
            else:
                default_title = "download.nzb"
            normalized_title = title.strip()[:500] or default_title

            async def submit_job() -> DownloadJob:
                executor = self.manager.executors.get("usenet")
                return self.manager.submit(
                    "usenet", content_identity, normalized_title,
                    cancellation_supported=True,
                    pause_supported=bool(getattr(executor, "supports_pause", False)),
                    origin="questarr",
                    origin_metadata={"transport": "usenet", "request_fingerprint": fingerprint,
                                     "external_client_id": client_id, "source": "Questarr",
                                     "rpc": rpc_metadata},
                )

            job = self._on_loop(submit_job())
            self._db.execute("UPDATE nzb_requests SET job_id=?, title=? WHERE client_id=?",
                             (job.job_id, normalized_title, client_id))
            self._db.commit()
            return client_id

    @staticmethod
    def _xml_response(value: Any) -> bytes:
        return dumps((value,), methodresponse=True, allow_none=False).encode("utf-8")

    def _job_row(self, client_id: int) -> tuple[DownloadJob | None, str]:
        with self._lock:
            row = self._db.execute("SELECT job_id,title FROM nzb_requests WHERE client_id=?",
                                   (client_id,)).fetchone()
        if row is None:
            return None, ""
        job_id, title = str(row[0]), str(row[1])
        job = next((item for item in self._jobs() if item.job_id == job_id), None)
        return job, title

    @staticmethod
    def _state(job: DownloadJob) -> str:
        if job.state in {JobState.QUEUED, JobState.STARTING}:
            return "QUEUED"
        if job.state in {JobState.TRANSFERRING, JobState.AWAITING_INTERACTION}:
            return "DOWNLOADING"
        if job.state in {JobState.PAUSED, JobState.PAUSING, JobState.RESUMING}:
            return "PAUSED"
        if job.state == JobState.FINALIZING:
            return "POST_PROCESSING"
        if job.state == JobState.COMPLETED:
            return "SUCCESS/ALL"
        if job.state == JobState.CANCELLED:
            return "DELETED"
        return "FAILURE"

    def _status_row(self, client_id: int, job: DownloadJob, title: str,
                    category: str = "questarr") -> dict[str, Any]:
        total = job.total_bytes or 0
        downloaded = job.downloaded_bytes or 0
        remaining = max(0, total - downloaded)
        state = self._state(job)
        common = {"NZBID": client_id, "Category": category}
        if state in {"SUCCESS/ALL", "FAILURE", "DELETED"}:
            return {**common, "Name": title, "Status": state,
                    "FileSizeMB": total / 1048576, "DownloadTimeSec": 0,
                    "ParStatus": "NONE", "UnpackStatus": "NONE", "FailedArticles": 0,
                    "DeleteStatus": "MANUAL" if state == "DELETED" else "NONE",
                    "DestDir": job.destination or ""}
        return {**common, "NZBName": title, "Status": state,
                "FileSizeMB": total / 1048576, "RemainingSizeMB": remaining / 1048576,
                "DownloadedSizeMB": downloaded / 1048576,
                "DownloadRate": job.download_rate or 0, "PostInfoText": job.stage,
                "PostStageProgress": 0, "PostStageTimeSec": 0}

    def call(self, method: str, params: tuple[Any, ...]) -> Any:
        if method == "version":
            return NZBGET_VERSION
        if method == "status":
            import shutil
            free = shutil.disk_usage(self.nzb_root).free
            return {"FreeDiskSpaceMB": free / 1048576}
        if method == "append":
            if len(params) != 10:
                raise Fault(400, "append expects Questarr's ten-parameter NZBGet request")
            if not isinstance(params[0], str) or not isinstance(params[1], str):
                raise Fault(400, "append expects a filename and content string")
            if not isinstance(params[2], str) or not isinstance(params[3], (int, float)) \
                    or not isinstance(params[4], bool) or not isinstance(params[5], bool) \
                    or not isinstance(params[6], str) or not isinstance(params[7], (int, float)) \
                    or not isinstance(params[8], str) or not isinstance(params[9], (list, tuple)):
                raise Fault(400, "append parameters do not match the supported Questarr NZBGet shape")
            name, submitted_content = params[0], params[1]
            category = params[2]
            rpc_metadata = {
                "method": "append", "parameter_count": len(params),
                "category": category[:128], "priority": params[3],
                "add_to_top": params[4], "add_paused": params[5],
                "duplicate_key_present": bool(params[6]), "duplicate_score": params[7],
                "duplicate_mode": params[8][:32], "postprocess_parameter_count": len(params[9]),
            }
            url_candidate = submitted_content.lstrip()
            if url_candidate.lower().startswith(("http://", "https://")):
                source: bytes | str = self._validated_url(url_candidate)
                parsed = urlsplit(source)
                rpc_metadata.update({"content_form": "url", "content_length": len(submitted_content),
                                     "url_scheme": parsed.scheme, "url_host": parsed.hostname or "",
                                     "url_path": parsed.path[:512],
                                     "url_query": "<redacted>" if parsed.query else "",
                                     "url_query_present": bool(parsed.query)})
            else:
                if len(submitted_content) > ((MAX_NZB_BYTES + 2) // 3) * 4:
                    raise Fault(413, "encoded NZB content exceeds the supported size")
                try:
                    decoded = base64.b64decode(submitted_content, validate=True)
                except (ValueError, TypeError) as error:
                    raise Fault(400, "append content is neither a supported URL nor valid base64") from error
                root_name = self._validate_document(decoded)
                source = decoded
                rpc_metadata.update({"content_form": "base64-xml", "encoded_length": len(submitted_content),
                                     "decoded_length": len(decoded), "document_root": root_name})
            LOGGER.info("Questarr NZBGet RPC shape filename_length=%d %s",
                        len(name), json.dumps(rpc_metadata, sort_keys=True, separators=(",", ":")))
            try:
                return self._submit(source, name, category, rpc_metadata)
            except Exception as error:
                LOGGER.warning("Questarr NZB submission rejected error_type=%s", type(error).__name__)
                raise Fault(503, str(error)[:300]) from error
        if method == "listgroups":
            with self._lock:
                rows = self._db.execute(
                    "SELECT client_id,title,job_id,category FROM nzb_requests ORDER BY client_id"
                ).fetchall()
            result = []
            jobs = {job.job_id: job for job in self._jobs()}
            for client_id, title, job_id, category in rows:
                job = jobs.get(str(job_id))
                if job and job.state not in {JobState.COMPLETED, JobState.FAILED, JobState.CANCELLED}:
                    result.append(self._status_row(int(client_id), job, str(title), str(category)))
            return result
        if method == "history":
            with self._lock:
                rows = self._db.execute(
                    "SELECT client_id,title,job_id,category FROM nzb_requests ORDER BY client_id"
                ).fetchall()
            jobs = {job.job_id: job for job in self._jobs()}
            return [self._status_row(int(client_id), jobs[str(job_id)], str(title), str(category))
                    for client_id, title, job_id, category in rows if str(job_id) in jobs
                    and jobs[str(job_id)].state in {JobState.COMPLETED, JobState.FAILED, JobState.CANCELLED}]
        if method == "editqueue":
            if len(params) < 4 or not isinstance(params[3], (list, tuple)):
                raise Fault(400, "editqueue expects operation and NZB IDs")
            action = str(params[0])
            ids = [int(value) for value in params[3]]
            for client_id in ids:
                job, _ = self._job_row(client_id)
                if job is None:
                    continue
                if action == "GroupPause":
                    self._on_loop(self.manager.pause(job.job_id))
                elif action == "GroupResume":
                    self._on_loop(self.manager.resume(job.job_id))
                elif action in {"GroupDelete", "GroupFinalDelete"}:
                    self._on_loop(self.manager.cancel(job.job_id))
                else:
                    raise Fault(400, f"unsupported editqueue operation: {action}")
            return True
        raise Fault(404, f"unsupported NZBGet method: {method}")


def make_handler(gateway: QuestarrGateway) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        server_version = "MudosQuestarrGateway/1"

        def do_POST(self) -> None:
            if self.path.rstrip("/") not in {"/xmlrpc", "/nzbget/xmlrpc"}:
                self.send_error(404)
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if length <= 0 or length > 32 * 1024 * 1024:
                    raise Fault(413, "invalid XML-RPC request size")
                params, method = loads(self.rfile.read(length))
                result = gateway.call(method, params)
                payload = gateway._xml_response(result)
                self.send_response(200)
                self.send_header("Content-Type", "text/xml")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
            except Fault as error:
                payload = dumps(error, allow_none=False).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/xml")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
            except Exception as error:
                LOGGER.warning("Questarr gateway request failed error_type=%s", type(error).__name__)
                self.send_error(400, "invalid XML-RPC request")

        def log_message(self, _format: str, *_args: object) -> None:
            return

    return Handler


def serve_gateway(gateway: QuestarrGateway, host: str = GATEWAY_HOST,
                  port: int = GATEWAY_PORT) -> ThreadingHTTPServer:
    server = ThreadingHTTPServer((host, port), make_handler(gateway))
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, name="questarr-gateway", daemon=True)
    thread.start()
    LOGGER.info("Questarr NZBGet compatibility gateway listening host=%s port=%s", host, port)
    return server
