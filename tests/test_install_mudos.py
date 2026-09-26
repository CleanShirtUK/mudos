import importlib.util
import json
from pathlib import Path
import subprocess

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
    assert "/home/josh/src/lulu" in data["protected"]
    assert "packages" in data["shared_dependencies"]
    assert not any("/opt/lulu/dev-current" in path for path in data["immutable"].values()
                   if isinstance(path, str))


def test_transmission_admin_config_unit_and_polkit_rule_are_installed_and_purge_owned():
    data = manifest()
    assert "/etc/systemd/system/lulu-transmission-config.service" in data["system_integration"]["systemd_files"]
    assert "/etc/polkit-1/rules.d/54-lulu-transmission.rules" in data["system_integration"]["system_files"]
    assert "/etc/polkit-1/rules.d/55-lulu-transmission-config.rules" in data["system_integration"]["system_files"]
    assert "/etc/polkit-1/rules.d/51-lulu-nzbget.rules" in data["system_integration"]["system_files"]
    assert "/etc/polkit-1/rules.d/52-lulu-acquisition.rules" in data["system_integration"]["system_files"]
    installer_source = (ROOT / "scripts/install_mudos.py").read_text()
    assert '"lulu-transmission-config.service": "lulu-transmission-config.service"' in installer_source
    assert '"lulu-transmission-config.service")' in installer_source


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
    provisioner = (ROOT / "scripts/provision-gamepad-osk.sh").read_text()
    assert "sha256sum --check" in provisioner


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


def test_questarr_restart_is_rate_limited_and_has_bounded_retries():
    unit = (ROOT / "packaging/lulu-questarr.service").read_text()
    assert "StartLimitIntervalSec=300" in unit
    assert "StartLimitBurst=3" in unit


def test_questarr_uses_configured_storage_resolver_not_hardcoded_host_root():
    unit = (ROOT / "packaging/lulu-questarr.service").read_text()
    launcher = (ROOT / "scripts/mudos-questarr").read_text()
    assert "mudos-questarr" in unit
    assert "PATHS.torrent_root" in launcher and "PATHS.usenet_root" in launcher
    assert "-d ${host_roots[0]}" in launcher


def test_release_builder_installs_questarr_launcher_at_service_exec_path():
    builder = (ROOT / "scripts/release.py").read_text()
    unit = (ROOT / "packaging/lulu-questarr.service").read_text()
    assert '"bin/mudos-questarr"' in builder
    assert 'source / "scripts" / "mudos-questarr"' in builder
    assert "ExecStart=/opt/lulu/current/bin/mudos-questarr" in unit


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
