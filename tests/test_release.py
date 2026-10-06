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
    def test_steam_normal_runtime_acceptance_harness_is_required_in_release(self):
        self.assertIn("scripts/steam-auth-surface.py", release.REQUIRED_FILES)
        self.assertIn("scripts/dolphin-bluetooth-lease.py", release.REQUIRED_FILES)
        self.assertIn("scripts/aurelia-graphical-launch.py", release.REQUIRED_FILES)
        self.assertIn("scripts/provision-aurelia-state.py", release.REQUIRED_FILES)

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

    def test_canonical_guard_rejects_noncanonical_source_or_host(self):
        root = self.git_repo()
        original_host = release.socket.gethostname
        release.socket.gethostname = lambda: release.CANONICAL_HOSTNAME
        try:
            with self.assertRaises(release.ReleaseError):
                release.ensure_canonical_source(root)
        finally:
            release.socket.gethostname = original_host

    def test_manifest_and_tamper_detection(self):
        root = Path(tempfile.mkdtemp())
        (root / "payload.txt").write_text("payload\n")
        (root / "bin").mkdir()
        (root / "bin" / "tool").write_text("tool\n")
        release.write_manifest(root)
        release.verify_manifest(root)
        manifest_paths = {
            line.split("  ", 1)[1]
            for line in (root / release.MANIFEST_NAME).read_text().splitlines()
        }
        self.assertEqual(manifest_paths, {"payload.txt", "bin/tool"})
        self.assertNotIn(release.MANIFEST_NAME, manifest_paths)
        (root / "payload.txt").write_text("tampered\n")
        with self.assertRaises(release.ReleaseError):
            release.verify_manifest(root)

    def test_manifest_rejects_uncovered_nested_manifest_and_symlinks(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "payload.txt").write_text("payload\n")
            release.write_manifest(root)
            release.verify_manifest(root)
            nested = root / "extra"
            nested.mkdir()
            (nested / "manifest.sha256").write_text("uncovered\n")
            with self.assertRaisesRegex(release.ReleaseError, "complete release"):
                release.verify_manifest(root)
            (nested / "manifest.sha256").unlink()
            (nested / "unlisted-dir").symlink_to(root, target_is_directory=True)
            with self.assertRaisesRegex(release.ReleaseError, "symlink"):
                release.verify_manifest(root)
            (nested / "unlisted-dir").unlink()
            (root / "manifest.sha256").unlink()
            (root / "manifest.sha256").symlink_to(root / "payload.txt")
            with self.assertRaisesRegex(release.ReleaseError, "no checksum manifest"):
                release.verify_manifest(root)

    def test_post_build_python_bytecode_is_not_an_implicit_manifest_exclusion(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "lib" / "lulu").mkdir(parents=True)
            (root / "lib" / "lulu" / "module.py").write_text("VALUE = 1\n")
            release.write_manifest(root)
            release.verify_manifest(root)
            cache = root / "lib" / "lulu" / "__pycache__"
            cache.mkdir()
            (cache / "module.cpython-314.pyc").write_bytes(b"runtime-generated")
            with self.assertRaisesRegex(release.ReleaseError, "complete release"):
                release.verify_manifest(root)

    def test_payload_build_keeps_native_intermediates_out_of_runtime_tree(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory) / "source-repo"
            repo.mkdir()
            subprocess.run(["git", "init", "-q", "-b", "main"], cwd=repo, check=True)
            for name in ("src/lulu", "ui", "scripts", "config", "packaging", "packages", "themes",
                         "deploy/payload/bin"):
                (repo / name).mkdir(parents=True, exist_ok=True)
            (repo / "themes/mudos-default").mkdir(parents=True, exist_ok=True)
            build_script = repo / "scripts/build-lulu-shell.sh"
            build_script.write_text(
                "#!/bin/sh\nset -eu\nout=$1\ndir=$(dirname \"$out\")\n"
                "touch \"$out\" \"$dir/mudos-guide\" \"$dir/mudos-notification\" \"$dir/generated.moc\"\n"
            )
            for path in (
                "packaging/lulu-vt", "packaging/mudos-provider-install",
                "scripts/release.py",
                "deploy/payload/bin/verify-mudos.sh", "src/lulu/__init__.py",
                "ui/placeholder.qml", "config/placeholder.toml", "packages/placeholder.txt",
            ):
                (repo / path).write_text("fixture\n")
            (repo / "themes/mudos-default/theme.json").write_text("{}\n")
            subprocess.run(["git", "add", "."], cwd=repo, check=True)
            subprocess.run([
                "git", "-c", "user.name=Test", "-c", "user.email=test@example.invalid",
                "commit", "-qm", "fixture",
            ], cwd=repo, check=True)
            payload = Path(directory) / "candidate"
            release.build_payload(repo, payload)
            self.assertTrue((payload / "bin/lulu-shell").is_file())
            self.assertTrue((payload / "bin/mudos-guide").is_file())
            self.assertTrue((payload / "bin/mudos-notification").is_file())
            self.assertFalse((payload / ".native-build").exists())
            self.assertFalse(any(path.suffix == ".moc" for path in payload.rglob("*")))
            for excluded in release.RUNTIME_EXCLUDED_SCRIPTS:
                self.assertFalse((payload / "scripts" / excluded).exists())

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
            manifested = {
                line.split("  ", 1)[1]
                for line in (built / release.MANIFEST_NAME).read_text().splitlines()
            }
            expected = {
                str(path.relative_to(built))
                for path in release.iter_files(built)
                if path.name != release.MANIFEST_NAME
            }
            self.assertEqual(manifested, expected)
            metadata = (built / "RELEASE").read_text()
            self.assertIn(f"revision={revision}\n", metadata)
            self.assertIn("branch=main\n", metadata)
            self.assertNotIn("source=", metadata)
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
