"""Synthetic secret-bearing diagnostic inputs must never reach output."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from steam_auth_status import (  # noqa: E402
    AuthenticationStatus,
    diagnostic_fields,
    status_from_lines,
    status_since,
)


def _load_script(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / filename)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


lifecycle = _load_script("steam_lifecycle_probe", "steam-lifecycle-probe.py")
auth_surface = _load_script("steam_auth_surface", "steam-auth-surface.py")


def test_auth_log_classifier_returns_only_allowlisted_status_for_token_lines(capsys):
    secret = b"synthetic-JWT-never-return-this-value"
    lines = [
        b"[time] Using JWT " + secret + b", persistence: 1\n",
        b"[Logged On] RecvMsgClientLogOnResponse() : 'OK'\n",
    ]

    status = status_from_lines(lines)
    diagnostic = json.dumps(diagnostic_fields(status), sort_keys=True)

    assert status is AuthenticationStatus.AUTHENTICATED
    assert diagnostic == '{"authentication": "authenticated"}'
    assert secret.decode() not in diagnostic
    assert capsys.readouterr() == ("", "")


def test_auth_log_classifier_fails_closed_without_success_and_never_echoes_token(tmp_path, capsys):
    secret = b"synthetic-refresh-secret-never-return-this-value"
    path = tmp_path / "connection_log.txt"
    path.write_bytes(b"[Logging On] failed token=" + secret + b"\n")

    status = status_since(path, 0)
    diagnostic = json.dumps(diagnostic_fields(status), sort_keys=True)

    assert status is AuthenticationStatus.NOT_AUTHENTICATED
    assert secret.decode() not in diagnostic
    assert capsys.readouterr() == ("", "")


def test_auth_log_classifier_marks_missing_or_truncated_evidence_unknown(tmp_path):
    missing = tmp_path / "missing.log"
    path = tmp_path / "truncated.log"
    path.write_bytes(b"short\n")
    assert status_since(missing, 0) is AuthenticationStatus.UNKNOWN
    assert status_since(path, 100) is AuthenticationStatus.UNKNOWN


def test_lifecycle_probe_never_emits_raw_process_arguments_or_embedded_secrets():
    secret = "synthetic-command-secret-never-return-this-value"
    argv = ("steam", "-login", "fixture-user", secret, "-applaunch", "26800",
            "--auth-token=" + secret)

    metadata = lifecycle.safe_steam_command(argv)
    diagnostic = json.dumps(metadata, sort_keys=True)

    assert metadata == {"kind": "applaunch", "appid": "26800"}
    assert secret not in diagnostic
    assert "fixture-user" not in diagnostic


def test_lifecycle_report_and_export_contain_only_safe_launch_fields(tmp_path, capsys):
    secret = "synthetic-refresh-token-in-process-argv"
    argv = ("steam", "--login", secret, "-applaunch", "26800", "--auth=" + secret)
    metadata = lifecycle.safe_steam_command(argv)
    lifecycle.emit("steam-command", pid=2468, **metadata)
    output = capsys.readouterr()
    assert secret not in output.out + output.err
    assert 'appid="26800"' in output.out
    export = tmp_path / "safe-diagnostic.json"
    export.write_text(json.dumps(metadata), encoding="utf-8")
    assert secret not in export.read_text(encoding="utf-8")


def test_lifecycle_report_drops_secret_bearing_window_titles_and_classes(monkeypatch, capsys):
    secret = "synthetic-session-token-hidden-in-window-title"
    xprop_output = (
        "STEAM_GAME(CARDINAL) = 26800\n"
        "_NET_WM_NAME(UTF8_STRING) = \"" + secret + "\"\n"
        "WM_NAME(STRING) = \"" + secret + "\"\n"
        "_NET_WM_PID(CARDINAL) = 1234\n"
        "WM_CLASS(STRING) = \"" + secret + "\"\n"
    )
    monkeypatch.setattr(lifecycle, "xprop", lambda *_args: xprop_output)
    metadata = lifecycle.window_snapshot(":190", 42)
    lifecycle.emit("surface-created", id=42, **metadata)
    output = capsys.readouterr()
    assert metadata == {"steam_game": 26800, "pid": 1234}
    assert secret not in output.out + output.err


def test_auth_surface_drops_unexpected_auth_fields_and_errors_are_static(monkeypatch):
    replies = iter([
        {"authenticated": True, "jwt": "synthetic-token-never-return-this-value"},
        {"authenticated": False, "refresh_token": "synthetic-token-never-return-this-value"},
        {"status": "surface_requested", "launch": "owned-launch-control",
         "auth_token": "synthetic-token-never-return-this-value"},
    ])
    monkeypatch.setattr(auth_surface, "_busctl", lambda *_args: next(replies))
    already = auth_surface.start()
    started = auth_surface.start()

    assert already == {
        "status": "authenticated",
        "authentication": {"authenticated": True},
        "message": "Steam is already authenticated; no new surface was opened.",
    }
    assert started == {"status": "surface_requested", "launch": "owned-launch-control"}

    class Failed:
        returncode = 1
        stdout = "synthetic-token-never-return-this-value"
        stderr = "synthetic-token-never-return-this-value"

    monkeypatch.undo()
    monkeypatch.setattr(auth_surface.subprocess, "run", lambda *_args, **_kwargs: Failed())
    try:
        auth_surface._busctl("GetPluginAuthStatus", "s", "steam")
    except RuntimeError as error:
        assert str(error) == "Consoled request failed"
        assert "synthetic-token" not in str(error)
    else:
        raise AssertionError("failed D-Bus request unexpectedly succeeded")


def test_auth_surface_cli_stdout_stderr_and_exception_are_token_safe(monkeypatch, capsys):
    secret = "synthetic-cli-token-never-export-this"
    monkeypatch.setattr(auth_surface.pwd, "getpwnam", lambda _name: type("User", (), {"pw_uid": 123})())
    monkeypatch.setattr(auth_surface.os, "geteuid", lambda: 123)
    monkeypatch.setattr(auth_surface, "_busctl", lambda *_args: {
        "authenticated": True, "access_token": secret, "refresh_token": secret,
    })
    assert auth_surface.main(["start"]) == 0
    result = capsys.readouterr()
    assert secret not in result.out + result.err
    assert json.loads(result.out) == {
        "authentication": {"authenticated": True},
        "message": "Steam is already authenticated; no new surface was opened.",
        "status": "authenticated",
    }

    def fail_with_secret(*_args):
        raise RuntimeError(secret)

    monkeypatch.setattr(auth_surface, "_busctl", fail_with_secret)
    assert auth_surface.main(["start"]) == 1
    result = capsys.readouterr()
    assert secret not in result.out + result.err
    assert result.out == ""
    assert result.err.strip() == "steam auth surface: Consoled request failed"
