import unittest
import json
import tempfile
from pathlib import Path
from urllib.error import HTTPError
from io import BytesIO
import base64
import time

from lulu.questarr_reconciler import QuestarrApi, QuestarrRateLimited, QuestarrReconciler


class Secrets:
    def __init__(self, values=None):
        self.values = values or {}

    def get(self, namespace, name):
        return self.values.get((namespace, name))

    def configured(self, namespace, name):
        return (namespace, name) in self.values


class Provider:
    def __init__(self, values, secrets):
        self.values = values
        self._secrets = secrets

    @property
    def configured(self):
        return bool(self.values.get("enabled", True)) and all(
            self.secret(name) for name in self.values.get("required", ())
        )

    def get(self, name, default=None):
        return self.values.get(name, default)

    def secret(self, name):
        return self._secrets.get(name)


class Config:
    def __init__(self, secrets):
        self.providers = {
            "providers.torrent": Provider(
                {"enabled": True, "required": ("username", "password")},
                {"username": "torrent-user", "password": "torrent-pass"},
            ),
            "providers.usenet": Provider(
                {"enabled": True, "username": "mudos", "required": ("rpc_password",)},
                {"rpc_password": "nzb-pass"},
            ),
            "providers.prowlarr": Provider(
                {"enabled": False}, {},
            ),
            "metadata.igdb": Provider(
                {"enabled": True, "client_id": ""}, {},
            ),
        }

    def provider(self, name):
        return self.providers[name]


class Api:
    def __init__(self, downloaders=None, prowlarr_error=False):
        self.downloaders = downloaders or []
        self.calls = []
        self.prowlarr_error = prowlarr_error
        self.token = ""

    def login(self, username, password):
        self.calls.append(("login", username, password))
        self.token = "backend-only-token"

    def get(self, path):
        self.calls.append(("get", path))
        if path == "/api/downloaders":
            return self.downloaders
        if path == "/api/indexers":
            return [{"protocol": "torznab"}, {"protocol": "newznab"}]
        raise AssertionError(path)

    def post(self, path, body):
        self.calls.append(("post", path, body))
        if path == "/api/indexers/prowlarr/sync" and self.prowlarr_error:
            raise RuntimeError("offline")
        if path == "/api/settings/igdb":
            return {"success": True}
        if path.endswith("/test"):
            return {"success": True}
        item = dict(body)
        item["id"] = f"id-{len(self.downloaders)}"
        self.downloaders.append(item)
        return item

    def patch(self, path, body):
        self.calls.append(("patch", path, body))
        return body


