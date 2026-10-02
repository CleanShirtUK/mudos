#!/usr/bin/env python3
"""Build, verify, and atomically activate immutable Lulu releases."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import os
from pathlib import Path
import shutil
import socket
import stat
import subprocess
import sys
import tarfile
import tempfile
from typing import Iterable


PAYLOAD_DIRS = ("ui", "scripts", "config", "packaging", "packages")
RUNTIME_EXCLUDED_SCRIPTS = (
    "dev-runtime.sh",
    "sessiond-dbus-probe.py",
    "steam-lifecycle-probe.py",
    "steam-bootstrap.sh",
    "steam-session-bootstrap.sh",
    "provision-steamcmd.sh",
    "migrate-prowlarr-key.sh",
    "usenet-acquisition-test.py",
)
REQUIRED_FILES = (
    "bin/lulu-shell",
    "bin/mudos-guide",
    "bin/lulu-vt",
    "bin/mudos-questarr",
    "bin/verify-mudos.sh",
    "lib/lulu/sessiond.py",
    "lib/lulu/consoled.py",
    "lib/lulu/bluetooth.py",
    "ui/ConsoleShell.qml",
    "ui/MudosSettingsPage.qml",
    "ui/SystemStatusStrip.qml",
    "scripts/console-ui.sh",
    "scripts/console-ui-bridge.py",
    "scripts/aurelia-graphical-launch.py",
    "scripts/provision-aurelia-state.py",
    "scripts/reconcile-questarr.py",
    "scripts/provision-inputplumber-gamepads.py",
    "scripts/dolphin-bluetooth-lease.py",
    "scripts/steam-auth-surface.py",
    "scripts/usenet-readiness.py",
    "config/inputplumber/devices/lulu-composite.yaml",
    "packaging/lulu-session@.service",
    "packaging/lulu-inputplumber-hotplug.service",
    "packaging/mudos-ownership.json",
)
MANIFEST_NAME = "manifest.sha256"
MANIFEST_SELF_EXCLUSION = "The checksum manifest is the only excluded regular file because it cannot hash itself."
FORBIDDEN_SYMBOLS = (b"MudosWifi", b"MudosBluetooth", b"WifiBackend", b"BluetoothBackend")
CANONICAL_HOSTNAME = "lulu"
CANONICAL_SOURCE = Path("/home/josh/src/lulu")
CANONICAL_MARKER = ".mudos-canonical-source"
CANONICAL_MARKER_CONTENT = "mudos-canonical-source-v1\n"


class ReleaseError(RuntimeError):
    pass


@dataclass(frozen=True)
class ReleaseInfo:
    repo_root: Path
    revision: str
    branch: str
    release_root: Path
    release_dir: Path
    activation: Path


def command_output(command: list[str], cwd: Path) -> str:
    return subprocess.run(command, cwd=cwd, check=True, text=True, capture_output=True).stdout.strip()


def source_info(repo_root: Path) -> tuple[str, str]:
    root = repo_root.resolve()
    if not root.is_dir():
        raise ReleaseError(f"source path is not a directory: {repo_root}")
    try:
        actual_root = Path(command_output(["git", "rev-parse", "--show-toplevel"], root)).resolve()
        revision = command_output(["git", "rev-parse", "HEAD"], root)
        branch = command_output(["git", "branch", "--show-current"], root) or "(detached HEAD)"
    except (OSError, subprocess.CalledProcessError) as error:
        raise ReleaseError(f"source path is not a Git checkout: {repo_root}") from error
    if actual_root != root:
        raise ReleaseError(f"source path is not the Git checkout root: {repo_root}")
    return revision, branch


def ensure_clean_source(repo_root: Path) -> None:
    status = command_output(["git", "status", "--porcelain", "--untracked-files=all"], repo_root)
    if status:
        raise ReleaseError("source tree is dirty; commit or remove changes before building")


def ensure_canonical_source(repo_root: Path) -> None:
    root = repo_root.resolve()
    if socket.gethostname() != CANONICAL_HOSTNAME:
        raise ReleaseError(f"promotable Mudos builds must run on {CANONICAL_HOSTNAME}")
    if root != CANONICAL_SOURCE:
        raise ReleaseError(f"promotable Mudos source must be {CANONICAL_SOURCE}")
    marker = root / CANONICAL_MARKER
    if not marker.is_file() or marker.read_text() != CANONICAL_MARKER_CONTENT:
        raise ReleaseError(f"canonical source marker is missing or invalid: {marker}")


def release_name(revision: str) -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    return f"{revision[:7]}-candidate-{timestamp}"


def extract_git_tree(repo_root: Path, destination: Path) -> None:
    destination.mkdir(parents=True)
    process = subprocess.Popen(["git", "archive", "--format=tar", "HEAD"], cwd=repo_root, stdout=subprocess.PIPE)
    assert process.stdout is not None
    try:
        with tarfile.open(fileobj=process.stdout, mode="r|") as archive:
            archive.extractall(destination)
    finally:
        process.stdout.close()
    if process.wait() != 0:
        raise ReleaseError("git archive failed")


def copy_tree(source: Path, destination: Path) -> None:
    if not source.is_dir():
        raise ReleaseError(f"required source directory is missing: {source}")
    shutil.copytree(source, destination, symlinks=False)


def make_executable(path: Path) -> None:
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def build_payload(repo_root: Path, payload: Path) -> None:
    source = payload.parent / "source"
    extract_git_tree(repo_root, source)
    payload.mkdir()
    (payload / "bin").mkdir()
    copy_tree(source / "src", payload / "lib")
    for directory in PAYLOAD_DIRS:
        copy_tree(source / directory, payload / directory)
    for relative in RUNTIME_EXCLUDED_SCRIPTS:
        (payload / "scripts" / relative).unlink(missing_ok=True)
    (payload / "scripts" / "release.py").unlink(missing_ok=True)
    build_dir = payload / ".native-build"
    build_dir.mkdir()
    subprocess.run(
        ["sh", str(source / "scripts" / "build-lulu-shell.sh"), str(build_dir / "lulu-shell")],
        cwd=source,
        env={**os.environ, "LULU_INSTALL_ROOT": str(source)},
        check=True,
    )
    # Keep generated moc sources and intermediates outside the runtime payload.
    for binary in ("lulu-shell", "mudos-guide", "mudos-notification"):
        shutil.move(str(build_dir / binary), payload / "bin" / binary)
    shutil.rmtree(build_dir)
    shutil.copy2(source / "packaging" / "lulu-vt", payload / "bin" / "lulu-vt")
    shutil.copy2(source / "scripts" / "mudos-questarr", payload / "bin" / "mudos-questarr")
    shutil.copy2(source / "packaging" / "mudos-provider-install", payload / "bin" / "mudos-provider-install")
    shutil.copy2(source / "deploy" / "payload" / "bin" / "verify-mudos.sh", payload / "bin" / "verify-mudos.sh")
    for path in payload.joinpath("bin").iterdir():
        make_executable(path)
    for path in payload.joinpath("scripts").rglob("*"):
        if path.is_file():
            make_executable(path)


def remove_bytecode(root: Path) -> None:
    for path in root.rglob("__pycache__"):
        if path.is_dir():
            shutil.rmtree(path)
    for path in root.rglob("*.pyc"):
        if path.is_file():
            path.unlink()


def validate_payload(payload: Path) -> None:
    for relative in REQUIRED_FILES:
        if not (payload / relative).is_file():
            raise ReleaseError(f"required release file is missing: {relative}")
    for path in payload.rglob("*"):
        if path.is_symlink():
            raise ReleaseError(f"release payload contains a symlink: {path.relative_to(payload)}")
    subprocess.run([sys.executable, "-m", "compileall", "-q", str(payload / "lib")], check=True)
    remove_bytecode(payload)
    linked = subprocess.run(["ldd", str(payload / "bin" / "lulu-shell")], check=True, text=True, capture_output=True)
    if any("not found" in line for line in linked.stdout.splitlines()):
        raise ReleaseError("native binary has missing libraries")
    for root in (payload / name for name in ("bin", "lib", "ui", "scripts", "config")):
        for path in root.rglob("*"):
            if path.is_file() and any(symbol in path.read_bytes() for symbol in FORBIDDEN_SYMBOLS):
                raise ReleaseError(f"forbidden connectivity symbol found in {path.relative_to(payload)}")


def iter_files(root: Path) -> Iterable[Path]:
    return sorted(path for path in root.rglob("*") if path.is_file())


def write_manifest(release: Path) -> None:
    """Hash every payload regular file except the manifest itself.

    ``MANIFEST_SELF_EXCLUSION`` documents the single unavoidable exclusion;
    verification does not ignore caches, build outputs, or runtime additions.
    """
    manifest = release / MANIFEST_NAME
    entries = [f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.relative_to(release)}" for path in iter_files(release) if path != manifest]
    manifest.write_text("\n".join(entries) + "\n")


def verify_manifest(release: Path) -> None:
    release = release.resolve()
    manifest = release / MANIFEST_NAME
    if manifest.is_symlink() or not manifest.is_file():
        raise ReleaseError(f"release has no checksum manifest: {release}")
    expected = set()
    for line in manifest.read_text().splitlines():
        if not line.strip():
            continue
        digest, relative = line.split("  ", 1)
        candidate = release / relative
        resolved = candidate.resolve()
        try:
            resolved.relative_to(release)
        except ValueError as error:
            raise ReleaseError(f"manifest path is unsafe: {relative}") from error
        if candidate.is_symlink():
            raise ReleaseError(f"manifest path is unsafe: {relative}")
        if not candidate.is_file() or hashlib.sha256(candidate.read_bytes()).hexdigest() != digest:
            raise ReleaseError(f"checksum mismatch: {relative}")
        expected.add(relative)
    if any(path.is_symlink() for path in release.rglob("*")):
        raise ReleaseError("release contains a symlink")
    # The manifest is the sole regular-file exclusion; all other files,
    # including bytecode caches created after release construction, fail closed.
    actual = {str(path.relative_to(release)) for path in iter_files(release) if path != manifest}
    if expected != actual:
        raise ReleaseError("checksum manifest does not cover the complete release")


def make_immutable(release: Path) -> None:
    for path in sorted(release.rglob("*"), reverse=True):
        path.chmod(path.stat().st_mode & ~stat.S_IWUSR & ~stat.S_IWGRP & ~stat.S_IWOTH)


def write_release_metadata(release: Path, info: ReleaseInfo) -> None:
    (release / "RELEASE").write_text(
        f"revision={info.revision}\ncommit={info.revision}\ntag={info.release_dir.name}\n"
        f"branch={info.branch}\n"
        f"status=clean\ncreated={datetime.now(timezone.utc).isoformat()}\nimmutable=true\n"
    )


def build_release(info: ReleaseInfo, dry_run: bool = False) -> Path:
    ensure_canonical_source(info.repo_root)
    revision, branch = source_info(info.repo_root)
    if revision != info.revision or branch != info.branch:
        raise ReleaseError("source changed while preparing build")
    ensure_clean_source(info.repo_root)
    if dry_run:
        return info.release_dir
    info.release_root.mkdir(parents=True, exist_ok=True)
    if info.release_dir.exists() or info.release_dir.is_symlink():
        raise ReleaseError(f"refusing to overwrite existing release: {info.release_dir}")
    staging = Path(tempfile.mkdtemp(prefix=".staging-", dir=info.release_root))
    try:
        payload = staging / "payload"
        build_payload(info.repo_root, payload)
        validate_payload(payload)
        write_release_metadata(payload, info)
        write_manifest(payload)
        verify_manifest(payload)
        make_immutable(payload)
        os.replace(payload, info.release_dir)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    shutil.rmtree(staging, ignore_errors=True)
    return info.release_dir


def activate_release(release: Path, release_root: Path, activation: Path) -> None:
    release = release.resolve()
    release_root = release_root.resolve()
    if release.parent != release_root or not release.is_dir():
        raise ReleaseError("activation release must be a direct child of the release root")
    verify_manifest(release)
    if activation.exists() and not activation.is_symlink():
        raise ReleaseError(f"activation path is not a symlink: {activation}")
    temporary = activation.with_name(f".{activation.name}.next-{os.getpid()}")
    if temporary.exists() or temporary.is_symlink():
        raise ReleaseError(f"temporary activation path already exists: {temporary}")
    activation.parent.mkdir(parents=True, exist_ok=True)
    os.symlink(os.path.relpath(release, activation.parent), temporary)
    os.replace(temporary, activation)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("build", "verify", "activate"))
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--release-root", type=Path, default=Path("/opt/lulu/releases"))
    parser.add_argument("--release-dir", type=Path)
    parser.add_argument("--activation", type=Path, default=Path("/opt/lulu/current"))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    try:
        repo = args.repo_root.resolve()
        revision, branch = source_info(repo) if args.command == "build" else ("", "")
        if args.command == "build":
            release = args.release_dir or args.release_root / release_name(revision)
            print(build_release(ReleaseInfo(repo, revision, branch, args.release_root, release, args.activation), args.dry_run))
        elif args.command == "verify":
            if args.release_dir is None:
                raise ReleaseError("verify requires --release-dir")
            verify_manifest(args.release_dir)
            print(f"valid release: {args.release_dir.resolve()}")
        else:
            if args.release_dir is None:
                raise ReleaseError("activate requires --release-dir")
            if args.dry_run:
                verify_manifest(args.release_dir)
                print(f"would atomically activate {args.release_dir.resolve()} at {args.activation}")
            else:
                activate_release(args.release_dir, args.release_root, args.activation)
                print(args.activation.resolve())
    except (OSError, subprocess.CalledProcessError, ReleaseError, ValueError) as error:
        print(f"release error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
