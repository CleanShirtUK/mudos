import importlib.util
import json
from pathlib import Path
import subprocess
import stat
from types import SimpleNamespace
from unittest.mock import patch

import pytest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("install_mudos", ROOT / "scripts/install_mudos.py")
installer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(installer)


def manifest():
    return installer.load_manifest(ROOT / "packaging/mudos-ownership.json")


def test_ownership_manifest_separates_release_state_and_shared_packages():
    data = manifest()
    assert data["immutable"]["selector"] == "/opt/lulu/current"
    assert "/home/lulu/.config/lulu" in data["mutable"]["exact_paths"]
    assert all(int(entry["mode"], 8) & 0o002 == 0 for entry in data["mutable"]["initial_directories"])
    assert all("/home/" not in item for item in data["protected"])
    assert "packages" in data["shared_dependencies"]
    assert not any("/opt/lulu/dev-current" in path for path in data["immutable"].values()
                   if isinstance(path, str))


def test_retired_service_names_are_cleanup_only_and_retired_data_is_not_owned():
    data = manifest()
    retired = data["system_integration"]["retired_systemd_units"]
    assert retired
    assert not set(retired).intersection(installer.SYSTEMD_UNITS)
    assert not any("questarr" in path for path in data["mutable"]["exact_paths"])
    assert all(path not in data["system_integration"]["systemd_files"] for path in
               data["system_integration"]["retired_exact_paths"])


def test_retired_service_cleanup_preserves_component_data(tmp_path, monkeypatch):
    unit_file = tmp_path / "old.service"
    polkit_file = tmp_path / "old.rules"
    application_data = tmp_path / "application-data"
    unit_file.write_text("old unit")
    polkit_file.write_text("old policy")
    application_data.mkdir()
    (application_data / "state.db").write_text("keep")
    calls = []
    monkeypatch.setattr(installer, "run", lambda args, **kwargs: calls.append((args, kwargs)))
    installer.retire_compatibility_integration({"system_integration": {
        "retired_systemd_units": ["old.service"],
        "retired_exact_paths": [str(unit_file), str(polkit_file)],
    }})
    assert not unit_file.exists()
    assert not polkit_file.exists()
    assert (application_data / "state.db").read_text() == "keep"
    assert calls[0][0] == ["systemctl", "disable", "--now", "old.service"]
    assert calls[-1][0] == ["systemctl", "daemon-reload"]


def test_session_service_does_not_order_shell_after_resident_steam():
    unit = (ROOT / "packaging/lulu-session@.service").read_text()
    runtime = (ROOT / "packaging/lulu-steam-runtime.service").read_text()
    after = next(line for line in unit.splitlines() if line.startswith("After="))
    assert "lulu-steam-runtime.service" not in after
    assert "lulu-steam-runtime.service" in next(
        line for line in unit.splitlines() if line.startswith("Wants="))
    assert "PartOf=lulu-session@2.service" in runtime
    assert "Restart=always" in runtime
    assert "TimeoutStartSec=180s" in runtime


def test_release_installs_a_readiness_driven_plymouth_handoff():
    unit = (ROOT / "packaging/mudos-startup-surface.service").read_text()
    quit_dropin = (ROOT / "packaging/plymouth-quit.service.d/mudos-handoff.conf").read_text()
    assert "TimeoutStartSec=120s" in unit
    assert "wait-startup-surface.py" in unit
    assert "Wants=mudos-startup-surface.service" in quit_dropin
    assert "After=mudos-startup-surface.service" in quit_dropin
    script = (ROOT / "scripts/wait-startup-surface.py").read_text()
    assert "inotify_init1" in script
    assert "time.sleep" not in script
    target = (ROOT / "packaging/lulu.target").read_text()
    assert "Before=multi-user.target" in target
    assert "After=multi-user.target" not in target


def test_update_plan_includes_post_activation_startup_host_integration(monkeypatch):
    monkeypatch.setattr(installer, "source_revision", lambda _repo: ("a" * 40, "test"))
    update_plan = installer.plan(ROOT, manifest(), "update")
    assert any("systemd, Plymouth theme/handoff and Limine hook" in item for item in update_plan)
    assert any("Limine default and rebuild initramfs" in item for item in update_plan)


