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

    def test_runtime_bootstrap_scripts_are_present_and_executable(self) -> None:
        for name in ("steam-session-bootstrap.sh", "steam-bootstrap.sh"):
            path = PAYLOAD / "scripts" / name
            self.assertTrue(path.is_file())
            self.assertTrue(path.stat().st_mode & stat.S_IXUSR)
        session = (PAYLOAD / "scripts/steam-session-bootstrap.sh").read_text()
        self.assertIn("scripts/steam-bootstrap.sh", session)
        bootstrap = (PAYLOAD / "scripts/steam-bootstrap.sh").read_text()
        self.assertIn("exec /usr/bin/steam -silent", bootstrap)
        self.assertNotIn("+open steam://open/minigameslist", bootstrap)

    def test_presentation_default_is_discovered_not_hardcoded(self) -> None:
        config = (PAYLOAD / "packaging/presentation.conf").read_text()
        self.assertNotIn("\nLULU_OUTPUT_CONNECTOR=HDMI-A-1\n", config)

    def test_legacy_steam_provider_install_is_disabled(self) -> None:
        installer = (ROOT / "packaging/mudos-provider-install").read_text()
        steam_case = installer.split("    steam)", 1)[1].split("    epic)", 1)[0]
        self.assertIn("SteamCMD backend are disabled", steam_case)
        self.assertNotIn("pacman -S", steam_case)
        self.assertNotIn("provision-steamcmd.sh", steam_case)
        ownership = (ROOT / "packaging/mudos-ownership.json").read_text()
        packages = ownership.split('"packages": [', 1)[1].split("]", 1)[0]
        self.assertNotIn('"steam"', packages)
        self.assertNotIn('"steam-devices"', packages)


if __name__ == "__main__":
    unittest.main()
