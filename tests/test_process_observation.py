from pathlib import Path
import os

from lulu.process_observation import (
    APP_ID_ENVIRONMENT_KEYS, process_argv, process_environment,
    process_has_app_id, processes_with_app_id,
)


def _process(root: Path, pid: int, *, environment: bytes, argv: bytes,
             executable: Path) -> Path:
    entry = root / str(pid)
    entry.mkdir()
    (entry / "environ").write_bytes(environment)
    (entry / "cmdline").write_bytes(argv)
    (entry / "exe").symlink_to(executable)
    return entry


def test_process_environment_and_argv_are_read_from_procfs_bytes(tmp_path):
    exe = tmp_path / "game"
    exe.touch()
    _process(tmp_path, 100, environment=b"SteamAppId=40800\0DISPLAY=:0\0",
             argv=b"/games/title\0--flag\0", executable=exe)
    assert process_environment(100, proc_root=tmp_path) == {
        "SteamAppId": "40800", "DISPLAY": ":0",
    }
    assert process_argv(100, proc_root=tmp_path) == ("/games/title", "--flag")


def test_appid_verification_requires_exact_live_environment_evidence(tmp_path):
    exe = tmp_path / "game"
    exe.touch()
    _process(tmp_path, 101, environment=b"SteamGameId=40800\0",
             argv=b"game\0", executable=exe)
    assert process_has_app_id(101, "40800", proc_root=tmp_path)
    assert not process_has_app_id(101, "4080", proc_root=tmp_path)
    assert not process_has_app_id(999, "40800", proc_root=tmp_path)
    assert len(APP_ID_ENVIRONMENT_KEYS) == 3


def test_process_scan_filters_to_same_user_appid_and_caller_runtime_policy(tmp_path):
    game = tmp_path / "game"
    runtime = tmp_path / "runtime-helper"
    game.touch()
    runtime.touch()
    _process(tmp_path, 201, environment=b"STEAM_COMPAT_APP_ID=945360\0",
             argv=b"/games/title.exe\0", executable=game)
    _process(tmp_path, 202, environment=b"SteamAppId=945360\0",
             argv=b"steamwebhelper\0", executable=runtime)
    _process(tmp_path, 203, environment=b"SteamAppId=9453600\0",
             argv=b"/games/other.exe\0", executable=game)

    pids = processes_with_app_id(
        "945360", proc_root=tmp_path, uid=os.getuid(),
        exclude=lambda executable, _argv: executable == str(runtime),
    )
    assert pids == [201]
    assert processes_with_app_id(
        "945360", proc_root=tmp_path, uid=os.getuid() + 1,
        exclude=lambda _executable, _argv: False,
    ) == []