def test_startup_integration_copies_host_assets_and_runs_boot_generators(tmp_path, monkeypatch):
    release = tmp_path / "release"
    for relative in (*installer.STARTUP_INTEGRATION_FILES,
                     *(f"packaging/plymouth/themes/mudos/{name}"
                       for name in installer.PLYMOUTH_THEME_FILES),
                     "scripts/configure-mudos-limine.py"):
        source = release / relative
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text(f"asset:{relative}\n")

    destinations = {
        source: tmp_path / "etc" / Path(target).relative_to("/")
        for source, target in installer.STARTUP_INTEGRATION_FILES.items()
    }
    theme_root = tmp_path / "usr/share/plymouth/themes/mudos"
    monkeypatch.setattr(installer, "STARTUP_INTEGRATION_FILES", destinations)
    monkeypatch.setattr(installer, "PLYMOUTH_THEME_ROOT", theme_root)
    calls = []
    monkeypatch.setattr(installer, "run", lambda args, **kwargs: calls.append((args, kwargs)))
    verified = []
    monkeypatch.setattr(installer, "verify_startup_integration", lambda selected: verified.append(selected))

    installer.install_startup_integration(release)

    for source, destination in destinations.items():
        assert destination.read_text() == f"asset:{source}\n"
        assert destination.stat().st_mode & 0o777 == 0o644
    for name in installer.PLYMOUTH_THEME_FILES:
        assert (theme_root / name).read_text() == f"asset:packaging/plymouth/themes/mudos/{name}\n"
    assert calls == [
        ([installer.sys.executable, str(release / "scripts/configure-mudos-limine.py")],
         {"check": True}),
        (["plymouth-set-default-theme", "mudos", "--rebuild-initrd"], {"check": True}),
    ]
    assert verified == [release]


def test_installer_verification_rejects_missing_or_stale_startup_integration(tmp_path, monkeypatch):
    release = tmp_path / "release"
    installed_files = {}
    for relative in (*installer.STARTUP_INTEGRATION_FILES,
                     *(f"packaging/plymouth/themes/mudos/{name}"
                       for name in installer.PLYMOUTH_THEME_FILES),
                     "scripts/configure-mudos-limine.py"):
        source = release / relative
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text(f"asset:{relative}\n")
        if relative in installer.STARTUP_INTEGRATION_FILES:
            installed = tmp_path / "installed" / Path(relative).name
            installed.parent.mkdir(parents=True, exist_ok=True)
            installed.write_bytes(source.read_bytes())
            installed_files[relative] = installed
    theme_root = tmp_path / "installed-theme"
    theme_root.mkdir()
    for name in installer.PLYMOUTH_THEME_FILES:
        (theme_root / name).write_bytes(
            (release / "packaging/plymouth/themes/mudos" / name).read_bytes())

    commands = []

    def fake_run(args, **kwargs):
        commands.append(args)
        return subprocess.CompletedProcess(args, 0, "mudos\n" if args == ["plymouth-set-default-theme"] else "", "")

    monkeypatch.setattr(installer, "run", fake_run)
    installer.verify_startup_integration(release, installed_files=installed_files,
                                         theme_root=theme_root)
    assert ["plymouth-set-default-theme"] in commands
    assert any(args[-1] == "--check" for args in commands)

    first = next(iter(installed_files.values()))
    first.unlink()
    with pytest.raises(installer.InstallError, match="startup integration does not match"):
        installer.verify_startup_integration(release, installed_files=installed_files,
                                             theme_root=theme_root)


def test_startup_host_snapshot_restores_only_captured_paths(tmp_path):
    existing = tmp_path / "etc/systemd/mudos-handoff.conf"
    absent = tmp_path / "etc/pacman.d/mudos-hook"
    existing.parent.mkdir(parents=True)
    existing.write_text("old integration\n")
    snapshot = {existing: (existing.read_bytes(), 0o640), absent: None}
    existing.write_text("partially updated integration\n")
    absent.parent.mkdir(parents=True)
    absent.write_text("new integration\n")

    installer.restore_startup_host_files(snapshot)

    assert existing.read_text() == "old integration\n"
    assert existing.stat().st_mode & 0o777 == 0o640
    assert not absent.exists()


def test_aurelia_review_provider_enable_preserves_other_user_configuration(tmp_path):
    config = tmp_path / "provider-services.toml"
    config.write_text("[providers.usenet]\nenabled = false\n\n"
                      "[providers.steam_aurelia]\nenabled = false\nendpoint = 'unused'\n")
    installer.enable_aurelia_review_provider(config)
    text = config.read_text()
    assert "[providers.usenet]\nenabled = false" in text
    assert "[providers.steam_aurelia]\nenabled = true\nendpoint = 'unused'" in text
    installer.enable_aurelia_review_provider(config)
    assert config.read_text().count("[providers.steam_aurelia]") == 1


def test_aurelia_review_provider_enable_adds_missing_section(tmp_path):
    config = tmp_path / "provider-services.toml"
    config.write_text("[metadata.protondb]\nenabled = false\n")
    installer.enable_aurelia_review_provider(config)
    assert "[providers.steam_aurelia]\nenabled = true" in config.read_text()


def test_steam_bootstrap_data_root_precedes_owned_steamapps_child():
    entries = manifest()["mutable"]["initial_directories"]
    paths = [entry["path"] for entry in entries]
    root = "/home/lulu/.local/share/Steam"
    child = root + "/steamapps"
    assert paths.index(root) < paths.index(child)
    assert next(item for item in entries if item["path"] == root) == {
        "path": root, "owner": "lulu", "mode": "0750"}


