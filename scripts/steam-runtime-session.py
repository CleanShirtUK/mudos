#!/usr/bin/python3
"""Run authenticated host Steam on its session-private Xvfb display."""
from __future__ import annotations

import os
from pathlib import Path
import pwd
import signal
import socket
import subprocess
import sys
import time

DISPLAY = ":99"
STEAM = "/usr/bin/steam"
XVFB = "/usr/bin/Xvfb"
LOGIN_LOG = Path("/home/lulu/.local/share/Steam/logs/connection_log.txt")
stopping = False


class AuthenticationUnavailable(RuntimeError):
    """Steam did not restore its saved authenticated session."""


def notify(message: str) -> None:
    address = os.environ.get("NOTIFY_SOCKET")
    if not address:
        return
    if address.startswith("@"):
        address = "\0" + address[1:]
    with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as client:
        client.connect(address)
        client.sendall(message.encode())


def runtime_directory() -> str:
    account = pwd.getpwnam("lulu")
    result = subprocess.run(
        ["/usr/bin/loginctl", "show-user", account.pw_name, "--property=RuntimePath", "--value"],
        check=True, capture_output=True, text=True, timeout=10,
    ).stdout.strip()
    path = Path(result)
    if not result or not path.is_absolute() or not path.is_dir():
        raise RuntimeError("active lulu user session has no usable runtime directory")
    return result


def isolated_environment(runtime: str) -> dict[str, str]:
    # Construct rather than inherit: DISPLAY/WAYLAND and other graphical Mudos
    # variables must never pass from the appliance session to host Steam.
    return {
        "HOME": "/home/lulu", "USER": "lulu", "LOGNAME": "lulu",
        "PATH": "/usr/local/bin:/usr/bin", "DISPLAY": DISPLAY,
        "XDG_RUNTIME_DIR": runtime,
        "DBUS_SESSION_BUS_ADDRESS": f"unix:path={runtime}/bus",
    }


def wait_for_x(display_number: str, process: subprocess.Popen[bytes], timeout: float = 20) -> None:
    socket_path = Path(f"/tmp/.X11-unix/X{display_number}")
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError("Xvfb exited before its display became ready")
        if socket_path.exists():
            # Socket creation precedes server readiness by a short interval.
            probe = socket.socket(socket.AF_UNIX)
            try:
                probe.settimeout(0.2)
                probe.connect(str(socket_path))
                return
            except OSError:
                time.sleep(0.1)
            finally:
                probe.close()
        time.sleep(0.1)
    raise RuntimeError("timed out waiting for the Xvfb display")


def wait_for_steam(steam: subprocess.Popen[bytes], previous_log_size: int,
                   timeout: float = 150) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if steam.poll() is not None and not steam_main_pids():
            raise RuntimeError(f"Steam exited during startup (status {steam.returncode})")
        try:
            with LOGIN_LOG.open("rb") as log:
                log.seek(previous_log_size)
                recent = log.read().decode(errors="replace")
        except FileNotFoundError:
            recent = ""
        if "RecvMsgClientLogOnResponse()" in recent and "'OK'" in recent and "[Logged On" in recent:
            return
        time.sleep(0.5)
    raise AuthenticationUnavailable(
        "Steam did not restore authentication within 150 seconds; manual sign-in on :99 is required"
    )


def steam_main_pids() -> list[int]:
    """Return native host Steam processes, excluding web helpers and games."""
    result = []
    for entry in Path("/proc").iterdir():
        if not entry.name.isdecimal():
            continue
        try:
            executable = (entry / "exe").resolve()
            if executable != Path("/home/lulu/.local/share/Steam/ubuntu12_32/steam"):
                continue
            environ = (entry / "environ").read_bytes().split(b"\0")
            if b"DISPLAY=:99" in environ:
                result.append(int(entry.name))
        except (OSError, PermissionError):
            continue
    return result


def wait_for_steam_exit(timeout: float = 20) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline and steam_main_pids():
        time.sleep(0.25)


def request_stop(_signum: int, _frame: object) -> None:
    global stopping
    stopping = True


def stop_process(process: subprocess.Popen[bytes] | None, timeout: float = 15) -> None:
    if process is None or process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def main() -> int:
    global stopping
    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)
    xvfb: subprocess.Popen[bytes] | None = None
    steam: subprocess.Popen[bytes] | None = None
    env = isolated_environment(runtime_directory())
    try:
        if Path("/tmp/.X11-unix/X99").exists() or Path("/tmp/.X99-lock").exists():
            raise RuntimeError("refusing to take over an existing X display :99")
        xvfb = subprocess.Popen(
            [XVFB, DISPLAY, "-screen", "0", "1280x720x24", "-nolisten", "tcp", "-noreset"],
            env=env, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=None,
        )
        wait_for_x("99", xvfb)
        old_size = LOGIN_LOG.stat().st_size if LOGIN_LOG.exists() else 0
        steam = subprocess.Popen(
            [STEAM, "-silent"], env=env, stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL, stderr=None,
        )
        wait_for_steam(steam, old_size)
        notify("READY=1\nSTATUS=Steam authenticated on isolated Xvfb :99")
        while not stopping:
            if xvfb.poll() is not None:
                raise RuntimeError(f"Xvfb exited unexpectedly (status {xvfb.returncode})")
            if not steam_main_pids():
                raise RuntimeError("native Steam client exited unexpectedly")
            time.sleep(1)
        # Graceful client shutdown before the display is removed.
        subprocess.run([STEAM, "-shutdown"], env=env, stdin=subprocess.DEVNULL,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=20,
                       check=False)
        wait_for_steam_exit()
        stop_process(steam)
        return 0
    except Exception as error:
        print(f"steam-runtime-session: {error}", file=sys.stderr, flush=True)
        if isinstance(error, AuthenticationUnavailable):
            return 78
        return 1
    finally:
        stop_process(steam)
        stop_process(xvfb)


if __name__ == "__main__":
    raise SystemExit(main())
