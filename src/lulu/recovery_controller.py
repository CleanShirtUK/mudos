"""Controller mode handoff for the standalone Mudos Recovery surface."""

from __future__ import annotations

from typing import Protocol

from .contracts import InputMode


class InputPlumberModeClient(Protocol):
    def runtime_composite_statuses(self) -> dict[str, tuple[str, tuple[str, ...]]]: ...
    def load_mode(self, mode: InputMode, object_path: str | None = None) -> list[str]: ...


def apply_recovery_gamepad_mode(client: InputPlumberModeClient) -> tuple[str, ...]:
    """Put connected recovery controllers in native gamepad mode, without restarting IP."""
    composites = client.runtime_composite_statuses()
    applied: list[str] = []
    for object_path, (_identity, source_paths) in sorted(composites.items()):
        if not source_paths:
            continue
        client.load_mode(InputMode.GAME, object_path)
        applied.append(object_path)
    return tuple(applied)