def test_update_repairs_only_steam_bootstrap_directory_metadata(tmp_path, monkeypatch):
    root = tmp_path / "Steam"
    root.mkdir()
    child = root / "steamapps"
    child.mkdir()
    preserved = child / "libraryfolders.vdf"
    preserved.write_text("keep Steam library metadata")
    original_lstat = Path.lstat
    fake_root_stat = SimpleNamespace(
        st_mode=stat.S_IFDIR | 0o755, st_uid=0, st_gid=0)

    def lstat(path):
        if path == root:
            return fake_root_stat
        return original_lstat(path)

    chown_calls = []
    monkeypatch.setattr(Path, "lstat", lstat)
    monkeypatch.setattr(installer.os, "chown",
                        lambda *args, **kwargs: chown_calls.append((args, kwargs)))
    assert installer.repair_steam_bootstrap_directory(root)
    assert chown_calls == [((root, 958, 958), {"follow_symlinks": False})]
    assert stat.S_IMODE(root.stat().st_mode) == 0o750
    assert preserved.read_text() == "keep Steam library metadata"


def test_transmission_admin_config_unit_and_polkit_rule_are_installed_and_purge_owned():
    data = manifest()
    assert "/etc/polkit-1/rules.d/61-lulu-dolphin-bluetooth.rules" in data["system_integration"]["system_files"]
    assert "/etc/systemd/system/lulu-transmission-config.service" in data["system_integration"]["systemd_files"]
    assert "/etc/polkit-1/rules.d/54-lulu-transmission.rules" in data["system_integration"]["system_files"]
    assert "/etc/polkit-1/rules.d/55-lulu-transmission-config.rules" in data["system_integration"]["system_files"]
    assert "/etc/polkit-1/rules.d/51-lulu-nzbget.rules" in data["system_integration"]["system_files"]
    assert "/etc/polkit-1/rules.d/52-lulu-acquisition.rules" in data["system_integration"]["system_files"]
    installer_source = (ROOT / "scripts/install_mudos.py").read_text()
    assert '"lulu-transmission-config.service": "lulu-transmission-config.service"' in installer_source
    assert '"lulu-transmission-config.service")' in installer_source


def test_every_installer_copied_unit_is_in_the_purge_ownership_contract():
    copied_units = installer.SYSTEMD_UNITS
    owned = set(manifest()["system_integration"]["systemd_files"])
    missing = {f"/etc/systemd/system/{target}" for target in copied_units.values()} - owned
    assert not missing, f"installer copies Mudos units not owned for purge: {sorted(missing)}"


def test_non_destructive_update_plan_has_no_purge_or_mutable_state_actions(monkeypatch):
    monkeypatch.setattr(installer, "source_revision", lambda _repo: ("a" * 40, "test"))
    actions = installer.plan(ROOT, manifest(), "update")
    text = " ".join(actions).casefold()
    assert "atomically switch /opt/lulu/current" in text
    assert "preserving all mutable state" in text
    assert "purge" not in text
    assert "remove" not in text


def test_update_refreshes_only_active_mudos_runtime_units(monkeypatch):
    calls = []
    def fake_run(args, **kwargs):
        calls.append(args)
        if args[:2] == ["runuser", "-u"]:
            return subprocess.CompletedProcess(args, 0, "", "")
        return subprocess.CompletedProcess(args, 0, "active\n", "")
    monkeypatch.setattr(installer, "run", fake_run)
    monkeypatch.setattr(installer.time, "sleep", lambda _delay: None)
    installer._restart_update_services([
        "lulu-session@2.service", "lulu-consoled.service", "lulu-acquisition.service",
        "lulu-admin.service", "inputplumber.service", "bluetooth.service"])
    restarts = [call for call in calls if call[:2] == ["systemctl", "restart"]]
    assert restarts == [["systemctl", "restart", "lulu-session@2.service"],
                        ["systemctl", "restart", "lulu-consoled.service"],
                        ["systemctl", "restart", "lulu-acquisition.service"],
                        ["systemctl", "restart", "lulu-admin.service"]]
    session_probe = next(i for i, call in enumerate(calls)
                         if call[:2] == ["runuser", "-u"] and "org.lulu.ConsoleSessiond" in call)
    consoled_restart = calls.index(["systemctl", "restart", "lulu-consoled.service"])
    assert session_probe < consoled_restart


def test_update_dbus_wait_retries_transient_unavailable_name(monkeypatch):
    outcomes = iter([
        subprocess.CompletedProcess([], 1, "", "The name is not activatable"),
        subprocess.CompletedProcess([], 0, "activating\n", ""),
        subprocess.CompletedProcess([], 0, "", ""),
    ])
    calls = []
    monkeypatch.setattr(installer, "run", lambda args, **_kwargs:
                        calls.append(args) or next(outcomes))
    monkeypatch.setattr(installer.time, "monotonic", lambda: 0.0)
    monkeypatch.setattr(installer.time, "sleep", lambda _delay: None)
    installer._wait_for_update_dbus("lulu-session@2.service", *installer.UPDATE_DBUS_BOUNDARIES[
        "lulu-session@2.service"], timeout=5)
    assert sum(call[:2] == ["runuser", "-u"] for call in calls) == 2


