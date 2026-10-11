"""Classify Steam authentication logs without exposing their contents."""
from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Iterable


class AuthenticationStatus(Enum):
    AUTHENTICATED = "authenticated"
    NOT_AUTHENTICATED = "not_authenticated"
    UNKNOWN = "unknown"


def status_from_lines(lines: Iterable[bytes]) -> AuthenticationStatus:
    """Recognize a successful logon response; never return or retain log text."""
    successful_response = False
    logged_on = False
    for line in lines:
        if b"RecvMsgClientLogOnResponse()" in line and b"'OK'" in line:
            successful_response = True
        if b"[Logged On" in line:
            logged_on = True
        if successful_response and logged_on:
            return AuthenticationStatus.AUTHENTICATED
    return AuthenticationStatus.NOT_AUTHENTICATED


def status_since(path: Path, offset: int) -> AuthenticationStatus:
    """Return a predefined status for bytes appended after *offset* only."""
    if offset < 0:
        return AuthenticationStatus.UNKNOWN
    try:
        with path.open("rb") as log:
            size = log.seek(0, 2)
            if size < offset:
                return AuthenticationStatus.UNKNOWN
            log.seek(offset)
            return status_from_lines(log)
    except OSError:
        return AuthenticationStatus.UNKNOWN


def diagnostic_fields(status: AuthenticationStatus) -> dict[str, str]:
    """Project evidence to an allowlisted value suitable for diagnostics."""
    if not isinstance(status, AuthenticationStatus):
        return {"authentication": AuthenticationStatus.UNKNOWN.value}
    return {"authentication": status.value}
