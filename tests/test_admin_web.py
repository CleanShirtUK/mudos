import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from lulu.admin_web import (AdminApp, Handler, SERVICES, _check_password, _hash_password,
                            _login_page, _page, _service_url)
from lulu.provider_config import ProviderConfigurationService


class FakeSecrets:
    def __init__(self): self.values = {}
    def configured(self, namespace, name): return (namespace, name) in self.values
    def get(self, namespace, name): return self.values.get((namespace, name))
    def put(self, namespace, name, value): self.values[(namespace, name)] = value
    def clear(self, namespace, name): self.values.pop((namespace, name), None)


class AdminWebTests(unittest.TestCase):
    def test_bootstrap_uses_deployed_runtime_and_lulu_secret_context(self):
        script = Path(__file__).parents[1] / "scripts/bootstrap-admin.sh"
        text = script.read_text()
        self.assertIn("/opt/lulu/dev-current/lib", text)
        self.assertIn("sudo -u lulu env HOME=/home/lulu", text)
        self.assertIn("XDG_DATA_HOME=/home/lulu/.local/share", text)
        self.assertIn("PYTHONPATH=\"$runtime/lib\"", text)

    def test_password_hash_and_invalid_password(self):
        encoded = _hash_password("correct horse")
        self.assertTrue(_check_password("correct horse", encoded))
        self.assertFalse(_check_password("wrong", encoded))

    def test_provider_mutation_uses_secret_store_and_blank_preserves(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            secrets = FakeSecrets()
            service = ProviderConfigurationService(system_path=root / "missing.toml",
                user_path=root / "provider.toml", secrets=secrets)
            service.update_provider("providers.usenet", {"enabled": True}, {"rpc_password": "old"})
            service = ProviderConfigurationService(system_path=root / "missing.toml",
                user_path=root / "provider.toml", secrets=secrets)
            service.update_provider("providers.usenet", {"enabled": True}, {})
            self.assertEqual(secrets.get("providers", "providers-rpc-password"), "old")
            self.assertNotIn("old", (root / "provider.toml").read_text())
            service.update_provider("providers.usenet", {}, {}, {"rpc_password"})
            self.assertFalse(secrets.configured("providers", "providers-rpc-password"))

    def test_provider_mutation_reuses_existing_system_secret_reference(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); secrets = FakeSecrets()
            system = root / "system.toml"
            system.write_text('[providers.usenet]\nenabled = true\n[providers.usenet.secrets]\nrpc_password = "usenet/rpc-password"\n')
            service = ProviderConfigurationService(system_path=system, user_path=root / "user.toml", secrets=secrets)
            service.update_provider("providers.usenet", {"enabled": True}, {"rpc_password": "replacement"})
            self.assertIn('rpc_password = "usenet/rpc-password"', (root / "user.toml").read_text())
            self.assertEqual(secrets.get("usenet", "rpc-password"), "replacement")

    def test_service_links_use_request_host_and_include_dufs(self):
        class Request:
            headers = {"Host": "mudos.local"}
        urls = {_service_url(Request(), item) for item in SERVICES}
        self.assertIn("http://mudos.local:8080/", urls)
        self.assertIn("http://mudos.local:6789/", urls)
        self.assertIn("http://mudos.local:9091/transmission/web/", urls)
        self.assertIn("https://mudos.local:47990/", urls)

    def test_provider_rows_never_include_secret_values(self):
        with patch("lulu.admin_web.AdminApp.password_configured", return_value=False):
            app = AdminApp()
            rows = app.provider_rows()
            self.assertTrue(all(all(isinstance(value, bool) for value in row["secrets"].values()) for row in rows))

    def test_relevant_provider_changes_trigger_optional_questarr_reconcile(self):
        admin = (Path(__file__).parents[1] / "src/lulu/admin_web.py").read_text()
        self.assertIn('"providers.torrent", "providers.usenet", "providers.prowlarr"', admin)
        self.assertIn('"lulu-questarr-reconcile.service"', admin)

    def test_transmission_admin_uses_secret_backed_username_and_preserves_blank_password(self):
        admin = (Path(__file__).parents[1] / "src/lulu/admin_web.py").read_text()
        self.assertIn("Leave blank to keep the existing password", admin)
        self.assertIn("Transmission authentication cannot be cleared", admin)
        self.assertIn("from .transmission_admin import apply_rpc_credentials", admin)
        self.assertIn("secrets_in[\"username\"] = rpc_username", admin)
        self.assertIn("lulu-transmission.service", admin)
        self.assertIn("previous credentials were preserved", admin)
        self.assertIn("capture_output=True", admin)
        self.assertIn("/var/lib/lulu-transmission", (Path(__file__).parents[1] / "packaging/lulu-admin.service").read_text())
        self.assertIn("TimeoutStopSec=60s", (Path(__file__).parents[1] / "scripts/provision-transmission.sh").read_text())

    def test_transmission_polkit_rule_is_unit_and_verb_scoped(self):
        rule = (Path(__file__).parents[1] / "packaging/polkit-1/rules.d/54-lulu-transmission.rules").read_text()
        self.assertIn('"lulu-transmission.service"', rule)
        self.assertIn('"stop"', rule)
        self.assertIn('"start"', rule)
        self.assertNotIn('systemctl *', rule)
        helper = (Path(__file__).parents[1] / "packaging/lulu-transmission-config.service").read_text()
        self.assertIn("User=root", helper)
        self.assertIn("setfacl -m u:lulu:rw,m:rw", helper)

    def test_admin_has_canonical_navigation_and_shared_mudos_surface(self):
        admin = (Path(__file__).parents[1] / "src/lulu/admin_web.py").read_text()
        for route in ('/integrations', '/services', '/system', '/integration/'):
            self.assertIn(route, admin)
        for token in ('--surface:', '--raised:', '--accent:', '.setting', '.badge', '.help', '@media(max-width:720px)'):
            self.assertIn(token, admin)
        self.assertIn('Server address', admin)
        self.assertIn('Maximum connections', admin)
        self.assertIn('Leave blank to keep the existing value', admin)
        self.assertIn('Technical details', admin)
        self.assertIn('self._redirect("/integration/"', admin)
        self.assertIn('self._redirect("/integrations")', admin)

    def test_login_page_uses_shared_surface_and_password_autofocus(self):
        page = _login_page().decode()
        self.assertIn("Sign in to manage this Mudos appliance.", page)
        self.assertIn('id=password name=password type=password', page)
        self.assertIn("autofocus", page)
        self.assertIn("--surface:", page)
        self.assertNotIn("SecretStore", page)

    def test_valid_login_creates_session_and_complete_redirect(self):
        class FakeHandler:
            def __init__(self): self.result = None
            def _form(self): return {"password": ["submitted"]}
            def _redirect(self, location, cookie=None): self.result = (location, cookie)
        fake = FakeHandler()
        with patch("lulu.admin_web.APP.authenticate", return_value=True):
            self.assertTrue(Handler.authenticate_form(fake))
        self.assertEqual(fake.result[0], "/")
        self.assertIn("mudos_session=", fake.result[1])
        self.assertIn("HttpOnly", fake.result[1])
        self.assertIn("SameSite=Lax", fake.result[1])

    def test_logout_invalidates_session(self):
        app = AdminApp()
        token, csrf = app.login()
        self.assertEqual(app.session(token), csrf)
        app.logout(token)
        self.assertIsNone(app.session(token))

    def test_authenticated_landing_page_uses_overview_surface(self):
        page = _page("Overview", '<h1>Overview</h1>', subtitle="A clear view", active="overview").decode()
        self.assertIn("Overview", page)
        self.assertIn("Integrations", page)
        self.assertIn("Services", page)
        self.assertIn("System", page)

    def test_invalid_login_is_rendered_not_connection_close(self):
        class FakeHandler:
            def __init__(self): self.result = None
            def _form(self): return {"password": ["wrong"]}
            def _send(self, content, status=200, headers=None): self.result = (content, status)
        fake = FakeHandler()
        with patch("lulu.admin_web.APP.authenticate", return_value=False):
            self.assertFalse(Handler.authenticate_form(fake))
        # The POST handler supplies the 401 page; this verifies the shared
        # login renderer is complete and does not contain a secret value.
        self.assertIn("Sign in", _login_page("The password was not accepted.").decode())
        self.assertNotIn("wrong", _login_page("The password was not accepted.").decode())

    def test_top_level_error_boundary_is_present_and_sanitized(self):
        admin = (Path(__file__).parents[1] / "src/lulu/admin_web.py").read_text()
        self.assertIn("admin request failed method=%s path=%s", admin)
        self.assertIn("Mudos could not complete that request", admin)


if __name__ == "__main__": unittest.main()
