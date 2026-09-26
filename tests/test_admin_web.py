import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from lulu.admin_web import (APP, AdminApp, Handler, SERVICES, _login_page, _page, _status_label,
                            _service_url, _setup_service_url)
from lulu.provider_config import ProviderConfigurationService
from lulu.plugins import ComponentRegistry
from lulu.plugins.core import ComponentDescriptor, ServiceContribution


class FakeSecrets:
    def __init__(self): self.values = {}
    def configured(self, namespace, name): return (namespace, name) in self.values
    def get(self, namespace, name): return self.values.get((namespace, name))
    def put(self, namespace, name, value): self.values[(namespace, name)] = value
    def clear(self, namespace, name): self.values.pop((namespace, name), None)


class AdminWebTests(unittest.TestCase):
    def test_status_badges_do_not_conflate_configured_with_connected(self):
        self.assertEqual(_status_label("configured"), ("Configured", "muted"))
        self.assertEqual(_status_label("unconfigured"), ("Not configured", "muted"))
        self.assertEqual(_status_label("connected"), ("Connected", "success"))
        self.assertEqual(_status_label("authenticated"), ("Authenticated", "success"))
        self.assertEqual(_status_label("healthy"), ("Healthy", "success"))
        self.assertEqual(_status_label("active"), ("Running", "success"))
        self.assertEqual(_status_label("inactive"), ("Stopped", "warning"))

    def test_plugin_service_without_a_live_status_is_not_reported_active(self):
        handler = object.__new__(Handler)
        handler.headers = {"Host": "mudos.local"}
        component = ComponentDescriptor("fixture", "Fixture", "Test", "plugin",
            services=(ServiceContribution("fixture-service", "Fixture Service", "Example"),))
        with patch.object(Handler, "_send") as send, \
                patch.object(APP, "service_state", return_value="inactive"), \
                patch.object(APP, "service_health", return_value="unhealthy"), \
                patch.object(APP.components, "all", return_value=(component,)):
            handler._services()
        page = send.call_args.args[0].decode()
        self.assertIn("Fixture Service", page)
        self.assertIn("Unknown", page.split("Fixture Service", 1)[1])
        self.assertIn("Stopped", page)
        self.assertIn("Needs attention", page)

    def test_epic_setup_auth_returns_actionable_error_for_missing_legendary_runtime(self):
        app = AdminApp()
        transaction = app.auth_transactions.create(
            "epic", "auth_browser", verification_url="https://legendary.gl/epiclogin")
        with patch.object(app, "complete_auth", side_effect=FileNotFoundError("legendary")):
            with self.assertRaisesRegex(ValueError, "Legendary is missing or incomplete"):
                app.complete_setup_auth("epic", transaction.transaction_id, "one-time-code")

    def test_gog_setup_auth_returns_actionable_error_for_missing_gogdl_module(self):
        app = AdminApp()
        transaction = app.auth_transactions.create("gog", "auth_browser")
        with patch.object(app, "complete_auth", side_effect=RuntimeError(
                "heroic-gogdl Python module is unavailable")):
            with self.assertRaisesRegex(ValueError, "gogdl is missing or incomplete"):
                app.complete_setup_auth("gog", transaction.transaction_id, "one-time-code")

    def test_steam_installer_failure_keeps_exit_diagnostic_in_setup_status(self):
        show = type("Result", (), {
            "stdout": "ActiveState=failed\nResult=exit-code\nExecMainStatus=203\nExecMainStartTimestamp=now\n",
        })()
        journal = type("Result", (), {"stdout": "Failed at step EXEC: missing executable"})()
        with patch("lulu.admin_web.subprocess.run", side_effect=[show, journal]), \
                patch("lulu.onboarding._provider_installed", return_value=False):
            state = AdminApp.provider_install_status("steam")
        self.assertEqual(state["status"], "install_failed")
        self.assertIn("missing executable", state["message"])

    def test_romm_setup_requires_explicit_http_or_https_scheme(self):
        with self.assertRaisesRegex(ValueError, "beginning with http:// or https://"):
            _setup_service_url("romm.example", "RomM")
        self.assertEqual(_setup_service_url("http://romm.local:8080", "RomM"),
                         "http://romm.local:8080")

    def test_bootstrap_uses_deployed_runtime_and_lulu_secret_context(self):
        script = Path(__file__).parents[1] / "scripts/bootstrap-admin.sh"
        text = script.read_text()
        self.assertIn("/opt/lulu/dev-current/lib", text)
        self.assertIn("sudo -u lulu env HOME=/home/lulu", text)
        self.assertIn("XDG_DATA_HOME=/home/lulu/.local/share", text)
        self.assertIn("PYTHONPATH=\"$runtime/lib\"", text)

    def test_admin_auth_uses_the_managed_system_account(self):
        from lulu.managed_account import MANAGED_ADMIN_ACCOUNT
        with patch("lulu.managed_account.authenticate_managed_account", return_value=True) as authenticate:
            app = AdminApp()
            self.assertTrue(app.authenticate("entered-password"))
        authenticate.assert_called_once_with("entered-password", MANAGED_ADMIN_ACCOUNT)

    def test_initial_password_uses_narrow_privileged_helper_only_during_setup(self):
        from lulu import onboarding
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "onboarding.json"
            with patch.object(onboarding, "_STATE_PATH", path), \
                    patch("lulu.admin_web.subprocess.run", return_value=type("Result", (), {"returncode": 0})()) as run, \
                    patch("lulu.managed_account.authenticate_managed_account", return_value=True) as verify:
                app = AdminApp()
                app.secrets = FakeSecrets()
                self.assertTrue(app.set_initial_admin_password("a-long-initial-password", "a-long-initial-password"))
                verify.assert_called_once_with("a-long-initial-password", "lulu")
                args, kwargs = run.call_args
                self.assertEqual(args[0], ["/usr/bin/pkexec", "/usr/libexec/mudos-set-initial-password"])
                self.assertNotIn("a-long-initial-password", args[0])
                self.assertNotIn("admin", app.secrets.values)
                self.assertTrue(app.password_configured())
                with self.assertRaisesRegex(ValueError, "no longer available"):
                    app.set_initial_admin_password("another-long-password", "another-long-password")

    def test_initial_password_accepts_lowercase_only_password_without_composition_rules(self):
        from lulu import onboarding
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "onboarding.json"
            password = "abcdefgh"
            with patch.object(onboarding, "_STATE_PATH", path), \
                    patch("lulu.admin_web.subprocess.run", return_value=type("Result", (), {"returncode": 0})()), \
                    patch("lulu.managed_account.authenticate_managed_account", return_value=True):
                app = AdminApp()
                app.secrets = FakeSecrets()
                self.assertTrue(app.set_initial_admin_password(password, password))

    def test_initial_password_is_not_marked_configured_if_pam_rejects_it(self):
        from lulu import onboarding
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "onboarding.json"
            with patch.object(onboarding, "_STATE_PATH", path), \
                    patch("lulu.admin_web.subprocess.run", return_value=type("Result", (), {"returncode": 0})()), \
                    patch("lulu.managed_account.authenticate_managed_account", return_value=False):
                app = AdminApp()
                app.secrets = FakeSecrets()
                self.assertFalse(app.set_initial_admin_password("abcdefgh", "abcdefgh"))
                self.assertFalse(app.password_configured())

    def test_admin_service_allows_only_the_scoped_initial_password_privilege_boundary(self):
        service = (Path(__file__).parents[1] / "packaging/lulu-admin.service").read_text()
        self.assertNotIn("NoNewPrivileges=true", service)
        self.assertIn("CAP_SETUID", service)
        self.assertIn("CAP_DAC_OVERRIDE", service)
        self.assertIn("CAP_AUDIT_WRITE", service)
        self.assertIn("ProtectSystem=off", service)
        self.assertIn("ProtectHome=read-only", service)
        rule = (Path(__file__).parents[1]
                / "packaging/polkit-1/rules.d/59-lulu-initial-password.rules").read_text()
        self.assertIn('action.lookup("program") == "/usr/libexec/mudos-set-initial-password"', rule)
        helper = (Path(__file__).parents[1] / "packaging/mudos-set-initial-password").read_text()
        self.assertIn('["/usr/bin/faillock", "--user", ACCOUNT, "--reset"]', helper)

    def test_steam_ownership_uses_signed_in_account_and_persists_username(self):
        import json
        from types import SimpleNamespace
        with tempfile.TemporaryDirectory() as directory:
            plugin_root = Path(directory) / "plugins"
            app = AdminApp()
            app.secrets = FakeSecrets()
            with patch("lulu.admin_web.PATHS", SimpleNamespace(plugins_root=plugin_root)), \
                    patch.object(app, "steam_auth_status", return_value={
                        "authenticated": True, "steam_id": "76561198000000000",
                        "account": "fixtureuser", "persona": "Fixture User",
                    }):
                result = app.save_setup_credentials("providers.steam", {
                    "steam_username": "fixtureuser", "steam_password": "fixture-password",
                    "api_key": "fixture-api-key",
                })
            config = json.loads((plugin_root / "steam/steam.json").read_text())
            self.assertTrue(result["configured"])
            self.assertEqual(config["steam_id"], "76561198000000000")
            self.assertEqual(config["steam_username"], "fixtureuser")
            self.assertEqual(app.secrets.get("steam", "web-api-key"), "fixture-api-key")
            self.assertEqual(app.secrets.get("steam", "password"), "fixture-password")
            self.assertEqual(app.secrets.get("steam", "username"), "fixtureuser")

    def test_steam_ownership_rejects_username_not_matching_authenticated_account(self):
        from types import SimpleNamespace
        app = AdminApp()
        app.secrets = FakeSecrets()
        with patch("lulu.admin_web.PATHS", SimpleNamespace(plugins_root=Path("/not-used"))), \
                patch.object(app, "steam_auth_status", return_value={
                    "authenticated": True, "steam_id": "76561198000000000",
                    "account": "fixtureuser", "persona": "Fixture User",
                }):
            with self.assertRaisesRegex(ValueError, "username shown"):
                app.save_setup_credentials("providers.steam", {
                    "steam_username": "wrong-user", "steam_password": "fixture-password",
                    "api_key": "fixture-api-key",
                })
        self.assertFalse(app.secrets.configured("steam", "web-api-key"))

    def test_steam_ownership_form_asks_for_username_instead_of_steamid64(self):
        from lulu.onboarding import INTEGRATION_METADATA
        fields = INTEGRATION_METADATA["providers.steam"]["fields"]
        self.assertEqual(fields[0]["name"], "steam_username")
        self.assertEqual(fields[0]["label"], "Steam username")
        self.assertTrue(fields[0]["required"])
        self.assertEqual(fields[1]["name"], "steam_password")
        self.assertEqual(fields[1]["type"], "secret")
        self.assertTrue(fields[1]["required"])
        self.assertIn("authenticated Steam client", INTEGRATION_METADATA["providers.steam"]["description"])

    def test_steam_username_is_visible_in_setup_and_console_without_changing_secret_storage(self):
        # Steam's username is still stored by the existing secret-backed API,
        # but should not be rendered as a password in either input surface.
        from lulu import admin_web
        import inspect
        setup = inspect.getsource(admin_web.Handler._setup_page)
        console = (Path(__file__).parents[1] / "ui/ConsoleShell.qml").read_text()
        self.assertIn("id==='providers.steam'&&f.name==='steam_username'?'text'", setup)
        self.assertIn("f.type==='secret'?'password'", setup)
        self.assertIn('beginPluginCredential("steam", "username", "Steam username", "Username", "secret", false)', console)
        self.assertIn('beginPluginCredential("steam", "password", "SteamCMD Password", "Password", "secret", true)', console)
        self.assertIn('else if (target.kind === "secret")', console)

    def test_setup_review_lists_all_components_in_a_scrollable_document(self):
        handler = object.__new__(Handler)
        with patch.object(Handler, "_token", return_value=""), \
                patch.object(Handler, "_send") as send, \
                patch("lulu.admin_web.APP.session", return_value=""):
            handler._setup_page(False)
        page = send.call_args.args[0].decode()
        review = page.split("else {root.innerHTML='<h2>Setup review", 1)[1].split("function fieldDefault", 1)[0]
        self.assertIn("data.providers.map(p=>", review)
        self.assertIn("data.integrations.map(i=>", review)
        self.assertNotIn("filter(p=>providerChoices.includes", review)
        self.assertNotIn("filter(i=>integrationChoices.includes", review)
        self.assertIn("p.installed?'Installed':'Not installed'", review)
        self.assertIn("i.configured?'Configured':'Not configured'", review)
        self.assertIn("Scroll to see all providers", review)
        self.assertNotIn("overflow:hidden", page)

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

    def test_first_time_secret_schema_creates_declared_reference_without_exposing_value(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); secrets = FakeSecrets()
            service = ProviderConfigurationService(system_path=root / "missing.toml",
                user_path=root / "user.toml", secrets=secrets)
            descriptor = next(item for item in ComponentRegistry().builtins
                              if item.component_id == "metadata.igdb")
            service.update_provider("metadata.igdb", {"enabled": True, "client_id": "public-id"},
                                   {"client_secret": "private-value"},
                                   secret_references={"client_secret": descriptor.secrets[0].reference})
            text = (root / "user.toml").read_text()
            self.assertIn('client_id = "public-id"', text)
            self.assertIn('client_secret = "metadata/igdb-client-secret"', text)
            self.assertNotIn("private-value", text)
            self.assertEqual(secrets.get("metadata", "igdb-client-secret"), "private-value")
            service.update_provider("metadata.igdb", {}, {})
            self.assertEqual(secrets.get("metadata", "igdb-client-secret"), "private-value")

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

    def test_provider_configuration_does_not_blindly_trigger_questarr_reconcile(self):
        admin = (Path(__file__).parents[1] / "src/lulu/admin_web.py").read_text()
        self.assertNotIn('if provider_id in {"providers.torrent", "providers.usenet", "providers.prowlarr"}', admin)
        self.assertIn("Questarr reconciliation is deferred", admin)

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
