"""Authoritative session lifecycle and orthogonal presentation policy state."""

from dataclasses import dataclass
from uuid import uuid4
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .process_supervisor import ProcessResult

from .contracts import InputMode, Lifecycle, Overlay, Presentation, ServiceDescriptor, ServiceName


DESCRIPTOR = ServiceDescriptor(
    name=ServiceName.CONSOLE_SESSIOND,
    authority="current session, lifecycle, presentation, overlay, and input policy",
    owned_state=("current game/application", "lifecycle", "presentation", "overlay", "input mode"),
    notes=("Gamescope presents; it does not determine lifecycle authority.",),
)


@dataclass(slots=True)
class SessionState:
    lifecycle: Lifecycle = Lifecycle.SHELL
    presentation: Presentation = Presentation.SHELL
    overlay: Overlay = Overlay.CLOSED
    input_mode: InputMode = InputMode.SHELL
    primary_id: str | None = None
    launch_token: str | None = None
    delegated_surface: str | None = None
    requested_surface: str | None = None
    session_kind: str = "shell"
    provider_id: str | None = None
    controller_mode: str | None = None


class SessionStateModel:
    descriptor = DESCRIPTOR

    def __init__(self) -> None:
        self.state = SessionState()
        self.last_failure_reason: str | None = None
        self.last_result: ProcessResult | None = None

    def request_launch(self, primary_id: str) -> str:
        if self.state.lifecycle is not Lifecycle.SHELL:
            raise ValueError("launch requires the shell lifecycle")
        if not primary_id:
            raise ValueError("primary id is required")
        token = uuid4().hex
        self.last_failure_reason = None
        self.state.primary_id = primary_id
        if primary_id.startswith("provider:"):
            self.state.session_kind = "provider_standalone"
            self.state.provider_id = primary_id.split(":", 2)[1]
        else:
            self.state.session_kind = "game"
            self.state.provider_id = None
        self.state.launch_token = token
        self.state.lifecycle = Lifecycle.LAUNCH_REQUESTED
        return token

    def launch_starting(self, token: str) -> None:
        if self.state.lifecycle is not Lifecycle.LAUNCH_REQUESTED:
            raise ValueError("launch can enter starting only after request")
        self._check_token(token)
        self.state.lifecycle = Lifecycle.STARTING

    def record_result(self, result: "ProcessResult") -> None:
        self.last_result = result

    def _check_token(self, token: str) -> None:
        if token != self.state.launch_token:
            raise ValueError("launch token does not own the active session")

    def primary_started(
        self,
        token: str,
        *,
        presentation: Presentation = Presentation.GAME,
        input_mode: InputMode = InputMode.GAME,
    ) -> None:
        if self.state.lifecycle not in (Lifecycle.STARTING, Lifecycle.PRESENTATION_PENDING):
            raise ValueError("primary can start only while launching")
        self._check_token(token)
        self.state.lifecycle = Lifecycle.GAME
        self.state.presentation = presentation
        self.state.input_mode = input_mode
        if self.state.primary_id == "steam-store":
            self.state.delegated_surface = "store"
        elif str(self.state.primary_id or "").startswith("steam-install:"):
            self.state.delegated_surface = "steam-install"

    def set_delegated_surface(self, surface: str) -> None:
        if self.state.primary_id != "steam-store" or self.state.lifecycle is not Lifecycle.GAME:
            raise ValueError("Steam Store delegated surface is not active")
        if surface != "store":
            raise ValueError("invalid delegated Steam surface")
        self.state.delegated_surface = surface

    def request_surface(self, surface: str) -> None:
        if surface != "downloads":
            raise ValueError("invalid Mudos surface")
        self.state.requested_surface = surface

    def clear_requested_surface(self) -> None:
        self.state.requested_surface = None

    def primary_observed(self, token: str) -> None:
        if self.state.lifecycle is not Lifecycle.STARTING:
            raise ValueError("primary can be observed only while starting")
        self._check_token(token)
        self.state.lifecycle = Lifecycle.PRESENTATION_PENDING

    def primary_exited(self, token: str, *, success: bool = True) -> None:
        if self.state.lifecycle is not Lifecycle.GAME:
            raise ValueError("primary can exit only while running")
        self._check_token(token)
        if not success:
            self.last_failure_reason = "primary exited unsuccessfully"
        self.state.lifecycle = Lifecycle.RETURNING

    def fail(self, token: str, reason: str) -> None:
        if self.state.lifecycle not in (
            Lifecycle.LAUNCH_REQUESTED,
            Lifecycle.STARTING,
            Lifecycle.PRESENTATION_PENDING,
            Lifecycle.GAME,
        ):
            raise ValueError("failure requires an active launch")
        self._check_token(token)
        if not reason:
            raise ValueError("failure reason is required")
        self.last_failure_reason = reason
        self.state.lifecycle = Lifecycle.RETURNING

    def return_complete(self, token: str) -> None:
        if self.state.lifecycle is not Lifecycle.RETURNING:
            raise ValueError("return cleanup requires returning lifecycle")
        self._check_token(token)
        self.state = SessionState()

    def return_failed(self, token: str, reason: str) -> None:
        if self.state.lifecycle is not Lifecycle.RETURNING:
            raise ValueError("return failure requires returning lifecycle")
        self._check_token(token)
        if not reason:
            raise ValueError("return failure reason is required")
        self.last_failure_reason = reason

    def set_input_mode(self, mode: InputMode) -> None:
        self.state.input_mode = mode

    def set_overlay(self, overlay: Overlay) -> None:
        self.state.overlay = overlay
