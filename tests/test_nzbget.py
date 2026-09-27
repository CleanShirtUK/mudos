import asyncio
import base64
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from lulu.jobs import DownloadJob, JobState
from lulu.paths import MudosPaths
from lulu.plugins.usenet.nzbget import NzbGetClient, NzbGetConfig, NzbHistory, UsenetProvider, _history_failure_message
from lulu.plugins.usenet.nzbget import NzbDownload
from lulu.nzbget_admin import apply_control_credentials, apply_news_server, apply_packaged_paths
from lulu.job_manager import JobCancelled, JobExecutionError


class NzbGetClientTests(unittest.TestCase):
    def test_control_credentials_are_materialized_without_logging(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "nzbget.conf"
            path.write_text("ControlIP=127.0.0.1\nControlUsername=old\nControlPassword=old-secret\n")
            apply_control_credentials("mudos-admin", "replacement-secret", path)
            values = dict(line.split("=", 1) for line in path.read_text().splitlines())
            self.assertEqual(values["ControlUsername"], "mudos-admin")
            self.assertEqual(values["ControlPassword"], "replacement-secret")

    def test_news_server_is_materialized_as_server_one(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "nzbget.conf"
            path.write_text("ControlPort=6789\nServer1.Active=no\nServer1.Connections=8\n")
            apply_news_server("reader.turbousenet.com", 563, True, 50, "user", "secret", True, path)
            values = dict(line.split("=", 1) for line in path.read_text().splitlines())
            self.assertEqual(values["Server1.Host"], "reader.turbousenet.com")
            self.assertEqual(values["Server1.Port"], "563")
            self.assertEqual(values["Server1.Encryption"], "yes")
            self.assertEqual(values["Server1.Connections"], "50")
            self.assertEqual(values["Server1.Active"], "yes")
            self.assertEqual(path.stat().st_mode & 0o777, 0o660)

    def test_news_server_materialization_fails_cleanly_when_managed_config_is_absent(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "missing" / "nzbget.conf"
            with self.assertRaises(FileNotFoundError):
                apply_news_server("reader.example", 563, True, 8, "user", "secret", path=path)
            self.assertFalse(path.parent.exists())

    def test_packaged_paths_are_materialized(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "nzbget.conf"
            path.write_text("WebDir=\nConfigTemplate=old\nScriptDir=old\n")
            apply_packaged_paths(path)
            values = dict(line.split("=", 1) for line in path.read_text().splitlines())
            self.assertEqual(values["WebDir"], "/usr/share/nzbget/webui")
            self.assertEqual(values["ConfigTemplate"], "/usr/share/nzbget/nzbget.conf")
            self.assertEqual(values["ScriptDir"], "/var/lib/nzbget/scripts")

    def test_json_rpc_auth_and_health(self) -> None:
        calls = []

        def request(payload):
            calls.append(json.loads(payload))
            method = calls[-1]["method"]
            result = "26.2" if method == "version" else {"DownloadRate": 12}
            return json.dumps({"jsonrpc": "2.0", "id": calls[-1]["id"], "result": result}).encode()

        async def exercise():
            client = NzbGetClient(NzbGetConfig(username="mudos", password="secret"))
            with patch.object(client, "_request_sync", side_effect=request):
                health = await client.health()
            self.assertEqual(health["version"], "26.2")

        asyncio.run(exercise())
        self.assertEqual([item["method"] for item in calls], ["version", "status"])

    def test_append_uses_base64_nzb_and_durable_dupe_key(self) -> None:
        async def exercise():
            client = NzbGetClient(NzbGetConfig())
            with patch.object(client, "call", return_value=41) as call:
                result = await client.append(b"<nzb/>", "game.nzb", category="mudos",
                                             dupe_key="mudos:job-1")
            self.assertEqual(result, 41)
            params = call.call_args.args[1]
            self.assertEqual(params[1], base64.b64encode(b"<nzb/>").decode())
            self.assertEqual(params[6], "mudos:job-1")

    def test_queue_commands_are_per_group_not_global(self) -> None:
        async def exercise():
            client = NzbGetClient(NzbGetConfig())
            with patch.object(client, "call", return_value=True) as call:
                await client.pause(7)
                await client.resume(7)
                await client.remove(7)
            self.assertEqual([item.args[0] for item in call.call_args_list], ["editqueue"] * 3)
            self.assertEqual([item.args[1][0] for item in call.call_args_list],
                             ["GroupPause", "GroupResume", "GroupDelete"])

        asyncio.run(exercise())

    def test_high_low_fields_are_combined(self) -> None:
        value = NzbGetClient._group({"NZBID": 4, "NZBName": "x", "DupeKey": "mudos:j",
                                     "FileSizeHi": 1, "FileSizeLo": 2,
                                     "RemainingSizeHi": 0, "RemainingSizeLo": 2,
                                     "DownloadedSizeHi": 0, "DownloadedSizeLo": 0})
        self.assertEqual(value.total_bytes, (1 << 32) + 2)


class UsenetProviderTests(unittest.TestCase):
    def test_external_manual_item_is_discovered_without_claiming_mudos_ownership(self) -> None:
        class FakeClient:
            async def groups(self):
                return (NzbDownload(1, "manual-game", "", "", "PAUSED", 100, 50, 50, 0,
                                    "/incomplete/manual", "", None, "NONE"),)
            async def history(self): return ()
        async def exercise():
            with tempfile.TemporaryDirectory() as directory:
                base = Path(directory)
                paths = MudosPaths(base / "Games", base / "config", base / "data", base / "cache", base / "run")
                records = await UsenetProvider(FakeClient(), paths).discover_external()
                self.assertEqual(len(records), 1)
                self.assertEqual(records[0].origin, "external")
                self.assertEqual(records[0].provenance, "external/manual")
                self.assertEqual(records[0].state.value, "paused")
                self.assertTrue(list(paths.usenet_ownership_root.glob("external/*.json")))
        asyncio.run(exercise())

    def test_external_failed_history_preserves_provider_error(self) -> None:
        class FakeClient:
            async def groups(self): return ()
            async def history(self):
                return (NzbHistory(11, "external-fixture", "", "", "FAILURE/PAR",
                                   "/incomplete", "", source_name="fixture.nzb",
                                   par_status="FAILURE", failed_articles=1, total_articles=10),)

        async def exercise():
            with tempfile.TemporaryDirectory() as directory:
                base = Path(directory)
                paths = MudosPaths(base / "Games", base / "config", base / "data", base / "cache", base / "run")
                record, = await UsenetProvider(FakeClient(), paths).discover_external()
                self.assertEqual(record.state.value, "failed")
                self.assertEqual(record.error.code, "usenet-provider-failure")
                self.assertIn("1 of 10 articles failed", record.error.message)

        asyncio.run(exercise())

    def test_external_identity_ignores_mutable_queue_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            paths = MudosPaths(base / "Games", base / "config", base / "data", base / "cache", base / "run")
            provider = UsenetProvider(object(), paths)  # type: ignore[arg-type]
            first = NzbDownload(1, "manual-game", "", "", "DOWNLOADING", 100, 50, 50, 10,
                                "/one", "", None, "NONE")
            second = NzbDownload(99, "manual-game", "changed", "", "PP_QUEUED", 100, 0, 100, 0,
                                 "/two", "/final", None, "NONE")
            origin, provenance = provider._external_origin(first)
            key = provider._external_key(first); provider._remember_external(key, first, origin, provenance)
            self.assertEqual(provider._external_key(second), key)

    def test_ownership_sidecar_and_dupe_key(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            paths = MudosPaths(base / "Games", base / "config", base / "data", base / "cache", base / "run")
            provider = UsenetProvider(object(), paths)  # type: ignore[arg-type]
            job = DownloadJob("job-1", "usenet", "Game", content_identity="/tmp/game.nzb")
            provider._record(job, 42, str(paths.usenet_complete_root))
            value = json.loads((paths.usenet_ownership_root / "job-1.json").read_text())
            self.assertEqual(value["dupe_key"], "mudos:job-1")
            self.assertEqual(value["nzbid"], 42)

    def test_unowned_queue_item_is_not_adopted(self) -> None:
        class FakeClient:
            async def find(self, key):
                return None, None

        async def exercise():
            with tempfile.TemporaryDirectory() as directory:
                base = Path(directory)
                paths = MudosPaths(base / "Games", base / "config", base / "data", base / "cache", base / "run")
                provider = UsenetProvider(FakeClient(), paths)  # type: ignore[arg-type]
                job = DownloadJob("job-1", "usenet", "Game", content_identity="missing.nzb")
                with self.assertRaises(Exception) as error:
                    await provider.run(job, object())  # type: ignore[arg-type]
                self.assertIn("requires an NZB", str(error.exception))

        asyncio.run(exercise())

    def test_post_processing_failure_is_a_provider_failure(self) -> None:
        history = NzbHistory(3, "game", "mudos", "mudos:job", "FAILURE/UNPACK", "/complete", "")
        self.assertTrue(history.status.startswith("FAILURE"))

    def test_history_maps_nzb_filename_separately_and_keeps_failure_reason(self) -> None:
        history = NzbGetClient._history({
            "NZBID": 9, "Name": "fixture", "Status": "FAILURE/PAR",
            "NZBFilename": "/staging/fixture.nzb", "ParStatus": "FAILURE",
            "FailedArticles": 88, "TotalArticles": 536, "ExtraParBlocks": 0,
        })
        self.assertIsNone(history.error)
        self.assertEqual(history.source_name, "/staging/fixture.nzb")
        self.assertEqual(
            _history_failure_message(history),
            "NZBGet PAR verification/repair failed (FAILURE/PAR); 88 of 536 articles failed; "
            "no additional recovery blocks were available",
        )

    def test_successful_history_is_completion_after_post_processing(self) -> None:
        class FakeClient:
            async def find(self, key):
                return None, NzbHistory(3, "game", "mudos", key, "SUCCESS/ALL", "/complete", "/complete/game")

        class Reporter:
            def __init__(self): self.values = {}
            async def metadata(self, **values): self.values.update(values)
            async def progress(self, *args, **values): self.values.update(values)

        async def exercise():
            with tempfile.TemporaryDirectory() as directory:
                base = Path(directory)
                paths = MudosPaths(base / "Games", base / "config", base / "data", base / "cache", base / "run")
                reporter = Reporter()
                await UsenetProvider(FakeClient(), paths).run(
                    DownloadJob("job-1", "usenet", "Game"), reporter)  # type: ignore[arg-type]
                self.assertEqual(reporter.values["stage"], "completed")
                self.assertEqual(reporter.values["completion_path"], "/complete/game/game")

        asyncio.run(exercise())

    def test_failed_and_manually_deleted_history_are_distinct(self) -> None:
        class FakeClient:
            def __init__(self, status): self.status = status
            async def find(self, key):
                return None, NzbHistory(3, "game", "mudos", key, self.status, "/complete", "")

        class Reporter:
            async def metadata(self, **values): pass
            async def progress(self, *args, **values): pass

        async def exercise():
            with tempfile.TemporaryDirectory() as directory:
                base = Path(directory)
                paths = MudosPaths(base / "Games", base / "config", base / "data", base / "cache", base / "run")
                job = DownloadJob("job-1", "usenet", "Game")
                with self.assertRaises(JobExecutionError):
                    await UsenetProvider(FakeClient("FAILURE/PAR"), paths).run(job, Reporter())  # type: ignore[arg-type]
                with self.assertRaises(JobCancelled):
                    await UsenetProvider(FakeClient("DELETED/MANUAL"), paths).run(job, Reporter())  # type: ignore[arg-type]
                with self.assertRaises(JobExecutionError) as duplicate:
                    await UsenetProvider(FakeClient("DELETED/COPY"), paths).run(job, Reporter())  # type: ignore[arg-type]
                self.assertEqual(duplicate.exception.code, "usenet-duplicate")
                self.assertIn("duplicate", str(duplicate.exception))

        asyncio.run(exercise())

    def test_owned_job_failure_details_include_missing_article_cause(self) -> None:
        class FakeClient:
            async def find(self, key):
                return None, NzbHistory(7, "fixture", "mudos", key, "FAILURE/PAR",
                                        "/incomplete", "", source_name="fixture.nzb",
                                        par_status="FAILURE", failed_articles=2,
                                        total_articles=21, extra_par_blocks=0)

        class Reporter:
            async def metadata(self, **values): pass
            async def progress(self, *args, **values): pass

        async def exercise():
            with tempfile.TemporaryDirectory() as directory:
                base = Path(directory)
                paths = MudosPaths(base / "Games", base / "config", base / "data", base / "cache", base / "run")
                with self.assertRaises(JobExecutionError) as error:
                    await UsenetProvider(FakeClient(), paths).run(
                        DownloadJob("job-7", "usenet", "fixture"), Reporter())  # type: ignore[arg-type]
                self.assertIn("2 of 21 articles failed", str(error.exception))
                self.assertEqual(error.exception.details["provider_status"], "FAILURE/PAR")

        asyncio.run(exercise())

    def test_owned_deleted_copy_reconciles_to_failed_not_stuck_starting(self) -> None:
        from lulu.job_manager import JobManager

        class FakeClient:
            async def find(self, key):
                return None, NzbHistory(8, "fixture", "mudos", key, "DELETED/COPY",
                                        "/incomplete", "", source_name="fixture.nzb")

        async def exercise():
            with tempfile.TemporaryDirectory() as directory:
                base = Path(directory)
                paths = MudosPaths(base / "Games", base / "config", base / "data", base / "cache", base / "run")
                manager = JobManager()
                manager.register_executor("usenet", UsenetProvider(FakeClient(), paths))  # type: ignore[arg-type]
                submitted = manager.submit("usenet", "fixture.nzb", "fixture")
                await asyncio.sleep(0.05)
                result = manager.jobs[submitted.job_id]
                self.assertEqual(result.state, JobState.FAILED)
                self.assertEqual(result.error.code, "usenet-duplicate")
                self.assertEqual(result.provider_job_id, "8")
                self.assertEqual(result.ownership_label, "mudos:" + submitted.job_id)
                self.assertEqual(result.provider_state, "DELETED/COPY")

        asyncio.run(exercise())


if __name__ == "__main__":
    unittest.main()
