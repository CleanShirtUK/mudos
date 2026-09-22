import base64
import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from lulu.questarr_metadata import QuestarrMetadataClient


class QuestarrMetadataTests(unittest.TestCase):
    def test_metadata_clients_reuse_backend_session(self) -> None:
        payload = base64.urlsafe_b64encode(
            json.dumps({"exp": int(time.time()) + 3600}).encode()
        ).decode().rstrip("=")
        token = f"x.{payload}.y"
        login_calls = 0

        class Response:
            def __init__(self, value):
                self.value = json.dumps(value).encode()

            def __enter__(self):
                return self

            def __exit__(self, *_):
                return None

            def read(self):
                return self.value

        def opener(request, timeout=15):
            nonlocal login_calls
            if request.full_url.endswith("/api/auth/login"):
                login_calls += 1
                return Response({"token": token})
            if request.full_url.endswith("/api/games"):
                return Response([])
            raise AssertionError(request.full_url)

        with tempfile.TemporaryDirectory() as directory, patch(
            "lulu.questarr_metadata.SecretStore"
        ) as store:
            store.return_value.get.side_effect = lambda namespace, name: {
                "username": "u", "password": "p"
            }.get(name)
            cache = Path(directory) / "session.json"
            first = QuestarrMetadataClient(transport=opener)
            first.api.cache_path = cache
            second = QuestarrMetadataClient(transport=opener)
            second.api.cache_path = cache
            # Both clients represent separate downloader-plugin instances.
            self.assertEqual(first.refresh(), ())
            self.assertEqual(second.refresh(), ())

        self.assertEqual(login_calls, 1)