def test_update_dbus_wait_fails_immediately_for_inactive_service(monkeypatch):
    def fake_run(args, **_kwargs):
        if args[:2] == ["runuser", "-u"]:
            return subprocess.CompletedProcess(args, 1, "", "NameHasNoOwner")
        return subprocess.CompletedProcess(args, 0, "failed\n", "")
    monkeypatch.setattr(installer, "run", fake_run)
    with pytest.raises(installer.InstallError, match="stopped before its D-Bus API"):
        installer._wait_for_update_dbus("lulu-consoled.service", *installer.UPDATE_DBUS_BOUNDARIES[
            "lulu-consoled.service"], timeout=5)


def test_update_dbus_wait_has_a_finite_deadline(monkeypatch):
    times = iter((0.0, 0.0, 0.6))

    def fake_run(args, **_kwargs):
        if args[:2] == ["runuser", "-u"]:
            return subprocess.CompletedProcess(args, 1, "", "NameHasNoOwner")
        return subprocess.CompletedProcess(args, 0, "activating\n", "")

    monkeypatch.setattr(installer, "run", fake_run)
    monkeypatch.setattr(installer.time, "monotonic", lambda: next(times))
    monkeypatch.setattr(installer.time, "sleep", lambda _delay: None)
    with pytest.raises(installer.InstallError, match="timed out waiting"):
        installer._wait_for_update_dbus("lulu-session@2.service", *installer.UPDATE_DBUS_BOUNDARIES[
            "lulu-session@2.service"], timeout=0.5, interval=0.1)


def test_systemd_release_copy_uses_only_declared_mudos_units(tmp_path):
    packaging = tmp_path / "packaging"
    target = tmp_path / "systemd"
    packaging.mkdir()
    for source in installer.SYSTEMD_UNITS:
        (packaging / source).write_text(f"# {source}\n")
    installer._install_systemd_units(packaging, target)
    assert {path.name for path in target.iterdir()} == set(installer.SYSTEMD_UNITS.values())


def test_update_selects_verified_release_without_touching_mutable_state(tmp_path, monkeypatch):
    data = json.loads((ROOT / "packaging/mudos-ownership.json").read_text())
    release_root = tmp_path / "releases"
    release_root.mkdir()
    previous = release_root / "old-immutable"
    previous.mkdir()
    (previous / "RELEASE").write_text("revision=" + "b" * 40 + "\nstatus=clean\nimmutable=true\n")
    selector = tmp_path / "current"
    selector.symlink_to(previous)
    alias_root = tmp_path / "aliases"
    alias_root.mkdir()
    aliases = [alias_root / name for name in ("bin", "lib", "ui", "config", "scripts")]
    for alias in aliases:
        alias.symlink_to("current/" + alias.name)
    data["immutable"]["release_root"] = str(release_root)
    data["immutable"]["selector"] = str(selector)
    data["immutable"]["application_roots"] = [str(path) for path in aliases]

    revision = "a" * 40
    candidate = release_root / f"{revision[:7]}-candidate-fixture"
    (candidate / "packaging").mkdir(parents=True)
    (candidate / "RELEASE").write_text(f"revision={revision}\nstatus=clean\nimmutable=true\n")
    for source in installer.SYSTEMD_UNITS:
        (candidate / "packaging" / source).write_text(f"# updated {source}\n")
    candidate_polkit = candidate / "packaging/polkit-1/rules.d"
    candidate_polkit.mkdir(parents=True)
    (candidate_polkit / "61-lulu-dolphin-bluetooth.rules").write_text("updated bluetooth rule\n")
    candidate_udev = candidate / "packaging/udev"
    candidate_udev.mkdir(parents=True)
    (candidate_udev / "82-lulu-dolphin-bluetooth.rules").write_text("updated adapter permissions\n")
    mutable_state = tmp_path / "user-state" / "provider-secret"
    mutable_state.parent.mkdir()
    mutable_state.write_text("keep-this-byte-for-byte")
    before_state = mutable_state.read_bytes()

    monkeypatch.setattr(installer, "source_revision", lambda _repo: (revision, "test"))
    monkeypatch.setattr(installer.os, "geteuid", lambda: 0)
    monkeypatch.setattr(installer, "_session_state", lambda: {"lifecycle": "shell"})
    monkeypatch.setattr(installer, "_active", lambda unit: unit != "lulu-file-browser.service")
    monkeypatch.setattr(installer, "mutable_paths",
                        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("mutable paths read")))
    monkeypatch.setattr(installer, "install_integration",
                        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("install path reused")))
    restarted = []
    monkeypatch.setattr(installer, "_restart_update_services", lambda units: restarted.extend(units))
    monkeypatch.setattr(installer, "_main_pid", lambda unit: 1000 + len(unit))
    monkeypatch.setattr(installer, "_verify_update_services", lambda _units, _pids: None)
    monkeypatch.setattr(installer, "snapshot_startup_host_files", lambda: {})
    startup_integrations = []
    monkeypatch.setattr(installer, "install_startup_integration",
                        lambda selected: startup_integrations.append(selected))
    commands = []

    def fake_run(args, **_kwargs):
        commands.append(args)
        if len(args) > 2 and args[1].endswith("release.py") and args[2] == "activate":
            selected = Path(args[args.index("--release-dir") + 1])
            next_link = selector.with_name(".current.next")
            next_link.unlink(missing_ok=True)
            next_link.symlink_to(selected)
            next_link.replace(selector)
        return subprocess.CompletedProcess(args, 0, "", "")

    monkeypatch.setattr(installer, "run", fake_run)
    systemd_root = tmp_path / "etc/systemd/system"
    polkit_rule = tmp_path / "etc/polkit-1/rules.d/61-lulu-dolphin-bluetooth.rules"
    monkeypatch.setattr(installer, "DOLPHIN_BLUETOOTH_POLKIT_RULE", polkit_rule)
    udev_rule = tmp_path / "etc/udev/rules.d/82-lulu-dolphin-bluetooth.rules"
    monkeypatch.setattr(installer, "DOLPHIN_BLUETOOTH_UDEV_RULE", udev_rule)
    steam_data_root = tmp_path / "Steam"
    installer.do_update(ROOT, data, False, systemd_root=systemd_root,
                        steam_data_root=steam_data_root)

    assert selector.resolve() == candidate
    assert startup_integrations == [candidate]
    assert polkit_rule.read_text() == "updated bluetooth rule\n"
    assert udev_rule.read_text() == "updated adapter permissions\n"
    assert ["udevadm", "control", "--reload-rules"] in commands
    assert ["udevadm", "trigger", "--action=add", "--subsystem-match=usb",
            "--attr-match=idVendor=0bda", "--attr-match=idProduct=8771"] in commands
    assert ["systemctl", "reload", "polkit.service"] in commands
    assert previous.is_dir()  # retained immutable rollback release
    assert mutable_state.read_bytes() == before_state
    assert not steam_data_root.exists()  # update does not initialize absent Steam state
    assert restarted == ["lulu-session@2.service", "lulu-consoled.service",
                         "lulu-acquisition.service", "lulu-admin.service",
                         "mudos-recovery.service"]
    assert not any("pacman" in " ".join(command) or "purge" in " ".join(command)
                   for command in commands)


