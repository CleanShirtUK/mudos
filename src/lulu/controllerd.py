"""Controller identity, assignment, role, and profile intent authority."""

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
import json

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


class BatteryKind(StrEnum):
    PERCENT = "percent"
    COARSE = "coarse"
    UNKNOWN = "unknown"
    NOT_APPLICABLE = "not_applicable"


@dataclass(frozen=True, slots=True)
class BatteryState:
    kind: BatteryKind = BatteryKind.UNKNOWN
    percentage: int | None = None
    state: str | None = None


@dataclass(slots=True)
class Controller:
    controller_id: str
    physical_identity: str | None = None
    capabilities: frozenset[str] = frozenset()
    connected: bool = True
    player: int | None = None
    role: Role = Role.PLAYER
    profile_intent: str | None = None
    battery: BatteryState = field(default_factory=BatteryState)
    # Runtime SDL identity is passed to providers; it is not a provider
    # default and must not be confused with physical assignment identity.
    sdl_index: int | None = None
    sdl_guid: str | None = None
    sdl_name: str | None = None
    button_count: int | None = None
    axis_count: int | None = None
    connection_type: str | None = None
    controller_type: str = "standard_gamepad"

    @property
    def gameplay_eligible(self) -> bool:
        """Eligibility is capability-based, not model/name/VID based."""
        return self.controller_type == "standard_gamepad"


