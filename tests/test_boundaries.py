import unittest
import asyncio
import subprocess
from pathlib import Path
import tempfile
from unittest.mock import AsyncMock, patch
from dbus_next import MessageType

from lulu.applicationd import ApplicationCatalog
from lulu.console_sessiond import SessionStateModel
from lulu.console_ui import ConsoleUi
from lulu.consoled import ConsoleCatalog
from lulu.catalogue import CatalogueGame, CatalogueStore
from lulu.metadata import MetadataCandidate
from lulu.controllerd import BatteryKind, BatteryState, Controller, ControllerRegistry
from lulu.controllerd import default_inputplumber_client
from lulu.inputplumber import InputPlumberClient
from lulu.contracts import InputMode, Lifecycle, Overlay, Role, ServiceName
from lulu.gamescope import GamescopeInvocation, GamescopePresentation, discover_presentation_output
from lulu.launch_identity import LaunchIdentity
from lulu.sessiond import ConsoleSessionInterface


class RecordingInputPlumber:
    def __init__(self, composites: dict[str, tuple[str, tuple[str, ...]]]) -> None:
        self.composites = composites
        self.loads: list[tuple[InputMode, str | None]] = []
        self.intercepts: list[tuple[int, str | None]] = []
        self.baselines: list[str | None] = []

    def runtime_composite_statuses(self) -> dict[str, tuple[str, tuple[str, ...]]]:
        return self.composites

    def load_mode(
        self, mode: InputMode, object_path: str | None = None, *, execute: bool = True
    ) -> list[str]:
        self.loads.append((mode, object_path))
        return []

    def set_intercept_mode(
        self, mode: int, object_path: str | None = None, *, execute: bool = True
    ) -> list[str]:
        self.intercepts.append((mode, object_path))
        return []

    def composite_status(self, object_path: str) -> tuple[str, tuple[str, ...]]:
        return self.composites[object_path]

    def ensure_default_intercept(self, object_path: str | None = None, *, execute: bool = True) -> list[list[str]]:
        self.baselines.append(object_path)
        self.intercepts.append((1, object_path))
        return []


def input_mode_interface(
    client: RecordingInputPlumber,
) -> ConsoleSessionInterface:
    interface = ConsoleSessionInterface.__new__(ConsoleSessionInterface)
    interface._inputplumber = client
    interface._applied_input_modes = {}
    interface._local_identity = None
    interface.model = SessionStateModel()
    interface.controller_registry = ControllerRegistry()
    interface.supervisor = type("Supervisor", (), {"state_details": lambda self: {}})()
    interface.StateChanged = lambda state: None
    return interface