def test_development_validation_dropin_is_purge_owned_and_removed_before_production():
    path = "/etc/systemd/system/lulu-inputplumber-hotplug.service.d/dev-validation.conf"
    assert path in manifest()["system_integration"]["systemd_files"]
    installer_source = (ROOT / "scripts/install_mudos.py").read_text()
    assert 'raw.endswith(("/dev-runtime.conf", "/dev-validation.conf"))' in installer_source


def test_installer_reloads_inputplumber_then_reconciles_already_connected_gamepads():
    source = (ROOT / "scripts/install_mudos.py").read_text()
    reload_rules = source.index('run(["udevadm", "control", "--reload-rules"]')
    dolphin_usb_permissions = source.index('"--attr-match=idVendor=0bda"')
    restart_inputplumber = source.index('run(["systemctl", "restart", "inputplumber.service"])')
    reconcile_devices = source.index('run(["systemctl", "start", "lulu-inputplumber-hotplug.service"])')
    start_session = source.index('run(["systemctl", "start", "lulu.target"])', reconcile_devices)
    assert reload_rules < dolphin_usb_permissions < restart_inputplumber < reconcile_devices < start_session


def test_lulu_target_is_installable_and_installer_verifies_boot_enablement():
    target = (ROOT / "packaging/lulu.target").read_text()
    installer_source = (ROOT / "scripts/install_mudos.py").read_text()
    ownership = manifest()
    assert "[Install]\nWantedBy=multi-user.target" in target
    assert "/etc/systemd/system/multi-user.target.wants/lulu.target" in ownership["system_integration"]["systemd_files"]
    assert 'run(["systemctl", "enable", unit])' in installer_source
    assert "Lulu appliance target is not enabled for boot" in installer_source


def test_reinstall_restarts_preexisting_session_to_load_new_immutable_release(monkeypatch):
    calls = []
    monkeypatch.setattr(installer, "run", lambda args, **_kwargs: calls.append(args))
    installer.start_runtime(session_was_active=True)
    assert calls == [["systemctl", "start", "lulu.target"],
                     ["systemctl", "restart", "lulu-session@2.service"]]


def test_first_install_starts_target_without_redundant_session_restart(monkeypatch):
    calls = []
    monkeypatch.setattr(installer, "run", lambda args, **_kwargs: calls.append(args))
    installer.start_runtime(session_was_active=False)
    assert calls == [["systemctl", "start", "lulu.target"]]


