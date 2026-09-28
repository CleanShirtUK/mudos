import json
import logging
import socket
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from lulu import questarr_pam_auth as pam_auth
from lulu import managed_account


class QuestarrPamAuthTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.socket_path = Path(self.temporary.name) / "pam.sock"
        self.server = pam_auth._Server(str(self.socket_path), pam_auth._Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.attempts = pam_auth._ATTEMPTS
        self.attempts.clear()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.attempts.clear()
        self.temporary.cleanup()

    def request(self, username="josh", password="test-only-password"):
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.settimeout(2)
            client.connect(str(self.socket_path))
            client.sendall(json.dumps({"username": username, "password": password}).encode() + b"\n")
            return json.loads(client.makefile("rb").readline())

    def test_fixed_account_uses_login_pam_and_logs_no_credential(self):
        with patch.object(pam_auth, "PAM_ACCOUNT", "josh"), \
                patch.object(pam_auth, "PROXY_ACCOUNT", "josh"), \
                patch.object(pam_auth, "authenticate_managed_account_diagnostic",
                             return_value=(True, "accepted", 0)) as authenticate, \
                self.assertLogs(pam_auth.LOGGER, level=logging.INFO) as captured:
            result = self.request()
        self.assertEqual(result, {"authenticated": True, "category": "accepted"})
        authenticate.assert_called_once_with("test-only-password", "josh")
        self.assertNotIn("test-only-password", "\n".join(captured.output))

    def test_unknown_account_is_rejected_before_pam(self):
        with patch.object(pam_auth, "PAM_ACCOUNT", "josh"), \
                patch.object(pam_auth, "PROXY_ACCOUNT", "josh"), \
                patch.object(pam_auth, "authenticate_managed_account_diagnostic") as authenticate:
            result = self.request(username="not-an-appliance-user")
        self.assertEqual(result["category"], "identity-rejected")
        authenticate.assert_not_called()

    def test_failed_authentication_category_is_returned_without_password(self):
        with patch.object(pam_auth, "PAM_ACCOUNT", "josh"), \
                patch.object(pam_auth, "PROXY_ACCOUNT", "josh"), \
                patch.object(pam_auth, "authenticate_managed_account_diagnostic",
                             return_value=(False, "pam-policy-or-service-error", 6)):
            result = self.request()
        self.assertEqual(result, {
            "authenticated": False, "category": "pam-policy-or-service-error",
        })

    def test_pam_failure_categories_distinguish_unknown_user_bad_password_and_policy(self):
        cases = (
            ("authenticate", 10, "unknown-user"),
            ("authenticate", 7, "bad-password-or-auth-rejected"),
            ("account", 6, "pam-policy-or-service-error"),
        )
        for phase, status, expected in cases:
            def run(_account, _service, _responder, _operation, diagnostic):
                diagnostic.update(phase=phase, status=status)
                return False
            with self.subTest(phase=phase, status=status), \
                    patch.object(managed_account, "_run_pam", side_effect=run):
                self.assertEqual(
                    managed_account.authenticate_managed_account_diagnostic("not-logged", "josh"),
                    (False, expected, status),
                )


if __name__ == "__main__":
    unittest.main()
