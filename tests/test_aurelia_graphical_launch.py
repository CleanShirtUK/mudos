from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from lulu.graphical_launch_context import GRAPHICAL_ENV
from lulu.plugins.steam.aurelia import AureliaClient


ROOT = Path(__file__).resolve().parents[1]
WRAPPER = ROOT / "scripts" / "aurelia-graphical-launch.py"


class AureliaScriptAdapterTests(unittest.IsolatedAsyncioTestCase):
    async def test_play_uses_explicit_mudos_wrapper_script(self):
        client = AureliaClient(executable="/usr/bin/aurelia", config_dir=Path(tempfile.mkdtemp()), run=lambda *_a, **_k: None)
        captured = {}

        async def create(*args, **kwargs):
            captured["args"] = args
            captured["kwargs"] = kwargs
            return object()

        with patch("lulu.plugins.steam.aurelia.asyncio.create_subprocess_exec", create), \
                patch.object(client, "_ensure_config_dir"):
            await client.spawn_play("104200")
        command = captured["args"]
        self.assertEqual(command[:6], ("/usr/bin/aurelia", "--json", "play", "104200", "--no-update", "--script"))
        self.assertEqual(Path(command[6]), WRAPPER)
        self.assertNotIn("--no-script", command)
        self.assertTrue(captured["kwargs"]["start_new_session"])


class WrapperBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.runtime = self.root / "runtime"
        self.runtime.mkdir()
        self.x11_dir = self.root / "x11"
        self.x11_dir.mkdir()
        self.wayland = self.runtime / "wayland-test"
        self.x11 = self.x11_dir / "X9"
        self.sockets = []
        for path in (self.wayland, self.x11):
            server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            server.bind(str(path))
            server.listen(4)
            self.sockets.append(server)
        self.context_path = self.root / "aurelia-graphical-launch-context.json"
        self.context = {
            "DISPLAY": f"unix:{self.x11}", "WAYLAND_DISPLAY": "wayland-test",
            "XDG_RUNTIME_DIR": str(self.runtime),
        }

    def tearDown(self):
        for server in self.sockets:
            server.close()
        self.temp.cleanup()

    def write_context(self, *, ready=True, session="test-session", updated_at=None):
        self.context_path.write_text(json.dumps({
            "environment": self.context,
            "session_id": session,
            "shell_pid": os.getpid(),
            "shell_start_time": self._own_start_time(),
            "updated_at": time.time() if updated_at is None else updated_at,
            "presentation_ready": ready,
        }))

    @staticmethod
    def _own_start_time():
        stat = Path(f"/proc/{os.getpid()}/stat").read_text()
        return stat[stat.rfind(")") + 2:].split()[19]

    def run_wrapper(self, *command, output=None):
        environment = {
            **os.environ,
            "PYTHONPATH": str(ROOT / "src"),
            "LULU_RUNTIME_ROOT": str(self.root),
            # Existing Aurelia launch variables must survive; these context values
            # intentionally disagree and must be replaced from Sessiond's snapshot.
            "DISPLAY": ":stale", "WAYLAND_DISPLAY": "stale", "XDG_RUNTIME_DIR": "/stale",
            "WINEPREFIX": "/aurelia/prefix", "LULU_TEST_CONTEXT_PATH": str(self.context_path),
        }
        return subprocess.run([sys.executable, str(WRAPPER), *command], env=environment,
                              text=True, capture_output=True)

    def test_exec_boundary_gets_approved_context_and_preserves_aurelia_environment(self):
        self.write_context()
        # Script itself receives the exact argv Aurelia documents: resolved program,
        # followed by each resolved argument without shell reconstruction.
        args = ["argument with spaces", "$(touch /tmp/should-not-exist)"]
        code = (
            "import json,os,sys; "
            "print(json.dumps({k:os.environ.get(k) for k in " + repr(GRAPHICAL_ENV) + "} | "
            "{'WINEPREFIX':os.environ.get('WINEPREFIX'),'argv':sys.argv[1:]}))"
        )
        result = self.run_wrapper(sys.executable, "-c", code, *args)
        self.assertEqual(result.returncode, 0, result.stderr)
        final = json.loads(result.stdout)
        self.assertEqual({key: final[key] for key in GRAPHICAL_ENV}, self.context)
        self.assertEqual(final["WINEPREFIX"], "/aurelia/prefix")
        self.assertEqual(final["argv"], args)

    def test_child_exit_code_propagates_through_exec(self):
        self.write_context()
        result = self.run_wrapper(sys.executable, "-c", "raise SystemExit(37)")
        self.assertEqual(result.returncode, 37)

    def test_unavailable_or_stale_context_fails_before_child_execution(self):
        marker = self.root / "ran"
        command = [sys.executable, "-c", f"open({str(marker)!r},'w').write('yes')"]
        cases = ((False, time.time(), "old", os.getpid()),
                 (True, time.time() - 5, "expired", os.getpid()),
                 (True, time.time(), "obsolete-shell", 2_000_000_000))
        for ready, updated, session, shell_pid in cases:
            with self.subTest(ready=ready, session=session):
                self.write_context(ready=ready, updated_at=updated, session=session)
                record = json.loads(self.context_path.read_text())
                record["shell_pid"] = shell_pid
                self.context_path.write_text(json.dumps(record))
                result = self.run_wrapper(*command)
                self.assertEqual(result.returncode, 125)
                self.assertIn("Mudos Aurelia launch: refusing", result.stderr)
                self.assertFalse(marker.exists())

    def test_missing_socket_or_context_fails_closed(self):
        self.write_context()
        self.wayland.unlink()
        result = self.run_wrapper(sys.executable, "-c", "raise SystemExit(0)")
        self.assertEqual(result.returncode, 125)
        self.assertIn("compositor socket", result.stderr)
        self.context_path.unlink()
        result = self.run_wrapper(sys.executable, "-c", "raise SystemExit(0)")
        self.assertEqual(result.returncode, 125)
        self.assertIn("no current graphical launch context", result.stderr)

    def test_shell_metacharacters_are_plain_argv_not_interpreted(self):
        self.write_context()
        marker = self.root / "shell-injection"
        argument = f"$(touch {marker})"
        result = self.run_wrapper(sys.executable, "-c", "import sys; print(sys.argv[1])", argument)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), argument)
        self.assertFalse(marker.exists())


if __name__ == "__main__":
    unittest.main()
