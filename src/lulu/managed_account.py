"""The single operating-system credential boundary used by Mudos Admin."""

from __future__ import annotations

import ctypes
import ctypes.util
import os
import pwd
import pty
import re
import select
import subprocess
import time
from typing import Callable


ACCOUNT_PATTERN = re.compile(r"^[a-z_][a-z0-9_-]{0,31}$")
MANAGED_ADMIN_ACCOUNT = os.environ.get("LULU_MANAGED_ADMIN_ACCOUNT", "lulu")


class PamMessage(ctypes.Structure):
    _fields_ = [("msg_style", ctypes.c_int), ("msg", ctypes.c_char_p)]


class PamResponse(ctypes.Structure):
    _fields_ = [("resp", ctypes.c_void_p), ("resp_retcode", ctypes.c_int)]


class PamConv(ctypes.Structure):
    pass


_ConvCallback = ctypes.CFUNCTYPE(
    ctypes.c_int, ctypes.c_int,
    ctypes.POINTER(ctypes.POINTER(PamMessage)),
    ctypes.POINTER(ctypes.POINTER(PamResponse)), ctypes.c_void_p,
)
PamConv._fields_ = [("conv", _ConvCallback), ("appdata_ptr", ctypes.c_void_p)]


def _pam_library():
    path = ctypes.util.find_library("pam")
    if not path:
        raise RuntimeError("system PAM is unavailable")
    pam = ctypes.CDLL(path)
    pam.pam_start.argtypes = [ctypes.c_char_p, ctypes.c_char_p,
                              ctypes.POINTER(PamConv), ctypes.POINTER(ctypes.c_void_p)]
    pam.pam_start.restype = ctypes.c_int
    pam.pam_authenticate.argtypes = [ctypes.c_void_p, ctypes.c_int]
    pam.pam_authenticate.restype = ctypes.c_int
    pam.pam_acct_mgmt.argtypes = [ctypes.c_void_p, ctypes.c_int]
    pam.pam_acct_mgmt.restype = ctypes.c_int
    pam.pam_chauthtok.argtypes = [ctypes.c_void_p, ctypes.c_int]
    pam.pam_chauthtok.restype = ctypes.c_int
    pam.pam_end.argtypes = [ctypes.c_void_p, ctypes.c_int]
    pam.pam_end.restype = ctypes.c_int
    return pam


def _run_pam(account: str, service: str, responder: Callable[[str, int], str],
             operation: str, diagnostic: dict[str, int | str] | None = None) -> bool:
    if not ACCOUNT_PATTERN.fullmatch(account):
        raise ValueError("invalid managed Mudos account")
    pam = _pam_library()
    libc = ctypes.CDLL(None)
    libc.calloc.argtypes = [ctypes.c_size_t, ctypes.c_size_t]
    libc.calloc.restype = ctypes.c_void_p
    libc.strdup.argtypes = [ctypes.c_char_p]
    libc.strdup.restype = ctypes.c_void_p
    handle = ctypes.c_void_p()
    prompt_index = 0

    @_ConvCallback
    def converse(count, messages, responses, appdata):
        nonlocal prompt_index
        if count < 0 or count > 32:
            return 19
        memory = libc.calloc(count, ctypes.sizeof(PamResponse))
        if not memory:
            return 5
        items = ctypes.cast(memory, ctypes.POINTER(PamResponse))
        for index in range(count):
            message = messages[index].contents
            if message.msg_style in (1, 2):
                prompt = message.msg.decode("utf-8", errors="replace") if message.msg else ""
                answer = responder(prompt, prompt_index)
                prompt_index += 1
                items[index].resp = libc.strdup(answer.encode("utf-8"))
                if not items[index].resp:
                    return 5
                items[index].resp_retcode = 0
            elif message.msg_style in (3, 4):
                items[index].resp = None
                items[index].resp_retcode = 0
            else:
                return 19
        responses[0] = items
        return 0

    conversation = PamConv(converse, None)
    status = pam.pam_start(service.encode(), account.encode(), ctypes.byref(conversation),
                           ctypes.byref(handle))
    try:
        if status != 0:
            if diagnostic is not None:
                diagnostic.update(phase="start", status=status)
            return False
        if operation == "authenticate":
            status = pam.pam_authenticate(handle, 0)
            phase = "authenticate"
            if status == 0:
                status = pam.pam_acct_mgmt(handle, 0)
                phase = "account"
        elif operation == "change":
            status = pam.pam_chauthtok(handle, 0)
            phase = "password"
        else:
            raise ValueError("unsupported PAM operation")
        if diagnostic is not None:
            diagnostic.update(phase=phase, status=status)
        return status == 0
    finally:
        if handle:
            pam.pam_end(handle, status)


