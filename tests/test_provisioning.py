import hashlib
import shutil
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
PAYLOAD = ROOT / "deploy/payload"


class ProvisioningTests(unittest.TestCase):
    def test_python_services_do_not_write_bytecode_into_immutable_release_roots(self) -> None:
        units = (
            "lulu-session@.service", "lulu-consoled.service", "lulu-acquisition.service",
            "lulu-admin.service", "lulu-inputplumber-hotplug.service",
            "lulu-osk@.service",
            "lulu-provider-install@.service", "mudos-recovery-guard.service",
            "mudos-recovery.service", "mudos-recovery-ui.service",
        )
        for unit in units:
            with self.subTest(unit=unit):
                content = (ROOT / "packaging" / unit).read_text()
                self.assertIn("Environment=PYTHONDONTWRITEBYTECODE=1", content)
        for script in ("dev-runtime.sh", "provision-transmission.sh"):
            with self.subTest(script=script):
                content = (ROOT / "scripts" / script).read_text()
                self.assertIn("PYTHONDONTWRITEBYTECODE=1", content)

    def test_shell_provisions_animated_webp_image_plugin(self) -> None:
        provisioning = (ROOT / "scripts" / "provision-appliance-services.sh").read_text()
        self.assertIn("qt6-webengine qt6-imageformats ffmpeg python-pillow", provisioning)

    def test_retired_provider_is_not_shipped_or_provisioned_as_a_service(self) -> None:
        service_units = tuple((ROOT / "packaging").glob("*.service"))
        for unit in service_units:
            with self.subTest(unit=unit.name):
                text = unit.read_text().casefold()
                self.assertNotIn("questarr", text)
        for script in ("provision-appliance-services.sh", "provision-transmission.sh",
                       "provision-nzbget.sh", "release.py"):
            with self.subTest(script=script):
                text = (ROOT / "scripts" / script).read_text().casefold()
                self.assertNotIn("questarr", text)
        self.assertFalse((ROOT / "config/plugins/questarr/plugin.toml").exists())

    def test_startup_handoff_and_plymouth_theme_are_release_assets(self) -> None:
        release = (ROOT / "scripts/release.py").read_text()
        for asset in ("packaging/mudos-startup-surface.service",
                      "packaging/plymouth/themes/mudos/mudos.plymouth",
                      "packaging/plymouth/themes/mudos/mudos.script",
                      "scripts/wait-startup-surface.py",
                      "scripts/configure-mudos-limine.py",
                      "packaging/pacman.d/hooks/99-mudos-limine-config.hook"):
            self.assertIn(asset, release)
            self.assertTrue((ROOT / asset).is_file(), asset)
        theme = ROOT / "packaging/plymouth/themes/mudos"
        self.assertTrue((theme / "mudos-wordmark.png").is_file())
        self.assertTrue((ROOT / "packaging/plymouth-quit.service.d/mudos-handoff.conf").is_file())

    def test_canonical_and_compatibility_qml_are_lintable(self) -> None:
        source = ROOT / "ui"
        shipped = PAYLOAD / "ui"
        # deploy/payload is historical installation compatibility material,
        # not source. Its integrity is checked by the manifest test below;
        # current development/release builders consume the canonical ui tree.
        qmllint = shutil.which("qmllint") or "/usr/lib/qt6/bin/qmllint"
        if not Path(qmllint).exists():
            self.skipTest("qmllint is not installed")
        for tree in (source, shipped):
            result = subprocess.run(
                [qmllint, "--max-warnings", "-1", "-I", str(tree),
                 *(str(path) for path in sorted(tree.glob("*.qml")))],
                capture_output=True, text=True,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_shipped_ui_audio_contract_matches_authoritative_source(self) -> None:
        source = ROOT / "ui/sounds"
        shipped = PAYLOAD / "ui/sounds"
        self.assertEqual(
            {path.name for path in shipped.iterdir()},
            {path.name for path in source.iterdir()},
        )
        for path in source.iterdir():
            self.assertEqual((shipped / path.name).read_bytes(), path.read_bytes(), path.name)

    def test_osk_waits_for_xwayland_before_starting(self) -> None:
        service = (ROOT / "packaging/lulu-osk@.service").read_text()
        self.assertIn("xprop -root", service)

    def test_storage_polkit_rule_is_shipped(self) -> None:
        rule = (ROOT / "packaging/polkit-1/rules.d/50-lulu-storage.rules").read_text()
        self.assertIn("org.freedesktop.udisks2.filesystem-mount", rule)
        self.assertIn("org.freedesktop.udisks2.power-off-drive", rule)

    def test_checkpoint_has_canonical_key_value_format(self) -> None:
        values = {}
        for line in (ROOT / "deploy/CHECKPOINT").read_text().splitlines():
            key, separator, value = line.partition("=")
            self.assertEqual(separator, "=")
            self.assertNotIn(":", key)
            values[key] = value
        self.assertRegex(values["commit"], r"^[0-9a-f]{7,40}$")
        self.assertTrue(values["tag"])
        self.assertRegex(values["generated"], r"^20[0-9]{6}$")

    def test_manifest_covers_existing_payload_and_matches_hashes(self) -> None:
        listed = set()
        for line in (PAYLOAD / "manifest.sha256").read_text().splitlines():
            digest, path = line.split(maxsplit=1)
            relative = Path(path.removeprefix("./"))
            listed.add(relative)
            self.assertTrue((PAYLOAD / relative).is_file(), relative)
            actual = hashlib.sha256((PAYLOAD / relative).read_bytes()).hexdigest()
            self.assertEqual(actual, digest, relative)
        actual_files = {
            path.relative_to(PAYLOAD)
            for path in PAYLOAD.rglob("*")
            if path.is_file() and path.name != "manifest.sha256"
        }
        self.assertEqual(actual_files, listed)

    def test_gamescope_presentation_is_shipped_from_authoritative_source(self) -> None:
        release_builder = (ROOT / "scripts/release.py").read_text()
        self.assertIn('copy_tree(source / "src", payload / "lib")', release_builder)

    def test_settings_model_is_built_from_canonical_source_not_compatibility_payload(self) -> None:
        release_builder = (ROOT / "scripts/release.py").read_text()
        self.assertIn('copy_tree(source / "src", payload / "lib")', release_builder)
        self.assertTrue((ROOT / "src/lulu/system_settings.py").is_file())
        self.assertTrue((ROOT / "src/lulu/bluetooth.py").is_file())

    def test_legacy_steam_bootstraps_are_not_in_the_immutable_runtime(self) -> None:
        release_source = (ROOT / "scripts/release.py").read_text()
        for name in ("steam-session-bootstrap.sh", "steam-bootstrap.sh", "provision-steamcmd.sh",
                     "gamescope-dbus-probe.py", "sessiond-dbus-probe.py",
                     "epic-acquisition-test.py", "test_provisioning.py"):
            self.assertIn(f'"{name}"', release_source)
        console_ui = (PAYLOAD / "scripts/console-ui.sh").read_text()
        self.assertNotIn("steam-session-bootstrap", console_ui)
        self.assertIn("Restart=on-failure", (ROOT / "packaging/lulu-session@.service").read_text())

    def test_clean_install_provisions_pinned_aurelia_without_authentication(self) -> None:
        provision = (ROOT / "scripts/provision-aurelia.sh").read_text()
        package = (ROOT / "packages/aurelia/PKGBUILD").read_text()
        installer = (ROOT / "scripts/install_mudos.py").read_text()
        self.assertIn("pacman -U --needed --noconfirm", provision)
        self.assertIn("installed == 0.1.38-1", provision)
        self.assertIn("pkgver=0.1.38", package)
        self.assertIn("3b67cf258100d466a75095c60b3500dfe1803cf1d803e1f414f1cf53d8c80a8e", package)
        self.assertIn('"scripts/provision-aurelia.sh"', installer)
        self.assertIn("enable_aurelia_review_provider(target)", installer)
        for service in ("lulu-session@.service", "lulu-consoled.service", "lulu-acquisition.service"):
            self.assertIn("Environment=LULU_AURELIA_EXECUTABLE=/usr/bin/aurelia",
                          (ROOT / "packaging" / service).read_text())

    def test_dev_refresh_releases_kms_capture_before_restarting_presentation(self) -> None:
        script = (ROOT / "scripts/dev-runtime.sh").read_text()
        stop = script.index("systemctl --user stop lulu-sunshine-dev.service")
        restart = script.index("systemctl restart lulu-session@2.service")
        start = script.index("systemctl --user enable --now lulu-sunshine-dev.service")
        self.assertLess(stop, restart)
        self.assertLess(restart, start)
        self.assertNotIn("systemctl restart lulu-acquisition.service lulu-consoled.service", script)
        self.assertIn("systemctl restart lulu-consoled.service", script)
        self.assertIn('chown lulu:lulu "$sunshine_user_units/default.target.wants"', script)

    def test_dev_sunshine_is_display_only_and_waits_for_gamescope(self) -> None:
        config = (ROOT / "packaging/sunshine-dev.conf").read_text()
        service = (ROOT / "packaging/lulu-sunshine-dev.service").read_text()
        self.assertIn("capture = kms", config)
        self.assertIn("controller = disabled", config)
        self.assertNotIn("gamepad =", config)
        self.assertIn("stream_audio = disabled", config)
        self.assertIn("bind_address = 192.168.0.245", config)
        self.assertIn('pgrep -u lulu -f "^gamescope --backend drm "', service)

    def test_dev_refresh_stages_provider_installer_inside_published_runtime(self) -> None:
        script = (ROOT / "scripts/dev-runtime.sh").read_text()
        self.assertIn('install -D -m 0755 "$staging/packaging/mudos-provider-install"', script)
        self.assertIn('"$staging/bin/mudos-provider-install"', script)
        self.assertNotIn('"$runtime/bin/mudos-provider-install"', script)
        self.assertLess(script.index('"$staging/bin/mudos-provider-install"'),
                        script.index('"$staging/scripts/provision-appliance-services.sh"'))
        admin = (ROOT / "scripts/provision-admin.sh").read_text()
        self.assertIn('[[ ! -x "$root/bin/mudos-provider-install" ]]', admin)
        installer = (ROOT / "packaging/mudos-provider-install").read_text()
        self.assertIn("SteamCMD backend are disabled", installer)
        self.assertNotIn("pacman -S --needed --noconfirm steam steam-devices", installer)
        self.assertNotIn('exec "$root/scripts/provision-steamcmd.sh"', installer)

    def test_settings_validation_runtime_switch_does_not_reprovision_inputplumber_or_host_policy(self) -> None:
        script = (ROOT / "scripts/dev-runtime.sh").read_text()
        workflow = script.split("settings_validation() {", 1)[1].split("\n}\n\n# Exercise", 1)[0]
        self.assertIn('if [ -e "$runtime" ] || [ -L "$runtime" ]', workflow)
        self.assertIn("promotable=false", workflow)
        self.assertIn('Environment=PYTHONPATH=$runtime/lib', workflow)
        self.assertIn('Environment=LULU_INSTALL_ROOT=$runtime', workflow)
        self.assertIn("systemctl restart lulu-session@2.service", workflow)
        self.assertNotIn("provision-inputplumber", workflow)
        self.assertNotIn("restart inputplumber.service", workflow)
        self.assertNotIn("configure-dev-sunshine-firewall", workflow)
        self.assertNotIn("provision-appliance-services", workflow)

    def test_controller_validation_uses_committed_generic_reconciler_without_mapping_reprovision(self) -> None:
        script = (ROOT / "scripts/dev-runtime.sh").read_text()
        workflow = script.split("controller_validation() {", 1)[1].split("\n}\n\ncase", 1)[0]
        self.assertIn('git -C "$repo_root" status --porcelain', workflow)
        self.assertIn("$repo_root/scripts/provision-inputplumber-gamepads.py", workflow)
        self.assertIn("dev-validation.conf", workflow)
        self.assertIn("systemctl start lulu-inputplumber-hotplug.service", workflow)
        self.assertNotIn("restart inputplumber.service", workflow)
        self.assertNotIn("/etc/inputplumber/profiles", workflow)
        self.assertIn("purpose=bluetooth-controller-path-validation", workflow)
        self.assertIn("systemctl restart lulu-session@2.service", workflow)
        self.assertIn("systemctl restart lulu-consoled.service", workflow)
        self.assertIn("promotable=false", workflow)

    def test_logind_policy_reserves_console_session_vt(self) -> None:
        policy = (ROOT / "packaging/logind.conf.d/lulu.conf").read_text()
        self.assertIn("[Login]", policy)
        self.assertIn("NAutoVTs=0", policy)
        self.assertIn("ReserveVT=0", policy)
        service = (ROOT / "packaging/lulu-consoled.service").read_text()
        self.assertIn("After=user@958.service lulu-session@2.service", service)
        self.assertNotIn("PartOf=lulu-session@2.service", service)

    def test_session_readiness_orders_daemons_before_graphical_bootstrap(self) -> None:
        session = (ROOT / "packaging/lulu-session@.service").read_text()
        consoled = (ROOT / "packaging/lulu-consoled.service").read_text()
        acquisition = (ROOT / "packaging/lulu-acquisition.service").read_text()
        target = (ROOT / "packaging/lulu.target").read_text()
        self.assertIn("Wants=inputplumber.service lulu-osk@%i.service lulu-consoled.service lulu-acquisition.service", session)
        self.assertIn("Type=notify", session)
        self.assertIn("NotifyAccess=main", session)
        self.assertNotIn("PartOf=lulu-session@2.service", consoled)
        self.assertIn("After=user@958.service lulu-session@2.service", consoled)
        self.assertIn("PartOf=lulu-session@2.service", acquisition)
        self.assertIn("After=user@958.service lulu-session@2.service", acquisition)
        self.assertNotIn("WantedBy=lulu.target", consoled)
        self.assertNotIn("WantedBy=lulu.target", acquisition)
        self.assertIn("Wants=inputplumber.service lulu-osk@%i.service lulu-consoled.service lulu-acquisition.service", session)
        self.assertIn("lulu-session@2.service", target)
        self.assertNotIn("lulu-consoled.service", target)
        self.assertNotIn("lulu-acquisition.service", target)
        dev_runtime = (ROOT / "scripts/dev-runtime.sh").read_text()
        self.assertIn('install -m 0644 "$staging/packaging/lulu-session@.service" "$session_unit"', dev_runtime)
        self.assertIn('install -m 0644 "$staging/packaging/lulu-consoled.service" "$consoled_unit"', dev_runtime)
        self.assertIn('install -m 0644 "$staging/packaging/lulu.target" "$target_unit"', dev_runtime)
        self.assertIn("systemctl disable lulu-acquisition.service lulu-consoled.service", dev_runtime)
        self.assertIn('install -m 0644 "$immutable_root/packaging/lulu-session@.service" "$session_unit"', dev_runtime)
        sessiond = (ROOT / "src/lulu/sessiond.py").read_text()
        self.assertIn("_notify_systemd_ready()", sessiond)
        self.assertIn("asyncio.create_task(bootstrap_after_services_ready(interface, bus))", sessiond)
        readiness = (ROOT / "src/lulu/service_readiness.py").read_text()
        for name in ("org.lulu.ConsoleSessiond", "org.lulu.Consoled", "org.lulu.Acquisitiond"):
            self.assertIn(name, readiness)


    def test_presentation_default_is_discovered_not_hardcoded(self) -> None:
        config = (PAYLOAD / "packaging/presentation.conf").read_text()
        self.assertNotIn("\nLULU_OUTPUT_CONNECTOR=HDMI-A-1\n", config)


if __name__ == "__main__":
    unittest.main()
