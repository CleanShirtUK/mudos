"""Shared process identity records."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class LaunchIdentity:
    token: str
    pid: int
    pgid: int
    executable: str
    argv: tuple[str, ...]