class BoundaryTests(unittest.TestCase):
    def test_gamescope_waits_for_late_steam_window_and_refreshes_pids(self) -> None:
        presentation = GamescopePresentation(poll_interval=0.001)
        pid_sets = [[], [1234]]
        polls = 0

        def current_pids():
            return pid_sets[0]

        def windows():
            nonlocal polls
            polls += 1
            if polls == 3:
                pid_sets[0] = pid_sets[1]
                return []
            if polls == 4:
                return [(456, 0, 1234)]
            return []

        presentation._focusable_windows = windows
        selected = presentation.window_for_pids(current_pids, timeout=1,
                                                  process_alive=lambda: True)
        self.assertEqual(selected, 456)
        self.assertGreaterEqual(polls, 3)

    def test_gamescope_window_wait_fails_when_owned_tree_exits(self) -> None:
        presentation = GamescopePresentation(poll_interval=0)
        presentation._focusable_windows = lambda: []
        with self.assertRaisesRegex(RuntimeError, "process tree exited"):
            presentation.window_for_pids(lambda: [1234], timeout=10,
                                          process_alive=lambda: False)

    def test_capable_source_is_inventory_fallback_when_composite_order_is_empty(self) -> None:
        from unittest.mock import patch

        class SourceOnlyClient(InputPlumberClient):
            def gamepad_order(self, *, execute: bool = True) -> tuple[str, ...]:
                return ()

            def _source_gamepad_path(self, *, execute: bool = True) -> str | None:
                return "/org/shadowblip/InputPlumber/devices/source/event8"

        client = SourceOnlyClient("/org/shadowblip/InputPlumber/CompositeDevice0", {})
        with patch("lulu.inputplumber.subprocess.run", return_value=type(
            "Result", (), {"stdout": ""}
        )()):
            self.assertEqual(
                client.runtime_composite_statuses(),
                {
                    "/org/shadowblip/InputPlumber/CompositeDevice0": (
                        "source:event8",
                        ("/org/shadowblip/InputPlumber/devices/source/event8",),
                    )
                },
            )
            self.assertEqual(client.runtime_gamepad_slots()[0][-1], 0)

    def test_console_catalog_metadata_search_exposes_duplicate_candidates(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = CatalogueStore(Path(directory) / "catalogue.sqlite3")
            store._upsert(CatalogueGame(
                "local:ps2:1", "local", "local:ps2:1", "Shadow of the Colossus", "ps2",
                "installed", True, "/roms/shadow.iso", "", 0, source_title="Shadow of the Colossus",
                normalized_search_title="Shadow of the Colossus",
            ))
            store.connection.commit()

            class FakeMetadata:
                def search(self, query, platform):
                    return [MetadataCandidate("86", "Shadow of the Colossus"), MetadataCandidate("5414306", "Shadow of the Colossus")]

            catalogue = ConsoleCatalog(store=store, metadata=FakeMetadata())
            results = catalogue.metadata_search("local:ps2:1", "Shadow of the Colossus")

        self.assertEqual([result["id"] for result in results], ["86", "5414306"])

    def test_metadata_match_operations_preserve_launch_identity(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = CatalogueStore(Path(directory) / "catalogue.sqlite3")
            store._upsert(CatalogueGame(
                "local:nes:1", "local", "local:nes:1", "Mario", "nes", "installed", True,
                "/roms/mario.nes", "", 0, source_title="Mario", normalized_search_title="Mario",
            ))
            store.connection.commit()
            catalogue = ConsoleCatalog(store=store)
            catalogue.artwork = type("Artwork", (), {
                "reload_configuration": lambda self: None,
                "resolve_typed": lambda self, game: None,
            })()
            catalogue.apply_metadata_match("local:nes:1", "steamgriddb", "42", "Mario Kart")
            record = store.get_game("local:nes:1")

        self.assertEqual((record.provider, record.provider_id), ("local", "local:nes:1"))
        self.assertEqual((record.metadata_provider, record.metadata_game_id, record.match_status),
                         ("steamgriddb", "42", "manual"))

    def test_metadata_search_failure_does_not_mutate_game(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = CatalogueStore(Path(directory) / "catalogue.sqlite3")
            store._upsert(CatalogueGame(
                "local:nes:1", "local", "local:nes:1", "Mario", "nes", "installed", True,
                "/roms/mario.nes", "", 0, source_title="Mario", normalized_search_title="Mario",
            ))
            store.connection.commit()

            class FailedMetadata:
                def search(self, query, platform):
                    return None

            catalogue = ConsoleCatalog(store=store, metadata=FailedMetadata())
            self.assertEqual(catalogue.metadata_search("local:nes:1", "Mario"), [])
            record = store.get_game("local:nes:1")

        self.assertEqual((record.title, record.metadata_game_id, record.match_status), ("Mario", "", ""))
    def test_all_first_step_boundaries_are_explicit(self) -> None:
        self.assertEqual(
            {
                ControllerRegistry.descriptor.name,
                SessionStateModel.descriptor.name,
                ConsoleCatalog.descriptor.name,
                ApplicationCatalog.descriptor.name,
                ConsoleUi.descriptor.name,
                ServiceName.ACQUISITIOND,
            },
            set(ServiceName),
        )

    def test_controller_navigation_is_separate_from_player_assignment(self) -> None:
        registry = ControllerRegistry()
        controller = Controller("pad-a", role=Role.PLAYER)
        registry.connect(controller)
        registry.assign_player("pad-a", 1)
        registry.set_navigation_controller("pad-a")
        self.assertEqual(registry.controllers["pad-a"].player, 1)
        self.assertEqual(registry.navigation_controller_id, "pad-a")

    def test_all_navigation_accepts_every_assigned_controller_without_changing_players(self) -> None:
        registry = ControllerRegistry()
        registry.observe_runtime_composites({
            "CompositeDevice0": ("pad-a", ("/dev/input/event1",)),
            "CompositeDevice1": ("pad-b", ("/dev/input/event2",)),
        })
        registry.set_navigation_controller("all")
        self.assertEqual(registry.navigation_mode, "all")
        self.assertIsNone(registry.navigation_controller_id)
        self.assertEqual(registry.controllers["CompositeDevice0"].player, 1)
        self.assertEqual(registry.controllers["CompositeDevice1"].player, 2)
        registry.observe_runtime_composites({
            "CompositeDevice1": ("pad-b", ("/dev/input/event3",)),
        })
        self.assertEqual(registry.navigation_mode, "all")
        self.assertIsNone(registry.navigation_controller_id)
        self.assertTrue(registry.controllers["CompositeDevice1"].connected)

    def test_specific_navigation_still_restricts_to_selected_controller(self) -> None:
        registry = ControllerRegistry()
        registry.observe_runtime_composites({
            "CompositeDevice0": ("pad-a", ("/dev/input/event1",)),
            "CompositeDevice1": ("pad-b", ("/dev/input/event2",)),
        })
        registry.set_navigation_controller("CompositeDevice1")
        self.assertEqual(registry.navigation_mode, "specific")
        self.assertEqual(registry.navigation_controller_id, "CompositeDevice1")
        registry.set_navigation_controller("all")
        self.assertEqual(registry.navigation_mode, "all")
        self.assertIsNone(registry.navigation_controller_id)

    def test_controller_policy_has_no_button_mapping_surface(self) -> None:
        source = (Path(__file__).parents[1] / "ui/ControllerSettings.qml").read_text()
        self.assertIn("operationRequested", source)
        self.assertIn('view === "player"', source)
        self.assertIn('view === "navigation"', source)
        self.assertIn('label: "Player " + player', source)
        self.assertNotIn("buttonMap", source)
        self.assertNotIn("remap", source.lower())

    def test_persisted_player_assignment_does_not_duplicate_on_rebind(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            policy = Path(directory) / "controller-policy.json"
            policy.write_text('{"players": {"receiver": 1}}')
            registry = ControllerRegistry(policy)
            registry.observe_runtime_composites({
                "CompositeDevice0": ("receiver", ("/dev/input/event1",)),
                "CompositeDevice1": ("receiver", ("/dev/input/event2",)),
            })
            players = [controller.player for controller in registry.controllers.values()]
            self.assertEqual(sorted(player for player in players if player is not None), [1, 2])

    def test_navigation_policy_follows_logical_player_when_identity_is_shared(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            policy = Path(directory) / "controller-policy.json"
            registry = ControllerRegistry(policy)
            registry.observe_runtime_composites({
                "CompositeDevice0": ("receiver", ("/dev/input/event1",)),
                "CompositeDevice1": ("receiver", ("/dev/input/event2",)),
            })
            registry.set_navigation_controller("CompositeDevice1")
            restored = ControllerRegistry(policy)
            restored.observe_runtime_composites({
                "CompositeDevice0": ("receiver", ("/dev/input/event3",)),
                "CompositeDevice1": ("receiver", ("/dev/input/event4",)),
            })
            self.assertEqual(restored.navigation_controller_id, "CompositeDevice1")


    def test_controller_battery_normalization_preserves_unknown(self) -> None:
        controller = Controller("pad-a", battery=BatteryState())
        self.assertEqual(controller.battery.kind, BatteryKind.UNKNOWN)
        self.assertIsNone(controller.battery.percentage)

        controller.battery = BatteryState(BatteryKind.PERCENT, 87)
        self.assertEqual(controller.battery.percentage, 87)

    def test_controller_indices_are_preserved_when_runtime_order_changes(self) -> None:
        registry = ControllerRegistry()
        registry.observe_runtime_composites({
            "CompositeDevice0": ("pad-a", ("/dev/input/event1",)),
            "CompositeDevice1": ("pad-b", ("/dev/input/event2",)),
        })
        self.assertEqual(registry.controllers["CompositeDevice0"].player, 1)
        self.assertEqual(registry.controllers["CompositeDevice1"].player, 2)
        registry.observe_runtime_composites({
            "CompositeDevice1": ("pad-b", ("/dev/input/event2",)),
        })
        self.assertFalse(registry.controllers["CompositeDevice0"].connected)
        self.assertEqual(registry.controllers["CompositeDevice1"].player, 2)

    def test_disconnect_releases_navigation_ownership_only(self) -> None:
        registry = ControllerRegistry()
        registry.connect(Controller("pad-a"))
        registry.assign_player("pad-a", 1)
        registry.set_navigation_controller("pad-a")
        registry.disconnect("pad-a")
        self.assertIsNone(registry.navigation_controller_id)
        self.assertEqual(registry.controllers["pad-a"].player, 1)

    def test_session_lifecycle_and_orthogonal_state(self) -> None:
        session = SessionStateModel()
        token = session.request_launch("game-1")
        self.assertEqual(session.state.lifecycle, Lifecycle.LAUNCH_REQUESTED)
        session.launch_starting(token)
        self.assertEqual(session.state.lifecycle, Lifecycle.STARTING)
        session.primary_started(token)
        self.assertEqual(session.state.lifecycle, Lifecycle.GAME)
        self.assertEqual(session.state.input_mode, InputMode.GAME)
        session.set_overlay(Overlay.OPEN)
        session.primary_exited(token)
        self.assertEqual(session.state.lifecycle, Lifecycle.RETURNING)
        session.return_complete(token)
        self.assertEqual(session.state.lifecycle, Lifecycle.SHELL)
        self.assertEqual(session.state.overlay, Overlay.CLOSED)

    def test_controllerd_loads_mode_profiles_without_target_replacement(self) -> None:
        client = default_inputplumber_client(Path("config/inputplumber"))
        command = client.load_mode(InputMode.COMPAT, execute=False)
        self.assertEqual(command[-1], "config/inputplumber/profiles/compat.yaml")
        self.assertNotIn("SetTargetDevices", command)

    def test_compatibility_mode_round_trip_applies_profiles(self) -> None:
        path = "/org/shadowblip/InputPlumber/CompositeDevice0"
        client = RecordingInputPlumber({path: ("045e_0291", ("/dev/input/event13",))})
        interface = input_mode_interface(client)
        token = interface.model.request_launch("game-1")
        interface.model.launch_starting(token)
        interface.model.primary_started(token)

        interface.SetInputMode("compat")
        interface.SetInputMode("gamepad")

        self.assertEqual(
            client.loads[-2:],
            [(InputMode.COMPAT, path), (InputMode.GAME, path)],
        )
        self.assertEqual(interface.model.state.input_mode, InputMode.GAME)

    def test_local_session_enters_and_leaves_authoritative_game_state(self) -> None:
        path = "/org/shadowblip/InputPlumber/CompositeDevice0"
        client = RecordingInputPlumber({path: ("045e_0291", ("/dev/input/event13",))})
        interface = input_mode_interface(client)
        interface.BeginLocalSession("local:wii:game", 123, 123, "/usr/bin/dolphin-emu", ["dolphin-emu", "-e", "game.rvz"])

        state = interface.model.state
        self.assertEqual(state.lifecycle, Lifecycle.GAME)
        self.assertEqual(state.primary_id, "local:wii:game")
        self.assertEqual(state.input_mode, InputMode.GAME)
        self.assertEqual(interface._local_identity.executable, "/usr/bin/dolphin-emu")

        interface.EndLocalSession(interface._local_identity.token, 0)

        self.assertEqual(interface.model.state.lifecycle, Lifecycle.SHELL)
        self.assertIsNone(interface._local_identity)
        self.assertEqual(interface.model.state.input_mode, InputMode.SHELL)

    def test_local_session_restores_shell_even_if_controller_profile_restore_fails(self) -> None:
        interface = input_mode_interface(RecordingInputPlumber({}))
        presentation = type("Presentation", (), {
            "select_shell": lambda self, pid: setattr(self, "selected_shell", pid),
        })()
        interface.supervisor = type("Supervisor", (), {
            "state_details": lambda self: {}, "_presentation": presentation,
            "_shell_process": type("Shell", (), {"pid": 99})(),
        })()
        token = interface.model.request_launch("local:test:game")
        interface.model.launch_starting(token)
        interface._local_identity = LaunchIdentity(token, 123, 123, "/usr/bin/sleep", ("sleep",))
        interface._local_provider_id = "steam"
        interface.model.primary_started(token)
        with patch.object(interface, "_apply_input_mode", side_effect=RuntimeError("controller disconnected")):
            interface.EndLocalSession(token, -15)
        self.assertEqual(interface.model.state.lifecycle, Lifecycle.SHELL)
        self.assertEqual(interface.model.state.input_mode, InputMode.SHELL)
        self.assertIsNone(interface._local_identity)
        self.assertEqual(presentation.selected_shell, 99)

    def test_steam_provider_surface_selects_client_window_and_restores_shell(self) -> None:
        class Presentation:
            def __init__(self):
                self.selected = []

            def select_pids(self, pids, timeout, process_alive=None):
                self.selected.append((pids(), timeout))
                return 456

            def select_shell(self, pid):
                self.selected.append(("shell", pid))

        interface = input_mode_interface(RecordingInputPlumber({}))
        presentation = Presentation()
        interface.supervisor = type("Supervisor", (), {
            "state_details": lambda self: {}, "_presentation": presentation,
            "_shell_process": type("Shell", (), {"pid": 99})(),
        })()
        with patch("lulu.plugins.steam.provider.SteamProvider.desktop_pids", return_value=[456]):
            interface.BeginProviderSession("steam", "compat", 123, 123,
                                           "/usr/bin/sleep", ["sleep"], 123)
        self.assertEqual(presentation.selected, [([456], 225.0)])
        self.assertEqual(interface.model.state.input_mode, InputMode.COMPAT)
        self.assertEqual(interface.model.state.lifecycle, Lifecycle.GAME)
        self.assertEqual(interface._local_provider_id, "steam")
        interface.EndLocalSession(interface._local_identity.token, 0)
        self.assertEqual(presentation.selected[-1], ("shell", 99))

    def test_local_runtime_window_is_selected_and_shell_restored_on_exit(self) -> None:
        class Presentation:
            def __init__(self):
                self.selected = []

            def select_pids(self, pids, timeout):
                self.selected.append((pids, timeout))

            def select_shell(self, pid):
                self.selected.append(("shell", pid))

        interface = input_mode_interface(RecordingInputPlumber({}))
        presentation = Presentation()
        interface.supervisor = type("Supervisor", (), {
            "state_details": lambda self: {}, "_presentation": presentation,
            "_shell_process": type("Shell", (), {"pid": 99})(),
        })()
        interface.BeginLocalSession("local:gamecube:fixture", 123, 123,
                                    "/usr/bin/dolphin-emu", ["dolphin-emu", "fixture.iso"])
        self.assertEqual(presentation.selected, [([123], 15.0)])
        interface.EndLocalSession(interface._local_identity.token, 0)
        self.assertEqual(presentation.selected[-1], ("shell", 99))

    def test_failed_local_session_does_not_leave_state_owned(self) -> None:
        class FailingInputPlumber(RecordingInputPlumber):
            def load_mode(self, mode, object_path=None, *, execute=True):
                raise OSError("profile unavailable")

        interface = input_mode_interface(FailingInputPlumber({}))
        with self.assertRaises(Exception):
            interface.BeginLocalSession("local:wii:game", 123, 123, "/usr/bin/dolphin-emu", ["dolphin-emu"])
        self.assertEqual(interface.model.state.lifecycle, Lifecycle.SHELL)
        self.assertIsNone(interface._local_identity)

    def test_compatibility_mode_is_rejected_in_shell(self) -> None:
        interface = input_mode_interface(RecordingInputPlumber({}))
        with self.assertRaisesRegex(Exception, "Compatibility Mode"):
            interface.SetInputMode("compat")

    def test_compatibility_profile_keeps_guide_intercepted_and_required_bindings(self) -> None:
        profile = (Path(__file__).parents[1] / "config/inputplumber/profiles/compat.yaml").read_text()
        self.assertIn("dbus: ui_guide", profile)
        self.assertIn("button: South", profile)
        self.assertIn("button: East", profile)
        self.assertIn("axis:\n          name: LeftStick", profile)
        self.assertIn("keyboard: KeyEnter", profile)
        for event in ("ui_up", "ui_down", "ui_accept", "ui_back", "ui_guide"):
            self.assertIn(f"dbus: {event}", profile)

    def test_guide_consumes_semantic_navigation_from_both_input_profiles(self) -> None:
        native_shell = (Path(__file__).parents[1] / "native/lulu-shell.cpp").read_text()
        compat = (Path(__file__).parents[1] / "config/inputplumber/profiles/compat.yaml").read_text()
        for event in ("ui_guide", "ui_up", "ui_down", "ui_accept", "ui_back"):
            self.assertIn(f'QStringLiteral("{event}")', native_shell)
            self.assertIn(f"dbus: {event}", compat)

    def test_osk_profile_has_no_second_keyboard_or_mouse_output(self) -> None:
        profile = (Path(__file__).parents[1] / "config/inputplumber/profiles/osk.yaml").read_text()
        self.assertIn("keyboard:", profile)
        self.assertNotIn("mouse:", profile)
        for key in ("KeyUp", "KeyDown", "KeyLeft", "KeyRight", "KeyEnter", "KeyEsc"):
            self.assertIn(f"keyboard: {key}", profile)
        self.assertNotIn("dbus:", profile)

    def test_controller_loss_releases_navigation_and_same_identity_reconnects(self) -> None:
        registry = ControllerRegistry()
        registry.observe_persistent_composite("", ())
        self.assertEqual(registry.controllers, {})
        self.assertIsNone(registry.navigation_controller_id)
        registry.observe_persistent_composite("045e_0291", ("/dev/input/event18",))
        self.assertEqual(registry.navigation_controller_id, "045e_0291")
        registry.observe_persistent_composite("", ())
        self.assertIsNone(registry.navigation_controller_id)
        self.assertFalse(registry.controllers["045e_0291"].connected)
        registry.observe_persistent_composite("045e_0291", ("/dev/input/event20",))
        self.assertEqual(registry.navigation_controller_id, "045e_0291")
        self.assertTrue(registry.controllers["045e_0291"].connected)
        self.assertEqual(registry.controllers["045e_0291"].player, 1)

    def test_runtime_controller_loss_transfers_navigation_to_other_slot(self) -> None:
        registry = ControllerRegistry()
        registry.set_navigation_controller("all")
        registry.observe_runtime_composites(
            {
                "CompositeDevice0": ("045e_0291", ("/dev/input/event18",)),
                "CompositeDevice1": ("045e_0291", ("/dev/input/event22",)),
            }
        )
        self.assertIsNone(registry.navigation_controller_id)
        self.assertEqual(registry.controllers["CompositeDevice0"].player, 1)
        self.assertEqual(registry.controllers["CompositeDevice1"].player, 2)

        registry.observe_runtime_composites(
            {"CompositeDevice1": ("045e_0291", ("/dev/input/event22",))}
        )
        self.assertFalse(registry.controllers["CompositeDevice0"].connected)
        self.assertTrue(registry.controllers["CompositeDevice1"].connected)
        self.assertEqual(registry.controllers["CompositeDevice0"].player, 1)
        self.assertIsNone(registry.navigation_controller_id)
        self.assertEqual(registry.controllers["CompositeDevice1"].player, 2)

    def test_runtime_order_does_not_reshuffle_connected_players(self) -> None:
        registry = ControllerRegistry()
        registry.observe_runtime_composites(
            {
                "CompositeDevice0": ("receiver", ("/dev/input/event8",)),
                "CompositeDevice1": ("receiver", ("/dev/input/event22",)),
                "CompositeDevice2": ("receiver", ("/dev/input/event26",)),
            }
        )
        registry.observe_runtime_composites(
            {
                "CompositeDevice0": ("receiver", ("/dev/input/event8",)),
                "CompositeDevice2": ("receiver", ("/dev/input/event26",)),
                "CompositeDevice1": ("receiver", ("/dev/input/event22",)),
            }
        )
        self.assertEqual(
            {
                key: value.player
                for key, value in registry.controllers.items()
                if value.connected
            },
            {
                "CompositeDevice0": 1,
                "CompositeDevice1": 2,
                "CompositeDevice2": 3,
            },
        )

    def test_runtime_reconciliation_fills_unassigned_connected_player_slots(self) -> None:
        registry = ControllerRegistry()
        registry.observe_runtime_composites({
            "CompositeDevice3": ("receiver@slot-a", ("/dev/input/event15",)),
            "CompositeDevice4": ("receiver@slot-b", ("/dev/input/event19",)),
            "CompositeDevice5": ("series", ("/dev/input/event13",)),
        })
        self.assertEqual(
            {controller.player for controller in registry.controllers.values()
             if controller.connected},
            {1, 2, 3},
        )

    def test_intercept_mode_is_bounded_to_inputplumber_api_values(self) -> None:
        client = default_inputplumber_client(Path("config/inputplumber"))
        self.assertEqual(client.set_intercept_mode(2, execute=False)[-1], "2")
        with self.assertRaises(ValueError):
            client.set_intercept_mode(4, execute=False)

    def test_shell_profile_load_is_optional_when_no_controller_exists(self) -> None:
        client = default_inputplumber_client(Path("config/inputplumber"))
        with patch("subprocess.run") as run:
            run.return_value.stdout = ""
            command = client.load_mode(InputMode.SHELL)
        self.assertEqual(command[-1], "config/inputplumber/profiles/shell.yaml")
        self.assertEqual(run.call_count, 1)

    def test_present_composite_converges_once_when_shell_mode_is_applied(self) -> None:
        path = "/org/shadowblip/InputPlumber/CompositeDevice0"
        client = RecordingInputPlumber({path: ("045e_0291", ("/dev/input/event13",))})
        interface = input_mode_interface(client)

        interface._apply_input_mode(InputMode.SHELL)
        interface._reconcile_input_mode(client.composites, InputMode.SHELL)

        self.assertEqual(client.loads, [(InputMode.SHELL, path)])

    def test_late_composite_converges_to_active_shell_mode(self) -> None:
        path = "/org/shadowblip/InputPlumber/CompositeDevice0"
        client = RecordingInputPlumber({})
        interface = input_mode_interface(client)

        interface._apply_input_mode(InputMode.SHELL)
        client.composites = {path: ("045e_0291", ("/dev/input/event13",))}
        interface._reconcile_input_mode(client.composites, InputMode.SHELL)

        self.assertEqual(client.loads, [(InputMode.SHELL, None), (InputMode.SHELL, path)])

    def test_recreated_composite_is_reapplied_while_shell_remains_active(self) -> None:
        path = "/org/shadowblip/InputPlumber/CompositeDevice0"
        client = RecordingInputPlumber({path: ("045e_0291", ("/dev/input/event13",))})
        interface = input_mode_interface(client)

        interface._reconcile_input_mode(client.composites, InputMode.SHELL)
        interface._reconcile_input_mode({}, InputMode.SHELL)
        interface._reconcile_input_mode(client.composites, InputMode.SHELL)

        self.assertEqual(
            client.loads,
            [(InputMode.SHELL, path), (InputMode.SHELL, path)],
        )

    def test_converged_composite_is_not_reapplied(self) -> None:
        path = "/org/shadowblip/InputPlumber/CompositeDevice0"
        client = RecordingInputPlumber({path: ("045e_0291", ("/dev/input/event13",))})
        interface = input_mode_interface(client)

        interface._reconcile_input_mode(client.composites, InputMode.SHELL)
        interface._reconcile_input_mode(client.composites, InputMode.SHELL)

        self.assertEqual(client.loads, [(InputMode.SHELL, path)])

    def test_composite_intercept_mode_is_initialized_once_per_runtime_instance(self) -> None:
        path = "/org/shadowblip/InputPlumber/CompositeDevice0"
        client = RecordingInputPlumber({path: ("045e_0291", ("/dev/input/event13",))})
        interface = input_mode_interface(client)
        interface._initialized_composites = {}

        asyncio.run(interface._initialize_composite(path))
        asyncio.run(interface._initialize_composite(path))

        self.assertEqual(client.baselines, [path])

    def test_recreated_composite_reapplies_default_baseline(self) -> None:
        path = "/org/shadowblip/InputPlumber/CompositeDevice0"
        first = ("045e_0291", ("/dev/input/event13",))
        replacement = ("045e_0291", ("/dev/input/event14",))
        client = RecordingInputPlumber({path: first})
        interface = input_mode_interface(client)
        interface._initialized_composites = {}

        asyncio.run(interface._initialize_composite(path, first))
        interface._initialized_composites.clear()
        client.composites = {path: replacement}
        asyncio.run(interface._initialize_composite(path, replacement))

        self.assertEqual(client.baselines, [path, path])

    def test_recreated_composite_resets_compatibility_to_gamepad(self) -> None:
        path = "/org/shadowblip/InputPlumber/CompositeDevice0"
        client = RecordingInputPlumber({path: ("045e_0291", ("/dev/input/event13",))})
        interface = input_mode_interface(client)
        token = interface.model.request_launch("game-1")
        interface.model.launch_starting(token)
        interface.model.primary_started(token)
        interface.model.set_input_mode(InputMode.COMPAT)
        interface._initialized_composites = {}

        asyncio.run(interface._initialize_composite(path, client.composites[path]))

        self.assertEqual(interface.model.state.input_mode, InputMode.GAME)
        self.assertEqual(client.baselines, [path])

    def test_shell_bootstrap_does_not_require_a_controller_then_initializes_late_composite(self) -> None:
        class ShellSupervisor:
            def __init__(self) -> None:
                self.commands = []

            async def launch_shell(self, command, timeout, select_shell=False):
                self.commands.append((command, timeout, select_shell))

        client = RecordingInputPlumber({})
        interface = input_mode_interface(client)
        interface._initialized_composites = {}
        interface._bootstrap_output = "HDMI-A-1"
        interface.supervisor = ShellSupervisor()
        interface._select_ready_shell = AsyncMock()

        async def exercise() -> None:
            await interface.bootstrap_shell()
            await asyncio.sleep(0)
            self.assertEqual(len(interface.supervisor.commands), 1)
            self.assertFalse(interface.supervisor.commands[0][2])
            path = "/org/shadowblip/InputPlumber/CompositeDevice0"
            composite = ("045e_0291", ("/dev/input/event13",))
            client.composites = {path: composite}
            await interface._initialize_composite(path, composite)
            self.assertEqual(client.baselines, [path])

        asyncio.run(exercise())

    def test_empty_gamepad_order_clears_recreated_composite_lifetime_state(self) -> None:
        path = "/org/shadowblip/InputPlumber/CompositeDevice0"
        interface = input_mode_interface(RecordingInputPlumber({path: ("045e_0291", ("/dev/input/event13",))}))
        interface._initialized_composites = {path: ("045e_0291", ("/dev/input/event13",))}
        interface._inputplumber_event = asyncio.Event()

        message = type(
            "Signal",
            (),
            {
                "message_type": MessageType.SIGNAL,
                "path": "/org/shadowblip/InputPlumber/Manager",
                "interface": "org.freedesktop.DBus.Properties",
                "member": "PropertiesChanged",
                "body": ("org.shadowblip.InputManager", {"GamepadOrder": []}, []),
            },
        )()

        interface._handle_inputplumber_signal(message)

        self.assertEqual(interface._initialized_composites, {})
        self.assertTrue(interface._inputplumber_event.is_set())

    def test_controller_monitor_survives_transient_composite_query_failure(self) -> None:
        path = "/org/shadowblip/InputPlumber/CompositeDevice0"

        class FlakyInputPlumber(RecordingInputPlumber):
            attempts = 0

            def runtime_composite_statuses(self):
                self.attempts += 1
                if self.attempts == 1:
                    raise subprocess.CalledProcessError(1, "busctl")
                return {path: ("045e_0291", ("/dev/input/event20",))}

        interface = input_mode_interface(FlakyInputPlumber({}))
        interface._inputplumber_event = asyncio.Event()
        interface._initialized_composites = {}
        interface._inputplumber_event.set()

        async def exercise() -> None:
            task = asyncio.create_task(interface._monitor_controller_events())
            await asyncio.sleep(0.05)
            interface._inputplumber_event.set()
            await asyncio.sleep(0.1)
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

        asyncio.run(exercise())
        self.assertIn(path, interface._initialized_composites)
        self.assertEqual(interface._inputplumber.intercepts, [(1, path)])

    def test_reconciliation_preserves_registry_ownership_and_player_assignment(self) -> None:
        path = "/org/shadowblip/InputPlumber/CompositeDevice0"
        client = RecordingInputPlumber({path: ("045e_0291", ("/dev/input/event13",))})
        interface = input_mode_interface(client)

        interface.controller_registry = ControllerRegistry()
        interface.controller_registry.observe_runtime_composites(client.composites)
        interface._reconcile_input_mode(client.composites, InputMode.SHELL)

        controller = interface.controller_registry.controllers[path]
        self.assertTrue(controller.connected)
        self.assertEqual(controller.player, 1)
        self.assertIsNone(interface.controller_registry.navigation_controller_id)
        self.assertEqual(interface.controller_registry.navigation_mode, "all")

    def test_gamescope_invocation_accepts_deployment_output(self) -> None:
        command = GamescopeInvocation().argv(["/usr/bin/true"])
        self.assertNotIn("--prefer-output", command)
        configured = GamescopeInvocation(output="HDMI-A-1").argv(["/usr/bin/true"])
        self.assertEqual(configured[3:5], ["--prefer-output", "HDMI-A-1"])

    def test_gamescope_invocation_can_enable_steam_integration(self) -> None:
        command = GamescopeInvocation(steam=True).argv(["/usr/bin/true"])
        self.assertIn("--steam", command)

    def test_gamescope_display_policy_uses_supported_flags(self) -> None:
        command = GamescopeInvocation(
            output="DP-1", output_width=1680, output_height=1050, output_refresh=59.88,
        ).argv(["/usr/bin/true"])
        self.assertIn("--output-width", command)
        self.assertIn("--output-height", command)
        self.assertIn("--nested-refresh", command)
        self.assertNotIn("--output-refresh", command)

    def test_gamescope_discovers_connected_connector(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            drm = Path(directory) / "card0-HDMI-A-1"
            drm.mkdir(parents=True)
            (drm / "status").write_text("connected\n")
            self.assertEqual(discover_presentation_output(directory), "HDMI-A-1")

    def test_gamescope_rejects_ambiguous_connected_connectors(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            for connector in ("HDMI-A-1", "DP-1"):
                drm = Path(directory) / f"card0-{connector}"
                drm.mkdir(parents=True)
                (drm / "status").write_text("connected\n")
            with self.assertRaisesRegex(RuntimeError, "multiple connected"):
                discover_presentation_output(directory)

    def test_session_can_start_without_a_controller_requirement(self) -> None:
        source = (Path(__file__).parents[1] / "src/lulu/sessiond.py").read_text()
        self.assertNotIn('raise RuntimeError("persistent InputPlumber composite is unavailable")', source)


if __name__ == "__main__":
    unittest.main()