class QuestarrReconcilerTests(unittest.TestCase):
    def configured(self, api=None, values=None, lock_path=None):
        secret_values = {
            ("web/questarr", "username"): "web-user",
            ("web/questarr", "password"): "web-pass",
        }
        secrets = Secrets(secret_values)
        return QuestarrReconciler(api=api or Api(), config=Config(secrets), secrets=secrets,
                                  lock_path=lock_path)

    def test_missing_web_credentials_is_safe_noop(self):
        api = Api()
        secrets = Secrets()
        result = QuestarrReconciler(api=api, config=Config(secrets), secrets=secrets).reconcile()
        self.assertEqual(result.status, "unconfigured")
        self.assertEqual(api.calls, [])

    def test_reconciliation_configures_only_acquisitiond_nzb_gateway(self):
        api = Api()
        result = self.configured(api).reconcile()
        self.assertEqual(result.status, "ok")
        self.assertEqual(result.transmission, "deferred-until-torrent-gateway")
        self.assertEqual(result.nzbget, "created")
        self.assertEqual(len([c for c in api.calls if c[0] == "post" and c[1].endswith("/test")]), 1)
        self.assertEqual(len(api.downloaders), 1)
        self.assertTrue(all('"owner":"mudos.questarr"' in d["settings"] for d in api.downloaders))
        downloader = api.downloaders[0]
        self.assertEqual(downloader["url"], "http://127.0.0.1")
        self.assertEqual(downloader["port"], 5001)
        self.assertEqual(downloader["username"], "")
        self.assertEqual(downloader["password"], "")
        self.assertEqual(downloader["urlPath"], "/xmlrpc")
        self.assertNotIn("nzb-pass", repr(downloader))

    def test_managed_gateway_entry_updates_without_duplicate(self):
        api = Api()
        self.configured(api).reconcile()
        api.calls.clear()
        result = self.configured(api).reconcile()
        self.assertEqual(result.transmission, "deferred-until-torrent-gateway")
        self.assertEqual(result.nzbget, "updated")
        self.assertEqual(len(api.downloaders), 1)
        self.assertEqual(len([c for c in api.calls if c[0] == "post" and c[1] == "/api/downloaders"]), 0)

    def test_igdb_is_projected_only_from_mudos_managed_configuration(self):
        api = Api()
        reconciler = self.configured(api)
        igdb = reconciler.config.providers["metadata.igdb"]
        igdb.values.update({"enabled": True, "client_id": "managed-client"})
        igdb._secrets["client_secret"] = "test-only-managed-secret"
        result = reconciler.reconcile()
        self.assertEqual(result.metadata, "configured")
        projection = next(call[2] for call in api.calls
                          if call[0] == "post" and call[1] == "/api/settings/igdb")
        self.assertTrue(projection["clientId"] == "managed-client")
        self.assertTrue(bool(projection["clientSecret"]))

    def test_unmarked_equivalent_is_not_overwritten(self):
        api = Api([{"id": "manual", "type": "transmission", "url": "http://127.0.0.1", "port": 9091}])
        result = self.configured(api).reconcile()
        self.assertEqual(result.transmission, "deferred-until-torrent-gateway")
        self.assertEqual(len(api.downloaders), 2)

    def test_runtime_jwt_cache_is_reused(self):
        payload = base64.urlsafe_b64encode(json.dumps({"exp": int(time.time()) + 3600}).encode()).decode().rstrip("=")
        token = f"x.{payload}.y"
        calls = []

        class Response:
            def __enter__(self): return self
            def __exit__(self, *_): return None
            def read(self): return json.dumps({"token": token}).encode()

        def opener(request, timeout=15):
            calls.append(request.full_url)
            return Response()

        with tempfile.TemporaryDirectory() as directory:
            cache = Path(directory) / "session.json"
            QuestarrApi(opener=opener, cache_path=cache).ensure_authenticated("u", "p")
            second = QuestarrApi(opener=lambda *_: (_ for _ in ()).throw(AssertionError("login repeated")),
                                 cache_path=cache)
            second.ensure_authenticated("u", "p")
        self.assertEqual(calls, ["http://127.0.0.1:5002/api/auth/login"])

    def test_429_is_deferred_without_destructive_calls(self):
        def opener(request, timeout=15):
            raise HTTPError(request.full_url, 429, "rate limited", {"Retry-After": "60"}, BytesIO())

        with tempfile.TemporaryDirectory() as directory:
            api = QuestarrApi(opener=opener, cache_path=Path(directory) / "session.json")
            with self.assertRaises(QuestarrRateLimited):
                api.ensure_authenticated("u", "p")
            self.assertTrue((Path(directory) / "session.deferred").is_file())

    def test_401_invalidates_and_reauthenticates_once(self):
        payload = base64.urlsafe_b64encode(json.dumps({"exp": int(time.time()) + 3600}).encode()).decode().rstrip("=")
        tokens = [f"x.{payload}.first", f"x.{payload}.second"]
        calls = []

        class Response:
            def __init__(self, body): self.body = body
            def __enter__(self): return self
            def __exit__(self, *_): return None
            def read(self): return self.body

        def opener(request, timeout=15):
            calls.append(request.full_url)
            if request.full_url.endswith("/login"):
                return Response(json.dumps({"token": tokens.pop(0)}).encode())
            if len(calls) == 2:
                raise HTTPError(request.full_url, 401, "expired", {}, BytesIO())
            return Response(b"[]")

        with tempfile.TemporaryDirectory() as directory:
            api = QuestarrApi(opener=opener, cache_path=Path(directory) / "session.json")
            api.ensure_authenticated("u", "p")
            self.assertEqual(api.get("/api/indexers"), [])
        self.assertEqual(calls.count("http://127.0.0.1:5002/api/auth/login"), 2)

    def test_concurrent_reconcile_is_coalesced(self):
        with tempfile.TemporaryDirectory() as directory:
            lock = Path(directory) / "reconcile.lock"
            first = self.configured(lock_path=lock)
            import fcntl
            with lock.open("a+") as held:
                fcntl.flock(held.fileno(), fcntl.LOCK_EX)
                result = first.reconcile()
            self.assertEqual(result.status, "deferred")
            self.assertEqual(result.transmission, "coalesced")


if __name__ == "__main__":
    unittest.main()
