import hashlib
import stat
import shutil
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
PAYLOAD = ROOT / "deploy/payload"


class ProvisioningTests(unittest.TestCase):
    def test_shipped_qml_is_complete_and_lintable(self) -> None:
        source = ROOT / "ui"
        shipped = PAYLOAD / "ui"
        source_files = {path.name for path in source.glob("*.qml")}
        shipped_files = {path.name for path in shipped.glob("*.qml")}
        self.assertEqual(shipped_files, source_files)
        for name in sorted(source_files):
            self.assertEqual((shipped / name).read_bytes(), (source / name).read_bytes(), name)
        qmllint = shutil.which("qmllint") or "/usr/lib/qt6/bin/qmllint"
        if not Path(qmllint).exists():
            self.skipTest("qmllint is not installed")
        result = subprocess.run(
            [qmllint, "--max-warnings", "-1", "-I", str(shipped),
             *(str(path) for path in sorted(shipped.glob("*.qml")))],
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
        self.assertIn("Restart=always", (PAYLOAD / "packaging/lulu-session@.service").read_text())

    def test_logind_policy_reserves_console_session_vt(self) -> None:
        policy = (ROOT / "packaging/logind.conf.d/lulu.conf").read_text()
        self.assertIn("[Login]", policy)
        self.assertIn("NAutoVTs=0", policy)
        self.assertIn("ReserveVT=0", policy)
        service = (ROOT / "packaging/lulu-consoled.service").read_text()
        self.assertIn("After=user@958.service lulu-session@2.service", service)


    def test_presentation_default_is_discovered_not_hardcoded(self) -> None:
        config = (PAYLOAD / "packaging/presentation.conf").read_text()
        self.assertNotIn("\nLULU_OUTPUT_CONNECTOR=HDMI-A-1\n", config)


if __name__ == "__main__":
    unittest.main()
