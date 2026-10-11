#!/usr/bin/env python3
"""Disposable systemd mount-namespace experiment; never targets production paths."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import uuid


SYNTHETIC_BASE = Path("/tmp/opencode")


def write_probe(mountpoint: Path, *, negative_child_mount: bool = False) -> dict[str, object]:
    """Run inside a transient unit and exercise the synthetic library boundary."""
    helper_path = Path(__file__).with_name("steam-ownership-guard-prototype.py")
    spec = importlib.util.spec_from_file_location("steam_ownership_guard_prototype", helper_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("prototype guard helper is unavailable")
    helper = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = helper
    spec.loader.exec_module(helper)
    SteamBoundaryError = helper.SteamBoundaryError
    parse_mountinfo = helper.parse_mountinfo
    validate_mount_boundary = helper.validate_mount_boundary

    root = mountpoint / "steamapps"
    payload = root / "common" / "synthetic-game" / "payload.dat"
    manifest = root / "appmanifest_424242.acf"
    staged = root / "downloading" / "424242" / "payload.dat"
    shader = root / "shadercache" / "424242" / "cache.bin"
    compat = root / "compatdata" / "424242" / "pfx" / "user.reg"
    allowed = (str(root / "shadercache"), str(root / "compatdata"))
    # Runtime exceptions are separate tmpfs mounts; the rest of steamapps is
    # protected by one read-only bind.
    mountinfo = Path("/proc/self/mountinfo").read_text()
    boundary_error = ""
    try:
        mounts = validate_mount_boundary(mountinfo, (str(root),), allowed)
        boundary_valid = True
    except SteamBoundaryError as error:
        if not negative_child_mount:
            raise
        boundary_error = str(error)
        boundary_valid = False
        mounts = parse_mountinfo(mountinfo)

    def denied(path: Path, *, append: bool = False) -> bool:
        try:
            if append:
                with path.open("a", encoding="utf-8") as stream:
                    stream.write("steam-write\n")
            else:
                path.write_text("steam-write\n", encoding="utf-8")
        except OSError as error:
            return error.errno in (1, 13, 30)  # EPERM/EACCES/EROFS
        return False

    denied_results = {
        "payload_append_denied": denied(payload, append=True),
        "manifest_rewrite_denied": denied(manifest),
        "stage_rewrite_denied": denied(staged),
        "stage_create_denied": denied(staged.parent / "new.chunk"),
        "commit_into_game_dir_denied": denied(payload),
    }
    if negative_child_mount:
        # The intentionally bad extra bind is a disposable demonstration that
        # an RW child mount punches through the RO parent. The guard must reject
        # the namespace even though this write succeeds.
        denied_results["injected_stage_mount_is_writable"] = not denied(staged, append=True)
    # Internal symlink aliases resolve back into the protected mount.
    alias = root / "common" / "alias.dat"
    denied_results["internal_symlink_alias_denied"] = denied(alias)
    external_alias = root / "common" / "external-alias.dat"
    denied_results["external_symlink_escape_denied"] = denied(external_alias)
    shader.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.link(payload, shader.parent / "hardlink-to-game.dat")
        denied_results["hardlink_into_runtime_exception_denied"] = False
    except OSError as error:
        denied_results["hardlink_into_runtime_exception_denied"] = error.errno == 18  # EXDEV
        denied_results["hardlink_errno"] = error.errno

    # Helper processes inherit the systemd service mount namespace.
    child_code = (
        "from pathlib import Path; import errno,sys; "
        "p=Path(sys.argv[1]); "
        "\ntry: p.write_text('child-write')\n"
        "except OSError as e: sys.exit(0 if e.errno in (1,13,30) else 2)\n"
        "sys.exit(1)"
    )
    child = subprocess.run([sys.executable, "-c", child_code, str(payload)],
                           capture_output=True, text=True, check=False)
    denied_results["child_process_write_denied"] = child.returncode == 0

    # Legitimate runtime state exceptions are deliberately narrow and outside
    # the protected content sets.
    shader.parent.mkdir(parents=True, exist_ok=True)
    compat.parent.mkdir(parents=True, exist_ok=True)
    shader.write_text("shader-cache", encoding="utf-8")
    compat.write_text("compat-prefix", encoding="utf-8")
    runtime_writable = shader.read_text() == "shader-cache" and compat.read_text() == "compat-prefix"

    mounts_report = [
        {"mount_id": mount.mount_id, "point": mount.point, "root": mount.root,
         "options": sorted(mount.options), "device": mount.device}
        for mount in mounts if mount.point == str(root) or mount.point.startswith(str(root) + "/")
    ]
    if negative_child_mount:
        expected = (not boundary_valid and "writable child mount" in boundary_error
                    and denied_results.get("injected_stage_mount_is_writable") is True)
        status = "pass" if expected and runtime_writable else "fail"
    else:
        status = "pass" if all(denied_results.values()) and runtime_writable else "fail"
    return {"denied": denied_results, "runtime_allowlist_writable": runtime_writable,
            "negative_child_mount": negative_child_mount,
            "mount_guard_rejected_injected_mount": not boundary_valid,
            "mount_guard_error": boundary_error,
            "mount_namespace": os.readlink("/proc/self/ns/mnt"),
            "mounts": mounts_report,
            "status": status}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--probe", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--negative-child-mount", action="store_true",
                        help="run a synthetic hostile RW-child-mount detector test")
    parser.add_argument("--keep-synthetic", action="store_true",
                        help="retain the disposable fixture after the report")
    parser.add_argument("probe_args", nargs="*", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.probe:
        if len(args.probe_args) != 1:
            parser.error("internal probe arguments invalid")
        result = write_probe(Path(args.probe_args[0]),
                             negative_child_mount=args.negative_child_mount)
        print(json.dumps(result, sort_keys=True))
        return 0 if result["status"] == "pass" else 1

    if os.geteuid() == 0:
        parser.error("run as an ordinary user; the script invokes one transient sudo systemd unit")
    if not shutil.which("systemd-run") or not shutil.which("sudo"):
        parser.error("systemd-run and sudo are required for the disposable namespace test")
    SYNTHETIC_BASE.mkdir(mode=0o755, parents=True, exist_ok=True)
    # Create a unique disposable root directly under the approved temp area.
    root = Path(tempfile.mkdtemp(prefix="steam-ownership-", dir=SYNTHETIC_BASE))
    library = root / "home" / "steam" / "steamapps"
    (library / "common" / "synthetic-game").mkdir(parents=True)
    (library / "downloading" / "424242").mkdir(parents=True)
    for name in ("shadercache/424242", "compatdata/424242/pfx"):
        (library / name).mkdir(parents=True)
    (library / "common/synthetic-game/payload.dat").write_text("fixture-content", encoding="utf-8")
    (library / "appmanifest_424242.acf").write_text('"StateFlags" "4"\n', encoding="utf-8")
    (library / "downloading/424242/payload.dat").write_text("fixture-stage", encoding="utf-8")
    (library / "common/alias.dat").symlink_to(library / "common/synthetic-game/payload.dat")
    outside = root / "outside-writable.dat"
    outside.write_text("external fixture", encoding="utf-8")
    (library / "common/external-alias.dat").symlink_to(outside)
    unit = f"steam-ownership-prototype-{uuid.uuid4().hex[:10]}.service"
    command = [
        "sudo", "-n", "systemd-run", "--quiet", "--wait", "--pipe", "--collect",
        f"--unit={unit}", "--property=Type=oneshot", f"--property=User={os.environ.get('USER', 'nobody')}",
        "--property=ProtectSystem=strict",
        f"--property=BindReadOnlyPaths={library}:{library}",
        f"--property=TemporaryFileSystem={library / 'shadercache'}:rw,mode=0755,uid={os.getuid()},gid={os.getgid()}",
        f"--property=TemporaryFileSystem={library / 'compatdata'}:rw,mode=0755,uid={os.getuid()},gid={os.getgid()}",
    ]
    if args.negative_child_mount:
        command.append(f"--property=BindPaths={library / 'downloading'}:{library / 'downloading'}")
    command.extend([
        sys.executable,
        str(Path(__file__).resolve()), "--probe", str(root / "home/steam"),
    ])
    if args.negative_child_mount:
        command.insert(command.index("--probe"), "--negative-child-mount")
    try:
        completed = subprocess.run(command, capture_output=True, text=True, check=False, timeout=40)
        try:
            report = json.loads(completed.stdout.strip())
        except json.JSONDecodeError:
            report = {"probe_output": completed.stdout.strip()}
        payload = library / "common/synthetic-game/payload.dat"
        host_write = False
        if payload.exists() and payload.read_text(encoding="utf-8") == "fixture-content":
            # This process remains in the caller's host namespace, outside the
            # transient systemd unit, and mutates the same file after the
            # restricted Steam-side process has exited.
            payload.write_text("host-acquisition", encoding="utf-8")
            host_write = payload.read_text(encoding="utf-8") == "host-acquisition"
        report.update({"unit": unit, "synthetic_root": str(root),
                       "command_status": completed.returncode,
                       "host_acquisition_write_succeeds": host_write,
                       "host_mount_namespace": os.readlink("/proc/self/ns/mnt"),
                       "stderr": completed.stderr.strip()})
        report["status"] = "pass" if completed.returncode == 0 and host_write else "fail"
        print(json.dumps(report, sort_keys=True))
        return 0 if report["status"] == "pass" else 1
    finally:
        # Best-effort cleanup is restricted to this unique transient unit and
        # exact fixture directory created above.
        subprocess.run(["sudo", "-n", "systemctl", "stop", unit],
                       capture_output=True, check=False)
        subprocess.run(["sudo", "-n", "systemctl", "reset-failed", unit],
                       capture_output=True, check=False)
        if not args.keep_synthetic and root.parent.resolve() == SYNTHETIC_BASE.resolve():
            shutil.rmtree(root)


if __name__ == "__main__":
    raise SystemExit(main())
