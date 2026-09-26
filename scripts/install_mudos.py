#!/usr/bin/env python3
"""Canonical immutable Mudos install, verification, and ownership-aware removal."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path, PurePosixPath
import platform
import shutil
import subprocess
import sys
from datetime import datetime, timezone


class InstallError(RuntimeError):
    pass


def load_manifest(path: Path) -> dict:
    data = json.loads(path.read_text())
    if data.get("schema") != 1:
        raise InstallError("unsupported ownership manifest schema")
    paths: list[str] = []
    paths.extend(data["immutable"]["application_roots"])
    paths.extend([data["immutable"]["release_root"], data["immutable"]["selector"]])
    paths.extend(data["system_integration"]["systemd_files"])
    paths.extend(data["system_integration"]["system_files"])
    paths.extend(data["mutable"]["exact_paths"])
    paths.extend(entry["path"] for entry in data["mutable"].get("initial_directories", []))
    for raw in paths:
        path_obj = PurePosixPath(raw)
        if not path_obj.is_absolute() or ".." in path_obj.parts or raw == "/":
            raise InstallError(f"unsafe ownership path: {raw}")
        if raw in data.get("protected", []) and raw in data["mutable"]["exact_paths"]:
            raise InstallError(f"protected path appears in owned paths: {raw}")
    for raw in data["system_integration"].get("patterns", []):
        path_obj = PurePosixPath(raw)
        if (not path_obj.is_absolute() or ".." in path_obj.parts
                or path_obj.parent != PurePosixPath("/etc/inputplumber/devices.d")
                or not path_obj.name.startswith("lulu-gamepad-event")
                or not path_obj.name.endswith(".yaml")):
            raise InstallError(f"unsafe owned path pattern: {raw}")
    mutable = data["mutable"]["exact_paths"]
    for left in mutable:
        for right in mutable:
            if left != right and PurePosixPath(left) in PurePosixPath(right).parents:
                raise InstallError(f"overlapping mutable ownership paths: {left} and {right}")
    for entry in data["mutable"].get("initial_directories", []):
        if entry.get("owner") not in {"lulu", "root"}:
            raise InstallError("initial directory owner must be lulu or root")
        try:
            mode = int(entry["mode"], 8)
        except (KeyError, ValueError) as exc:
            raise InstallError("initial directory has invalid mode") from exc
        if mode & 0o002:
            raise InstallError("initial directory must not be world-writable")
    return data


def run(args: list[str], *, check: bool = True, capture: bool = False) -> subprocess.CompletedProcess:
    return subprocess.run(args, check=check, text=True, capture_output=capture)


def host_mount_state(mount: dict) -> str | None:
    """Return active state only for the exact fstab-generated Steam bind mount."""
    result = run(["systemctl", "show", mount["unit"],
                  "--property=FragmentPath,SourcePath,Where,ActiveState"],
                 check=False, capture=True)
    if result.returncode != 0:
        return None
    fields = dict(line.split("=", 1) for line in result.stdout.splitlines() if "=" in line)
    if not fields.get("FragmentPath"):
        return None
    unit_text = run(["systemctl", "cat", mount["unit"]], check=False, capture=True).stdout
    unit_fields = dict(line.strip().split("=", 1) for line in unit_text.splitlines()
                       if line.strip().startswith(("What=", "Where=")) and "=" in line)
    if (not fields.get("FragmentPath", "").startswith("/run/systemd/generator/")
            or fields.get("SourcePath") != "/etc/fstab"
            or unit_fields.get("What") != mount["source"]
            or fields.get("Where") != mount["target"]
            or unit_fields.get("Where") != mount["target"]):
        raise InstallError(f"refusing to alter non-matching host mount {mount['unit']}")
    return fields.get("ActiveState", "inactive")


def copy_if_absent(source: Path, destination: Path, *, uid: int | None = None,
                   gid: int | None = None, mode: int | None = None) -> bool:
    """Initialize mutable configuration once; never reset operator state."""
    if destination.exists() or destination.is_symlink():
        return False
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    if uid is not None and gid is not None:
        os.chown(destination, uid, gid)
    if mode is not None:
        destination.chmod(mode)
    return True


def existing_release(release_root: Path, revision: str) -> Path | None:
    """Reuse a previously built immutable release for this exact source SHA."""
    for candidate in sorted(release_root.glob(f"{revision[:7]}-candidate-*"), reverse=True):
        metadata = candidate / "RELEASE"
        if candidate.is_symlink() or not candidate.is_dir() or not metadata.is_file():
            continue
        fields = dict(line.split("=", 1) for line in metadata.read_text().splitlines() if "=" in line)
        if fields.get("revision") == revision and fields.get("status") == "clean" and fields.get("immutable") == "true":
            return candidate
    return None


def packages_to_install(packages: list[str], alternatives: dict[str, list[str]],
                        installed=None) -> list[str]:
    """Avoid replacing an already installed compatible package variant."""
    installed = installed or (lambda name: run(["pacman", "-Q", name], check=False,
                                               capture=True).returncode == 0)
    result = []
    for package in packages:
        if installed(package):
            continue
        if any(installed(alternative) for alternative in alternatives.get(package, [])):
            continue
        result.append(package)
    return result


def source_revision(repo: Path) -> tuple[str, str]:
    sha = run(["git", "-C", str(repo), "rev-parse", "HEAD"], capture=True).stdout.strip()
    branch = run(["git", "-C", str(repo), "branch", "--show-current"], capture=True).stdout.strip()
    dirty = run(["git", "-C", str(repo), "status", "--porcelain", "--untracked-files=all"], capture=True).stdout
    if dirty:
        raise InstallError("source checkout is dirty; commit changes before production installation")
    return sha, branch


def mutable_paths(manifest: dict, lulu_home: Path = Path("/home/lulu")) -> list[Path]:
    """Resolve configured game/emulation storage using MudosPaths semantics."""
    paths = [Path(p) for p in manifest["mutable"]["exact_paths"]]
    config = lulu_home / ".config/lulu/storage-targets.json"
    try:
        state = json.loads(config.read_text())
    except (OSError, ValueError):
        return paths
    protected = [Path(p) for p in manifest["protected"]]
    for key in ("game_path", "emulation_path"):
        value = state.get(key)
        if not value:
            continue
        base = Path(value)
        if not base.is_absolute() or ".." in base.parts or len(base.parts) < 3:
            raise InstallError(f"unsafe configured {key}; refusing to purge storage")
        mudos_root = base / "Mudos"
        if mudos_root == Path("/") or any(mudos_root == item or item in mudos_root.parents
                                             or mudos_root in item.parents for item in protected):
            raise InstallError(f"configured {key} overlaps protected storage")
        paths.extend(mudos_root / child for child in ("ROMs", "BIOS", "Executables", ".acquisition"))
    return list(dict.fromkeys(paths))


def storage_roots(manifest: dict, lulu_home: Path = Path("/home/lulu")) -> list[Path]:
    """Return the active game-storage roots using the runtime path policy."""
    state_path = lulu_home / ".config/lulu/storage-targets.json"
    roots = {lulu_home / "Games"}
    try:
        state = json.loads(state_path.read_text())
    except (OSError, ValueError):
        state = {}
    for key in ("game_path", "emulation_path"):
        value = state.get(key)
        if not value:
            continue
        base = Path(value)
        if not base.is_absolute() or ".." in base.parts or len(base.parts) < 3:
            raise InstallError(f"unsafe configured {key}; refusing to initialize storage")
        roots.add(base / "Mudos")
    return sorted(roots)


def validate_configured_storage_targets(manifest: dict,
                                       lulu_home: Path = Path("/home/lulu")) -> None:
    """Never initialize configured game trees on an absent mountpoint."""
    state_path = lulu_home / ".config/lulu/storage-targets.json"
    try:
        state = json.loads(state_path.read_text())
    except (OSError, ValueError):
        return
    if not isinstance(state, dict):
        raise InstallError("configured storage target state is not an object")
    protected = [Path(item).resolve(strict=False) for item in manifest["protected"]]
    for key in ("game_path", "emulation_path"):
        raw = state.get(key)
        if not raw:
            continue
        target = Path(str(raw))
        if not target.is_absolute() or ".." in target.parts or len(target.parts) < 3:
            raise InstallError(f"unsafe configured {key}; refusing to initialize storage")
        resolved = target.resolve(strict=False)
        if any(resolved == item or resolved in item.parents or item in resolved.parents
               for item in protected):
            raise InstallError(f"configured {key} overlaps protected storage")
        if target.is_symlink() or not target.is_dir() or not os.path.ismount(target):
            raise InstallError(f"configured {key} is unavailable; connect and mount the selected storage")


def acquisition_directories(manifest: dict, lulu_home: Path = Path("/home/lulu")) -> list[Path]:
    return [root / ".acquisition" / provider
            for root in storage_roots(manifest, lulu_home)
            for provider in ("torrents", "usenet")]


def initialize_acquisition_directories(paths: list[Path], *, uid: int = 958,
                                       gid: int = 958, mode: int = 0o770) -> None:
    """Create the provider-owned leaves without changing their storage parents."""
    for path in paths:
        path.mkdir(parents=True, exist_ok=True)
        os.chown(path, uid, gid)
        path.chmod(mode)


def provider_install_writable_paths(manifest: dict,
                                    lulu_home: Path = Path("/home/lulu")) -> list[Path]:
    """Systemd write exceptions are limited to acquisition parents in use."""
    return sorted({path.parent for path in acquisition_directories(manifest, lulu_home)})


def integration_paths(manifest: dict) -> list[Path]:
    owned = manifest["system_integration"]
    paths = [Path(p) for p in [*owned["systemd_files"], *owned["system_files"]]]
    for pattern in owned.get("patterns", []):
        path = Path(pattern)
        paths.extend(sorted(path.parent.glob(path.name)))
    return paths


def safe_remove(path: Path, repo: Path, protected: list[str]) -> None:
    absolute = Path(os.path.abspath(path))
    forbidden = [Path(p) for p in protected]
    forbidden.append(repo.resolve())
    for item in forbidden:
        if absolute == item or item in absolute.parents or absolute in item.parents:
            raise InstallError(f"refusing to remove protected path: {absolute}")
    if any(parent.is_symlink() for parent in absolute.parents):
        raise InstallError(f"refusing to remove through symlinked parent: {absolute}")
    # Never follow a symlink from an ownership boundary.
    if absolute.is_symlink() or absolute.is_file():
        absolute.unlink(missing_ok=True)
    elif absolute.is_dir():
        shutil.rmtree(absolute)


def preflight() -> None:
    if platform.system() != "Linux" or not Path("/etc/arch-release").exists():
        raise InstallError("supported base is CachyOS/Arch Linux (detected system is unsupported)")
    if shutil.which("pacman") is None:
        raise InstallError("pacman is required for CachyOS dependency provisioning")


def ensure_account(manifest: dict, *, apply: bool) -> None:
    account = manifest["account"]
    result = run(["getent", "passwd", account["name"]], check=False, capture=True)
    if result.returncode == 0:
        fields = result.stdout.strip().split(":")
        if int(fields[2]) != account["uid"] or int(fields[3]) != account["gid"] or fields[5] != account["home"]:
            raise InstallError("existing lulu account conflicts with the supported UID/GID/home contract")
        if run(["getent", "group", "seat"], check=False, capture=True).returncode == 0:
            groups = run(["id", "-Gn", "lulu"], capture=True).stdout.split()
            if "seat" not in groups and apply:
                run(["usermod", "--append", "--groups", "seat", "lulu"])
        return
    uid_owner = run(["getent", "passwd", str(account["uid"])], check=False, capture=True)
    if uid_owner.returncode == 0:
        raise InstallError("required lulu UID 958 is already owned by another account")
    if not apply:
        print("would create lulu user/group (uid/gid 958)")
        return
    group = run(["getent", "group", str(account["gid"])], check=False, capture=True)
    if group.returncode == 0 and group.stdout.split(":", 1)[0] != "lulu":
        raise InstallError("required lulu GID 958 is already owned by another group")
    if group.returncode != 0:
        run(["groupadd", "--system", "--gid", str(account["gid"]), "lulu"])
    run(["useradd", "--system", "--uid", str(account["uid"]), "--gid", str(account["gid"]),
         "--home-dir", account["home"], "--create-home", "--shell", "/usr/bin/nologin", "lulu"])
    if run(["getent", "group", "seat"], check=False, capture=True).returncode == 0:
        run(["usermod", "--append", "--groups", "seat", "lulu"])


def plan(repo: Path, manifest: dict, action: str, *, purge: bool = False) -> list[str]:
    if action == "install":
        sha, _ = source_revision(repo)
        return [f"build and verify immutable release from {sha}", "atomically select /opt/lulu/current",
                "install only missing shared pacman dependencies",
                "install manifest-owned system integration", "initialize writable directories without overwriting state",
                "enable/start Mudos core and Recovery services; leave OOBE incomplete"]
    if action == "uninstall":
        return ["stop and disable owned Mudos services", "remove manifest-owned system integration",
                *[f"remove system-owned path {p}" for p in integration_paths(manifest)],
                "remove owned /opt/lulu/{bin,lib,ui,config,scripts} compatibility symlinks",
                "remove /opt/lulu/current selector only", "preserve immutable releases and all mutable user data"]
    if action == "purge":
        if not purge:
            raise InstallError("purge requires the explicit --purge-user-data flag")
        staging = sorted(Path(manifest["developer_runtime"]["staging_prefix"]).parent.glob(
            Path(manifest["developer_runtime"]["staging_prefix"]).name + "*"))
        return ["stop and disable owned Mudos services", "remove manifest-owned system integration",
                *[f"stop (preserve host fstab entry for) {mount['unit']}"
                  for mount in manifest.get("preserved_host_mounts", [])],
                *[f"remove system-owned path {p}" for p in integration_paths(manifest)],
                "remove owned /opt/lulu/{bin,lib,ui,config,scripts} compatibility symlinks",
                "remove /opt/lulu/current selector only", *[f"remove mutable owned path {p}" for p in mutable_paths(manifest)],
                f"remove developer runtime {manifest['developer_runtime']['path']}",
                *[f"remove disposable dev staging path {p}" for p in staging]]
    raise InstallError(f"unsupported action: {action}")


def stop_services(apply: bool, manifest: dict, *, stop_host_mounts: bool) -> None:
    units = ["lulu.target", "lulu-session@2.service", "lulu-admin.service", "lulu-consoled.service",
             "lulu-acquisition.service", "mudos-recovery.service", "mudos-recovery-ui.service",
             "lulu-transmission.service", "lulu-questarr.service", "lulu-questarr-reconcile.service",
             "nzbget.service", "lulu-file-browser.service"]
    for unit in units:
        if apply:
            run(["systemctl", "disable", "--now", unit], check=False)
        else:
            print(f"would stop/disable {unit}")
    if apply:
        run(["runuser", "-u", "lulu", "--", "env", "XDG_RUNTIME_DIR=/run/user/958",
             "DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/958/bus", "systemctl", "--user",
             "disable", "--now", "lulu-sunshine-dev.service"], check=False)
        for mount in (manifest.get("preserved_host_mounts", []) if stop_host_mounts else []):
            if host_mount_state(mount) is not None:
                run(["systemctl", "stop", mount["unit"]])
    else:
        for mount in (manifest.get("preserved_host_mounts", []) if stop_host_mounts else []):
            print(f"would stop (preserve host fstab entry for) {mount['unit']}")


def install_integration(repo: Path, release: Path, manifest: dict,
                       *, session_was_active: bool = False) -> None:
    root = Path("/")
    packaging = release / "packaging"
    systemd = {
        "lulu.target": "lulu.target", "lulu-session@.service": "lulu-session@.service",
        "lulu-consoled.service": "lulu-consoled.service", "lulu-acquisition.service": "lulu-acquisition.service",
        "mudos-recovery.service": "mudos-recovery.service", "mudos-recovery-guard.service": "mudos-recovery-guard.service",
        "mudos-recovery-ui.service": "mudos-recovery-ui.service", "lulu-inputplumber-hotplug.service": "lulu-inputplumber-hotplug.service",
        "lulu-osk@.service": "lulu-osk@.service", "lulu-file-browser.service": "lulu-file-browser.service",
        "lulu-transmission-config.service": "lulu-transmission-config.service",
        "lulu-questarr-reconcile.service": "lulu-questarr-reconcile.service",
    }
    for source, target in systemd.items():
        text = (packaging / source).read_text()
        dest = root / "etc/systemd/system" / target
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(text)
        dest.chmod(0o644)
    # The provider installer may write only to each active Mudos acquisition
    # subtree. Keep the target-specific exception explicit and ownership-scoped.
    storage_dropin = Path("/etc/systemd/system/lulu-provider-install@.service.d/storage.conf")
    storage_dropin.parent.mkdir(parents=True, exist_ok=True)
    writable = [str(path) for path in provider_install_writable_paths(manifest)]
    storage_dropin.write_text("[Service]\nReadWritePaths=" + " ".join(writable) + "\n")
    storage_dropin.chmod(0o644)
    # Existing development refresh drop-ins override immutable service paths;
    # they are listed as Mudos-owned integration and must not survive install.
    for raw in manifest["system_integration"]["systemd_files"]:
        if raw.endswith(("/dev-runtime.conf", "/dev-validation.conf")):
            Path(raw).unlink(missing_ok=True)
    # Admin provisioner is authoritative for recovery token creation, admin/helper
    # files, policy rules, Avahi, and service activation. Runtime points at current.
    run(["bash", str(Path("/opt/lulu/current/scripts/provision-admin.sh"))], check=True)
    # Copy owned support files which the admin provisioner intentionally does not own.
    copies = {
        "packaging/lulu-session.pam": "/etc/pam.d/lulu-session",
        "packaging/presentation.conf": "/etc/lulu/presentation.conf",
        "packaging/tmpfiles.d/lulu.conf": "/etc/tmpfiles.d/lulu.conf",
        "packaging/udev/80-lulu-osk.rules": "/etc/udev/rules.d/80-lulu-osk.rules",
        "packaging/udev/81-lulu-gamepad-hotplug.rules": "/etc/udev/rules.d/81-lulu-gamepad-hotplug.rules",
        "config/inputplumber/devices/lulu-composite.yaml": "/etc/inputplumber/devices.d/lulu-composite.yaml",
        "packaging/inputplumber-restart.conf": "/etc/systemd/system/inputplumber.service.d/lulu.conf",
    }
    for source, target in copies.items():
        src = release / source
        if not src.is_file():
            continue
        dest = Path(target)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
        dest.chmod(0o644)
    rules = packaging / "polkit-1/rules.d"
    owned_rules = {Path(raw).name for raw in manifest["system_integration"]["system_files"]
                   if "/polkit-1/rules.d/" in raw}
    for source in sorted(rules.glob("*.rules")):
        if source.name not in owned_rules:
            continue
        dest = Path("/etc/polkit-1/rules.d") / source.name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, dest)
        dest.chmod(0o644)
    # Persistent user directories and first-run baseline; never overwrite state.
    for entry in manifest["mutable"]["initial_directories"]:
        path = Path(entry["path"])
        path.mkdir(parents=True, exist_ok=True)
        os.chown(path, 958, 958)
        path.chmod(int(entry["mode"], 8))
    # Downloader services mount these paths even before the optional provider
    # is configured. Initialize only the Mudos-owned acquisition leaves.
    initialize_acquisition_directories(acquisition_directories(manifest))
    template = release / "config/provider-services.toml.example"
    target = Path("/home/lulu/.config/lulu/provider-services.toml")
    if template.is_file():
        copy_if_absent(template, target, uid=958, gid=958, mode=0o640)
    # Install executable scripts/provider helper are in release; verify service
    # environments refer solely to the immutable current selector.
    run(["systemctl", "daemon-reload"])
    run(["udevadm", "control", "--reload-rules"], check=False)
    run(["systemd-tmpfiles", "--create", "/etc/tmpfiles.d/lulu.conf"])
    for mount in manifest.get("preserved_host_mounts", []):
        if host_mount_state(mount) is not None:
            run(["systemctl", "start", mount["unit"]])
    for unit in ("lulu.target", "lulu-admin.service", "mudos-recovery.service"):
        run(["systemctl", "enable", unit])
    run(["systemctl", "enable", "lulu-session@2.service"])
    run(["systemctl", "enable", "seatd.service"])
    run(["systemctl", "enable", "inputplumber.service"])
    run(["systemctl", "start", "mudos-recovery.service"])
    run(["systemctl", "start", "lulu-admin.service"])
    start_runtime(session_was_active=session_was_active)


def start_runtime(*, session_was_active: bool) -> None:
    # The supported installation ends at the genuine shell first-run route.
    run(["systemctl", "start", "lulu.target"])
    if session_was_active:
        # `start lulu.target` does not replace an already-running shell after
        # /opt/lulu/current changes. Restart only an existing session so its
        # sessiond, Consoled and Acquisitiond processes all reload the selected
        # immutable release; a fresh install still starts the target once.
        run(["systemctl", "restart", "lulu-session@2.service"])


def do_install(repo: Path, manifest: dict, dry_run: bool) -> None:
    preflight()
    sha, branch = source_revision(repo)
    print(f"source {sha} ({branch})")
    if dry_run:
        for item in plan(repo, manifest, "install"):
            print("would " + item)
        return
    if os.geteuid() != 0:
        raise InstallError("installation needs root; rerun as root or with sudo")
    validate_configured_storage_targets(manifest)
    session_was_active = (run(["systemctl", "is-active", "lulu-session@2.service"],
                              check=False, capture=True).returncode == 0)
    dependency = manifest["shared_dependencies"]
    packages = packages_to_install(dependency["packages"], dependency.get("alternatives", {}))
    if packages:
        run(["pacman", "-S", "--needed", "--noconfirm", *packages])
    run(["systemctl", "enable", "--now", "bluetooth.service"])
    ensure_account(manifest, apply=True)
    root = Path("/opt/lulu")
    root.mkdir(parents=True, exist_ok=True)
    release = existing_release(root / "releases", sha)
    if release is None:
        release = root / "releases" / f"{sha[:7]}-candidate-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
        run([sys.executable, str(repo / "scripts/release.py"), "build", "--repo-root", str(repo), "--release-dir", str(release)])
    run([sys.executable, str(repo / "scripts/release.py"), "verify", "--release-dir", str(release)])
    run([sys.executable, str(repo / "scripts/release.py"), "activate", "--release-dir", str(release)])
    for raw in manifest["immutable"]["application_roots"]:
        alias = Path(raw)
        component = alias.name
        expected = f"current/{component}"
        if alias.exists() and not alias.is_symlink():
            raise InstallError(f"refusing to replace non-symlink compatibility path: {alias}")
        if alias.is_symlink() and os.readlink(alias) != expected:
            alias.unlink()
        if not alias.is_symlink():
            alias.symlink_to(expected)
    # The on-screen keyboard is required for controller-driven OOBE. Reuse
    # the checksum-pinned canonical provisioner and keep its output mutable.
    run(["bash", str(release / "scripts/provision-gamepad-osk.sh")])
    # DUFS is a core appliance service; provision its package and private
    # authentication configuration on every canonical installation.
    run(["bash", str(repo / "scripts/provision-dufs.sh")])
    # Release creation must not depend on mutable paths; install only from current.
    install_integration(repo, release, manifest, session_was_active=session_was_active)
    print(f"installed immutable release {release} from {sha}")


def remove_owned(repo: Path, manifest: dict, *, purge: bool, dry_run: bool) -> None:
    if not dry_run and os.geteuid() != 0:
        raise InstallError("uninstall/purge needs root; rerun as root or with sudo")
    # Resolve ownership against an actually mounted configured target. Without
    # this guard, a missing removable disk could make purge delete a stale
    # <mountpoint>/Mudos tree on the system disk instead.
    if purge:
        validate_configured_storage_targets(manifest)
    for item in plan(repo, manifest, "purge" if purge else "uninstall", purge=purge):
        print(item)
    stop_services(not dry_run, manifest, stop_host_mounts=purge)
    if dry_run:
        return
    owned = manifest["system_integration"]
    for path in integration_paths(manifest):
        safe_remove(path, repo, manifest["protected"])
    for raw in manifest["immutable"]["application_roots"]:
        alias = Path(raw)
        if alias.is_symlink() and os.readlink(alias) == f"current/{alias.name}":
            alias.unlink()
    selector = Path(manifest["immutable"]["selector"])
    if selector.is_symlink():
        selector.unlink()
    if purge:
        for path in mutable_paths(manifest):
            safe_remove(path, repo, manifest["protected"])
        safe_remove(Path(manifest["developer_runtime"]["path"]), repo, manifest["protected"])
        staging_prefix = Path(manifest["developer_runtime"]["staging_prefix"])
        for staging in staging_prefix.parent.glob(staging_prefix.name + "*"):
            safe_remove(staging, repo, manifest["protected"])
    run(["systemctl", "daemon-reload"], check=False)


def verify(repo: Path, manifest: dict) -> None:
    source_sha, _branch = source_revision(repo)
    selector = Path(manifest["immutable"]["selector"])
    if not selector.is_symlink():
        raise InstallError("/opt/lulu/current is not an immutable release selector")
    release = selector.resolve(strict=True)
    release_root = Path(manifest["immutable"]["release_root"]).resolve(strict=False)
    if release.parent != release_root:
        raise InstallError("selected runtime is not a direct immutable release")
    for raw in manifest["immutable"]["application_roots"]:
        alias = Path(raw)
        if not alias.is_symlink() or os.readlink(alias) != f"current/{alias.name}":
            raise InstallError(f"missing immutable compatibility selector: {alias}")
    run([sys.executable, str(repo / "scripts/release.py"), "verify", "--release-dir", str(release)])
    provenance = release / "RELEASE"
    metadata = provenance.read_text()
    if "status=clean" not in metadata or "immutable=true" not in metadata:
        raise InstallError("selected release lacks clean immutable provenance")
    release_revision = next((line.partition("=")[2] for line in metadata.splitlines()
                             if line.startswith("revision=")), "")
    if release_revision != source_sha:
        raise InstallError("selected immutable release does not match the clean source checkout")
    if shutil.which("dufs") is None:
        raise InstallError("core DUFS file manager package is not installed")
    for package in ("bluez", "bluez-utils"):
        if run(["pacman", "-Q", package], check=False, capture=True).returncode:
            raise InstallError(f"required Bluetooth package is not installed: {package}")
    if run(["systemctl", "is-enabled", "bluetooth.service"], check=False, capture=True).returncode \
            or run(["systemctl", "is-active", "bluetooth.service"], check=False, capture=True).returncode:
        raise InstallError("BlueZ Bluetooth service is not enabled and active")
    file_browser_config = Path("/etc/lulu/file-browser.env")
    if not file_browser_config.is_file():
        raise InstallError("core DUFS file manager configuration is missing")
    config_stat = file_browser_config.stat()
    if (config_stat.st_uid, config_stat.st_gid, config_stat.st_mode & 0o777) != (0, 0, 0o600):
        raise InstallError("core DUFS file manager configuration has unsafe ownership or mode")
    # These units are required on every supported installation and are copied
    # from the selected release without host-specific transformations.
    required_units = ("lulu.target", "lulu-session@.service", "lulu-consoled.service",
                      "lulu-acquisition.service", "lulu-admin.service",
                      "lulu-provider-install@.service", "mudos-recovery.service",
                      "mudos-recovery-guard.service", "mudos-recovery-ui.service",
                      "lulu-inputplumber-hotplug.service", "lulu-osk@.service",
                      "lulu-questarr-reconcile.service",
                      "lulu-file-browser.service", "lulu-transmission-config.service")
    for unit in required_units:
        installed = Path("/etc/systemd/system") / unit
        packaged = release / "packaging" / unit
        if not installed.is_file() or not packaged.is_file() \
                or installed.read_bytes() != packaged.read_bytes():
            raise InstallError(f"production service does not match the selected release: {unit}")
    target_link = Path("/etc/systemd/system/multi-user.target.wants/lulu.target")
    if not target_link.is_symlink() or os.readlink(target_link) != "/etc/systemd/system/lulu.target":
        raise InstallError("Lulu appliance target is not enabled for boot")
    for raw in manifest["system_integration"]["systemd_files"]:
        path = Path(raw)
        if path.is_file() and "/opt/lulu/dev-current" in path.read_text():
            raise InstallError(f"production service references development runtime: {path.name}")
    for path in acquisition_directories(manifest):
        if not path.is_dir():
            raise InstallError(f"missing required acquisition directory: {path}")
        stat = path.stat()
        if (stat.st_uid, stat.st_gid, stat.st_mode & 0o777) != (958, 958, 0o770):
            raise InstallError(f"incorrect owner/mode for acquisition directory: {path}")
    validate_configured_storage_targets(manifest)
    writable = " ".join(str(path) for path in provider_install_writable_paths(manifest))
    dropin = Path("/etc/systemd/system/lulu-provider-install@.service.d/storage.conf")
    expected_dropin = "[Service]\nReadWritePaths=" + writable + "\n"
    if not dropin.is_file() or dropin.read_text() != expected_dropin:
        raise InstallError("provider installer storage write paths do not match configured acquisition roots")
    for mount in manifest.get("preserved_host_mounts", []):
        state = host_mount_state(mount)
        if state is not None and state != "active":
            raise InstallError(f"preserved Steam bind mount is not active: {mount['unit']}")
    print(f"verified immutable production runtime {release}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--uninstall", action="store_true")
    parser.add_argument("--purge-user-data", action="store_true")
    args = parser.parse_args()
    try:
        repo = args.repo_root.resolve()
        manifest = load_manifest(repo / "packaging/mudos-ownership.json")
        if os.geteuid() != 0 and not args.dry_run and not args.verify:
            sudo = shutil.which("sudo")
            if not sudo:
                raise InstallError("sudo is required for installation/removal")
            os.execv(sudo, [sudo, sys.executable, str(Path(__file__).resolve()),
                            "--repo-root", str(repo), *sys.argv[1:]])
        if args.verify:
            verify(repo, manifest)
        elif args.uninstall or args.purge_user_data:
            remove_owned(repo, manifest, purge=args.purge_user_data, dry_run=args.dry_run)
        else:
            do_install(repo, manifest, args.dry_run)
    except (InstallError, OSError, subprocess.CalledProcessError, json.JSONDecodeError) as exc:
        print(f"Mudos installer: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
