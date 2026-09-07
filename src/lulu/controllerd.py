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

    def observe_persistent_composite(self, persistent_id: str, source_paths: tuple[str, ...]) -> None:
        """Reconcile physical presence without replacing InputPlumber targets."""
        if not persistent_id or not source_paths:
            for controller_id, controller in self.controllers.items():
                if controller.connected:
                    controller.connected = False
                if self.navigation_controller_id == controller_id:
                    self.navigation_controller_id = None
            return
        controller = self.controllers.get(persistent_id)
        if controller is None:
            controller = Controller(persistent_id, player=1)
            self.connect(controller)
        else:
            controller.connected = True
        if self.navigation_controller_id is None:
            self.navigation_controller_id = persistent_id

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
