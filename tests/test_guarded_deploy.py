import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch


MODULE = Path(__file__).parents[1] / "scripts" / "guarded-deploy.py"
SPEC = importlib.util.spec_from_file_location("guarded_deploy", MODULE)
guard = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(guard)


def session(**changes):
    value = {"lifecycle": "shell", "presentation": "shell", "presentation_ready": True,
             "active_identity": None, "launch_token": None, "delegated_surface": None,
             "requested_surface": None, "session_kind": "shell", "primary_id": None,
             "provider_id": None, "session_title": "",
             "resident_steam_runtime": {"state": "ready", "authentication": "authenticated"},
             "controller": {"controllers": {"fixture": {"connected": True}}}}
    value.update(changes)
    return json.dumps(value)


def acquisition(jobs=None, **changes):
    value = {"jobs": jobs or [], "activeDownloadCount": len(jobs or [])}
    value.update(changes)
    return json.dumps(value)


class IdleValidationTests(unittest.TestCase):
    def test_normal_idle_shell(self):
        guard.validate_idle_state(session(), acquisition())

    def test_rejects_malformed_partial_unknown_and_active_session_states(self):
        cases = [
            ("{", acquisition()),
            (json.dumps({"lifecycle": "shell"}), acquisition()),
            (session(lifecycle="mystery"), acquisition()),
            (session(active_identity={"id": "game"}), acquisition()),
            (session(launch_token="pending"), acquisition()),
            (session(delegated_surface="steam"), acquisition()),
            (session(requested_surface="game"), acquisition()),
            (session(presentation_ready=False), acquisition()),
            (session(controller={"controllers": {"fixture": {"connected": False}}}), acquisition()),
        ]
        for session_json, acquisition_json in cases:
            with self.subTest(session=session_json):
                with self.assertRaises(guard.GuardError):
                    guard.validate_idle_state(session_json, acquisition_json)

    def test_rejects_malformed_acquisition_and_active_job_types(self):
        active_operations = ("acquire", "install", "update", "remove")
        for operation in active_operations:
            with self.subTest(operation=operation):
                with self.assertRaisesRegex(guard.GuardError, "active acquisition"):
                    guard.validate_idle_state(session(), acquisition([
                        {"state": "transferring", "operation": operation}]))
        for invalid in ("{", json.dumps({"jobs": []}),
                        acquisition([{"operation": "update"}]),
                        acquisition([{"operation": "unknown", "state": "failed"}]),
                        acquisition([], activeDownloadCount="unknown")):
            with self.subTest(acquisition=invalid):
                with self.assertRaises(guard.GuardError):
                    guard.validate_idle_state(session(), invalid)

    def test_user_bus_transport_failure_and_unhealthy_unit_fail_closed(self):
        with patch.object(guard, "_run", side_effect=subprocess.CalledProcessError(1, ["busctl"])):
            with self.assertRaisesRegex(guard.GuardError, "user-bus query failed"):
                guard._as_user_bus_call(*guard.SESSION_BUS)
        def inactive(argv, **_kwargs):
            return subprocess.CompletedProcess(argv, 0, "inactive\n", "")
        with self.assertRaisesRegex(guard.GuardError, "not active"):
            guard._require_healthy_units(inactive)


class DeploymentOrchestrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.releases = root / "releases"
        self.releases.mkdir()
        self.previous = self.releases / "previous"
        self.candidate = self.releases / "candidate"
        self.previous.mkdir()
        self.candidate.mkdir()
        self.activation = root / "current"
        self.activation.symlink_to(self.previous)
        self.old_root, self.old_activation = guard.RELEASE_ROOT, guard.ACTIVATION
        guard.RELEASE_ROOT, guard.ACTIVATION = self.releases, self.activation
        self.old_read = guard.read_and_validate
        self.old_health = guard._require_healthy_units
        self.old_bus_call = guard._as_user_bus_call
        guard.read_and_validate = Mock()
        guard._require_healthy_units = Mock()
        guard._as_user_bus_call = Mock(return_value="[]")
        self.commands = []

    def tearDown(self):
        guard.RELEASE_ROOT, guard.ACTIVATION = self.old_root, self.old_activation
        guard.read_and_validate = self.old_read
        guard._require_healthy_units = self.old_health
        guard._as_user_bus_call = self.old_bus_call
        self.temp.cleanup()

    def runner(self, argv, **_kwargs):
        self.commands.append(argv)
        if argv[1:3] == [str(guard.RELEASE_TOOL), "activate"]:
            target = Path(argv[argv.index("--release-dir") + 1])
            self.activation.unlink()
            self.activation.symlink_to(target)
        return subprocess.CompletedProcess(argv, 0, "", "")

    def test_rejected_preflight_does_not_verify_activate_or_restart(self):
        guard.read_and_validate.side_effect = guard.GuardError("Acquisitiond unavailable")
        with self.assertRaisesRegex(guard.GuardError, "Acquisitiond unavailable"):
            guard.deploy(self.candidate, run=self.runner)
        self.assertEqual(self.activation.resolve(), self.previous.resolve())
        self.assertFalse(any("activate" in command for command in self.commands))
        self.assertFalse(any(command[:2] == ["systemctl", "restart"] for command in self.commands))

    def test_state_change_on_immediate_recheck_prevents_activation(self):
        guard.read_and_validate.side_effect = [None, guard.GuardError("game started")]
        with self.assertRaisesRegex(guard.GuardError, "game started"):
            guard.deploy(self.candidate, run=self.runner)
        self.assertEqual(self.activation.resolve(), self.previous.resolve())
        self.assertFalse(any("activate" in command for command in self.commands))

    def test_successful_deploy_verifies_then_rechecks_and_restarts(self):
        previous = guard.deploy(self.candidate, run=self.runner)
        self.assertEqual(previous, self.previous)
        self.assertEqual(self.activation.resolve(), self.candidate.resolve())
        self.assertEqual(guard.read_and_validate.call_count, 3)
        self.assertTrue(any("verify" in command for command in self.commands))
        restarted = [command[2] for command in self.commands if command[:2] == ["systemctl", "restart"]]
        self.assertEqual(restarted, list(guard.RESTART_ORDER))

    def test_activation_failure_rolls_back_to_previous(self):
        calls = 0
        def fails_first_activation(argv, **_kwargs):
            nonlocal calls
            self.commands.append(argv)
            if argv[1:3] == [str(guard.RELEASE_TOOL), "activate"]:
                calls += 1
                if calls == 1:
                    raise subprocess.CalledProcessError(1, argv, stderr="activation refused")
                target = Path(argv[argv.index("--release-dir") + 1])
                self.activation.unlink()
                self.activation.symlink_to(target)
            return subprocess.CompletedProcess(argv, 0, "", "")
        with self.assertRaisesRegex(guard.GuardError, "rolled back"):
            guard.deploy(self.candidate, run=fails_first_activation)
        self.assertEqual(self.activation.resolve(), self.previous.resolve())

    def test_release_verification_failure_never_activates_or_restarts(self):
        def failed_verify(argv, **_kwargs):
            self.commands.append(argv)
            if "verify" in argv:
                raise subprocess.CalledProcessError(1, argv, stderr="checksum mismatch")
            return self.runner(argv)
        with self.assertRaises(subprocess.CalledProcessError):
            guard.deploy(self.candidate, run=failed_verify)
        self.assertEqual(self.activation.resolve(), self.previous.resolve())
        self.assertFalse(any("activate" in command for command in self.commands))
        self.assertFalse(any(command[:2] == ["systemctl", "restart"] for command in self.commands))

    def test_restart_failure_rolls_back_selector(self):
        failed = False
        def fails_restart(argv, **_kwargs):
            nonlocal failed
            if argv[:3] == ["systemctl", "restart", "lulu-session@2.service"]:
                if not failed:
                    failed = True
                    raise subprocess.CalledProcessError(1, argv, stderr="restart failed")
            return self.runner(argv)
        with self.assertRaisesRegex(guard.GuardError, "rolled back"):
            guard.deploy(self.candidate, run=fails_restart)
        self.assertEqual(self.activation.resolve(), self.previous.resolve())

    def test_post_activation_readiness_failure_rolls_back(self):
        guard.read_and_validate.side_effect = [None, None, guard.GuardError("Acquisitiond unavailable")]
        with self.assertRaisesRegex(guard.GuardError, "rolled back"):
            guard.deploy(self.candidate, run=self.runner, sleep=lambda _delay: None,
                         readiness_timeout=0.001)
        self.assertEqual(self.activation.resolve(), self.previous.resolve())


if __name__ == "__main__":
    unittest.main()
