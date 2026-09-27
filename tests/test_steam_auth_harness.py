import importlib.util
import json
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "steam_auth_surface", ROOT / "scripts/steam-auth-surface.py")
HARNESS = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(HARNESS)


def _reply(value):
    return type("Completed", (), {
        "returncode": 0,
        "stdout": json.dumps({"type": "s", "data": [json.dumps(value)]}),
        "stderr": "",
    })()


def test_start_calls_the_exact_consoled_oobe_auth_operation():
    replies = iter([_reply({"authenticated": False}), _reply({
        "status": "surface_requested", "launch": "owned-token"})])
    with patch.object(HARNESS.subprocess, "run", side_effect=lambda *a, **kw: next(replies)) as run:
        result = HARNESS.start()
    calls = [call.args[0] for call in run.call_args_list]
    assert calls[0][-3:] == ["GetPluginAuthStatus", "s", "steam"]
    assert calls[1][-4:-1] == ["BeginPluginAuthenticationTraced", "ss", "steam"]
    assert len(calls[1][-1]) == 12
    assert result["launch"] == "owned-token"


def test_start_detects_authenticated_session_without_opening_another_surface():
    with patch.object(HARNESS, "_busctl", return_value={
            "authenticated": True, "account": "fixture"}) as call:
        result = HARNESS.start()
    call.assert_called_once_with("GetPluginAuthStatus", "s", "steam")
    assert result["status"] == "authenticated"


def test_dismiss_calls_consoled_with_only_the_owned_launch_token():
    with patch.object(HARNESS, "_busctl", return_value={"dismissed": True}) as call:
        result = HARNESS.dismiss("owned-token")
    call.assert_called_once_with("DismissPluginAuthentication", "ss", "steam", "owned-token")
    assert result["dismissed"]
