import tempfile
import unittest
import re
import io
import urllib.error
from pathlib import Path
from unittest.mock import Mock, patch

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
    def test_deselected_provider_does_not_retain_stale_install_failure_status(self):
        app = AdminApp()
        source = [dict(id="steam", name="Steam", installed=False)]
        with patch("lulu.admin_web.provider_manifest", return_value=source), \
                patch("lulu.admin_web.onboarding_state", return_value={"selected_providers": []}), \
                patch.object(app, "provider_install_status", return_value={
                    "status": "install_failed", "message": "old failure"}):
            row = app.setup_provider_states()[0]
        self.assertEqual(row["status"], "not_selected")
        self.assertFalse(row["selected"])
        self.assertFalse(row["state"]["failed"])

    def test_admin_integration_save_invalidates_setup_validation_only_after_success(self):
        from types import SimpleNamespace
        handler = object.__new__(Handler)
        before = SimpleNamespace(values={}, secret_refs={}, secret=lambda key: None)
        with patch.object(APP.config, "provider", return_value=before), \
                patch.object(APP.config, "update_provider") as update, \
                patch.object(APP.components, "all", return_value=[]), \
                patch("lulu.admin_web.save_validation") as validate, \
                patch.object(Handler, "_redirect") as redirect:
            handler._save_provider("metadata.steamgriddb", {"enabled": ["true"]}, None)
        update.assert_called_once()
        validate.assert_called_once_with("metadata.steamgriddb", False,
                                         "Connection details changed in Admin; retest before finishing setup.")
        redirect.assert_called_once_with("/integrations?updated=1")

        with patch.object(APP.config, "provider", return_value=before), \
                patch.object(APP.config, "update_provider", side_effect=[OSError("failed"), None]), \
                patch.object(APP.components, "all", return_value=[]), \
                patch("lulu.admin_web.save_validation") as validate, \
                patch.object(Handler, "_send"):
            handler._save_provider("metadata.steamgriddb", {"enabled": ["true"]}, None)
        validate.assert_not_called()

    def test_finish_request_rejects_unvalidated_setup_before_password_mutation(self):
        handler = object.__new__(Handler)
        handler.path = "/api/setup/initial-password"
        with patch.object(APP, "password_configured", return_value=False), \
                patch("lulu.admin_web.onboarding_state", return_value={"status": "partial"}), \
                patch.object(Handler, "_json_body", return_value={
                    "new_password": "fixture-password", "confirm_password": "fixture-password", "finish": True}), \
                patch("lulu.onboarding.require_validated_integrations",
                      side_effect=ValueError("Test and Save before finishing")) as validate, \
                patch.object(APP, "set_initial_admin_password") as password, \
                patch.object(Handler, "_json") as response:
            handler.do_POST()
        validate.assert_called_once_with()
        password.assert_not_called()
        response.assert_called_once_with({"error": "Test and Save before finishing"}, 400)

    def test_onboarding_handoff_qr_and_normal_web_home_have_distinct_routes(self):
        handler = object.__new__(Handler)
        handler.path = "/setup/qr.png"
        handler.wfile = io.BytesIO()
        with patch("lulu.admin_web.subprocess.run", return_value=type(
                "Result", (), {"stdout": b"fixture-png"})()) as qr, \
                patch.object(Handler, "send_response"), patch.object(Handler, "send_header"), \
                patch.object(Handler, "end_headers"):
            handler.do_GET()
        self.assertEqual(qr.call_args.args[0][-1], "http://mudos.local/setup")
        self.assertEqual(handler.wfile.getvalue(), b"fixture-png")
        handler.path = "/"
        with patch.object(Handler, "_require", return_value="csrf"), \
                patch.object(Handler, "_dashboard") as dashboard, \
                patch.object(Handler, "_setup_page") as setup:
            handler.do_GET()
        dashboard.assert_called_once_with()
        setup.assert_not_called()

    def test_persisted_store_ready_requires_current_account_authentication(self):
        app = AdminApp()
        rows = [dict(id=id, name=name, installed=True) for id, name in
                (("steam", "Steam"), ("epic", "Epic Games"), ("gog", "GOG"))]
        with patch("lulu.admin_web.provider_manifest", return_value=rows), \
                patch("lulu.admin_web.onboarding_state", return_value={
                    "selected_providers": [row["id"] for row in rows]}), \
                patch("lulu.provider_readiness.ProviderReadinessStore") as store, \
                patch.object(app, "steam_auth_status", return_value={"authenticated": False}), \
                patch.object(app, "auth_status", side_effect=lambda id: {
                    "authenticated": False, "status": "unavailable" if id == "gog" else "authentication_required"}):
            store.return_value.get.return_value = {"status": "ready", "message": "Stale reconciliation"}
            states = app.setup_provider_states()
        self.assertEqual([state["status"] for state in states], ["authentication_required"] * 3)
        self.assertNotIn("Stale reconciliation", [state["status_message"] for state in states])
        self.assertIn("unavailable", states[2]["status_message"])

        with patch("lulu.admin_web.provider_manifest", return_value=rows[:1]), \
                patch("lulu.admin_web.onboarding_state", return_value={"selected_providers": ["steam"]}), \
                patch("lulu.provider_readiness.ProviderReadinessStore") as store, \
                patch.object(app, "steam_auth_status", return_value={
                    "authenticated": True, "entitlement_configured": False}):
            store.return_value.get.return_value = {"status": "ready", "message": "Stale reconciliation"}
            steam = app.setup_provider_states()[0]
        self.assertEqual(steam["status"], "configuration_required")
        with patch("lulu.admin_web.provider_manifest", return_value=rows[:1]), \
                patch("lulu.admin_web.onboarding_state", return_value={"selected_providers": ["steam"]}), \
                patch("lulu.provider_readiness.ProviderReadinessStore") as store, \
                patch.object(app, "steam_auth_status", return_value={
                    "authenticated": True, "entitlement_configured": True}):
            store.return_value.get.return_value = {"status": "ready", "message": "Reconciled"}
            steam = app.setup_provider_states()[0]
        self.assertEqual(steam["status"], "ready")
        self.assertEqual(steam["status_message"], "Reconciled")

    def test_saving_setup_credentials_invalidates_prior_success_until_retested(self):
        handler = object.__new__(Handler)
        handler.path = "/api/setup/credentials"
        with patch.object(APP, "password_configured", return_value=False), \
                patch("lulu.admin_web.onboarding_state", return_value={"status": "never"}), \
                patch.object(Handler, "_json_body", return_value={"integration": "metadata.igdb"}), \
                patch.object(APP, "save_setup_credentials", return_value={"configured": True}) as save, \
                patch("lulu.admin_web.save_validation") as validate, \
                patch.object(Handler, "_json") as response:
            handler.do_POST()
        save.assert_called_once_with("metadata.igdb", {"integration": "metadata.igdb"})
        validate.assert_called_once_with("metadata.igdb", False,
                                         "Connection details saved; test this integration before continuing.")
        response.assert_called_once_with({"configured": True})
        with patch.object(APP, "password_configured", return_value=False), \
                patch("lulu.admin_web.onboarding_state", return_value={"status": "never"}), \
                patch.object(Handler, "_json_body", return_value={"integration": "metadata.igdb"}), \
                patch.object(APP, "save_setup_credentials", side_effect=ValueError("save failed")), \
                patch("lulu.admin_web.save_validation") as validate, \
                patch.object(Handler, "_json") as response:
            handler.do_POST()
        validate.assert_not_called()
        response.assert_called_once_with({"error": "save failed"}, 400)

    def test_setup_local_providers_do_not_claim_ready_from_installation_alone(self):
        app = AdminApp()
        rows = [dict(id=provider, name=provider, installed=True)
                for provider in ("retroarch", "dolphin", "pcsx2", "eden", "lutris", "flatpak")]
        with patch("lulu.admin_web.provider_manifest", return_value=rows), \
                patch("lulu.admin_web.onboarding_state", return_value={
                    "selected_providers": [row["id"] for row in rows]}):
            states = app.setup_provider_states()
        self.assertEqual([state["status"] for state in states], ["installed"] * len(rows))
        self.assertTrue(all("not been validated" in state["status_message"] for state in states))
        self.assertTrue(all(state["installed"] for state in states))

    def test_setup_downloaders_separate_rpc_health_from_download_readiness(self):
        app = AdminApp()
        rows = [dict(id="torrent", name="Transmission", installed=True),
                dict(id="usenet", name="NZBGet", installed=True)]
        class NewsServer:
            enabled = True
            def __init__(self, host, password): self.host, self.password = host, password
            def get(self, key, default=None): return self.host if key == "host" else default
            def secret_available(self, key): return key == "username" or self.password

        with patch("lulu.admin_web.provider_manifest", return_value=rows), \
                patch("lulu.admin_web.onboarding_state", return_value={
                    "selected_providers": ["torrent", "usenet"]}), \
                patch.object(app, "test_provider", return_value=(True, "RPC healthy")), \
                patch.object(app.config, "provider", return_value=NewsServer("", False)):
            states = app.setup_provider_states()
        self.assertEqual([row["status"] for row in states], ["configured", "configuration_required"])
        self.assertIn("news server", states[1]["status_message"])
        with patch("lulu.admin_web.provider_manifest", return_value=rows), \
                patch("lulu.admin_web.onboarding_state", return_value={
                    "selected_providers": ["torrent", "usenet"]}), \
                patch.object(app, "test_provider", return_value=(True, "RPC healthy")), \
                patch.object(app.config, "provider", return_value=NewsServer("news.example", True)):
            states = app.setup_provider_states()
        self.assertEqual([row["status"] for row in states], ["configured", "configured"])
        self.assertIn("real transfer", states[0]["status_message"])
        self.assertIsNone(states[1]["news_server"]["authenticated"])
        self.assertIn("test the saved Usenet", states[1]["status_message"])
        self.assertFalse(states[1]["state"]["ready"])
        with patch("lulu.admin_web.provider_manifest", return_value=rows), \
                patch("lulu.admin_web.onboarding_state", return_value={
                    "selected_providers": ["usenet"], "validation": {
                        "providers.usenet.server": {"ok": True, "message": "NNTP accepted", "checked_at": 123}}}), \
                patch.object(app, "test_provider", return_value=(True, "RPC healthy")), \
                patch.object(app.config, "provider", return_value=NewsServer("news.example", True)):
            usenet = app.setup_provider_states()[1]
        self.assertTrue(usenet["news_server"]["authenticated"])
        self.assertTrue(usenet["state"]["authenticated"])
        self.assertIn("real transfer", usenet["status_message"])
        self.assertFalse(usenet["state"]["ready"])
        class DisabledAcquisition:
            enabled = False
        with patch("lulu.admin_web.provider_manifest", return_value=rows), \
                patch("lulu.admin_web.onboarding_state", return_value={
                    "selected_providers": ["usenet"], "validation": {
                        "providers.usenet.server": {"ok": True, "message": "NNTP accepted", "checked_at": 123}}}), \
                patch.object(app, "test_provider", return_value=(True, "RPC healthy")), \
                patch.object(app.config, "provider", side_effect=lambda provider: (
                    NewsServer("news.example", True) if provider == "providers.usenet.server"
                    else DisabledAcquisition())):
            usenet = app.setup_provider_states()[1]
        self.assertTrue(usenet["news_server"]["configured"])
        self.assertFalse(usenet["news_server"]["executor_enabled"])
        self.assertEqual(usenet["status"], "configuration_required")
        self.assertIn("no registered Usenet executor", usenet["status_message"])
        with patch("lulu.admin_web.provider_manifest", return_value=rows), \
                patch("lulu.admin_web.onboarding_state", return_value={
                    "selected_providers": ["torrent", "usenet"]}), \
                patch.object(app, "test_provider", return_value=(False, "RPC unavailable")):
            states = app.setup_provider_states()
        self.assertEqual([row["status"] for row in states], ["configuration_required"] * 2)

    def test_oobe_usenet_save_enables_acquisition_executor_and_reloads_service(self):
        class Secrets(FakeSecrets):
            pass
        app = AdminApp()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            app.config = ProviderConfigurationService(
                system_path=root / "system.toml", user_path=root / "user.toml",
                secrets=Secrets())
            with patch.object(app, "wait_for_nzbget_rpc", return_value=(True, "NZBGet RPC healthy")), \
                    patch("lulu.nzbget_admin.apply_news_server") as apply, \
                    patch("lulu.admin_web.subprocess.run") as run:
                result = app.save_setup_credentials("providers.usenet.server", {
                    "host": "news.example", "port": 563, "tls": "true", "connections": 8,
                    "username": "reader", "password": "fixture-secret",
                })
            config_text = (root / "user.toml").read_text()
        self.assertTrue(result["configured"])
        self.assertIn("[providers.usenet]\nenabled = true", config_text)
        self.assertIn("[providers.usenet.server]", config_text)
        self.assertEqual([call.args[0][-1] for call in run.call_args_list],
                         ["nzbget.service", "lulu-acquisition.service"])
        apply.assert_called_once()

    def test_usenet_plugin_registers_only_after_oobe_enables_parent_provider(self):
        import shutil
        from types import SimpleNamespace
        from lulu.plugins import PluginRegistry
        source = Path(__file__).parents[1] / "config/plugins/usenet"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plugin_root = root / "plugins"
            shutil.copytree(source, plugin_root / "usenet",
                            ignore=shutil.ignore_patterns("__pycache__"))
            user = root / ".config/lulu/provider-services.toml"
            user.parent.mkdir(parents=True)
            with patch("lulu.provider_config.PATHS", SimpleNamespace(config_root=root / ".config/lulu")):
                registry = PluginRegistry(plugin_root)
                registry.discover()
                self.assertEqual(registry.with_capability("acquisition"), ())
                user.write_text("[providers.usenet]\nenabled = true\n")
                registry.discover()
            registered = registry.with_capability("acquisition")
        self.assertEqual(len(registered), 1)
        self.assertEqual(registered[0]["provider"], "usenet")

    def test_questarr_account_probe_and_setup_do_not_conflate_health_with_readiness(self):
        app = AdminApp()
        with patch("lulu.admin_web.urllib.request.urlopen", return_value=io.BytesIO(b'{"hasUsers":false}')):
            self.assertEqual(app.questarr_account_status(), "missing")
        with patch("lulu.admin_web.urllib.request.urlopen", return_value=io.BytesIO(b'{"hasUsers":true}')):
            self.assertEqual(app.questarr_account_status(), "present")
        with patch("lulu.admin_web.urllib.request.urlopen", return_value=io.BytesIO(b'{"hasUsers":"false"}')):
            self.assertEqual(app.questarr_account_status(), "unknown")
        with patch("lulu.admin_web.urllib.request.urlopen", side_effect=urllib.error.URLError("offline")):
            self.assertEqual(app.questarr_account_status(), "unknown")
        with patch.object(app, "service_state", return_value="active"), \
                patch.object(app, "service_health", return_value="healthy"), \
                patch.object(app, "questarr_account_status", return_value="missing"), \
                patch.object(app, "test_provider", wraps=app.test_provider) as validate:
            ok, reason = app.test_provider("questarr")
            self.assertFalse(ok)
            self.assertIn("first-run account", reason)
            self.assertEqual(validate.call_count, 1)  # no backend probe before account setup
        with patch.object(app, "service_state", return_value="active"), \
                patch.object(app, "service_health", return_value="healthy"), \
                patch.object(app, "questarr_account_status", return_value="present"):
            # An account and a healthy backend are still not evidence of an
            # authenticated Questarr setup or initial reconciliation.
            original = app.test_provider
            def backend(provider):
                return (True, "Backend healthy") if provider.startswith("providers.") else original(provider)
            with patch.object(app, "test_provider", side_effect=backend):
                ok, reason = app.test_provider("questarr")
            self.assertFalse(ok)
            self.assertIn("verify authenticated Questarr setup", reason)
        with patch("lulu.admin_web.provider_manifest", return_value=[dict(
                id="questarr", name="Questarr", installed=True)]), \
                patch("lulu.admin_web.onboarding_state", return_value={"selected_providers": ["questarr"]}), \
                patch.object(app, "service_state", return_value="active"), \
                patch.object(app, "test_provider", return_value=(False, "Create the Questarr first-run account")):
            row = app.setup_provider_states()[0]
        self.assertEqual(row["status"], "degraded")
        self.assertTrue(row["state"]["running"])
        self.assertFalse(row["state"]["healthy"])
        self.assertFalse(row["state"]["configured"])
        self.assertIn("first-run account", row["status_message"])

    def test_setup_integration_state_uses_provider_selection_and_persisted_skip(self):
        app = AdminApp()
        integration = {"id": "providers.romm", "name": "RomM", "fields": [], "help": "#"}
        with patch("lulu.admin_web.onboarding_state", return_value={
                "selected_providers": ["romm"], "selected_integrations": [],
                "skipped_integrations": ["providers.romm"]}), \
                patch("lulu.admin_web.integration_manifest", return_value=[integration]), \
                patch("lulu.admin_web.provider_manifest", return_value=[]), \
                patch.object(app, "setup_provider_states", return_value=[]), \
                patch("lulu.plugins.romm.RommConfig.from_file", return_value=None), \
                patch("lulu.plugins.romm.readiness.RommReadinessStore") as readiness, \
                patch("lulu.setup_files.file_setup_manifest", return_value=[]):
            readiness.return_value.snapshot.return_value = {
                "status": "missing_configuration", "message": "Token required"}
            result = app.setup_snapshot()
        row = result["integrations"][0]
        self.assertTrue(row["selected"])
        self.assertTrue(row["skipped"])
        self.assertTrue(row["state"]["selected"])
        self.assertTrue(row["state"]["skipped"])
        self.assertFalse(row["state"]["ready"])

    def test_setup_epic_gog_status_exposes_verified_authentication(self):
        app = AdminApp()
        rows = [dict(id=id, name=name, installed=True) for id, name in
                (("epic", "Epic Games"), ("gog", "GOG"))]
        with patch("lulu.admin_web.provider_manifest", return_value=rows), \
                patch("lulu.admin_web.onboarding_state", return_value={
                    "selected_providers": ["epic", "gog"]}), \
                patch("lulu.provider_readiness.ProviderReadinessStore") as store, \
                patch.object(app, "auth_status", side_effect=lambda id: {
                    "authenticated": id == "epic", "status": "authenticated" if id == "epic"
                    else "authentication_required", "methods": ["auth_browser"]}):
            store.return_value.get.return_value = {"status": "syncing"}
            states = app.setup_provider_states()
        self.assertTrue(states[0]["authentication"]["authenticated"])
        self.assertFalse(states[1]["authentication"]["authenticated"])
        self.assertEqual(states[1]["status"], "authentication_required")

    def test_setup_store_accounts_have_sequential_signin_before_integrations(self):
        import gi
        gi.require_version("JavaScriptCore", "4.1")
        from gi.repository import JavaScriptCore

        handler = object.__new__(Handler)
        with patch.object(Handler, "_token", return_value=""), \
                patch.object(Handler, "_send") as send, \
                patch("lulu.admin_web.APP.session", return_value=""):
            handler._setup_page(False)
        script = re.search(r"<script>(.*?)</script>", send.call_args.args[0].decode(), re.S).group(1)
        fixture = """
var calls=[];
var fixture={providers:[
 {id:'epic',name:'Epic Games',installed:true,installable:true,dependencies:[],dependencies_any:[],
 authentication:{authenticated:true},status:'ready'},
 {id:'gog',name:'GOG',installed:true,installable:true,dependencies:[],dependencies_any:[],
 authentication:{authenticated:false},status:'authentication_required',status_message:'Sign in to GOG.'}],
 integrations:[{id:'metadata.igdb',name:'IGDB',configured:false}],setup_files:[],
 onboarding:{selected_providers:['epic','gog'],selected_integrations:[],validation:{}}};
var content={innerHTML:'',querySelector:()=>null},noticeElement={textContent:''};
var document={querySelector:s=>s==='#content'?content:s==='#notice'?noticeElement
 :s==='#provider-auth-code'?{value:'fixture-code'}:null,
 querySelectorAll:s=>s==='[data-provider]:checked'?['epic','gog'].map(id=>({dataset:{provider:id}})):[]};
var window={location:{assign:()=>{}}},CSS={escape:x=>x};
var setTimeout=()=>0,clearInterval=()=>{},setInterval=()=>0;
var fetch=async function(path,options){calls.push(path);let body=options&&options.body?JSON.parse(options.body):{};
 if(path==='/api/setup/provider-auth-complete')fixture.providers[1].authentication.authenticated=true;
 let value=path==='/api/setup/progress'?{state:{selected_providers:['epic','gog']}}
 :path==='/api/setup/provider-authenticate'?{transaction_id:'fixture',verification_url:'https://fixture.local'}
 :fixture;
 return {ok:true,headers:{get:()=> 'application/json'},json:async()=>value};};
"""
        engine = JavaScriptCore.Context.new()
        engine.evaluate(fixture, -1)
        engine.evaluate(script, -1)

        def value(code):
            result = engine.evaluate(code, -1)
            self.assertIsNone(engine.get_exception(), code)
            return result.to_string()

        value("nextProviders()")
        self.assertEqual(value("String(accountStep)"), "true")
        self.assertIn("Epic Games sign-in", value("content.innerHTML"))
        self.assertIn("Next store", value("content.innerHTML"))
        self.assertNotIn("IGDB", value("content.innerHTML"))
        value("advanceAccountStep()")
        self.assertIn("GOG sign-in", value("content.innerHTML"))
        self.assertIn("Skip for now", value("content.innerHTML"))
        value("beginProviderSignin('gog')")
        self.assertIn("One-time authorization code", value("content.innerHTML"))
        value("completeProviderSignin()")
        self.assertIn("Account signed in", value("content.innerHTML"))
        self.assertIn("Reconnect", value("content.innerHTML"))
        value("advanceAccountStep()")
        self.assertEqual(value("String(accountStep)"), "false")
        self.assertIn("IGDB", value("content.innerHTML"))
        self.assertNotIn("GOG account", value("content.innerHTML"))
        value("backToAccountStep()")
        self.assertIn("GOG sign-in", value("content.innerHTML"))
        value("fixture.providers[1].authentication.authenticated=false;render()")
        self.assertIn("Skip for now", value("content.innerHTML"))
        value("advanceAccountStep()")
        self.assertIn("IGDB", value("content.innerHTML"))
        self.assertEqual(value("String(calls.includes('/api/setup/install'))"), "false")

    def test_status_badges_do_not_conflate_configured_with_connected(self):
        self.assertEqual(_status_label("configured"), ("Configured", "muted"))
        self.assertEqual(_status_label("unconfigured"), ("Not configured", "muted"))
        self.assertEqual(_status_label("connected"), ("Connected", "success"))
        self.assertEqual(_status_label("authenticated"), ("Authenticated", "success"))
        self.assertEqual(_status_label("healthy"), ("Healthy", "success"))
        self.assertEqual(_status_label("active"), ("Running", "success"))
        self.assertEqual(_status_label("inactive"), ("Stopped", "warning"))
        self.assertEqual(_status_label("available"), ("Available", "success"))
        self.assertEqual(_status_label("missing"), ("Not installed", "warning"))

    def test_flatpak_contribution_probes_only_its_allowlisted_local_command(self):
        flatpak = ServiceContribution("flatpak", "Flatpak", "Local apps", health="flatpak")
        untrusted = ServiceContribution("fixture", "External", "Unprobed", health="flatpak")
        with patch("lulu.admin_web.shutil.which", return_value="/usr/bin/flatpak") as which, \
                patch("lulu.admin_web.subprocess.run", return_value=type(
                    "Result", (), {"returncode": 0})()) as run:
            self.assertEqual(APP.plugin_service_status(flatpak), "available")
            self.assertEqual(APP.plugin_service_status(untrusted), "unknown")
        which.assert_called_once_with("flatpak")
        run.assert_called_once()
        self.assertEqual(run.call_args.args[0], ["/usr/bin/flatpak", "--version"])
        with patch("lulu.admin_web.shutil.which", return_value=None):
            self.assertEqual(APP.plugin_service_status(flatpak), "missing")
        with patch("lulu.admin_web.shutil.which", return_value="/usr/bin/flatpak"), \
                patch("lulu.admin_web.subprocess.run", return_value=type(
                    "Result", (), {"returncode": 1})()):
            self.assertEqual(APP.plugin_service_status(flatpak), "unknown")

        handler = object.__new__(Handler)
        handler.headers = {"Host": "mudos.local"}
        component = ComponentDescriptor("flatpak", "Flatpak", "Test", "plugin", services=(flatpak,))
        with patch.object(APP, "service_state", return_value="inactive"), \
                patch.object(APP, "service_health", return_value="unhealthy"), \
                patch("lulu.admin_web.shutil.which", return_value="/usr/bin/flatpak"), \
                patch("lulu.admin_web.subprocess.run", return_value=type(
                    "Result", (), {"returncode": 0})()), \
                patch.object(APP.components, "all", return_value=(component,)):
            page = handler._service_rows()
        self.assertIn("Flatpak", page)
        self.assertIn("Available", page.split("Flatpak", 1)[1])

    def test_plugin_service_without_a_live_status_is_not_reported_active(self):
        handler = object.__new__(Handler)
        handler.headers = {"Host": "mudos.local"}
        component = ComponentDescriptor("fixture", "Fixture", "Test", "plugin",
            services=(ServiceContribution("fixture-service", "Fixture Service", "Example"),))
        with patch.object(APP, "service_state", return_value="inactive"), \
                patch.object(APP, "service_health", return_value="unhealthy"), \
                patch.object(APP.components, "all", return_value=(component,)):
            page = handler._service_rows()
        self.assertIn("Fixture Service", page)
        self.assertIn("Unknown", page.split("Fixture Service", 1)[1])
        self.assertIn("Stopped", page)
        self.assertIn("Needs attention", page)

    def test_integrations_and_services_share_one_page_and_legacy_route_redirects(self):
        handler = object.__new__(Handler)
        handler.path = "/integrations"
        with patch.object(APP.config, "provider", return_value=type("Config", (), {"status": "configured"})()), \
                patch.object(Handler, "_service_rows", return_value="SERVICE_ROWS"), \
                patch.object(Handler, "_send") as send:
            handler._providers()
        page = send.call_args.args[0].decode()
        self.assertIn('id="services"', page)
        self.assertIn("SERVICE_ROWS", page)
        self.assertIn('href="/integrations"', page)
        self.assertNotIn('href="/services"', page)
        with patch.object(Handler, "_redirect") as redirect:
            handler._services()
        redirect.assert_called_once_with("/integrations#services")

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

    def test_rejected_installer_start_survives_reload_until_accepted_retry(self):
        from lulu import onboarding
        from types import SimpleNamespace
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(onboarding, "_STATE_PATH", Path(directory) / "onboarding.json"):
                rejected = SimpleNamespace(returncode=1, stderr="systemd rejected start", stdout="")
                with patch("lulu.admin_web.subprocess.run", return_value=rejected):
                    with self.assertRaisesRegex(ValueError, "could not be started"):
                        AdminApp.start_provider_install("steam")
                self.assertIn("could not be started", onboarding.install_start_failure("steam"))
                show = SimpleNamespace(stdout=("ActiveState=inactive\nResult=success\n"
                                               "ExecMainStatus=0\nExecMainStartTimestamp=\n"))
                with patch("lulu.admin_web.subprocess.run", return_value=show), \
                        patch("lulu.onboarding._provider_installed", return_value=False):
                    status = AdminApp.provider_install_status("steam")
                self.assertEqual(status["status"], "install_failed")
                self.assertIn("Retry installation", status["message"])
                accepted = SimpleNamespace(returncode=0, stderr="", stdout="")
                with patch("lulu.admin_web.subprocess.run", return_value=accepted):
                    AdminApp.start_provider_install("steam")
                self.assertEqual(onboarding.install_start_failure("steam"), "")
                with patch("lulu.admin_web.subprocess.run", return_value=show), \
                        patch("lulu.onboarding._provider_installed", return_value=False):
                    self.assertEqual(AdminApp.provider_install_status("steam")["status"], "selected")

    def test_installer_timeout_rechecks_unit_before_recording_failure(self):
        from lulu import onboarding
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(onboarding, "_STATE_PATH", Path(directory) / "onboarding.json"):
                with patch.object(AdminApp, "provider_install_status", return_value={
                        "provider": "steam", "status": "installing", "message": "Running"}):
                    self.assertEqual(AdminApp.record_provider_install_timeout("steam")["status"], "installing")
                self.assertEqual(onboarding.install_start_failure("steam"), "")
                with patch.object(AdminApp, "provider_install_status", return_value={
                        "provider": "steam", "status": "selected", "message": "Not started"}):
                    result = AdminApp.record_provider_install_timeout("steam")
                self.assertEqual(result["status"], "install_failed")
                self.assertIn("within 16 seconds", onboarding.install_start_failure("steam"))
        handler = object.__new__(Handler)
        handler.path = "/api/setup/install-timeout"
        with patch.object(APP, "password_configured", return_value=False), \
                patch("lulu.admin_web.onboarding_state", return_value={"status": "never"}), \
                patch.object(Handler, "_json_body", return_value={"provider": "steam"}), \
                patch.object(APP, "record_provider_install_timeout", return_value={
                    "provider": "steam", "status": "install_failed", "message": "Not started"}) as timeout, \
                patch.object(Handler, "_json") as response:
            handler.do_POST()
        timeout.assert_called_once_with("steam")
        response.assert_called_once_with({"provider": "steam", "status": "install_failed",
                                          "message": "Not started"})

    def test_setup_selection_and_review_explain_failed_provider_install(self):
        import gi
        gi.require_version("JavaScriptCore", "4.1")
        from gi.repository import JavaScriptCore

        handler = object.__new__(Handler)
        with patch.object(Handler, "_token", return_value=""), \
                patch.object(Handler, "_send") as send, \
                patch("lulu.admin_web.APP.session", return_value=""):
            handler._setup_page(False)
        script = re.search(r"<script>(.*?)</script>", send.call_args.args[0].decode(), re.S).group(1)
        engine = JavaScriptCore.Context.new()
        engine.evaluate("""
var content={innerHTML:'',querySelector:()=>null},noticeElement={textContent:''};
var document={querySelector:s=>s==='#content'?content:s==='#notice'?noticeElement:null};
var window={location:{assign:()=>{}}},sessionStorage={getItem:()=>'',removeItem:()=>{}};
var setTimeout=()=>0,clearInterval=()=>{},setInterval=()=>0;
var fetch=()=>new Promise(()=>{});
""", -1)
        engine.evaluate(script, -1)
        engine.evaluate("""
data={providers:[{id:'steam',name:'Steam',summary:'Games',installed:false,
 installable:true,status:'install_failed',status_message:'Failed <at step EXEC>',
 dependencies:[],dependencies_any:[]}],integrations:[],onboarding:{},setup_files:[]};
providerChoices=['steam'];step=0;render();
""", -1)
        self.assertIsNone(engine.get_exception())
        selection = engine.evaluate("content.innerHTML", -1).to_string()
        self.assertIn("Installation failed", selection)
        self.assertIn("Failed &lt;at step EXEC&gt;", selection)
        self.assertNotIn("Failed <at step EXEC>", selection)
        engine.evaluate("step=3;render()", -1)
        self.assertIsNone(engine.get_exception())
        review = engine.evaluate("content.innerHTML", -1).to_string()
        self.assertIn("Not installed", review)
        self.assertIn("Installation failed", review)
        self.assertIn("Failed &lt;at step EXEC&gt;", review)

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

    def test_steam_credentials_remain_in_setup_admin_not_console_plugin_views(self):
        # Provider credentials belong to the authenticated setup/Admin surface;
        # the retired console Plugins destination must not expose a dead form.
        from lulu import admin_web
        import inspect
        setup = inspect.getsource(admin_web.Handler._setup_page)
        console = (Path(__file__).parents[1] / "ui/ConsoleShell.qml").read_text()
        self.assertIn("id==='providers.steam'&&f.name==='steam_username'?'text'", setup)
        self.assertIn("f.type==='secret'?'password'", setup)
        self.assertIn("action == \"credentials\"", inspect.getsource(admin_web.Handler.do_POST))
        self.assertNotIn('beginPluginCredential("steam"', console)

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

    def test_setup_credentials_require_test_and_save_then_retry_or_skip(self):
        import gi
        gi.require_version("JavaScriptCore", "4.1")
        from gi.repository import JavaScriptCore

        handler = object.__new__(Handler)
        with patch.object(Handler, "_token", return_value=""), \
                patch.object(Handler, "_send") as send, \
                patch("lulu.admin_web.APP.session", return_value=""):
            handler._setup_page(False)
        script = re.search(r"<script>(.*?)</script>", send.call_args.args[0].decode(), re.S).group(1)
        fixture = """
var fixtureFail=true;
var fixture={providers:[],integrations:[{id:'providers.romm',name:'RomM',help:'#',
 fields:[{name:'url',label:'URL',type:'url',required:true}],configured:false}],setup_files:[],
     onboarding:{selected_providers:[],selected_integrations:['providers.romm'],skipped_integrations:[],validation:{},
 admin_password_configured:false,status:'partial'}};
var content={innerHTML:'',querySelector:()=>null}, noticeElement={textContent:''};
var document={querySelector:s=>s==='#content'?content:s==='#notice'?noticeElement:null,
 querySelectorAll:()=>[{dataset:{field:'url'},type:'url',value:'https://fixture.local'}]};
var window={location:{assign:()=>{}}},CSS={escape:x=>x};
var setTimeout=()=>0,clearInterval=()=>{},setInterval=()=>0;
 var fetch=async function(path,options){let body=options&&options.body?JSON.parse(options.body):{};
      if(path==='/api/setup/progress')fixture.onboarding.selected_integrations=body.integrations||[];
      if(path==='/api/setup/skip-integration')fixture.onboarding.skipped_integrations=[body.integration];
  if(path==='/api/setup/credentials'){
   fixture.integrations[0].configured=true;
   fixture.onboarding.validation[body.integration]={ok:false,message:'Retest required'};
  }
  let value=path==='/api/setup/test'?{ok:!fixtureFail,message:fixtureFail?'Fixture failed':'Fixture ready'}
      :path==='/api/setup/progress'||path==='/api/setup/skip-integration'?{state:fixture.onboarding}
  :fixture;
  if(path==='/api/setup/test')fixture.onboarding.validation[body.integration]=value;
 return {ok:true,headers:{get:()=> 'application/json'},json:async()=>value};};
"""

        def context():
            engine = JavaScriptCore.Context.new()
            engine.evaluate(fixture, -1)
            engine.evaluate(script, -1)
            self.assertIsNone(engine.get_exception())
            return engine

        def evaluate(engine, code):
            value = engine.evaluate(code, -1)
            self.assertIsNone(engine.get_exception(), code)
            return value.to_string()

        failed = context()
        evaluate(failed, "step=2;render()")
        self.assertIn("Test and Save", evaluate(failed, "content.innerHTML"))
        evaluate(failed, "testAndSave('providers.romm')")
        self.assertIn("Retry", evaluate(failed, "content.innerHTML"))
        self.assertIn("Skip", evaluate(failed, "content.innerHTML"))
        self.assertNotIn("Review Setup", evaluate(failed, "content.innerHTML"))
        evaluate(failed, "reviewSetup()")
        self.assertEqual(evaluate(failed, "String(step)"), "2")
        evaluate(failed, "skipIntegration('providers.romm')")
        self.assertEqual(evaluate(failed, "String(integrationChoices.length)"), "0")
        evaluate(failed, "reviewSetup()")
        self.assertEqual(evaluate(failed, "String(step)"), "3")
        self.assertIn("Skipped", evaluate(failed, "content.innerHTML"))

        retried = context()
        evaluate(retried, "step=2;render();testAndSave('providers.romm')")
        evaluate(retried, "fixtureFail=false;testAndSave('providers.romm')")
        self.assertIn("Review Setup", evaluate(retried, "content.innerHTML"))
        evaluate(retried, "reviewSetup()")
        self.assertEqual(evaluate(retried, "String(step)"), "3")

        evaluate(retried, "step=2;fixture.onboarding.validation['providers.romm']="
                 "{ok:false,message:'Saved in another tab; retest required'};reviewSetup()")
        self.assertEqual(evaluate(retried, "String(step)"), "2")
        self.assertIn("Retry", evaluate(retried, "content.innerHTML"))
        self.assertIn("Saved in another tab", evaluate(retried, "content.innerHTML"))

        multiple = context()
        evaluate(multiple, "fixture.integrations.push({id:'providers.second',name:'Second',help:'#',"
                 "fields:[{name:'url',label:'URL',type:'url',required:true}],configured:false});"
                 "integrationChoices=['providers.romm','providers.second'];step=2;render()")
        self.assertIn("Integration 1 of 2", evaluate(multiple, "content.innerHTML"))
        self.assertIn("RomM", evaluate(multiple, "content.innerHTML"))
        self.assertNotIn("Second", evaluate(multiple, "content.innerHTML"))
        evaluate(multiple, "fixtureFail=false;testAndSave('providers.romm')")
        self.assertIn("Next integration", evaluate(multiple, "content.innerHTML"))
        evaluate(multiple, "nextCredential()")
        self.assertIn("Integration 2 of 2", evaluate(multiple, "content.innerHTML"))
        self.assertNotIn("RomM", evaluate(multiple, "content.innerHTML"))
        evaluate(multiple, "fixtureFail=true;testAndSave('providers.second')")
        self.assertIn("Retry", evaluate(multiple, "content.innerHTML"))
        self.assertNotIn("Review Setup", evaluate(multiple, "content.innerHTML"))
        evaluate(multiple, "skipIntegration('providers.second')")
        self.assertIn("All selected connections are complete", evaluate(multiple, "content.innerHTML"))
        evaluate(multiple, "reviewSetup()")
        self.assertEqual(evaluate(multiple, "String(step)"), "3")

    def test_setup_retry_preserves_unsaved_fields_after_invalid_url_and_save_failure(self):
        import gi
        gi.require_version("JavaScriptCore", "4.1")
        from gi.repository import JavaScriptCore

        handler = object.__new__(Handler)
        with patch.object(Handler, "_token", return_value=""), \
                patch.object(Handler, "_send") as send, \
                patch("lulu.admin_web.APP.session", return_value=""):
            handler._setup_page(False)
        script = re.search(r"<script>(.*?)</script>", send.call_args.args[0].decode(), re.S).group(1)
        fixture = """
var calls=[],saveFails=true,fields=[];
function newFields(){let error={textContent:''};fields=[
 {dataset:{field:'url'},type:'url',value:'',setAttribute:()=>{},
 closest:()=>({querySelector:()=>error})},
 {dataset:{field:'api_key'},type:'password',value:'',setAttribute:()=>{}}];}
var content={_html:'',get innerHTML(){return this._html},set innerHTML(value){this._html=value;newFields()},querySelector:()=>null};
var noticeElement={textContent:''},fixture={providers:[],integrations:[{id:'providers.romm',
 name:'RomM',help:'#',fields:[{name:'url',label:'URL',type:'url',required:true},
 {name:'api_key',label:'Token',type:'secret',required:true}],configured:false}],setup_files:[],
 onboarding:{selected_providers:[],selected_integrations:['providers.romm'],validation:{}}};
var document={querySelector:s=>s==='#content'?content:s==='#notice'?noticeElement
 :s==='[data-integration="providers.romm"][data-field="url"]'?fields[0]:null,
 querySelectorAll:()=>fields};
var window={location:{assign:()=>{}}},CSS={escape:x=>x};
var setTimeout=()=>0,clearInterval=()=>{},setInterval=()=>0;
var fetch=async function(path,options){calls.push(path);let failure=path==='/api/setup/credentials'&&saveFails;
 let value=failure?{error:'Save refused'}:path==='/api/setup/test'?{ok:true,message:'Ready'}:fixture;
 return {ok:!failure,headers:{get:()=> 'application/json'},json:async()=>value};};
"""
        engine = JavaScriptCore.Context.new()
        engine.evaluate(fixture, -1)
        engine.evaluate(script, -1)

        def value(code):
            result = engine.evaluate(code, -1)
            self.assertIsNone(engine.get_exception(), code)
            return result.to_string()

        value("step=2;render();fields[0].value='romm.local';fields[1].value='unsaved-token';"
              "testAndSave('providers.romm')")
        self.assertIn("Retry", value("content.innerHTML"))
        self.assertEqual(value("fields[0].value"), "romm.local")
        self.assertEqual(value("fields[1].value"), "unsaved-token")
        self.assertEqual(value("String(calls.includes('/api/setup/credentials'))"), "false")
        value("fields[0].value='https://romm.local';testAndSave('providers.romm')")
        self.assertEqual(value("fields[0].value"), "https://romm.local")
        self.assertEqual(value("fields[1].value"), "unsaved-token")
        self.assertIn("Save refused", value("content.innerHTML"))
        value("saveFails=false;testAndSave('providers.romm')")
        self.assertIn("Review Setup", value("content.innerHTML"))
        self.assertEqual(value("fields[1].value"), "")

    def test_setup_shows_provider_install_progress_with_real_completed_counts(self):
        import gi
        gi.require_version("JavaScriptCore", "4.1")
        from gi.repository import JavaScriptCore

        handler = object.__new__(Handler)
        with patch.object(Handler, "_token", return_value=""), \
                patch.object(Handler, "_send") as send, \
                patch("lulu.admin_web.APP.session", return_value=""):
            handler._setup_page(False)
        script = re.search(r"<script>(.*?)</script>", send.call_args.args[0].decode(), re.S).group(1)
        fixture = """
var screens=[],calls=[],firstPoll=0,secondPoll=0,stuck=false;
var fixture={providers:[
 {id:'first',name:'First',installed:false,installable:true,dependencies:[],dependencies_any:[]},
 {id:'second',name:'Second',installed:false,installable:true,dependencies:[],dependencies_any:[]},
 {id:'existing',name:'Existing',installed:true,installable:true,dependencies:[],dependencies_any:[]}],
 integrations:[],setup_files:[],onboarding:{selected_providers:[],selected_integrations:[],validation:{}}};
var content={};Object.defineProperty(content,'innerHTML',{set:html=>screens.push(html),get:()=>screens.at(-1)});
var document={querySelector:s=>s==='#content'?content:{textContent:''},
 querySelectorAll:s=>s==='[data-provider]:checked'?['first','second','existing'].map(id=>({dataset:{provider:id}})):[]};
var window={location:{assign:()=>{}}},CSS={escape:x=>x};
var setTimeout=callback=>callback(),clearInterval=()=>{},setInterval=()=>0;
var fetch=async function(path,options){calls.push(path);let body=options&&options.body?JSON.parse(options.body):{};
 if(path==='/api/setup/progress'&&body.providers)fixture.onboarding.selected_providers=body.providers;
 let value=path==='/api/setup/progress'?{state:fixture.onboarding}
 :path==='/api/setup/install/first'?(++firstPoll===1?{status:'selected'}:
    firstPoll===2?{status:'installing'}:{status:'installed'})
 :path==='/api/setup/install-timeout'?{status:'install_failed',message:'Installer did not start within 16 seconds. Check its service status and retry.'}
 :path==='/api/setup/install/second'?(++secondPoll&&stuck?{status:'selected'}:
    {status:'install_failed',message:'Fixture failure'})
 :fixture;
 return {ok:true,headers:{get:()=> 'application/json'},json:async()=>value};};
"""
        engine = JavaScriptCore.Context.new()
        engine.evaluate(fixture, -1)
        engine.evaluate(script, -1)
        engine.evaluate("nextProvidersOriginal()", -1)
        self.assertIsNone(engine.get_exception())

        def value(expression):
            result = engine.evaluate(expression, -1)
            self.assertIsNone(engine.get_exception(), expression)
            return result.to_string()

        self.assertEqual(value("String(step)"), "1")
        history = value("screens.join(' ')")
        self.assertIn("Installing First", history)
        self.assertIn("Installing Second", history)
        self.assertIn('max="3"', history)
        self.assertIn("1 of 3 completed", history)
        self.assertIn("3 of 3 completed", history)
        self.assertIn("Fixture failure", history)
        self.assertEqual(value("String(firstPoll)"), "3")
        self.assertNotIn("First — Failed", history)
        self.assertEqual(value("String(calls.includes('/api/setup/install'))"), "true")
        self.assertEqual(value("String(calls.includes('/api/setup/install/existing'))"), "false")

        timed_out = JavaScriptCore.Context.new()
        timed_out.evaluate(fixture, -1)
        timed_out.evaluate(script, -1)
        timed_out.evaluate("stuck=true;nextProvidersOriginal()", -1)
        self.assertIsNone(timed_out.get_exception())
        polls = timed_out.evaluate("String(secondPoll)", -1)
        self.assertIsNone(timed_out.get_exception())
        self.assertEqual(polls.to_string(), "10")
        history = timed_out.evaluate("screens.join(' ')", -1)
        self.assertIsNone(timed_out.get_exception())
        self.assertIn("Installer did not start within 16 seconds", history.to_string())
        requested = timed_out.evaluate("String(calls.includes('/api/setup/install-timeout'))", -1)
        self.assertIsNone(timed_out.get_exception())
        self.assertEqual(requested.to_string(), "true")

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

    def test_nzbget_restart_readiness_waits_for_authenticated_rpc(self):
        app = AdminApp()
        app.test_provider = Mock(side_effect=[(False, "starting"), (True, "NZBGet RPC healthy")])
        with patch("time.sleep") as sleep:
            result = app.wait_for_nzbget_rpc(attempts=3, interval=0.1)
        self.assertEqual(result, (True, "NZBGet RPC healthy"))
        self.assertEqual(app.test_provider.call_count, 2)
        sleep.assert_called_once_with(0.1)

    def test_store_provider_rows_use_the_same_auth_files_as_oobe_and_catalogue(self):
        class Config:
            status = "not_configured"
            configured = False
            secret_refs = {}

            @staticmethod
            def secret_available(_key):
                return False

        class Auth:
            @staticmethod
            def status():
                return {"configured": True, "authenticated": True}

        app = AdminApp()
        app.config.provider = lambda _provider: Config()
        app._auth = lambda provider: Auth() if provider in {"epic", "gog"} else None
        with patch("lulu.plugins.romm.RommConfig.from_file",
                   return_value=type("Romm", (), {"client_token": "stored-secret-reference"})()):
            rows = {row["id"]: row for row in app.provider_rows()}
        for provider in ("epic", "gog"):
            self.assertEqual(rows[provider]["status"], "configured")
            self.assertTrue(rows[provider]["configured"])
        self.assertEqual(rows["providers.romm"]["status"], "configured")
        self.assertTrue(rows["providers.romm"]["configured"])

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
        self.assertNotIn('href="/services"', page)
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
