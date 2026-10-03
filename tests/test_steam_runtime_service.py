import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/steam-runtime-session.py"
SPEC = importlib.util.spec_from_file_location("steam_runtime_session", SCRIPT)
runtime = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runtime)


def test_steam_unit_is_session_scoped_and_restarts_independently_of_games():
    unit = (ROOT / "packaging/lulu-steam-runtime.service").read_text()
    assert "PartOf=lulu-session@2.service" in unit
    assert "Restart=always" in unit
    assert "RestartPreventExitStatus=78" in unit
    assert "RestartSec=5s" in unit
    assert "KillMode=mixed" in unit
    assert "ExecStart=/usr/bin/python /opt/lulu/current/scripts/steam-runtime-session.py" in unit
    assert "lulu-steam-runtime.service" not in (ROOT / "packaging/lulu.target").read_text() or \
        "WantedBy=lulu.target" in unit


def test_graphical_session_orders_after_nonfatal_steam_runtime():
    session = (ROOT / "packaging/lulu-session@.service").read_text()
    assert "Wants=" in session
    wants = next(line for line in session.splitlines() if line.startswith("Wants="))
    after = next(line for line in session.splitlines() if line.startswith("After="))
    assert "lulu-steam-runtime.service" in wants
    assert "lulu-steam-runtime.service" in after
    assert "Requires=lulu-steam-runtime.service" not in session


def test_steam_environment_is_constructed_without_inheriting_console_display(monkeypatch):
    monkeypatch.setenv("DISPLAY", ":0")
    monkeypatch.setenv("WAYLAND_DISPLAY", "gamescope-0")
    monkeypatch.setenv("GAMESCOPE_WAYLAND_DISPLAY", "gamescope-0")
    env = runtime.isolated_environment("/run/user/4242")
    assert env["DISPLAY"] == ":99"
    assert env["XDG_RUNTIME_DIR"] == "/run/user/4242"
    assert "WAYLAND_DISPLAY" not in env
    assert "GAMESCOPE_WAYLAND_DISPLAY" not in env
    assert "/run/user/958" not in str(env)


def test_runtime_starts_xvfb_then_silent_host_steam_on_the_same_isolated_display():
    source = SCRIPT.read_text()
    assert 'wait_for_x("99", xvfb)' in source
    assert 'subprocess.Popen(\n            [STEAM, "-silent"]' in source
    assert "env=env" in source
    assert 'DISPLAY = ":99"' in source
    assert 'STEAM = "/usr/bin/steam"' in source


def test_runtime_waits_for_authentication_and_stops_steam_before_xvfb():
    source = SCRIPT.read_text()
    assert "wait_for_steam(steam, old_size)" in source
    assert "RecvMsgClientLogOnResponse()" in source
    assert "[Logged On" in source
    assert "AuthenticationUnavailable" in source
    assert source.index("subprocess.run([STEAM, \"-shutdown\"]") < \
        source.index("finally:\n        stop_process(steam)\n        stop_process(xvfb)")


def test_aurelia_game_launch_graphical_environment_contract_is_unchanged():
    sessiond = (ROOT / "src/lulu/sessiond.py").read_text()
    wrapper = (ROOT / "scripts/aurelia-graphical-launch.py").read_text()
    assert '("DISPLAY", "WAYLAND_DISPLAY", "XDG_RUNTIME_DIR")' in sessiond
    assert "environment.update(graphical_environment)" in wrapper
    assert "_load_context_reader()()" in wrapper
    assert '"DISPLAY=:99"' not in sessiond
    assert '"WAYLAND_DISPLAY=:99"' not in wrapper


def test_installer_and_release_own_ship_the_runtime_service():
    installer = (ROOT / "scripts/install_mudos.py").read_text()
    release = (ROOT / "scripts/release.py").read_text()
    manifest = (ROOT / "packaging/mudos-ownership.json").read_text()
    assert '"lulu-steam-runtime.service": "lulu-steam-runtime.service"' in installer
    assert '"packaging/lulu-steam-runtime.service"' in release
    assert "/etc/systemd/system/lulu-steam-runtime.service" in manifest
    assert "scripts/steam-runtime-session.py" in release
