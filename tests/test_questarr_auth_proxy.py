import json
import unittest
from unittest.mock import patch

from lulu import questarr_auth_proxy as proxy


class MemorySecrets:
    values = {}

    def __init__(self):
        self.values = {}

    def get(self, namespace, name):
        return self.values.get((namespace, name))

    def put(self, namespace, name, value):
        self.values[(namespace, name)] = value


class QuestarrAuthProxyTests(unittest.TestCase):
    def test_first_run_identity_is_generated_and_saved_only_in_secretstore(self):
        secrets = MemorySecrets()
        calls = []

        def request(path, value=None):
            calls.append((path, value))
            if path == "/api/auth/status":
                return 200, b'{"hasUsers":false}'
            if path == "/api/auth/setup":
                return 201, b'{"ok":true}'
            raise AssertionError(path)

        with patch.object(proxy, "SecretStore", return_value=secrets), \
                patch.object(proxy, "_json_request", side_effect=request):
            self.assertTrue(proxy.provision_internal_identity())
        self.assertEqual(secrets.get("web/questarr", "username"), proxy.MANAGED_ADMIN_ACCOUNT)
        generated = secrets.get("web/questarr", "password")
        self.assertTrue(generated and len(generated) >= 40)
        self.assertTrue(calls[1][1]["password"] == generated)
        self.assertFalse(generated in repr(calls[0]))

    def test_browser_login_validates_pam_then_uses_private_questarr_credential(self):
        secrets = MemorySecrets()
        secrets.put("web/questarr", "username", "lulu")
        secrets.put("web/questarr", "password", "internal-random-secret")
        with patch.object(proxy, "SecretStore", return_value=secrets), \
                patch.object(proxy, "authenticate_managed_account", return_value=True) as pam, \
                patch.object(proxy, "_json_request", return_value=(200, b'{"token":"opaque"}')) as upstream:
            status, response = proxy._login_system_user("lulu", "pam-password-not-saved")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(response)["token"], "opaque")
        pam.assert_called_once_with("pam-password-not-saved", account="lulu")
        self.assertTrue(upstream.call_args.args[1]["username"] == "lulu")
        self.assertTrue(upstream.call_args.args[1]["password"] == "internal-random-secret")
        self.assertFalse(any(value == "pam-password-not-saved"
                             for value in upstream.call_args.args[1].values()))
        self.assertFalse(any(value == "pam-password-not-saved" for value in secrets.values.values()))

    def test_non_appliance_user_never_reaches_pam_or_questarr(self):
        with patch.object(proxy, "authenticate_managed_account") as pam, \
                patch.object(proxy, "_json_request") as upstream:
            status, _ = proxy._login_system_user("other-user", "password")
        self.assertEqual(status, 401)
        pam.assert_not_called()
        upstream.assert_not_called()

    def test_login_rate_limit_is_enforced_at_the_pam_boundary(self):
        address = "test-rate-limit-address"
        for index in range(20):
            self.assertTrue(proxy._allow_login_attempt(address, now=1000 + index))
        self.assertFalse(proxy._allow_login_attempt(address, now=1020))
        self.assertTrue(proxy._allow_login_attempt(address, now=1900))

    def test_questarr_unavailable_does_not_create_a_fake_internal_identity(self):
        secrets = MemorySecrets()
        with patch.object(proxy, "SecretStore", return_value=secrets), \
                patch.object(proxy, "_json_request", return_value=(503, b"unavailable")):
            self.assertFalse(proxy.provision_internal_identity())
        self.assertFalse(secrets.values)

    def test_proxy_session_cookie_is_opaque_and_expires(self):
        session = proxy._create_pam_session()
        cookie = "mudos_questarr_session=" + session
        self.assertTrue(proxy._is_active_pam_session(cookie))
        self.assertFalse(proxy._is_active_pam_session("mudos_questarr_session=forged"))
        with proxy._SESSION_LOCK:
            proxy._PAM_SESSIONS[session] = 0
        self.assertFalse(proxy._is_active_pam_session(cookie))


if __name__ == "__main__":
    unittest.main()
