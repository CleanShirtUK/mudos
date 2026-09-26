from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from lulu.plugins.steam.auth import SteamAuthentication
from lulu.provider_readiness import ProviderReadinessStore
from lulu import onboarding
from lulu.catalogue import CatalogueStore
from lulu.consoled import ConsoleCatalog
from lulu.plugins import PluginRegistry
from lulu.plugins.steam.entitlements import SteamEntitlement


class FakeSteam:
    def _steam_client_pids(self):
        return [1234]


class FakeSecrets:
    def get(self, *_args):
        return None

    def configured(self, *_args):
        return False


class FakeSteamSource:
    provider_id = "steam"
    config = object()
    snapshot = (SteamEntitlement("42", "Fixture Game"),)
    has_snapshot = True
    last_refresh_succeeded = True

    def refresh(self):
        return self.snapshot


class FakeInstalledSteam:
    def list_installed(self):
        return []


class SteamOobeTests(unittest.TestCase):
    def test_setup_has_a_distinct_signin_stage_between_install_and_integrations(self):
        source = Path(__file__).parents[1] / "src/lulu/admin_web.py"
        text = source.read_text()
        self.assertIn("function renderSteamSignin()", text)
        self.assertIn("Sign in to Steam", text)
        self.assertIn("Waiting for Steam sign-in…", text)
        self.assertIn("function continueSteamSignin()", text)
        self.assertIn("steamSignin=providerChoices.includes('steam')", text)
        self.assertIn("function nextProvidersOriginal()", text)
        self.assertIn("steamSignin=true;render()", text)
        self.assertIn("BeginPluginAuthentication", text)
        self.assertIn("Steam is installed. Select Open Steam sign-in", text)
        self.assertIn("Steam Guard device or choose Enter Code on the Mudos screen", text)
        self.assertIn('"steam_password"', text)
        shell = (Path(__file__).parents[1] / "ui/ConsoleShell.qml").read_text()
        self.assertIn("A: I Approved   X: Enter Code   B: Cancel", shell)
        self.assertIn('"approved", "enter-code"',
                      (Path(__file__).parents[1] / "src/lulu/acquisitiond.py").read_text())
        self.assertIn("function testAndSave(id)", text)
        self.assertIn("id==='providers.steam'", text)
        self.assertIn("api('/api/setup/test',{{integration:id}})", text)
        self.assertNotIn("Verify Steam and Review", text)

    def test_acquisition_credentials_are_discovered_while_shell_is_idle(self):
        root = Path(__file__).parents[1]
        shell = (root / "ui/ConsoleShell.qml").read_text()
        timer = shell[shell.index("id: credentialTimer"):shell.index("id: browserTextEntryShortcutTimer")]
        self.assertIn("running: true", timer)
        self.assertIn('root.request("/credential", "GET"', timer)
        source = (root / "src/lulu/consoled.py").read_text()
        self.assertIn("async def VerifySteamAcquisition", source)

    def test_oobe_reads_auth_from_consoled_plugin_status_method(self):
        from lulu.admin_web import AdminApp
        result = type("Result", (), {
            "stdout": '{"type":"s","data":["{\\"authenticated\\":true,\\"persona\\":\\"Test Account\\"}"]}',
        })()
        with patch("lulu.admin_web.subprocess.run", return_value=result) as run:
            status = AdminApp().steam_auth_status()
        self.assertTrue(status["authenticated"])
        self.assertEqual(status["persona"], "Test Account")
        self.assertIn("GetPluginAuthStatus", run.call_args.args[0])

    def test_owned_sync_without_steamcmd_auth_does_not_report_ready(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry = PluginRegistry(root / "plugins")
            registry.discover()
            catalog = ConsoleCatalog(
                CatalogueStore(root / "catalogue.sqlite3"), FakeInstalledSteam(),
                steam_entitlements=FakeSteamSource(), plugin_registry=registry,
            )
            with patch.object(onboarding, "_STATE_PATH", root / "onboarding.json"):
                onboarding.save_progress(providers=["steam"])
                catalog.refresh({"steam"})
            state = catalog.provider_readiness.get("steam")
            self.assertEqual(state["status"], "authentication_required")
            self.assertEqual(state["catalogue_count"], 1)

    def test_steam_ready_requires_verified_separate_acquisition_session(self):
        class VerifiedAuth:
            async def verify_acquisition(self):
                return {"status": "authenticated"}

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry = PluginRegistry(root / "plugins")
            registry.discover()
            catalog = ConsoleCatalog(
                CatalogueStore(root / "catalogue.sqlite3"), FakeInstalledSteam(),
                steam_entitlements=FakeSteamSource(), plugin_registry=registry,
            )
            with patch.object(type(registry), "for_plugin", return_value=[VerifiedAuth()]), \
                    patch.object(onboarding, "_STATE_PATH", root / "onboarding.json"):
                onboarding.save_progress(providers=["steam"])
                catalog.refresh({"steam"})
            self.assertEqual(catalog.provider_readiness.get("steam")["status"], "ready")

    def test_gui_account_requires_live_client_and_matching_local_account_state(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            root = home / ".local/share/Steam"
            (root / "config").mkdir(parents=True)
            (root / "userdata/39734272/config").mkdir(parents=True)
            (root / "userdata/39734272/config/localconfig.vdf").write_text('"UserLocalConfigStore" {}')
            (root / "config/loginusers.vdf").write_text(
                '"users" { "76561198000000000" { "AccountName" "fixture" '
                '"PersonaName" "Fixture User" "MostRecent" "1" } }'
            )
            auth = SteamAuthentication(FakeSteam())
            with patch("pathlib.Path.home", return_value=home):
                account = auth._active_account()
            self.assertEqual(account, {"steam_id": "76561198000000000",
                                       "persona": "Fixture User", "account_name": "fixture"})

    def test_gui_account_accepts_single_complete_loginusers_record_without_most_recent(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            root = home / ".local/share/Steam"
            (root / "config").mkdir(parents=True)
            (root / "userdata/39734272/config").mkdir(parents=True)
            (root / "userdata/39734272/config/localconfig.vdf").write_text('"UserLocalConfigStore" {}')
            (root / "config/loginusers.vdf").write_text(
                '"users" { "76561198000000000" { "AccountName" "fixture" '
                '"PersonaName" "Fixture User" } }'
            )
            auth = SteamAuthentication(FakeSteam())
            with patch("pathlib.Path.home", return_value=home):
                account = auth._active_account()
            self.assertEqual(account, {"steam_id": "76561198000000000",
                                       "persona": "Fixture User", "account_name": "fixture"})

    def test_gui_auth_does_not_imply_steamcmd_or_entitlement_readiness(self):
        auth = SteamAuthentication(FakeSteam())
        with patch("lulu.plugins.steam.auth.SecretStore", return_value=FakeSecrets()), \
                patch("lulu.plugins.steam.auth.SteamEntitlementConfig.from_file", return_value=None), \
                patch("lulu.plugins.steam.auth.SteamAuthentication._active_account", return_value={
                    "steam_id": "76561198000000000", "persona": "Fixture", "account_name": "fixture"
                }), \
                patch("pathlib.Path.is_file", return_value=False):
            state = auth.status()
        self.assertEqual(state["status"], "authenticated")
        self.assertTrue(state["authenticated"])
        self.assertFalse(state["entitlement_configured"])
        self.assertFalse(state["acquisition_usable"])

    def test_guard_wait_state_survives_store_reconstruction(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "provider-readiness.json"
            store = ProviderReadinessStore(path)
            store.set("steam", "authorization_pending",
                      message="Waiting for Steam Guard approval.")
            restarted = ProviderReadinessStore(path)
            self.assertEqual(restarted.get("steam")["status"], "authorization_pending")

    def test_restart_without_a_live_steam_process_recovers_stale_guard_wait(self):
        from lulu.admin_web import AdminApp
        store = type("Readiness", (), {
            "get": lambda self, _provider: {"status": "authorization_pending",
                                             "message": "Waiting for approval."},
            "set": lambda self, _provider, status, **_kwargs: setattr(self, "written", status),
        })()
        with patch("lulu.admin_web.AdminApp.auth_status", return_value={
            "authenticated": False, "client_running": False
        }), patch("lulu.provider_readiness.ProviderReadinessStore", return_value=store):
            state = AdminApp().steam_oobe_auth_status()
        self.assertEqual(state["status"], "authentication_required")
        self.assertIn("Resume authentication", state["message"])
        self.assertEqual(store.written, "authentication_required")

    def test_acquisition_auth_task_survives_verification_caller_cancellation(self):
        class FakeAcquisition:
            account = ""

            def __init__(self):
                self.started = asyncio.Event()
                self.finish = asyncio.Event()

            async def authenticate(self):
                self.started.set()
                await self.finish.wait()
                return {"status": "authenticated"}

        import asyncio
        acquisition = FakeAcquisition()
        auth = SteamAuthentication(FakeSteam(), acquisition)
        with patch("lulu.plugins.steam.auth.SteamAuthentication._active_account",
                   return_value={"account_name": "fixture", "steam_id": "76561198000000000",
                                 "persona": "Fixture"}):
            async def exercise():
                caller = asyncio.create_task(auth.verify_acquisition())
                await acquisition.started.wait()
                owner_task = auth.verification_task
                caller.cancel()
                with self.assertRaises(asyncio.CancelledError):
                    await caller
                self.assertIsNotNone(owner_task)
                self.assertFalse(owner_task.cancelled())
                acquisition.finish.set()
                return await owner_task
            result = asyncio.run(exercise())
        self.assertEqual(acquisition.account, "fixture")
        self.assertEqual(result["status"], "authenticated")

    def test_existing_oobe_auth_boundary_uses_consoled_plugin_auth(self):
        from pathlib import Path
        source = Path(__file__).parents[1] / "src/lulu/admin_web.py"
        text = source.read_text()
        self.assertIn('"BeginPluginAuthentication", "s", "steam"', text)
        self.assertIn('"authorization_pending"', text)
        self.assertIn("Open Steam sign-in", text)
        begin = text[text.index("def begin_steam_oobe_auth"):text.index("def steam_oobe_auth_status")]
        self.assertNotIn("password", begin.casefold())
        self.assertNotIn("username", begin.casefold())

    def test_auth_launch_persists_guard_waiting_state(self):
        from lulu.admin_web import AdminApp
        with patch("lulu.admin_web.subprocess.run", return_value=type("Result", (), {
            "returncode": 0, "stdout": "s \"{\\\"provider_id\\\":\\\"steam\\\"}\"", "stderr": ""
        })()) as run, patch("lulu.provider_readiness.ProviderReadinessStore") as store:
            result = AdminApp().begin_steam_oobe_auth()
        self.assertEqual(result["status"], "authorization_pending")
        self.assertIn("QR sign-in or Steam Guard", result["message"])
        self.assertEqual(store.return_value.set.call_args.args[:2],
                         ("steam", "authorization_pending"))
        self.assertIn("BeginPluginAuthentication", run.call_args.args[0])

    def test_setup_dismisses_only_its_owned_steam_signin_surface(self):
        import asyncio
        import json
        from types import SimpleNamespace
        from unittest.mock import AsyncMock, Mock

        from lulu.admin_web import AdminApp
        from lulu.consoled import ConsoleInterface

        launch = 'setup-owned-token'
        envelope = lambda value: json.dumps({"data": [json.dumps(value)]})
        with patch("lulu.admin_web.subprocess.run", return_value=SimpleNamespace(
                returncode=0, stdout=envelope({"launch": launch}), stderr="")), \
                patch("lulu.provider_readiness.ProviderReadinessStore"):
            started = AdminApp().begin_steam_oobe_auth()
        self.assertEqual(started["launch"], launch)
        with patch("lulu.admin_web.subprocess.run", return_value=SimpleNamespace(
                stdout=envelope({"dismissed": True}))) as run:
            self.assertTrue(AdminApp.dismiss_steam_oobe_auth(launch))
        self.assertEqual(run.call_args.args[0][-3:], ["ss", "steam", launch])
        self.assertFalse(AdminApp.dismiss_steam_oobe_auth(""))

        process = Mock()
        session = SimpleNamespace(call_get_state=AsyncMock(return_value=json.dumps({
            "launch_token": launch, "session_kind": "provider_standalone",
            "provider_id": "steam"})))
        interface = SimpleNamespace(_local_token=launch, _local_process=process, sessiond=session)

        async def dismiss(provider, token):
            method = ConsoleInterface.DismissPluginAuthentication.__wrapped__
            return json.loads(await method(interface, provider, token))

        self.assertFalse(asyncio.run(dismiss('steam', 'unrelated-token'))['dismissed'])
        self.assertFalse(asyncio.run(dismiss('epic', launch))['dismissed'])
        process.terminate.assert_not_called()
        self.assertTrue(asyncio.run(dismiss('steam', launch))['dismissed'])
        process.terminate.assert_called_once_with()

        session.call_get_state.return_value = json.dumps({
            "launch_token": launch, "session_kind": "game", "provider_id": "steam"})
        self.assertFalse(asyncio.run(dismiss('steam', launch))['dismissed'])
        process.terminate.assert_called_once_with()

        source = (Path(__file__).parents[1] / "src/lulu/admin_web.py").read_text()
        self.assertIn("if(launch){{try{{await api('/api/setup/steam/dismiss',{{launch}})", source)
        self.assertIn("rememberSteamLaunchToken", source)

    def test_already_signed_in_setup_never_launches_or_dismisses_steam(self):
        import gi
        import re
        gi.require_version("JavaScriptCore", "4.1")
        from gi.repository import JavaScriptCore
        from lulu.admin_web import Handler

        handler = object.__new__(Handler)
        with patch.object(Handler, "_token", return_value=""), \
                patch.object(Handler, "_send") as send, \
                patch("lulu.admin_web.APP.session", return_value=""):
            handler._setup_page(False)
        script = re.search(r"<script>(.*?)</script>", send.call_args.args[0].decode(), re.S).group(1)
        fixture = """
var calls=[],dismissFails=false,stored={},sessionStorage={getItem:key=>stored[key]||null,
 setItem:(key,value)=>stored[key]=value,removeItem:key=>delete stored[key]};
var fixture={providers:[{id:'steam',name:'Steam',installed:true,installable:true,
 dependencies:[],dependencies_any:[],authentication:{authenticated:true,persona:'Fixture'}}],
 integrations:[],setup_files:[],onboarding:{selected_providers:['steam'],selected_integrations:[],validation:{}}};
var content={innerHTML:'',querySelector:()=>null},noticeElement={textContent:''};
var document={querySelector:s=>s==='#content'?content:s==='#notice'?noticeElement:null,
 querySelectorAll:()=>[]};
var window={location:{assign:()=>{}}},CSS={escape:x=>x};
var setTimeout=()=>0,clearInterval=()=>{},setInterval=()=>0;
var fetch=async function(path,options){calls.push(path);let bad=path==='/api/setup/steam/dismiss'&&dismissFails;
 let value=bad?{error:'Unavailable'}:path==='/api/setup/steam/auth-status'
 ?{status:'authenticated',authentication:{authenticated:true,persona:'Fixture'}}
 :path==='/api/setup/progress'?{state:{selected_integrations:['providers.steam']}}:fixture;
 return {ok:!bad,headers:{get:()=> 'application/json'},json:async()=>value};};
"""
        engine = JavaScriptCore.Context.new()
        engine.evaluate(fixture, -1)
        engine.evaluate(script, -1)
        engine.evaluate("continueSteamSignin()", -1)
        self.assertIsNone(engine.get_exception())
        result = engine.evaluate("JSON.stringify({step, calls})", -1)
        self.assertIsNone(engine.get_exception())
        state = __import__("json").loads(result.to_string())
        self.assertEqual(state["step"], 1)
        self.assertNotIn("/api/setup/steam/authenticate", state["calls"])
        self.assertNotIn("/api/setup/steam/dismiss", state["calls"])

        owned = JavaScriptCore.Context.new()
        owned.evaluate(fixture, -1)
        owned.evaluate("stored['mudos-setup-steam-launch']='setup-owned-token'", -1)
        owned.evaluate(script, -1)
        recovered = owned.evaluate("steamOobeLaunchToken", -1)
        self.assertEqual(recovered.to_string(), "setup-owned-token")
        owned.evaluate("continueSteamSignin()", -1)
        self.assertIsNone(owned.get_exception())
        request = owned.evaluate("JSON.stringify(calls)", -1)
        self.assertIsNone(owned.get_exception())
        self.assertIn("/api/setup/steam/dismiss", __import__("json").loads(request.to_string()))
        removed = owned.evaluate("String(stored['mudos-setup-steam-launch'])", -1)
        self.assertEqual(removed.to_string(), "undefined")

        unavailable = JavaScriptCore.Context.new()
        unavailable.evaluate(fixture, -1)
        unavailable.evaluate("stored['mudos-setup-steam-launch']='setup-owned-token';dismissFails=true", -1)
        unavailable.evaluate(script, -1)
        unavailable.evaluate("continueSteamSignin()", -1)
        self.assertIsNone(unavailable.get_exception())
        retained = unavailable.evaluate("stored['mudos-setup-steam-launch']", -1)
        self.assertEqual(retained.to_string(), "setup-owned-token")

    def test_delayed_steam_window_does_not_turn_launch_timeout_into_failure(self):
        from lulu.admin_web import AdminApp
        with patch("lulu.admin_web.subprocess.run", side_effect=__import__(
                "subprocess").TimeoutExpired("busctl", 35)), \
                patch("lulu.provider_readiness.ProviderReadinessStore") as store:
            result = AdminApp().begin_steam_oobe_auth()
        self.assertEqual(result["status"], "authorization_pending")
        self.assertIn("Mudos screen", result["message"])
        self.assertEqual(store.return_value.set.call_args.args[:2],
                         ("steam", "authorization_pending"))


if __name__ == "__main__":
    unittest.main()