@pytest.mark.parametrize("bad", ["relative/path", "/../../etc", "/"])
def test_manifest_rejects_unsafe_mutable_paths(tmp_path, bad):
    data = json.loads((ROOT / "packaging/mudos-ownership.json").read_text())
    data["mutable"]["exact_paths"].append(bad)
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(data))
    with pytest.raises(installer.InstallError):
        installer.load_manifest(path)


def test_manifest_rejects_nested_purge_paths(tmp_path):
    data = json.loads((ROOT / "packaging/mudos-ownership.json").read_text())
    data["mutable"]["exact_paths"].append("/home/lulu/.config/lulu/secret")
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(data))
    with pytest.raises(installer.InstallError, match="overlapping"):
        installer.load_manifest(path)


def test_manifest_rejects_broad_system_cleanup_pattern(tmp_path):
    data = json.loads((ROOT / "packaging/mudos-ownership.json").read_text())
    data["system_integration"]["patterns"] = ["/etc/*.yaml"]
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(data))
    with pytest.raises(installer.InstallError, match="unsafe owned path pattern"):
        installer.load_manifest(path)


def test_uninstall_preserves_mutable_state_but_purge_requires_explicit_flag():
    data = manifest()
    uninstall = installer.plan(ROOT, data, "uninstall")
    assert not any(path in " ".join(uninstall) for path in data["mutable"]["exact_paths"])
    assert "preserve immutable releases and all mutable user data" in uninstall[-1]
    with pytest.raises(installer.InstallError, match="explicit"):
        installer.plan(ROOT, data, "purge")
    purge = installer.plan(ROOT, data, "purge", purge=True)
    assert any("/home/lulu/Games/ROMs" in row for row in purge)


def test_mutable_configuration_initialization_is_idempotent(tmp_path):
    source = tmp_path / "template"
    destination = tmp_path / "mutable/config.toml"
    source.write_text("default = true\n")
    assert installer.copy_if_absent(source, destination)
    destination.write_text("operator = true\n")
    assert not installer.copy_if_absent(source, destination)
    assert destination.read_text() == "operator = true\n"


def test_mutable_configuration_initializer_applies_owner_and_mode(tmp_path, monkeypatch):
    source = tmp_path / "template"
    destination = tmp_path / "mutable/config.toml"
    source.write_text("default = true\n")
    ownership = []
    monkeypatch.setattr(installer.os, "chown", lambda path, uid, gid: ownership.append((Path(path), uid, gid)))
    assert installer.copy_if_absent(source, destination, uid=958, gid=958, mode=0o640)
    assert ownership == [(destination, 958, 958)]
    assert destination.stat().st_mode & 0o777 == 0o640


def test_exact_source_release_is_reused_on_reinstall(tmp_path):
    revision = "a" * 40
    release = tmp_path / "releases" / f"{revision[:7]}-candidate-20260926"
    release.mkdir(parents=True)
    (release / "RELEASE").write_text(
        f"revision={revision}\nstatus=clean\nimmutable=true\n"
    )
    assert installer.existing_release(release.parent, revision) == release
    assert installer.existing_release(release.parent, "b" * 40) is None


def test_shared_package_selection_reuses_installed_compatible_variants():
    installed = {"gamescope-git", "qt6-base"}
    selected = installer.packages_to_install(
        ["gamescope", "qt6-base", "inputplumber"],
        {"gamescope": ["gamescope-git"]},
        installed=lambda name: name in installed,
    )
    assert selected == ["inputplumber"]


def test_install_dependency_contract_includes_controller_osk_toolchain():
    packages = manifest()["shared_dependencies"]["packages"]
    assert {"go", "sdl3_ttf", "libx11", "curl", "patch"} <= set(packages)
    assert {"bluez", "bluez-utils", "python-dbus-next"} <= set(packages)
    provisioner = (ROOT / "scripts/provision-gamepad-osk.sh").read_text()
    assert "sha256sum --check" in provisioner


def test_bluetooth_is_enabled_and_checked_by_canonical_installer():
    source = (ROOT / "scripts/install_mudos.py").read_text()
    assert 'systemctl", "enable", "--now", "bluetooth.service' in source
    assert '"bluez", "bluez-utils"' in source
    assert '"BlueZ Bluetooth service is not enabled and active"' in source


def test_host_mount_contract_matches_only_fstab_generated_exact_mount(monkeypatch):
    mount = manifest()["preserved_host_mounts"][0]
    outputs = [
        "FragmentPath=/run/systemd/generator/mount.service\nSourcePath=/etc/fstab\n"
        "Where=/home/lulu/.local/share/Steam/steamapps\nActiveState=active\n",
        "# generated\n[Mount]\nWhat=/home/lulu/Games/Executables/steam/steamapps\n"
        "Where=/home/lulu/.local/share/Steam/steamapps\n",
    ]

    def fake_run(args, **kwargs):
        return subprocess.CompletedProcess(args, 0, outputs.pop(0), "")

    monkeypatch.setattr(installer, "run", fake_run)
    assert installer.host_mount_state(mount) == "active"


