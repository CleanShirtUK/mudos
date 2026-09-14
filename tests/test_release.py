import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).parents[1] / "scripts" / "release.py"
SPEC = importlib.util.spec_from_file_location("release", MODULE_PATH)
release = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules["release"] = release
SPEC.loader.exec_module(release)


class ReleaseToolTests(unittest.TestCase):
    def git_repo(self):
        root = Path(tempfile.mkdtemp())
        subprocess.run(["git", "init", "-q", "-b", "main"], cwd=root, check=True)
        (root / "tracked.txt").write_text("tracked\n")
        subprocess.run(["git", "add", "."], cwd=root, check=True)
        subprocess.run(["git", "-c", "user.name=Test", "-c", "user.email=test@example.invalid", "commit", "-qm", "initial"], cwd=root, check=True)
        return root

    def test_source_info_and_dirty_rejection(self):
        root = self.git_repo()
        revision, branch = release.source_info(root)
        self.assertRegex(revision, r"^[0-9a-f]{40}$")
        self.assertEqual(branch, "main")
        release.ensure_clean_source(root)
        (root / "dirty.txt").write_text("dirty\n")
        with self.assertRaises(release.ReleaseError):
            release.ensure_clean_source(root)

    def test_manifest_and_tamper_detection(self):
        root = Path(tempfile.mkdtemp())
        (root / "payload.txt").write_text("payload\n")
        (root / "bin").mkdir()
        (root / "bin" / "tool").write_text("tool\n")
        release.write_manifest(root)
        release.verify_manifest(root)
        (root / "payload.txt").write_text("tampered\n")
        with self.assertRaises(release.ReleaseError):
            release.verify_manifest(root)

    def test_build_records_provenance_and_refuses_overwrite(self):
        root = self.git_repo()
        output = Path(tempfile.mkdtemp())
        revision, branch = release.source_info(root)
        info = release.ReleaseInfo(root, revision, branch, output, output / "candidate", output / "current")
        original = release.build_payload
        original_validate = release.validate_payload
        original_guard = release.ensure_canonical_source
        release.build_payload = lambda _root, payload: (payload.mkdir(), (payload / "payload.txt").write_text("x\n"))
        release.validate_payload = lambda _payload: None
        release.ensure_canonical_source = lambda _root: None
        try:
            built = release.build_release(info)
            release.verify_manifest(built)
            metadata = (built / "RELEASE").read_text()
            self.assertIn(f"revision={revision}\n", metadata)
            self.assertIn("branch=main\n", metadata)
            self.assertIn(f"source={root.resolve()}\n", metadata)
            with self.assertRaises(release.ReleaseError):
                release.build_release(info)
        finally:
            release.build_payload = original
            release.validate_payload = original_validate
            release.ensure_canonical_source = original_guard

    def test_activation_replaces_symlink_atomically(self):
        root = Path(tempfile.mkdtemp())
        releases = root / "releases"
        releases.mkdir()
        first = releases / "first"
        second = releases / "second"
        for candidate in (first, second):
            candidate.mkdir()
            (candidate / "payload.txt").write_text(candidate.name)
            release.write_manifest(candidate)
        activation = root / "current"
        activation.symlink_to("releases/first")
        release.activate_release(second, releases, activation)
        self.assertEqual(activation.resolve(), second)


if __name__ == "__main__":
    unittest.main()
