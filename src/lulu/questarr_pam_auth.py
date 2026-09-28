"""Narrow root-owned PAM authenticator for the unprivileged Questarr proxy."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
import pwd
import socket
import socketserver
import struct
import threading
import time
from collections import deque

from .managed_account import authenticate_managed_account_diagnostic

LOGGER = logging.getLogger("lulu.questarr-pam-auth")
SOCKET_PATH = Path("/run/lulu-questarr-pam/auth.sock")
PAM_ACCOUNT = os.environ.get("LULU_QUESTARR_PAM_ACCOUNT", "josh")
PROXY_ACCOUNT = "lulu"
MAX_REQUEST_BYTES = 16 * 1024
_ATTEMPTS: deque[float] = deque()
_ATTEMPT_LOCK = threading.Lock()
_RATE_LIMIT = 20
_RATE_WINDOW = 900


def _allow_attempt(now: float | None = None) -> bool:
    current = time.monotonic() if now is None else now
    with _ATTEMPT_LOCK:
        while _ATTEMPTS and current - _ATTEMPTS[0] >= _RATE_WINDOW:
            _ATTEMPTS.popleft()
        if len(_ATTEMPTS) >= _RATE_LIMIT:
            return False
        _ATTEMPTS.append(current)
        return True


class _Handler(socketserver.StreamRequestHandler):
    def handle(self) -> None:
        self.request.settimeout(10)
        credentials = self.request.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED,
                                              struct.calcsize("3i"))
        _pid, uid, _gid = struct.unpack("3i", credentials)
        try:
            proxy_uid = pwd.getpwnam(PROXY_ACCOUNT).pw_uid
        except KeyError:
            proxy_uid = -1
        if uid != proxy_uid:
            self._reply({"authenticated": False, "category": "proxy-identity-rejected"})
            return

        raw = self.rfile.readline(MAX_REQUEST_BYTES + 1)
        if len(raw) > MAX_REQUEST_BYTES or not raw.endswith(b"\n"):
            self._reply({"authenticated": False, "category": "invalid-request"})
            return
        try:
            value = json.loads(raw)
            username = value.get("username")
            password = value.get("password")
        except (ValueError, AttributeError, TypeError):
            self._reply({"authenticated": False, "category": "invalid-request"})
            return
        if username != PAM_ACCOUNT or not isinstance(password, str) or not password:
            self._reply({"authenticated": False, "category": "identity-rejected"})
            return
        if len(password) > 1024:
            self._reply({"authenticated": False, "category": "invalid-credential-input"})
            return
        if not _allow_attempt():
            self._reply({"authenticated": False, "category": "rate-limited"})
            return

        accepted, category, status = authenticate_managed_account_diagnostic(password, PAM_ACCOUNT)
        # Never include the submitted credential, PAM conversation, or response
        # body in logs. Status and category distinguish policy from bad-auth.
        LOGGER.info("PAM login outcome=%s phase_status=%s", category,
                    status if status is not None else "unavailable")
        self._reply({"authenticated": accepted, "category": category})

    def _reply(self, value: dict[str, object]) -> None:
        try:
            self.wfile.write(json.dumps(value, separators=(",", ":")).encode() + b"\n")
            self.wfile.flush()
        except OSError:
            pass


class _Server(socketserver.ThreadingUnixStreamServer):
    daemon_threads = True
    allow_reuse_address = True


def main() -> None:
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s %(message)s")
    directory = SOCKET_PATH.parent
    directory.mkdir(mode=0o750, parents=True, exist_ok=True)
    os.chmod(directory, 0o750)
    SOCKET_PATH.unlink(missing_ok=True)
    server = _Server(str(SOCKET_PATH), _Handler)
    os.chmod(SOCKET_PATH, 0o660)
    LOGGER.info("PAM authentication helper ready account=%s service=login", PAM_ACCOUNT)
    try:
        server.serve_forever()
    finally:
        server.server_close()
        SOCKET_PATH.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
