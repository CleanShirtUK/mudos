import subprocess
import unittest
from unittest.mock import patch

from lulu import recovery_service as recovery


class RecoveryServiceTests(unittest.TestCase):
    def test_action_map_is_fixed_and_rejects_client_supplied_units(self):
        with patch.object(recovery, "_bus_api", return_value=(False, "unavailable")), \
             patch.object(recovery, "_request_systemd") as request:
            result = recovery.perform_action("restart_mudos", True)
        request.assert_called_once_with("restart", "lulu-session@2.service")
        self.assertEqual(result["status"], "requested")
        with patch.object(recovery, "_request_systemd") as request:
            with self.assertRaisesRegex(ValueError, "Unknown recovery action"):
                recovery.perform_action("systemctl restart anything", True)
        request.assert_not_called()

    def test_mutations_require_explicit_confirmation(self):
        with patch.object(recovery, "_request_systemd") as request:
            with self.assertRaisesRegex(ValueError, "explicit confirmation"):
                recovery.perform_action("reboot", False)
        request.assert_not_called()

    def test_action_api_authenticates_local_mutation_clients(self):
        with patch.dict("os.environ", {"LULU_RECOVERY_TOKEN": "a" * 64}):
            self.assertFalse(recovery._authorized_action_request(None))
            self.assertFalse(recovery._authorized_action_request("Bearer " + "b" * 64))
            self.assertTrue(recovery._authorized_action_request("Bearer " + "a" * 64))
        with patch.dict("os.environ", {"LULU_RECOVERY_TOKEN": ""}):
            self.assertFalse(recovery._authorized_action_request("Bearer " + "a" * 64))

    def test_each_action_advertises_impact_and_data_risk(self):
        actions = recovery.available_actions({
            "mudos_session": {"state": "failed"},
            "consoled": {"state": "failed"},
            "acquisitiond": {"state": "healthy", "evidence": {"active_download_count": 2}},
            "admin": {"state": "healthy"},
        })
        by_id = {item["action_id"]: item for item in actions}
        self.assertIn("restart_mudos", by_id)
        self.assertIn("restart_consoled", by_id)
        self.assertNotIn("restart_acquisitiond", by_id)
        self.assertNotIn("restart_admin", by_id)
        self.assertIn("active acquisition job(s)", " ".join(by_id["reboot"]["impact"]))
        self.assertTrue(by_id["reboot"]["requires_confirmation"])
        self.assertIn("persisted user files", by_id["reboot"]["data_risk"])

    def test_process_service_active_and_api_failure_remains_distinguishable(self):
        component = recovery._component(
            "consoled", "degraded", "Process is running; API is not responding.",
            {"available": True, "unit": "lulu-consoled.service",
             "active_state": "active", "api_available": False},
            last_error="The service API did not respond",
        )
        self.assertEqual(component["state"], "degraded")
        self.assertEqual(component["evidence"]["active_state"], "active")
        self.assertFalse(component["evidence"]["api_available"])
        self.assertEqual(component["freshness"], "current")

    def test_missing_unit_evidence_is_unknown_not_healthy(self):
        with patch.object(recovery, "_systemd", return_value=None):
            component = recovery._unit_component("questarr")
        self.assertEqual(component["state"], "unknown")
        self.assertEqual(component["freshness"], "unavailable")

    def test_user_bus_string_decoder_handles_structured_owner_snapshot(self):
        raw = 's "{\\"activeDownloadCount\\":2,\\"jobs\\":[]}"'
        self.assertEqual(recovery._decode_bus_string(raw), '{"activeDownloadCount":2,"jobs":[]}')


if __name__ == "__main__":
    unittest.main()
