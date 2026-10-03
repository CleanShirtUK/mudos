from __future__ import annotations

import asyncio
import json
from pathlib import Path
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from lulu.console_sessiond import SessionStateModel
from lulu.resident_steam_runtime import (
    READY_STATUS,
    ResidentSteamRuntimeStatus,
    parse_systemd_properties,
    read_resident_steam_runtime_status,
)
from lulu.sessiond import ConsoleSessionInterface


ROOT = Path(__file__).resolve().parents[1]


class ResidentSteamRuntimeStatusTests(unittest.TestCase):
    def test_systemd_ready_means_authenticated_at_notify_not_continuously(self):
        status = parse_systemd_properties(
            "LoadState=loaded\nActiveState=active\nSubState=running\n"
            f"StatusText={READY_STATUS}\nResult=success\nNRestarts=2\n"
        )
        self.assertEqual(status.state, "ready")
        self.assertEqual(status.authentication, "authenticated-at-readiness")
        self.assertEqual(status.restart_count, 2)

    def test_automatic_restart_is_reported_as_recovering(self):
        status = parse_systemd_properties(
            "LoadState=loaded\nActiveState=activating\nSubState=auto-restart\n"
            "Result=exit-code\nNRestarts=3\n"
        )
        self.assertEqual(status.state, "recovering")
        self.assertEqual(status.authentication, "unknown")

    def test_authentication_exit_78_is_distinguished_from_other_failures(self):
        auth = parse_systemd_properties(
            "LoadState=loaded\nActiveState=failed\nSubState=failed\n"
            "Result=exit-code\nExecMainStatus=78\n"
        )
        crash = parse_systemd_properties(
            "LoadState=loaded\nActiveState=failed\nSubState=failed\n"
            "Result=exit-code\nExecMainStatus=1\n"
        )
        self.assertEqual(auth.state, "failed")
        self.assertEqual(auth.authentication, "authentication-required")
        self.assertEqual(crash.authentication, "unknown")

    def test_active_without_the_readiness_notification_is_not_claimed_healthy(self):
        status = parse_systemd_properties(
            "LoadState=loaded\nActiveState=active\nSubState=running\nStatusText=starting\n"
        )
        self.assertEqual(status.state, "degraded")
        self.assertEqual(status.authentication, "unknown")

    def test_missing_unit_or_unavailable_systemd_is_unknown(self):
        self.assertEqual(parse_systemd_properties("LoadState=not-found\n").state, "unknown")
        with patch("lulu.resident_steam_runtime.subprocess.run", side_effect=OSError("offline")):
            status = read_resident_steam_runtime_status()
        self.assertEqual(status, ResidentSteamRuntimeStatus(error="OSError"))

    def test_observer_uses_read_only_systemctl_show(self):
        completed = Mock(stdout=(
            "LoadState=loaded\nActiveState=inactive\nSubState=dead\nNRestarts=0\n"
        ))
        with patch("lulu.resident_steam_runtime.subprocess.run", return_value=completed) as run:
            status = read_resident_steam_runtime_status()
        self.assertEqual(status.state, "inactive")
        command = run.call_args.args[0]
        self.assertEqual(command[:3], ["/usr/bin/systemctl", "show", "lulu-steam-runtime.service"])
        self.assertNotIn("start", command)
        self.assertNotIn("restart", command)
        self.assertEqual(run.call_args.kwargs["timeout"], 2)

    def test_service_declares_nonfatal_ordered_start_and_auth_restart_exclusion(self):
        service = (ROOT / "packaging/lulu-steam-runtime.service").read_text()
        session = (ROOT / "packaging/lulu-session@.service").read_text()
        self.assertIn("Type=notify", service)
        self.assertIn("Restart=always", service)
        self.assertIn("RestartPreventExitStatus=78", service)
        self.assertIn("Wants=", session)
        self.assertNotIn("Requires=lulu-steam-runtime.service", session)


class ResidentSteamRuntimeSessionTests(unittest.IsolatedAsyncioTestCase):
    async def test_failed_resident_runtime_is_reported_without_changing_game_lifecycle(self):
        interface = ConsoleSessionInterface.__new__(ConsoleSessionInterface)
        interface.model = SessionStateModel()
        token = interface.model.request_launch("steam-aurelia:945360")
        interface.model.launch_starting(token)
        interface.model.primary_started(token)
        interface._resident_steam_runtime = ResidentSteamRuntimeStatus()
        interface._resident_steam_runtime_task = None
        interface.StateChanged = Mock()
        interface._state_json = Mock(return_value="{}")

        failed = ResidentSteamRuntimeStatus(
            state="failed", active_state="failed", sub_state="failed",
            result="exit-code", authentication="authentication-required",
        )
        task = asyncio.create_task(
            interface._monitor_resident_steam_runtime()
        )
        try:
            with patch("lulu.sessiond.read_resident_steam_runtime_status", return_value=failed):
                # Let the observer consume one sample; it then sleeps on its normal cadence.
                for _ in range(20):
                    if interface._resident_steam_runtime == failed:
                        break
                    await asyncio.sleep(0.01)
            self.assertEqual(interface._resident_steam_runtime, failed)
            self.assertEqual(interface.model.state.lifecycle.value, "game")
            interface.StateChanged.assert_called_once_with("{}")
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    def test_get_state_exposes_runtime_readback_separately_from_lifecycle(self):
        interface = ConsoleSessionInterface.__new__(ConsoleSessionInterface)
        interface.model = SessionStateModel()
        token = interface.model.request_launch("steam-aurelia:945360")
        interface.model.launch_starting(token)
        interface.model.primary_started(token)
        interface._resident_steam_runtime = ResidentSteamRuntimeStatus(
            state="recovering", active_state="activating", sub_state="auto-restart",
        )
        interface._local_identity = None
        interface.controller_registry = SimpleNamespace(
            navigation_controller_id=None, navigation_mode="all", controllers={}
        )
        interface.supervisor = SimpleNamespace(
            launch_cancellable=False, state_details=lambda: {},
        )
        state = json.loads(interface._state_json())
        self.assertEqual(state["lifecycle"], "game")
        self.assertEqual(state["resident_steam_runtime"]["state"], "recovering")
        self.assertEqual(state["resident_steam_runtime"]["sub_state"], "auto-restart")


if __name__ == "__main__":
    unittest.main()
