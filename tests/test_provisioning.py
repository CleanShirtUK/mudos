import hashlib
import stat
import shutil
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
PAYLOAD = ROOT / "deploy/payload"


class ProvisioningTests(unittest.TestCase):
    def test_shell_provisions_animated_webp_image_plugin(self) -> None:
        provisioning = (ROOT / "scripts" / "provision-appliance-services.sh").read_text()
        self.assertIn("qt6-webengine qt6-imageformats ffmpeg python-pillow", provisioning)

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
        self.assertEqual(
            (PAYLOAD / "lib/lulu/gamescope.py").read_bytes(),
            (ROOT / "src/lulu/gamescope.py").read_bytes(),
        )

    def test_settings_model_is_shipped_from_authoritative_source(self) -> None:
        self.assertEqual(
            (PAYLOAD / "lib/lulu/system_settings.py").read_bytes(),
            (ROOT / "src/lulu/system_settings.py").read_bytes(),
        )

    def test_runtime_bootstrap_scripts_are_present_and_executable(self) -> None:
        for name in ("steam-session-bootstrap.sh", "steam-bootstrap.sh"):
            path = PAYLOAD / "scripts" / name
            self.assertTrue(path.is_file())
            self.assertTrue(path.stat().st_mode & stat.S_IXUSR)
        session = (PAYLOAD / "scripts/steam-session-bootstrap.sh").read_text()
        self.assertIn("scripts/steam-bootstrap.sh", session)
        console_ui = (PAYLOAD / "scripts/console-ui.sh").read_text()
        self.assertNotIn("steam-session-bootstrap", console_ui)
        bootstrap = (PAYLOAD / "scripts/steam-bootstrap.sh").read_text()
        self.assertIn("exec /usr/bin/steam -silent", bootstrap)
        self.assertNotIn("+open steam://open/minigameslist", bootstrap)
        self.assertIn("Restart=on-failure", (ROOT / "packaging/lulu-session@.service").read_text())

    def test_dev_refresh_releases_kms_capture_before_restarting_presentation(self) -> None:
        script = (ROOT / "scripts/dev-runtime.sh").read_text()
        stop = script.index("systemctl --user stop lulu-sunshine-dev.service")
        restart = script.index("systemctl restart lulu-session@2.service")
        start = script.index("systemctl --user enable --now lulu-sunshine-dev.service")
        self.assertLess(stop, restart)
        self.assertLess(restart, start)
        self.assertNotIn("systemctl restart lulu-acquisition.service lulu-consoled.service", script)

    def test_dev_refresh_stages_provider_installer_inside_published_runtime(self) -> None:
        script = (ROOT / "scripts/dev-runtime.sh").read_text()
        self.assertIn('install -D -m 0755 "$staging/packaging/mudos-provider-install"', script)
        self.assertIn('"$staging/bin/mudos-provider-install"', script)
        self.assertNotIn('"$runtime/bin/mudos-provider-install"', script)
        installer = (ROOT / "packaging/mudos-provider-install").read_text()
        self.assertIn("pacman -S --needed --noconfirm steam steam-devices", installer)
        self.assertIn('exec "$root/scripts/provision-steamcmd.sh"', installer)

    def test_logind_policy_reserves_console_session_vt(self) -> None:
        policy = (ROOT / "packaging/logind.conf.d/lulu.conf").read_text()
        self.assertIn("[Login]", policy)
        self.assertIn("NAutoVTs=0", policy)
        self.assertIn("ReserveVT=0", policy)
        service = (ROOT / "packaging/lulu-consoled.service").read_text()
        self.assertIn("After=user@958.service lulu-session@2.service", service)
        self.assertIn("PartOf=lulu-session@2.service", service)

    def test_session_readiness_orders_daemons_before_graphical_bootstrap(self) -> None:
        session = (ROOT / "packaging/lulu-session@.service").read_text()
        consoled = (ROOT / "packaging/lulu-consoled.service").read_text()
        acquisition = (ROOT / "packaging/lulu-acquisition.service").read_text()
        target = (ROOT / "packaging/lulu.target").read_text()
        self.assertIn("Wants=inputplumber.service lulu-osk@%i.service lulu-consoled.service lulu-acquisition.service", session)
        self.assertIn("Type=notify", session)
        self.assertIn("NotifyAccess=main", session)
        self.assertIn("PartOf=lulu-session@2.service", consoled)
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
        self.assertIn("await bootstrap_after_services_ready(interface, bus)", sessiond)
        readiness = (ROOT / "src/lulu/service_readiness.py").read_text()
        for name in ("org.lulu.ConsoleSessiond", "org.lulu.Consoled", "org.lulu.Acquisitiond"):
            self.assertIn(name, readiness)


    def test_presentation_default_is_discovered_not_hardcoded(self) -> None:
        config = (PAYLOAD / "packaging/presentation.conf").read_text()
        self.assertNotIn("\nLULU_OUTPUT_CONNECTOR=HDMI-A-1\n", config)


if __name__ == "__main__":
    unittest.main()