class ControllerRegistry:
    """Normalized controller state; InputPlumber remains device authority."""

    descriptor = DESCRIPTOR

    def __init__(self, policy_path: Path | None = None) -> None:
        self.controllers: dict[str, Controller] = {}
        self.navigation_controller_id: str | None = None
        self.navigation_mode = "all"
        self.policy_path = policy_path
        self._policy: dict[str, object] = {}
        self._runtime_seen = False
        if policy_path is not None:
            try:
                value = json.loads(policy_path.read_text())
                if isinstance(value, dict):
                    self._policy = value
            except (OSError, ValueError, json.JSONDecodeError):
                pass

    def _save_policy(self) -> None:
        if self.policy_path is None:
            return
        self.policy_path.parent.mkdir(parents=True, exist_ok=True)
        self.policy_path.write_text(json.dumps(self._policy, sort_keys=True) + "\n")

    def connect(self, controller: Controller) -> None:
        controller.connected = True
        assignments = self._policy.get("players", {})
        if controller.physical_identity and isinstance(assignments, dict):
            saved_player = assignments.get(controller.physical_identity)
            occupied = {candidate.player for candidate in self.controllers.values()
                        if candidate.connected and candidate.player is not None}
            if (isinstance(saved_player, int) and saved_player in range(1, 5)
                    and saved_player not in occupied):
                controller.player = saved_player
            elif controller.player in occupied:
                controller.player = next(
                    (candidate for candidate in range(1, 5) if candidate not in occupied),
                    None,
                )
        self.controllers[controller.controller_id] = controller

    def disconnect(self, controller_id: str) -> None:
        self.controllers[controller_id].connected = False
        if self.navigation_controller_id == controller_id:
            self._select_navigation_fallback()

    def _select_navigation_fallback(self) -> None:
        if self.navigation_mode == "all":
            self.navigation_controller_id = None
            return
        connected = [
            (controller.player if controller.player is not None else 999, controller_id)
            for controller_id, controller in self.controllers.items()
            if controller.connected
        ]
        self.navigation_controller_id = min(connected)[1] if connected else None
        self._policy["navigation_player"] = (
            self.controllers[self.navigation_controller_id].player
            if self.navigation_controller_id else None
        )
        self._save_policy()

    def assign_player(self, controller_id: str, player: int | None) -> None:
        if controller_id not in self.controllers:
            raise ValueError("unknown controller")
        if player is not None and player not in range(1, 5):
            raise ValueError("player must be between 1 and 4")
        if player is not None:
            for candidate_id, candidate in self.controllers.items():
                if candidate_id != controller_id and candidate.player == player:
                    candidate.player = None
        self.controllers[controller_id].player = player
        identity = self.controllers[controller_id].physical_identity
        if identity:
            players = self._policy.setdefault("players", {})
            if isinstance(players, dict):
                if player is None:
                    players.pop(identity, None)
                else:
                    players[identity] = player
            self._save_policy()

    def set_navigation_controller(self, controller_id: str | None) -> None:
        if controller_id == "all":
            self.navigation_mode = "all"
            self.navigation_controller_id = None
            self._policy["navigation_mode"] = "all"
            self._policy.pop("navigation_identity", None)
            self._policy.pop("navigation_player", None)
            self._save_policy()
            return
        if controller_id is None:
            self.navigation_mode = "automatic"
            self.navigation_controller_id = None
            self._policy["navigation_mode"] = "automatic"
            self._policy.pop("navigation_identity", None)
            self._policy.pop("navigation_player", None)
            self._save_policy()
            self._select_navigation_fallback()
            return
        if controller_id is not None and controller_id not in self.controllers:
            raise ValueError("unknown controller")
        if controller_id is not None and not self.controllers[controller_id].connected:
            raise ValueError("navigation controller must be connected")
        self.navigation_controller_id = controller_id
        self.navigation_mode = "specific"
        identity = self.controllers[controller_id].physical_identity if controller_id else None
        self._policy["navigation_mode"] = "specific"
        self._policy["navigation_identity"] = identity
        self._policy["navigation_player"] = (
            self.controllers[controller_id].player if controller_id else None
        )
        self._save_policy()

    def observe_persistent_composite(self, persistent_id: str, source_paths: tuple[str, ...]) -> None:
        """Reconcile physical presence without replacing InputPlumber targets."""
        if self.navigation_mode == "all":
            self.navigation_controller_id = None
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
        preferred = self._policy.get("navigation_identity")
        preferred_player = self._policy.get("navigation_player")
        if (isinstance(preferred_player, int) and controller.player == preferred_player):
            self.navigation_controller_id = persistent_id
        elif self.navigation_controller_id is None or preferred == persistent_id:
            self.navigation_controller_id = persistent_id

    def observe_runtime_composites(
        self, composites: dict[str, tuple[str, tuple[str, ...]]]
    ) -> None:
        """Assign ordered runtime composites to stable logical player slots."""
        connected_ids = [
            runtime_id for runtime_id, (_, sources) in composites.items() if sources
        ]
        for runtime_id, controller in self.controllers.items():
            if runtime_id not in connected_ids:
                controller.connected = False

        for runtime_id in composites:
            persistent_id, source_paths = composites[runtime_id]
            if not source_paths:
                continue
            controller = self.controllers.get(runtime_id)
            if controller is None or not controller.connected:
                connected_players = {
                    candidate.player
                    for candidate in self.controllers.values()
                    if candidate.connected and candidate.player is not None
                }
                player = next(
                    (candidate for candidate in range(1, 5) if candidate not in connected_players),
                    None,
                )
                controller = Controller(
                    runtime_id,
                    physical_identity=persistent_id or None,
                    player=player,
                )
                self.connect(controller)
            else:
                controller.connected = True

        # Runtime handles can be recreated while a hotplug reconciliation is
        # in flight. Fill any slots that were temporarily unavailable during
        # connect(), without disturbing valid existing assignments.
        used_players: set[int] = set()
        for runtime_id in connected_ids:
            controller = self.controllers[runtime_id]
            if controller.player in range(1, 5) and controller.player not in used_players:
                used_players.add(controller.player)
            else:
                controller.player = next(
                    (player for player in range(1, 5) if player not in used_players), None
                )
                if controller.player is not None:
                    used_players.add(controller.player)

        persisted_mode = self._policy.get("navigation_mode")
        if persisted_mode in {"all", "automatic", "specific"} and not self._runtime_seen:
            self.navigation_mode = persisted_mode
        if self.navigation_mode == "all":
            self.navigation_controller_id = None
            self._runtime_seen = True
            return
        preferred_player = self._policy.get("navigation_player") if not self._runtime_seen else None
        preferred_runtime = next(
            (runtime_id for runtime_id in connected_ids
             if isinstance(preferred_player, int)
             and self.controllers.get(runtime_id) is not None
             and self.controllers[runtime_id].player == preferred_player), None)
        if preferred_runtime is not None:
            self.navigation_controller_id = preferred_runtime
        elif self.navigation_controller_id not in connected_ids:
            self._select_navigation_fallback()
        self._runtime_seen = True

    def request_input_mode(self, mode: InputMode, client: InputPlumberClient) -> list[str]:
        """Ask InputPlumber to load a mapping without changing target topology."""
        return client.load_mode(mode)


def default_inputplumber_client(config_root: Path) -> InputPlumberClient:
    return InputPlumberClient(
        object_path="/org/shadowblip/InputPlumber/CompositeDevice0",
        profile_paths={
            InputMode.SHELL: config_root / "profiles" / "shell.yaml",
            InputMode.GAME: config_root / "profiles" / "game.yaml",
            InputMode.COMPAT: config_root / "profiles" / "compat.yaml",
        },
    )
