from __future__ import annotations

import tempfile
import unittest
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import patch

from lulu import onboarding, recovery
from lulu.plugins import ComponentRegistry, PluginRegistry


ROOT = Path(__file__).resolve().parents[1]


class OnboardingStateTests(unittest.TestCase):
    def test_epic_provider_requires_a_runnable_legendary_not_just_a_wrapper_file(self) -> None:
        with patch("lulu.onboarding.shutil.which", return_value="/usr/local/bin/legendary"), \
                patch("lulu.onboarding.subprocess.run", side_effect=FileNotFoundError):
            self.assertFalse(onboarding._provider_installed("epic", onboarding.PROVIDER_INFO["epic"]))

    def test_gog_provider_requires_a_runnable_gogdl_not_just_a_wrapper_file(self) -> None:
        with patch("lulu.onboarding.shutil.which", return_value="/usr/local/bin/gogdl"), \
                patch("lulu.onboarding.subprocess.run", side_effect=FileNotFoundError):
            self.assertFalse(onboarding._provider_installed("gog", onboarding.PROVIDER_INFO["gog"]))

    def test_first_launch_skip_partial_and_completion_are_distinct_persistent_states(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "onboarding.json"
            with patch.object(onboarding, "_STATE_PATH", path):
                self.assertTrue(onboarding.onboarding_state()["required"])
                onboarding.save_progress(providers=["retroarch"])
                state = onboarding.onboarding_state()
                self.assertEqual(state["status"], "partial")
                self.assertTrue(state["required"])
                onboarding.dismiss_onboarding()
                self.assertEqual(onboarding.onboarding_state()["status"], "dismissed")
                self.assertFalse(onboarding.onboarding_state()["required"])
                onboarding.reopen_onboarding()
                self.assertTrue(onboarding.onboarding_state()["required"])
                onboarding.finish_onboarding()
                self.assertEqual(onboarding.onboarding_state()["status"], "completed")
                self.assertFalse(onboarding.onboarding_state()["required"])
                self.assertTrue(path.exists())

    def test_dismissal_is_independent_from_setup_progress_across_restart(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "onboarding.json"
            with patch.object(onboarding, "_STATE_PATH", path):
                # Continue to Home, then edit setup later: the OOBE choice sticks.
                onboarding.dismiss_onboarding()
                self.assertFalse(onboarding.onboarding_state()["required"])
                onboarding.save_progress(providers=["romm"])
                self.assertFalse(onboarding.onboarding_state()["required"])
                self.assertTrue(onboarding._read()["oobe_dismissed"])

                # A partial setup without a prior dismissal still opens OOBE.
                onboarding.reopen_onboarding()
            self.assertTrue(onboarding.onboarding_state()["required"])

    def test_explicit_fresh_oobe_reset_clears_progress_not_account_setup(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "onboarding.json"
            with patch.object(onboarding, "_STATE_PATH", path):
                onboarding.save_progress(providers=["steam", "romm"],
                                         integrations=["providers.steam"])
                onboarding.save_admin_password_configured()
                onboarding.save_validation("providers.steam", True, "ready")
                state = onboarding.reset_onboarding()
            self.assertEqual(state["status"], "never")
            self.assertFalse(state["oobe_dismissed"])
            self.assertEqual(state["selected_providers"], [])
            self.assertEqual(state["selected_integrations"], [])
            self.assertEqual(state["validation"], {})
            self.assertTrue(state["admin_password_configured"])

    def test_manifest_uses_supported_components_and_platform_summaries(self) -> None:
        plugins = PluginRegistry(ROOT / "config/plugins")
        plugins.discover()
        components = ComponentRegistry(plugins)
        components.discover()
        with patch("lulu.onboarding._provider_installed", return_value=False), \
                patch("lulu.onboarding._repository_packages_available", return_value=True):
            rows = onboarding.provider_manifest(components)
        by_id = {row["id"]: row for row in rows}
        self.assertIn("steam", by_id)
        self.assertIn("epic", by_id)
        self.assertIn("gog", by_id)
        self.assertIn("flatpak", by_id)
        self.assertIn("retroarch", by_id)
        self.assertIn("dolphin", by_id)
        self.assertIn("eden", by_id)
        self.assertIn("pcsx2", by_id)
        self.assertIn("RomM", [row["name"] for row in rows])
        self.assertIn("GameCube and Wii", by_id["dolphin"]["summary"])
        installer = (ROOT / "packaging/mudos-provider-install").read_text()
        self.assertIn('libretro_directory = "/usr/lib/libretro"', installer)
        self.assertIn('libretro_info_path = "/usr/share/libretro/info"', installer)

    def test_pcsx2_and_eden_have_managed_flatpak_installers(self) -> None:
        installer = (ROOT / "packaging/mudos-provider-install").read_text()
        self.assertIn('pcsx2) app_id=net.pcsx2.PCSX2', installer)
        self.assertIn('eden) app_id=dev.eden_emu.eden', installer)
        self.assertIn('flatpak install --system --assumeyes flathub "$app_id"', installer)
        self.assertIn("lulu-provider-install@eden.service", (
            ROOT / "packaging/polkit-1/rules.d/57-lulu-provider-install.rules").read_text())
        self.assertTrue((ROOT / "packaging/pcsx2-qt-flatpak").is_file())
        self.assertTrue((ROOT / "packaging/eden-flatpak").is_file())

    def test_integration_manifest_has_typed_credentials_and_official_help_links(self) -> None:
        rows = {row["id"]: row for row in onboarding.integration_manifest()}
        self.assertEqual([field["name"] for field in rows["metadata.igdb"]["fields"]],
                         ["client_id", "client_secret"])
        self.assertEqual([field["name"] for field in rows["providers.romm"]["fields"]],
                         ["url", "api_key"])
        self.assertEqual([field["name"] for field in rows["providers.prowlarr"]["fields"]],
                         ["endpoint", "api_key"])
        self.assertIn("api-docs.igdb.com/#getting-started", rows["metadata.igdb"]["help"])
        self.assertIn("Client API Token", str(rows["providers.romm"]))

    def test_oobe_reuses_network_manager_and_skips_network_page_when_online(self) -> None:
        adapter = (ROOT / "src/lulu/network_manager.py").read_text()
        qml = (ROOT / "ui/ConsoleShell.qml").read_text()
        page = (ROOT / "ui/Onboarding.qml").read_text()
        self.assertIn('"online": connectivity == 4', adapter)
        self.assertIn("systemStatus.networkOnline", qml)
        self.assertIn('openSystemCategory(systemCategories.indexOf("Network"))', qml)
        self.assertIn("networkAdapterAvailable", page)
        self.assertIn("Ethernet or another network interface", page)

    def test_retroarch_uses_pacman_group_and_never_online_updater_cores(self) -> None:
        installer = (ROOT / "packaging/mudos-provider-install").read_text()
        descriptor = (ROOT / "src/lulu/onboarding.py").read_text()
        self.assertIn("pacman -Sg libretro", installer)
        self.assertIn("retroarch libretro libretro-core-info", installer)
        self.assertIn('libretro_directory = "/usr/lib/libretro"', installer)
        self.assertIn('libretro_info_path = "/usr/share/libretro/info"', installer)
        self.assertNotIn("Online Updater", installer)
        self.assertIn('"retroarch"', descriptor)

    def test_steam_installed_detection_requires_gui_packages_and_steamcmd(self) -> None:
        info = onboarding.PROVIDER_INFO["steam"]
        with patch("lulu.onboarding._pacman_installed", return_value=True), \
                patch("lulu.onboarding.shutil.which", return_value="/usr/bin/steam"), \
                patch("lulu.onboarding.PATHS", SimpleNamespace(steamcmd_executable=Path("/missing/steamcmd"))), \
                patch("lulu.onboarding.os.access", return_value=False):
            self.assertFalse(onboarding._provider_installed("steam", info))

    def test_provider_install_unit_does_not_reown_provider_state_directory(self) -> None:
        unit = (ROOT / "packaging/lulu-provider-install@.service").read_text()
        self.assertNotIn("StateDirectory=lulu", unit)
        self.assertIn("/var/lib/lulu", unit)


class RecoveryStateTests(unittest.TestCase):
    def test_three_recent_failures_enter_recovery_and_success_clears_the_window(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "recovery.json"
            recovery.record_failure("shell exited", now=1000, path=path)
            recovery.record_failure("shell exited", now=1004, path=path)
            self.assertFalse(recovery.recovery_required(now=1005, path=path))
            state = recovery.record_failure("QML failed", now=1008, path=path)
            self.assertTrue(state["active"])
            self.assertTrue(recovery.recovery_required(now=1010, path=path))
            self.assertFalse(recovery.recovery_required(now=1400, path=path))
            recovery.clear_failures(path)
            self.assertFalse(recovery.recovery_required(now=1010, path=path))

    def test_recovery_portal_contract_is_allowlisted_and_independent(self) -> None:
        source = (ROOT / "src/lulu/admin_web.py").read_text()
        qml = (ROOT / "ui/Recovery.qml").read_text()
        service = (ROOT / "packaging/lulu-admin.service").read_text()
        recovery_service = (ROOT / "packaging/mudos-recovery.service").read_text()
        recovery_ui = (ROOT / "packaging/mudos-recovery-ui.service").read_text()
        session_unit = (ROOT / "packaging/lulu-session@.service").read_text()
        self.assertIn('path == "/recovery"', source)
        self.assertIn("Recovery.qml", (ROOT / "src/lulu/sessiond.py").read_text())
        self.assertIn("modelData.label", qml)
        self.assertIn("D-pad / arrows", qml)
        self.assertIn("127.0.0.1:38124", qml)
        self.assertIn("WantedBy=multi-user.target", service)
        self.assertNotIn("network-online.target", service)
        self.assertIn("WantedBy=multi-user.target", recovery_service)
        self.assertNotIn("lulu-session@2.service", recovery_service)
        self.assertIn("Conflicts=lulu-session@2.service", recovery_ui)
        self.assertIn("OnFailure=mudos-recovery-guard.service", session_unit)
        self.assertIn("StartLimitBurst=5", session_unit)
        self.assertIn("127.0.0.1", (ROOT / "src/lulu/recovery_service.py").read_text())
        self.assertIn("X-CSRF-Token", source)
        self.assertNotIn("subprocess.run(payload", source)
        installer = (ROOT / "packaging/lulu-provider-install@.service").read_text()
        policy = (ROOT / "packaging/polkit-1/rules.d/57-lulu-provider-install.rules").read_text()
        avahi = (ROOT / "packaging/avahi/mudos-http.service").read_text()
        self.assertIn("mudos-provider-install %i", installer)
        self.assertIn('action.lookup("verb") == "start"', policy)
        self.assertIn("_http._tcp", avahi)
        self.assertIn("<port>80</port>", avahi)
        self.assertIn("mudos-provider-install", (ROOT / "scripts/release.py").read_text())


if __name__ == "__main__":
    unittest.main()
