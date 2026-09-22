import json
import tempfile
import unittest
from pathlib import Path

from lulu.transmission_admin import (TransmissionMutationError, apply_rpc_credentials,
                                     replace_rpc_credentials)


class TransmissionAdminTests(unittest.TestCase):
    def test_materializes_credentials_without_dropping_torrent_state(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            path.write_text(json.dumps({
                "rpc-username": "old",
                "rpc-password": "{hashed}",
                "rpc-port": 9091,
                "download-dir": "/preserve/complete",
                "torrent-count-sentinel": 5,
            }))
            apply_rpc_credentials("new-user", "replacement", path)
            values = json.loads(path.read_text())
            self.assertEqual(values["rpc-username"], "new-user")
            self.assertEqual(values["rpc-password"], "replacement")
            self.assertEqual(values["rpc-port"], 9091)
            self.assertEqual(values["download-dir"], "/preserve/complete")
            self.assertEqual(values["torrent-count-sentinel"], 5)

    def test_rejects_empty_or_multiline_credentials(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            path.write_text("{}")
            for username, password in (("", "x"), ("u", ""), ("u\n", "p"), ("u", "p\n")):
                with self.assertRaises(ValueError):
                    apply_rpc_credentials(username, password, path)

    def test_stop_failure_does_not_commit_or_touch_runtime(self) -> None:
        events = []
        with self.assertRaises(TransmissionMutationError):
            replace_rpc_credentials("new", "new-pass", "old", "old-pass",
                stop=lambda: (_ for _ in ()).throw(RuntimeError("stop")),
                start=lambda: events.append("start"), materialize=lambda *_: events.append("materialize"),
                health=lambda *_: events.append("health"), commit=lambda: events.append("commit"),
                rollback_commit=lambda: events.append("rollback-commit"),
                refresh=lambda: events.append("refresh"), reconcile=lambda: events.append("reconcile"))
        self.assertEqual(events, [])

    def test_materialize_failure_rolls_back_runtime_and_secret_commit(self) -> None:
        events = []
        def materialize(username, password):
            events.append(f"materialize:{username}")
            if username == "new":
                raise RuntimeError("materialize")
        with self.assertRaises(TransmissionMutationError):
            replace_rpc_credentials("new", "new-pass", "old", "old-pass",
                stop=lambda: events.append("stop"), start=lambda: events.append("start"),
                materialize=materialize, health=lambda *_: events.append("health"),
                commit=lambda: events.append("commit"), rollback_commit=lambda: events.append("rollback"),
                refresh=lambda: events.append("refresh"), reconcile=lambda: events.append("reconcile"))
        self.assertEqual(events, ["stop", "materialize:new", "stop", "materialize:old", "start", "rollback"])

    def test_success_commits_then_refreshes_dependents(self) -> None:
        events = []
        replace_rpc_credentials("new", "new-pass", "old", "old-pass",
            stop=lambda: events.append("stop"), start=lambda: events.append("start"),
            materialize=lambda *_: events.append("materialize"),
            health=lambda *_: events.append("health"), commit=lambda: events.append("commit"),
            rollback_commit=lambda: events.append("rollback"), refresh=lambda: events.append("refresh"),
            reconcile=lambda: events.append("reconcile"))
        self.assertEqual(events, ["stop", "materialize", "start", "health", "commit", "refresh", "reconcile"])


if __name__ == "__main__":
    unittest.main()
