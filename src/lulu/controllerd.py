"""Controller identity, assignment, role, and profile intent authority."""

from dataclasses import dataclass
from pathlib import Path

from .contracts import InputMode, Role, ServiceDescriptor, ServiceName
from .inputplumber import InputPlumberClient


DESCRIPTOR = ServiceDescriptor(
    name=ServiceName.CONTROLLERD,
    authority="physical controller and logical controller intent",
    owned_state=(
        "physical identity",
        "capabilities",
        "connection state",
        "player assignment",
        "role",
        "profile intent",
    ),
    notes=("InputPlumber owns actual runtime routing and virtual presentation.",),
)


@dataclass(slots=True)
class Controller:
    controller_id: str
    capabilities: frozenset[str] = frozenset()
    connected: bool = True
    player: int | None = None
    role: Role = Role.PLAYER
    profile_intent: str | None = None


class ControllerRegistry:
    """In-memory contract model; persistence and device discovery are deferred."""

    descriptor = DESCRIPTOR

    def __init__(self) -> None:
        self.controllers: dict[str, Controller] = {}
        self.navigation_controller_id: str | None = None

    def connect(self, controller: Controller) -> None:
        controller.connected = True
        self.controllers[controller.controller_id] = controller

    def disconnect(self, controller_id: str) -> None:
        self.controllers[controller_id].connected = False
        if self.navigation_controller_id == controller_id:
            self.navigation_controller_id = None

    def assign_player(self, controller_id: str, player: int | None) -> None:
        self.controllers[controller_id].player = player

    def set_navigation_controller(self, controller_id: str | None) -> None:
        if controller_id is not None and not self.controllers[controller_id].connected:
            raise ValueError("navigation controller must be connected")
        self.navigation_controller_id = controller_id

    def request_input_mode(self, mode: InputMode, client: InputPlumberClient) -> list[str]:
        """Ask InputPlumber to load a mapping without changing target topology."""
        return client.load_mode(mode)


def default_inputplumber_client(config_root: Path) -> InputPlumberClient:
    return InputPlumberClient(
        object_path="/org/shadowblip/InputPlumber/CompositeDevice0",
        profile_paths={
            mode: config_root / "profiles" / f"{mode.value}.yaml"
            for mode in InputMode
        },
    )