def test_host_mount_contract_rejects_unrelated_or_conflicting_mount(monkeypatch):
    mount = manifest()["preserved_host_mounts"][0]
    outputs = [
        "FragmentPath=/run/systemd/generator/unrelated.mount\nSourcePath=/etc/fstab\n"
        "Where=/home/lulu/.local/share/Steam/steamapps\nActiveState=active\n",
        "[Mount]\nWhat=/mnt/unrelated\nWhere=/home/lulu/.local/share/Steam/steamapps\n",
    ]

    def fake_run(args, **kwargs):
        return subprocess.CompletedProcess(args, 0, outputs.pop(0), "")

    monkeypatch.setattr(installer, "run", fake_run)
    with pytest.raises(installer.InstallError, match="non-matching host mount"):
        installer.host_mount_state(mount)


def test_safe_remove_refuses_repository_and_immutable_releases(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    release_root = tmp_path / "releases"
    release_root.mkdir()
    with pytest.raises(installer.InstallError, match="protected"):
        installer.safe_remove(repo, repo, [])
    with pytest.raises(installer.InstallError, match="protected"):
        installer.safe_remove(release_root, repo, [str(release_root)])


def test_clean_source_required_for_release_install(tmp_path):
    repo = tmp_path / "source"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.email", "installer-test@example.invalid"], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.name", "Installer Test"], check=True)
    file = repo / "tracked"
    file.write_text("committed")
    subprocess.run(["git", "-C", str(repo), "add", "tracked"], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-qm", "initial"], check=True)
    sha, _branch = installer.source_revision(repo)
    assert len(sha) == 40
    file.write_text("dirty")
    with pytest.raises(installer.InstallError, match="dirty"):
        installer.source_revision(repo)


def test_safe_remove_only_removes_named_path(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    parent = tmp_path / "home" / "lulu"
    owned = parent / ".config" / "lulu"
    unrelated = parent / ".config" / "editor"
    owned.mkdir(parents=True)
    unrelated.mkdir()
    (owned / "state").write_text("owned")
    (unrelated / "state").write_text("keep")
    installer.safe_remove(owned, repo, [])
    assert not owned.exists()
    assert (unrelated / "state").read_text() == "keep"


def test_safe_remove_refuses_symlinked_parent(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    real = tmp_path / "real"
    (real / "owned").mkdir(parents=True)
    link = tmp_path / "link"
    link.symlink_to(real, target_is_directory=True)
    with pytest.raises(installer.InstallError, match="symlinked parent"):
        installer.safe_remove(link / "owned", repo, [])
    assert (real / "owned").is_dir()


def test_custom_storage_purge_is_scoped_to_mudos_subtree(tmp_path):
    home = tmp_path / "home" / "lulu"
    config = home / ".config/lulu/storage-targets.json"
    config.parent.mkdir(parents=True)
    configured = tmp_path / "mounted-games"
    config.write_text(json.dumps({"game_path": str(configured)}))
    paths = installer.mutable_paths(manifest(), home)
    assert configured / "Mudos/ROMs" in paths
    assert configured not in paths


def test_acquisition_directories_cover_default_and_configured_game_and_emulation(tmp_path):
    home = tmp_path / "home" / "lulu"
    custom_game = tmp_path / "mounted" / "games"
    custom_emu = tmp_path / "mounted" / "roms"
    config = home / ".config/lulu/storage-targets.json"
    config.parent.mkdir(parents=True)
    config.write_text(json.dumps({"game_path": str(custom_game),
                                  "emulation_path": str(custom_emu)}))
    paths = installer.acquisition_directories(manifest(), home)
    assert home / "Games/.acquisition/torrents" in paths
    assert custom_game / "Mudos/.acquisition/usenet" in paths
    assert custom_emu / "Mudos/.acquisition/torrents" in paths
    assert custom_game in paths or custom_game / "Mudos/.acquisition/torrents" in paths
    writable = installer.provider_install_writable_paths(manifest(), home)
    assert home / "Games/.acquisition" in writable
    assert custom_game / "Mudos/.acquisition" in writable
    assert custom_emu / "Mudos/.acquisition" in writable


def test_installer_refuses_to_initialize_an_unmounted_configured_storage_target(tmp_path):
    home = tmp_path / "home" / "lulu"
    config = home / ".config/lulu/storage-targets.json"
    config.parent.mkdir(parents=True)
    target = tmp_path / "mnt" / "games"
    target.mkdir(parents=True)
    config.write_text(json.dumps({"game_path": str(target)}))
    with pytest.raises(installer.InstallError, match="connect and mount"):
        installer.validate_configured_storage_targets(manifest(), home)


def test_installer_accepts_only_present_mount_for_configured_storage_target(tmp_path, monkeypatch):
    home = tmp_path / "home" / "lulu"
    config = home / ".config/lulu/storage-targets.json"
    config.parent.mkdir(parents=True)
    target = tmp_path / "mnt" / "games"
    target.mkdir(parents=True)
    config.write_text(json.dumps({"game_path": str(target)}))
    monkeypatch.setattr(installer.os.path, "ismount", lambda path: Path(path) == target)
    installer.validate_configured_storage_targets(manifest(), home)


def test_purge_checks_configured_mount_ownership_before_printing_or_removing(monkeypatch):
    checked = []
    monkeypatch.setattr(installer, "validate_configured_storage_targets",
                        lambda data: checked.append(data))
    monkeypatch.setattr(installer, "plan", lambda *_args, **_kwargs: [])
    installer.remove_owned(ROOT, manifest(), purge=True, dry_run=True)
    assert checked == [manifest()]


def test_acquisition_initialization_creates_only_leaves_with_restricted_modes(tmp_path):
    parent = tmp_path / "mounted" / "Mudos" / ".acquisition"
    paths = [parent / "torrents", parent / "usenet"]
    installer.initialize_acquisition_directories(
        paths, uid=__import__("os").getuid(), gid=__import__("os").getgid())
    assert parent.is_dir()
    assert all(path.is_dir() and path.stat().st_mode & 0o777 == 0o770 for path in paths)
    assert not (tmp_path / "mounted").stat().st_mode & 0o002


def test_acquisition_paths_are_narrowly_added_to_provider_installer_sandbox():
    unit = (ROOT / "packaging/lulu-provider-install@.service").read_text()
    assert "ReadWritePaths=/home/lulu/.config /home/lulu/.local/share/lulu -/home/lulu/.local/share/flatpak /home/lulu/Games/.acquisition " in unit
    assert "ReadWritePaths=/home/lulu " not in unit


def test_flatpak_provider_install_runs_idempotent_user_remote_provisioner():
    installer = (ROOT / "packaging/mudos-provider-install").read_text()
    service = (ROOT / "packaging/lulu-provider-install@.service").read_text()
    provisioner = (ROOT / "scripts/provision-flatpak.sh").read_text()
    assert 'flatpak) exec "$root/scripts/provision-flatpak.sh" ;;' in installer
    assert "flatpak --user remote-add --if-not-exists flathub" in provisioner
    assert "-/home/lulu/.local/share/flatpak" in service


def test_file_browser_bind_sources_are_initialized_for_first_start():
    data = manifest()
    initial = {item["path"] for item in data["mutable"]["initial_directories"]}
    unit = (ROOT / "packaging/lulu-file-browser.service").read_text()
    for source in ("/home/lulu/Games", "/home/lulu/Recordings",
                   "/home/lulu/Replays", "/home/lulu/Screenshots"):
        assert f"BindPaths={source}:" in unit
        assert source in initial


def test_dufs_is_provisioned_as_a_canonical_core_service():
    provisioner = (ROOT / "scripts/provision-dufs.sh").read_text()
    firewall = (ROOT / "scripts/configure-acquisition-firewall.sh").read_text()
    pkgbuild = (ROOT / "packages/dufs/PKGBUILD").read_text()
    installer_source = (ROOT / "scripts/install_mudos.py").read_text()
    assert "provision-dufs.sh" in installer_source
    assert "file-browser.env" in provisioner
    assert "makepkg --cleanbuild" in provisioner
    assert "pacman -U" in provisioner
    assert '"$repo_root/scripts/configure-acquisition-firewall.sh"' in provisioner
    assert 'to any port 8080 proto tcp comment \'Mudos file browser\'' in firewall
    assert "817769f726613194bcff9d0e3e481eaccc86ac11208857614f36a8c02f410977" in pkgbuild
    assert "core DUFS file manager package is not installed" in installer_source










def test_production_units_do_not_reference_dev_runtime():
    for name in ("lulu.target", "lulu-session@.service", "lulu-consoled.service",
                 "lulu-acquisition.service", "lulu-admin.service", "mudos-recovery.service",
                 "mudos-recovery-ui.service", "lulu-inputplumber-hotplug.service"):
        assert "/opt/lulu/dev-current" not in (ROOT / "packaging" / name).read_text()


def test_admin_sandbox_allows_absent_optional_provider_state():
    unit = (ROOT / "packaging/lulu-admin.service").read_text()
    assert "-/var/lib/nzbget" in unit
    assert "-/var/lib/lulu-transmission" in unit


def test_fresh_onboarding_default_is_incomplete_and_has_no_auth_seed():
    source = (ROOT / "src/lulu/onboarding.py").read_text()
    assert '"status": "never"' in source
    assert '"oobe_dismissed": False' in source
    assert "SecretStore" not in source[:source.index("def _read")]


def test_installer_entrypoint_exposes_safe_operations():
    result = subprocess.run([str(ROOT / "install-mudos.sh"), "--help"], cwd=ROOT,
                            text=True, capture_output=True, check=True)
    assert "--purge-user-data" in result.stdout
    assert "--verify" in result.stdout
