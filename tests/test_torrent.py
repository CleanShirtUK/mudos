import asyncio
import base64
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from lulu.plugins.torrent.transmission import (
    TransmissionClient, TransmissionConfig, TorrentProvider,
    TorrentDownload,
)
from lulu.jobs import DownloadJob
from lulu.paths import MudosPaths
from lulu.job_manager import JobExecutionError


class TransmissionClientTests(unittest.TestCase):
    def test_409_session_retry_and_json_rpc(self):
        calls = []
        def request(body, headers):
            calls.append((json.loads(body), headers.copy()))
            if len(calls) == 1:
                return 409, {"x-transmission-session-id": "session-1"}, b"{}"
            return 200, {}, json.dumps({"result": {"version": "4.1.3"}}).encode()
        async def exercise():
            client = TransmissionClient(TransmissionConfig(username="u", password="p"))
            with patch.object(client, "_request_sync", side_effect=request):
                result = await client.call("session_get", {"fields": ["version"]})
            self.assertEqual(result["version"], "4.1.3")
        asyncio.run(exercise())
        self.assertEqual(calls[1][0]["jsonrpc"], "2.0")
        self.assertEqual(calls[1][0]["method"], "session_get")
        self.assertEqual(calls[1][1]["X-Transmission-Session-Id"], "session-1")
        self.assertTrue(calls[1][1]["Authorization"].startswith("Basic "))

    def test_magnet_and_metainfo_use_current_torrent_add(self):
        methods = []
        async def exercise():
            client = TransmissionClient(TransmissionConfig())
            async def call(method, params=None):
                methods.append((method, params))
                return {"torrent_added": {"hash_string": "abc"}}
            with patch.object(client, "call", side_effect=call):
                self.assertEqual(await client.add_magnet("magnet:?xt=urn:btih:abc", "/complete", "mudos"), "abc")
                self.assertEqual(await client.add_torrent(b"torrent", "/complete", "mudos"), "abc")
        asyncio.run(exercise())
        self.assertEqual(methods[0][0], "torrent_add")
        self.assertEqual(methods[0][1]["filename"], "magnet:?xt=urn:btih:abc")
        self.assertEqual(methods[1][1]["metainfo"], base64.b64encode(b"torrent").decode())
        self.assertNotIn("/upload", str(methods))

    def test_status_and_file_normalization(self):
        client = TransmissionClient(TransmissionConfig())
        value = client._normalize({
            "hash_string": "abc", "name": "Game", "download_dir": "/complete",
            "files": [{"name": "Game/file.bin", "length": 10}],
            "file_stats": [{"bytes_completed": 10}], "wanted": [True], "priorities": [1],
            "percent_done": 1.0, "bytes_completed": 10, "size_when_done": 10,
            "status": 6, "eta": -1, "is_finished": True, "labels": ["mudos"],
        })
        self.assertEqual(value.state, "completed")
        self.assertTrue(value.seeding)
        self.assertEqual(value.files[0].name, "Game/file.bin")

    def test_file_selection_uses_normalized_arguments(self):
        async def exercise():
            client = TransmissionClient(TransmissionConfig())
            with patch.object(client, "call", return_value={}) as call:
                await client.set_files("abc", wanted=[0], unwanted=[1], high=[0], low=[1])
            self.assertEqual(call.call_args.args[0], "torrent_set")
            self.assertEqual(call.call_args.args[1]["ids"], ["abc"])
            self.assertEqual(call.call_args.args[1]["files_wanted"], [0])
            self.assertEqual(call.call_args.args[1]["priority_low"], [1])
        asyncio.run(exercise())

    def test_remove_can_request_payload_deletion(self):
        async def exercise():
            client = TransmissionClient(TransmissionConfig())
            with patch.object(client, "call", return_value={}) as call:
                await client.remove("abc", delete_local_data=True)
            self.assertEqual(call.call_args.args[0], "torrent_remove")
            self.assertTrue(call.call_args.args[1]["delete_local_data"])
        asyncio.run(exercise())


class TorrentSafetyTests(unittest.TestCase):
    def test_external_discovery_uses_hash_and_preserves_questarr_origin(self):
        item = TorrentDownload("ABCDEF12", "Manual", "/downloads", (), .5, 5, 10, 2, 0,
                               None, "transferring", "4", None, ("questarr",), False, False)
        class FakeClient:
            async def list_all(self): return (item,)
        async def exercise():
            provider = TorrentProvider(FakeClient())  # type: ignore[arg-type]
            records = await provider.discover_external()
            self.assertEqual(records[0].content_identity, "transmission:abcdef12")
            self.assertEqual(records[0].origin, "questarr")
            self.assertEqual(records[0].provenance, "questarr")
        asyncio.run(exercise())

    def test_mudos_ownership_sidecar_records_job_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            paths = MudosPaths(base / "Games", base / "config", base / "data", base / "cache", base / "run")
            provider = TorrentProvider(object(), paths)  # type: ignore[arg-type]
            job = DownloadJob("job-1", "torrent", "Game", content_identity="magnet:?xt=urn:btih:abc")
            provider._record_ownership(job, "abcdef12")
            value = json.loads((paths.torrent_ownership_root / "abcdef12.json").read_text())
            self.assertEqual(value["job_id"], "job-1")
            self.assertEqual(value["label"], "mudos")

    def test_delete_path_requires_owned_torrent_root(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            paths = MudosPaths(base / "Games", base / "config", base / "data", base / "cache", base / "run")
            provider = TorrentProvider(object(), paths)  # type: ignore[arg-type]
            job = DownloadJob("job", "torrent", "Game", provider_job_id="abc", ownership_label="mudos")
            with self.assertRaises(JobExecutionError):
                provider._owned_path(str(base / "Games" / "outside.bin"), job)

    def test_symlink_escape_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            paths = MudosPaths(base / "Games", base / "config", base / "data", base / "cache", base / "run")
            paths.torrent_incomplete_root.mkdir(parents=True)
            outside = base / "outside"
            outside.mkdir()
            link = paths.torrent_incomplete_root / "link"
            link.symlink_to(outside, target_is_directory=True)
            provider = TorrentProvider(object(), paths)  # type: ignore[arg-type]
            job = DownloadJob("job", "torrent", "Game", provider_job_id="abc", ownership_label="mudos")
            with self.assertRaises(JobExecutionError):
                provider._owned_path(str(link), job)