def authenticate_managed_account(password: str, account: str = MANAGED_ADMIN_ACCOUNT) -> bool:
    if not password or "\0" in password:
        return False
    return _run_pam(account, "login", lambda _prompt, _index: password, "authenticate")


def authenticate_managed_account_diagnostic(password: str, account: str) -> tuple[bool, str, int | None]:
    """Authenticate using PAM and return a password-free diagnostic category."""
    if not password or "\0" in password:
        return False, "invalid-credential-input", None
    result: dict[str, int | str] = {}
    try:
        accepted = _run_pam(account, "login", lambda _prompt, _index: password,
                            "authenticate", result)
    except (OSError, RuntimeError, ValueError):
        return False, "pam-policy-or-service-error", None
    status = int(result.get("status", -1))
    phase = str(result.get("phase", "unknown"))
    if accepted:
        return True, "accepted", status
    if status == 10:
        category = "unknown-user"
    elif phase == "account" or status in {3, 4, 6, 9, 12, 13, 14, 22, 28}:
        category = "pam-policy-or-service-error"
    elif status == 7:
        category = "bad-password-or-auth-rejected"
    else:
        category = "pam-policy-or-service-error"
    return False, category, status


def change_managed_account_password(current_password: str, new_password: str,
                                    account: str = MANAGED_ADMIN_ACCOUNT) -> bool:
    if (not current_password or len(new_password) < 8 or len(new_password) > 1024
            or "\0" in current_password + new_password):
        raise ValueError("Use the current Mudos account password and a new password of at least 8 characters")

    try:
        if pwd.getpwuid(os.getuid()).pw_name != account:
            raise RuntimeError("the admin service may only change its own managed account")
    except KeyError as error:
        raise RuntimeError("the managed account is not the admin service account") from error
    master, slave = pty.openpty()
    process = subprocess.Popen(
        ["/usr/bin/passwd", account], stdin=slave, stdout=slave, stderr=slave,
        close_fds=True, start_new_session=True,
        env={**os.environ, "LC_ALL": "C", "TERM": "dumb"},
    )
    os.close(slave)
    output = bytearray()
    sent: set[str] = set()
    deadline = time.monotonic() + 45
    try:
        while time.monotonic() < deadline:
            if process.poll() is not None:
                break
            readable, _, _ = select.select([master], [], [], 0.2)
            if not readable:
                continue
            try:
                chunk = os.read(master, 4096)
            except OSError:
                break
            if not chunk:
                break
            output.extend(chunk)
            prompt = output.decode("utf-8", errors="ignore").casefold()
            response = None
            marker = None
            if "current" in prompt and "password" in prompt and "current" not in sent:
                marker, response = "current", current_password
            elif any(word in prompt for word in ("retype", "again", "repeat", "confirm")) \
                    and "confirmation" not in sent:
                marker, response = "confirmation", new_password
            elif "new" in prompt and "password" in prompt and "new" not in sent:
                marker, response = "new", new_password
            if response is not None and marker is not None:
                os.write(master, response.encode("utf-8") + b"\n")
                sent.add(marker)
                output.clear()
        if process.poll() is None:
            process.kill()
            process.wait(timeout=2)
            return False
        # passwd normally requests current, new, and confirmation. Root-owned
        # bootstrap can omit current-password authentication, but never the
        # two matching new-password prompts.
        return process.returncode == 0 and "new" in sent and "confirmation" in sent
    finally:
        os.close(master)
        if process.poll() is None:
            process.kill()
            process.wait(timeout=2)
