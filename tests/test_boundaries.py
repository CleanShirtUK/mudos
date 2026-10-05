import unittest
import asyncio
import subprocess
import signal
import json
import os
import sys
import time
from pathlib import Path
import tempfile
import threading
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
from lulu.inputplumber import (DEFAULT_PROFILE_PATH, CompositeProfileState,
                               InputPlumberClient, InputPlumberObjectDisappeared)
from lulu.contracts import (InputMode, LaunchDescriptor, Lifecycle, Overlay, Presentation,
                            Role, ServiceName, SessionClassification)
from lulu.gamescope import GamescopeInvocation, GamescopePresentation, discover_presentation_output
from lulu.launch_identity import LaunchIdentity
from lulu.sessiond import ConsoleSessionInterface
from lulu.process_supervisor import ProcessSupervisor


class RecordingInputPlumber:
    def __init__(self, composites: dict[str, tuple[str, tuple[str, ...]]]) -> None:
        self.composites = composites
        self.loads: list[tuple[InputMode, str | None]] = []
        self.intercepts: list[tuple[int, str | None]] = []
        self.baselines: list[str | None] = []
        self.profile_paths = {
            InputMode.SHELL: Path("/profiles/shell.yaml"),
            InputMode.GAME: Path("/profiles/game.yaml"),
            InputMode.COMPAT: Path("/profiles/compat.yaml"),
        }
        self.profile_states = {
            path: CompositeProfileState("/profiles/shell.yaml", "Lulu SHELL", 1)
            for path in composites
        }
        self.reported_mutation_profile: str | None = None
        self.disappear_on_read: set[str] = set()

    def composite_profile_state(self, object_path=None, *, execute=True):
        if object_path in self.disappear_on_read:
            raise InputPlumberObjectDisappeared(object_path)
        if object_path not in self.composites:
            raise InputPlumberObjectDisappeared(object_path)
        return self.profile_states.setdefault(
            object_path, CompositeProfileState(DEFAULT_PROFILE_PATH, "Default", 1),
        )

    def runtime_composite_statuses(self) -> dict[str, tuple[str, tuple[str, ...]]]:
        return self.composites

    def load_mode(
        self, mode: InputMode, object_path: str | None = None, *, execute: bool = True
    ) -> list[str]:
        self.loads.append((mode, object_path))
        if object_path in self.profile_states:
            profile_path = self.reported_mutation_profile or str(self.profile_paths[mode])
            self.profile_states[object_path] = CompositeProfileState(
                profile_path, f"Lulu {mode.name}", self.profile_states[object_path].intercept_mode,
            )
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
        if object_path in self.profile_states:
            self.profile_states[object_path] = CompositeProfileState(DEFAULT_PROFILE_PATH, "Default", 1)
        return []


def input_mode_interface(
    client: RecordingInputPlumber,
) -> ConsoleSessionInterface:
    interface = ConsoleSessionInterface.__new__(ConsoleSessionInterface)
    interface._inputplumber = client
    interface._applied_input_modes = {}
    interface._local_identity = None
    interface._local_provider_id = ""
    interface._local_surface_owner_pid = None
    interface.model = SessionStateModel()
    interface.controller_registry = ControllerRegistry()
    interface.supervisor = type("Supervisor", (), {
        "state_details": lambda self: {}, "launch_cancellable": False,
        "presentation_available": False, "active_identity": None,
        "session_process_ids": lambda self, identity=None: ({identity.pid} if identity else set()),
        "terminate_session": lambda self, identity, signum: None,
        "select_session_surface": lambda self, identity, timeout, include_related_processes=False: None,
        "selected_session_surface_owner": lambda self, identity: None,
        "session_surface_is_owned": lambda self, owner_pid, identity: owner_pid == identity.pid,
        "session_surface_process_ids": lambda self, identity: set(),
        "select_shell_presentation": lambda self: None,
        "select_steam_session_surface": lambda self, token, pgid: None,
        "shell_status": lambda self: None,
    })()
    interface.StateChanged = lambda state: None
    return interface


class BoundaryTests(unittest.TestCase):
    def test_managed_game_input_policy_tracks_focus_fullscreen_and_session_override(self) -> None:
        session = SessionStateModel()
        token = session.request_launch("game-1")
        session.launch_starting(token)
        self.assertEqual(session.state.input_mode_override.value, "auto")
        session.primary_started(token)

        self.assertEqual(session.automatic_game_input_mode(focused=True, fullscreen=False), InputMode.COMPAT)
        self.assertEqual(session.automatic_game_input_mode(focused=True, fullscreen=True), InputMode.GAME)
        self.assertEqual(session.automatic_game_input_mode(focused=False, fullscreen=True), InputMode.COMPAT)
        self.assertEqual(session.automatic_game_input_mode(focused=True, fullscreen=True), InputMode.GAME)

        session.set_explicit_game_input_mode(InputMode.COMPAT)
        self.assertEqual(session.state.input_mode_override.value, "explicit_compat")
        self.assertEqual(session.automatic_game_input_mode(focused=True, fullscreen=True), InputMode.COMPAT)
        session.set_explicit_game_input_mode(InputMode.GAME)
        self.assertEqual(session.state.input_mode_override.value, "explicit_gamepad")
        self.assertEqual(session.automatic_game_input_mode(focused=True, fullscreen=False), InputMode.GAME)

        session.primary_exited(token)
        session.return_complete(token)
        self.assertEqual(session.state.input_mode, InputMode.SHELL)
        self.assertEqual(session.state.input_mode_override.value, "auto")

    def test_failed_and_cancelled_launch_do_not_retain_game_input_override(self) -> None:
        for failed in (False, True):
            session = SessionStateModel()
            token = session.request_launch("game-1")
            session.launch_starting(token)
            if failed:
                session.fail(token, "launch failed")
            else:
                session.fail(token, "launch cancelled")
            session.return_complete(token)
            self.assertEqual(session.state.lifecycle.value, "shell")
            self.assertEqual(session.state.input_mode.value, "shell")
            self.assertEqual(session.state.input_mode_override.value, "auto")

    def test_sessiond_applies_mode_only_for_focused_owned_gamescope_surface(self) -> None:
        from types import SimpleNamespace
        from lulu.launch_identity import LaunchIdentity

        path = "/org/shadowblip/InputPlumber/CompositeDevice0"
        client = RecordingInputPlumber({path: ("045e_0291", ("/dev/input/event13",))})
        interface = input_mode_interface(client)
        interface._last_automatic_mode = None
        interface._observed_game_surface = (None, None, False)
        token = interface.model.request_launch("game-1")
        interface.model.launch_starting(token)
        interface.model.primary_started(token)
        identity = LaunchIdentity(token, 4321, 4321, "/game", ("/game",))
        interface.supervisor.active_identity = identity
        interface.supervisor.session_process_ids = lambda identity=None: {4321, 4322}

        interface._observed_game_surface = (123, 9999, True)
        interface._reconcile_game_input_policy()
        self.assertEqual(client.loads[-1][0], InputMode.COMPAT)
        interface._observed_game_surface = (123, 4322, False)
        interface._reconcile_game_input_policy()
        self.assertEqual(client.loads[-1][0], InputMode.COMPAT)
        interface._observed_game_surface = (123, 4322, True)
        interface._reconcile_game_input_policy()
        self.assertEqual(client.loads[-1][0], InputMode.GAME)

        interface.model.set_explicit_game_input_mode(InputMode.COMPAT)
        interface._reconcile_game_input_policy()
        self.assertEqual(client.loads[-1][0], InputMode.COMPAT)

    def test_gamescope_close_targets_only_the_resolved_window(self) -> None:
        from unittest.mock import patch

        presentation = GamescopePresentation(display=":7")
        with patch("lulu.gamescope.subprocess.run") as run:
            presentation.request_window_close(456)

        args, kwargs = run.call_args
        self.assertEqual(args[0], ["xdotool", "windowclose", "456"])
        self.assertTrue(kwargs["check"])
        self.assertEqual(kwargs["env"]["DISPLAY"], ":7")

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

    def test_gamescope_return_maps_shell_before_discovery_and_selection(self) -> None:
        presentation = GamescopePresentation(poll_interval=0)
        presentation.shell_window = 456
        presentation.shell_window_pid = 100
        events = []
        presentation._cached_shell_matches = lambda pid: pid == 100
        presentation._window_command = lambda action, window: events.append((action, window))

        def focusable():
            events.append(("discover", 456))
            return [(456, 0, 100)]

        presentation._focusable_windows = focusable
        presentation._select_window = lambda window: events.append(("select", window)) or True

        self.assertEqual(presentation.select_shell(100), 456)
        self.assertEqual(events[0], ("map", 456))
        self.assertLess(events.index(("map", 456)), events.index(("select", 456)))
        self.assertEqual(presentation.shell_owner_pid, 100)

    def test_gamescope_game_suspension_unmaps_after_surface_selection(self) -> None:
        presentation = GamescopePresentation()
        presentation.shell_window = 456
        events = []
        presentation.window_for_pids = lambda *args, **kwargs: 789
        presentation._select_window = lambda window: events.append(("select", window)) or True
        presentation._focusable_windows = lambda: [(456, 0, 100)]
        presentation._window_command = lambda action, window: events.append((action, window))

        self.assertEqual(presentation.select_pids([200]), 789)
        presentation.selected_base_window = lambda: 789
        presentation.suspend_shell_window()
        self.assertEqual(events, [("select", 789), ("unmap", 456)])

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
            # A source-only provisional record has no InputPlumber target slot;
            # SDL identity must not be guessed from the source/order position.
            self.assertEqual(client.runtime_gamepad_slots(), [])

    def test_composite_disappearing_during_snapshot_is_skipped_and_reappears(self) -> None:
        first = "/org/shadowblip/InputPlumber/CompositeDevice0"
        transient = "/org/shadowblip/InputPlumber/CompositeDevice1"
        source_a = "/org/shadowblip/InputPlumber/devices/source/event13"
        source_b = "/org/shadowblip/InputPlumber/devices/source/event14"
        vanished = {transient}

        class RacingClient(InputPlumberClient):
            def gamepad_order(self, *, execute: bool = True) -> tuple[str, ...]:
                return (first, transient)

            def _source_gamepad_path(self, *, execute: bool = True) -> str | None:
                return None

        def get_property(command, **kwargs):
            path, prop = command[3], command[-1]
            if path == transient and path in vanished:
                error = subprocess.CalledProcessError(1, command, stderr=(
                    "Call failed: org.freedesktop.DBus.Error.UnknownObject: "
                    "Unknown object at path"
                ))
                raise error
            values = {
                (first, "PersistentId"): 's "045e_0291"',
                (first, "SourceDevicePaths"): f'as 1 "{source_a}"',
                (transient, "PersistentId"): 's "045e_0292"',
                (transient, "SourceDevicePaths"): f'as 1 "{source_b}"',
            }
            return type("Result", (), {"stdout": values[(path, prop)]})()

        client = RacingClient(first, {})
        registry = ControllerRegistry()
        with patch("lulu.inputplumber.subprocess.run", side_effect=get_property):
            initial = client.runtime_composite_statuses()
            self.assertEqual(set(initial), {first})
            self.assertTrue(initial[first][0].startswith("045e_0291"))
            registry.observe_runtime_composites(initial)
            vanished.clear()
            returned = client.runtime_composite_statuses()
            registry.observe_runtime_composites(returned)

        self.assertEqual(set(returned), {first, transient})
        self.assertTrue(returned[transient][0].startswith("045e_0292"))
        self.assertTrue(registry.controllers[first].connected)
        self.assertTrue(registry.controllers[transient].connected)
        self.assertEqual(registry.navigation_mode, "all")

    def test_only_disappearing_composite_produces_empty_snapshot(self) -> None:
        path = "/org/shadowblip/InputPlumber/CompositeDevice1"

        class RacingClient(InputPlumberClient):
            def gamepad_order(self, *, execute: bool = True) -> tuple[str, ...]:
                return (path,)

            def _source_gamepad_path(self, *, execute: bool = True) -> str | None:
                return None

        def vanished(command, **kwargs):
            raise subprocess.CalledProcessError(
                1, command, stderr="org.freedesktop.DBus.Error.UnknownObject: Unknown object"
            )

        with patch("lulu.inputplumber.subprocess.run", side_effect=vanished):
            self.assertEqual(RacingClient(path, {}).runtime_composite_statuses(), {})

    def test_unrelated_composite_dbus_error_is_not_swallowed(self) -> None:
        path = "/org/shadowblip/InputPlumber/CompositeDevice0"

        class RacingClient(InputPlumberClient):
            def gamepad_order(self, *, execute: bool = True) -> tuple[str, ...]:
                return (path,)

        def failed(command, **kwargs):
            raise subprocess.CalledProcessError(1, command, stderr="AccessDenied")

        with patch("lulu.inputplumber.subprocess.run", side_effect=failed):
            with self.assertRaises(subprocess.CalledProcessError):
                RacingClient(path, {}).runtime_composite_statuses()

    def test_target_lookup_race_keeps_other_controller_slot(self) -> None:
        first = "/org/shadowblip/InputPlumber/CompositeDevice0"
        transient = "/org/shadowblip/InputPlumber/CompositeDevice1"

        class RacingClient(InputPlumberClient):
            def gamepad_order(self, *, execute: bool = True) -> tuple[str, ...]:
                return (first, transient)

            def composite_status(self, object_path=None, *, execute=True):
                return (object_path, (f"/dev/input/{object_path[-1]}",))

        def get_target(command, **kwargs):
            if command[3] == transient:
                raise subprocess.CalledProcessError(
                    1, command, stderr="org.freedesktop.DBus.Error.UnknownObject: Unknown object"
                )
            return type("Result", (), {
                "stdout": 'ao 1 "/org/shadowblip/InputPlumber/devices/target/gamepad0"'
            })()

        with patch("lulu.inputplumber.subprocess.run", side_effect=get_target), patch(
            "lulu.inputplumber.associate_sdl_targets", return_value={first: 0}
        ):
            slots = RacingClient(first, {}).runtime_gamepad_slots([])
        self.assertEqual(slots, [(first, first, 0)])

    def test_session_controller_monitor_starts_with_no_controller(self) -> None:
        client = RecordingInputPlumber({})
        interface = input_mode_interface(client)
        interface._inputplumber_event = None
        interface._presentation_watchdog_enabled = False
        interface._shell_selection_task = None
        interface._presentation_watchdog_task = None

        class FakeBus:
            def __init__(self):
                self.handlers = []
                self.rules = []

            async def connect(self):
                return self

            def _add_match_rule(self, rule):
                self.rules.append(rule)

            def add_message_handler(self, handler):
                self.handlers.append(handler)

            def remove_message_handler(self, handler):
                self.handlers.remove(handler)

            def disconnect(self):
                pass

            async def introspect(self, *args):
                raise AssertionError("Sessiond startup must not introspect a controller object")

        fake_bus = FakeBus()

        async def exercise() -> None:
            with patch("lulu.sessiond.MessageBus", return_value=fake_bus), patch(
                "lulu.sessiond.sdl_gamepad_inventory", return_value=[]
            ), patch("lulu.sessiond.GamescopeWindowObserver",
                     return_value=type("Observer", (), {"start": lambda self: None,
                                                          "stop": lambda self: None})()):
                await interface.start_controller_monitor()
                self.assertEqual(interface.controller_registry.controllers, {})
                self.assertIsNotNone(interface._controller_monitor_task)
                self.assertEqual(len(fake_bus.handlers), 1)
                await interface.stop_controller_monitor()

        asyncio.run(exercise())

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

    def test_navigation_defaults_to_all_and_only_changes_on_explicit_selection(self) -> None:
        registry = ControllerRegistry()
        self.assertEqual(registry.navigation_mode, "all")
        self.assertIsNone(registry.navigation_controller_id)
        registry.observe_runtime_composites({
            "CompositeDevice0": ("pad-a", ("/dev/input/event1",)),
        })
        self.assertEqual(registry.navigation_mode, "all")
        self.assertIsNone(registry.navigation_controller_id)

    def test_unavailable_specific_navigation_selection_stays_null_until_reconnected(self) -> None:
        registry = ControllerRegistry()
        registry.observe_runtime_composites({
            "CompositeDevice0": ("pad-a", ("/dev/input/event1",)),
            "CompositeDevice1": ("pad-b", ("/dev/input/event2",)),
        })
        registry.set_navigation_controller("CompositeDevice0")

        registry.observe_runtime_composites({
            "CompositeDevice1": ("pad-b", ("/dev/input/event2",)),
        })
        self.assertEqual(registry.navigation_mode, "specific")
        self.assertIsNone(registry.navigation_controller_id)

        registry.observe_runtime_composites({
            "CompositeDevice0": ("pad-a", ("/dev/input/event3",)),
            "CompositeDevice1": ("pad-b", ("/dev/input/event2",)),
        })
        self.assertEqual(registry.navigation_controller_id, "CompositeDevice0")

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
        registry.connect(Controller("pad-b"))
        registry.assign_player("pad-a", 1)
        registry.assign_player("pad-b", 2)
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

    def test_compatibility_mode_can_be_enabled_during_steam_launch_startup(self) -> None:
        path = "/org/shadowblip/InputPlumber/CompositeDevice0"
        client = RecordingInputPlumber({path: ("045e_0291", ("/dev/input/event13",))})
        interface = input_mode_interface(client)
        token = interface.model.request_launch("steam:40800")
        interface.model.launch_starting(token)

        interface.SetInputMode("compat")

        self.assertEqual(client.loads, [(InputMode.COMPAT, path)])
        self.assertEqual(interface.model.state.input_mode, InputMode.COMPAT)

    def test_compatibility_mode_stays_blocked_during_non_steam_startup(self) -> None:
        interface = input_mode_interface(RecordingInputPlumber({}))
        token = interface.model.request_launch("game-1")
        interface.model.launch_starting(token)

        with self.assertRaises(Exception):
            interface.SetInputMode("compat")

    def test_local_session_enters_and_leaves_authoritative_game_state(self) -> None:
        path = "/org/shadowblip/InputPlumber/CompositeDevice0"
        client = RecordingInputPlumber({path: ("045e_0291", ("/dev/input/event13",))})
        interface = input_mode_interface(client)
        interface.BeginLocalSession("local:wii:game", 123, 123, "/usr/bin/dolphin-emu", ["dolphin-emu", "-e", "game.rvz"], "dolphin")

        state = interface.model.state
        self.assertEqual(state.lifecycle, Lifecycle.GAME)
        self.assertEqual(state.primary_id, "local:wii:game")
        self.assertEqual(state.input_mode, InputMode.GAME)
        self.assertEqual(interface._local_identity.executable, "/usr/bin/dolphin-emu")

        asyncio.run(ConsoleSessionInterface.EndLocalSession.__wrapped__(
            interface, interface._local_identity.token, 0
        ))

        self.assertEqual(interface.model.state.lifecycle, Lifecycle.SHELL)
        self.assertIsNone(interface._local_identity)
        self.assertEqual(interface.model.state.input_mode, InputMode.SHELL)

    def test_local_session_restores_shell_even_if_controller_profile_restore_fails(self) -> None:
        interface = input_mode_interface(RecordingInputPlumber({}))
        presentation = type("Presentation", (), {
            "select_shell": lambda self, pid: setattr(self, "selected_shell", pid),
        })()
        interface.supervisor = type("Supervisor", (), {
            "state_details": lambda self: {}, "launch_cancellable": False,
            "presentation_available": True,
            "shell_status": lambda self: type("ShellStatus", (), {
                "pid": 99, "running": True, "presentation_available": True,
            })(),
            "select_shell_presentation": lambda self: presentation.select_shell(99),
            "session_process_ids": lambda self, identity: {identity.pid},
        })()
        token = interface.model.request_launch("local:test:game")
        interface.model.launch_starting(token)
        interface._local_identity = LaunchIdentity(token, 123, 123, "/usr/bin/sleep", ("sleep",))
        interface._local_provider_id = "steam"
        interface.model.primary_started(token)
        with patch.object(interface, "_apply_input_mode", side_effect=RuntimeError("controller disconnected")):
            asyncio.run(ConsoleSessionInterface.EndLocalSession.__wrapped__(interface, token, -15))
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
            "state_details": lambda self: {}, "launch_cancellable": False,
            "presentation_available": True,
            "shell_status": lambda self: type("ShellStatus", (), {
                "pid": 99, "running": True, "presentation_available": True,
            })(),
            "select_shell_presentation": lambda self: presentation.select_shell(99),
            "select_steam_session_surface": lambda self, token, pgid: presentation.select_pids(lambda: [456], 225.0),
            "session_process_ids": lambda self, identity: {identity.pid},
        })()
        with patch("lulu.plugins.steam.provider.SteamProvider.desktop_pids", return_value=[456]):
            interface.BeginProviderSession("steam", "compat", 123, 123,
                                           "/usr/bin/sleep", ["sleep"], 123)
        self.assertEqual(presentation.selected, [([456], 225.0)])
        self.assertEqual(interface.model.state.input_mode, InputMode.COMPAT)
        self.assertEqual(interface.model.state.lifecycle, Lifecycle.GAME)
        self.assertEqual(interface._local_provider_id, "steam")
        asyncio.run(ConsoleSessionInterface.EndLocalSession.__wrapped__(
            interface, interface._local_identity.token, 0
        ))
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
            "state_details": lambda self: {}, "launch_cancellable": False,
            "presentation_available": True,
            "shell_status": lambda self: type("ShellStatus", (), {
                "pid": 99, "running": True, "presentation_available": True,
            })(),
            "select_shell_presentation": lambda self: presentation.select_shell(99),
            "select_session_surface": lambda self, identity, timeout, include_related_processes=False: presentation.select_pids(
                [identity.pid], timeout),
            "session_process_ids": lambda self, identity: {identity.pid},
        })()
        interface.BeginLocalSession("local:gamecube:fixture", 123, 123,
                                    "/usr/bin/dolphin-emu", ["dolphin-emu", "fixture.iso"], "dolphin")
        self.assertEqual(presentation.selected, [([123], 15.0)])
        asyncio.run(ConsoleSessionInterface.EndLocalSession.__wrapped__(
            interface, interface._local_identity.token, 0
        ))
        self.assertEqual(presentation.selected[-1], ("shell", 99))

    def test_eden_appimage_selection_records_owned_child_window_owner(self) -> None:
        class Presentation:
            def __init__(self):
                self.selected = []

            def select_pids(self, pids, timeout, process_alive=None):
                self.selected.append((pids(), timeout, process_alive()))

        interface = input_mode_interface(RecordingInputPlumber({}))
        presentation = Presentation()
        interface.supervisor = type("Supervisor", (), {
            "state_details": lambda self: {}, "launch_cancellable": False,
            "presentation_available": True,
            "select_session_surface": lambda self, identity, timeout, include_related_processes=False: presentation.select_pids(
                lambda: [321, 456] if include_related_processes else [identity.pid],
                timeout, lambda: True),
            "session_process_ids": lambda self, identity: {identity.pid, 321, 456},
            "selected_session_surface_owner": lambda self, identity: 321,
            "session_surface_is_owned": lambda self, owner_pid, identity: owner_pid in {123, 321, 456},
            "session_surface_process_ids": lambda self, identity: {321, 456},
        })()
        interface.BeginLocalSession("local:switch:game", 123, 123,
                                    "/usr/bin/bash", ["/var/lib/lulu/providers/eden/d16735f5b6/Eden-Linux-d16735f5b6-amd64-clang-pgo.AppImage"], "eden")
        self.assertEqual(presentation.selected, [([321, 456], 15.0, True)])
        self.assertEqual(interface.model.state.lifecycle, Lifecycle.GAME)
        self.assertEqual(interface._local_provider_id, "eden")
        self.assertEqual(interface._local_surface_owner_pid, 321)

    def test_eden_surface_exit_returns_shell_while_appimage_helper_remains(self) -> None:
        client = RecordingInputPlumber({})
        interface = input_mode_interface(client)
        group = {123, 456, 789}  # AppImage entrypoint, Eden UI child, runtime helper.
        selected = []
        terminated = []
        interface.supervisor = type("Supervisor", (), {
            "state_details": lambda self: {}, "launch_cancellable": False,
            "presentation_available": True,
            "select_session_surface": lambda self, identity, timeout, include_related_processes=False: None,
            "selected_session_surface_owner": lambda self, identity: 456,
            "session_process_ids": lambda self, identity=None: set(group),
            "session_surface_is_owned": lambda self, pid, identity: pid in {123, 456, 789},
            # The non-presenting AppImage helper remains in the owned group,
            # but has no Gamescope window after the Eden child exits.
            "session_surface_process_ids": lambda self, identity: set(),
            "terminate_session": lambda self, identity, signum: (terminated.append((identity.pgid, signum)), group.clear()),
            "shell_status": lambda self: type("ShellStatus", (), {
                "pid": 99, "running": True, "presentation_available": True,
            })(),
            "select_shell_presentation": lambda self: selected.append(("shell", 99)),
        })()
        transitions = []
        interface.StateChanged = lambda _state: transitions.append(interface.model.state.lifecycle)
        interface.BeginLocalSession(
            "local:switch:fixture", 123, 123, "/var/lib/lulu/providers/eden/Eden.AppImage",
            ("/var/lib/lulu/providers/eden/Eden.AppImage", "--appimage-extract-and-run", "game.xci"),
            "eden",
        )
        self.assertEqual(interface._local_surface_owner_pid, 456)
        group.remove(456)  # Eden window child has exited; entrypoint and helper remain.
        with patch("lulu.sessiond.ProcessSupervisor._pid_is_live", return_value=False):
            asyncio.run(interface._reconcile_eden_surface_lifecycle(interface._local_identity))

        self.assertEqual(transitions[-2:], [Lifecycle.RETURNING, Lifecycle.SHELL])
        self.assertEqual(selected, [("shell", 99)])
        self.assertEqual(terminated, [(123, signal.SIGTERM)])
        self.assertEqual(client.loads[-1][0], InputMode.SHELL)
        self.assertIsNone(interface._local_identity)

    def test_appimage_parent_child_tree_returns_on_ui_exit_not_helper_exit(self) -> None:
        async def exercise() -> None:
            parent_code = (
                "import json,subprocess,sys,time; "
                "ui=subprocess.Popen([sys.executable,'-c','import time; time.sleep(0.25)']); "
                "helper=subprocess.Popen([sys.executable,'-c','import time; time.sleep(20)']); "
                "print(json.dumps({'ui':ui.pid,'helper':helper.pid}),flush=True); "
                "ui.wait(); time.sleep(20)"
            )
            parent = await asyncio.create_subprocess_exec(
                sys.executable, "-c", parent_code,
                stdout=asyncio.subprocess.PIPE, start_new_session=True,
            )
            group_id = parent.pid
            try:
                topology = json.loads((await parent.stdout.readline()).decode())
                ui_pid = topology["ui"]
                helper_pid = topology["helper"]

                def parent_pid(pid: int) -> int:
                    stat = Path(f"/proc/{pid}/stat").read_text()
                    fields = stat[stat.rfind(")") + 1:].split()
                    return int(fields[1])

                self.assertEqual(parent_pid(ui_pid), parent.pid)
                self.assertEqual(parent_pid(helper_pid), parent.pid)
                self.assertEqual(os.getpgid(ui_pid), group_id)
                self.assertEqual(os.getpgid(helper_pid), group_id)
                self.assertEqual(os.getsid(ui_pid), parent.pid)

                class Supervisor:
                    presentation_available = True

                    def __init__(self):
                        self.selected_shell = []

                    def state_details(self): return {}
                    def select_session_surface(self, *_args, **_kwargs): pass
                    def selected_session_surface_owner(self, _identity): return ui_pid
                    def session_process_ids(self, identity=None):
                        return ProcessSupervisor._process_group_members(group_id)
                    def session_surface_is_owned(self, pid, _identity):
                        return pid in self.session_process_ids()
                    def session_surface_process_ids(self, _identity):
                        return {ui_pid} if ui_pid in self.session_process_ids() else set()
                    def terminate_session(self, identity, signum): os.killpg(identity.pgid, signum)
                    def shell_status(self):
                        return type("ShellStatus", (), {
                            "pid": 99, "running": True, "presentation_available": True,
                        })()
                    def select_shell_presentation(self): self.selected_shell.append(99)

                client = RecordingInputPlumber({})
                interface = input_mode_interface(client)
                interface._state_json = lambda: "{}"
                supervisor = Supervisor()
                interface.supervisor = supervisor
                interface.BeginLocalSession(
                    "local:switch:fixture", parent.pid, group_id, sys.executable,
                    ("Eden-Linux-pinned.AppImage", "--appimage-extract-and-run", "fixture.xci"),
                    "eden",
                )
                await asyncio.sleep(0.35)  # Eden child/window exited; helper and host remain.
                self.assertIn(parent.pid, supervisor.session_process_ids())
                self.assertIn(helper_pid, supervisor.session_process_ids())
                started = time.monotonic()
                await interface._reconcile_eden_surface_lifecycle(interface._local_identity)
                elapsed = time.monotonic() - started
                self.assertLess(elapsed, 0.5)
                self.assertEqual(interface.model.state.lifecycle, Lifecycle.SHELL)
                self.assertEqual(supervisor.selected_shell, [99])
                self.assertEqual(client.loads[-1][0], InputMode.SHELL)
                await asyncio.wait_for(parent.wait(), timeout=2)
            finally:
                try:
                    os.killpg(group_id, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                if parent.returncode is None:
                    await parent.wait()

        asyncio.run(exercise())

    def test_owned_surface_discovery_excludes_non_window_and_unrelated_processes(self) -> None:
        class Presentation:
            def focusable_window_pids(self):
                return {456, 999}

            def pid_is_owned_by(self, pid, owned):
                return pid in owned

        supervisor = ProcessSupervisor(SessionStateModel(), presentation=Presentation())
        identity = LaunchIdentity("appimage", 123, 123, "/runtime/Eden.AppImage",
                                  ("Eden.AppImage", "--appimage-extract-and-run"))
        with patch.object(supervisor, "session_process_ids", return_value={123, 456, 789}):
            self.assertEqual(supervisor.session_surface_process_ids(identity), {456})

    def test_failed_local_session_does_not_leave_state_owned(self) -> None:
        class FailingInputPlumber(RecordingInputPlumber):
            def load_mode(self, mode, object_path=None, *, execute=True):
                raise OSError("profile unavailable")

        interface = input_mode_interface(FailingInputPlumber({}))
        with self.assertRaises(Exception):
            interface.BeginLocalSession("local:wii:game", 123, 123, "/usr/bin/dolphin-emu", ["dolphin-emu"], "dolphin")
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
        for event in ("ui_accept", "ui_back", "ui_guide"):
            self.assertIn(f"dbus: {event}", profile)
        for event in ("ui_up", "ui_down"):
            self.assertNotIn(f"dbus: {event}", profile)
        self.assertIn("keyboard: KeyUp", profile)
        self.assertIn("keyboard: KeyDown", profile)

    def test_guide_consumes_semantic_navigation_from_both_input_profiles(self) -> None:
        native_shell = (Path(__file__).parents[1] / "native/lulu-shell.cpp").read_text()
        compat = (Path(__file__).parents[1] / "config/inputplumber/profiles/compat.yaml").read_text()
        for event in ("ui_guide", "ui_up", "ui_down", "ui_accept", "ui_back"):
            self.assertIn(f'QStringLiteral("{event}")', native_shell)
        self.assertNotIn("dbus: ui_up", compat)
        self.assertNotIn("dbus: ui_down", compat)
        for event in ("ui_guide", "ui_accept", "ui_back"):
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

    def test_composite_profile_readback_reads_profile_path_name_and_intercept(self) -> None:
        client = default_inputplumber_client(Path("config/inputplumber"))
        values = {
            "ProfilePath": 's "config/inputplumber/profiles/game.yaml"',
            "ProfileName": 's "Lulu GAME"',
            "InterceptMode": "u 2",
        }

        def run(command, **_kwargs):
            return type("Result", (), {"stdout": values[command[-1]]})()

        with patch("lulu.inputplumber.subprocess.run", side_effect=run) as mocked:
            state = client.composite_profile_state("/controller/0")

        self.assertEqual(state.profile_path, "config/inputplumber/profiles/game.yaml")
        self.assertEqual(state.profile_name, "Lulu GAME")
        self.assertEqual(state.intercept_mode, 2)
        self.assertEqual(mocked.call_count, 3)

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

        self.assertEqual(client.loads, [])
        self.assertEqual(interface._applied_input_modes[path], InputMode.SHELL)

    def test_late_composite_converges_to_active_shell_mode(self) -> None:
        path = "/org/shadowblip/InputPlumber/CompositeDevice0"
        client = RecordingInputPlumber({})
        interface = input_mode_interface(client)

        interface._apply_input_mode(InputMode.SHELL)
        client.composites = {path: ("045e_0291", ("/dev/input/event13",))}
        interface._reconcile_input_mode(client.composites, InputMode.SHELL)

        self.assertEqual(client.loads, [(InputMode.SHELL, None), (InputMode.SHELL, path)])

    def test_native_input_mode_does_not_require_a_controller(self) -> None:
        interface = input_mode_interface(RecordingInputPlumber({}))
        interface._native_controller = True

        interface._apply_input_mode(InputMode.SHELL)

        self.assertEqual(interface._inputplumber.baselines, [])
        self.assertEqual(interface._inputplumber.loads, [])

    def test_recreated_composite_is_reapplied_while_shell_remains_active(self) -> None:
        path = "/org/shadowblip/InputPlumber/CompositeDevice0"
        client = RecordingInputPlumber({path: ("045e_0291", ("/dev/input/event13",))})
        interface = input_mode_interface(client)

        interface._reconcile_input_mode(client.composites, InputMode.SHELL)
        interface._reconcile_input_mode({}, InputMode.SHELL)
        client.profile_states.pop(path, None)
        interface._reconcile_input_mode(client.composites, InputMode.SHELL)

        self.assertEqual(
            client.loads,
            [(InputMode.SHELL, path)],
        )

    def test_converged_composite_is_not_reapplied(self) -> None:
        path = "/org/shadowblip/InputPlumber/CompositeDevice0"
        client = RecordingInputPlumber({path: ("045e_0291", ("/dev/input/event13",))})
        interface = input_mode_interface(client)

        interface._reconcile_input_mode(client.composites, InputMode.SHELL)
        interface._reconcile_input_mode(client.composites, InputMode.SHELL)

        self.assertEqual(client.loads, [])
        self.assertEqual(interface._applied_input_modes[path], InputMode.SHELL)

    def test_readback_corrects_game_drift_from_shell_profile(self) -> None:
        path = "/org/shadowblip/InputPlumber/CompositeDevice0"
        client = RecordingInputPlumber({path: ("045e_0291", ("/dev/input/event13",))})
        interface = input_mode_interface(client)
        interface._applied_input_modes[path] = InputMode.GAME
        client.profile_states[path] = CompositeProfileState("/profiles/shell.yaml", "Lulu SHELL", 1)

        interface._reconcile_input_mode(client.composites, InputMode.GAME)

        self.assertEqual(client.loads, [(InputMode.GAME, path)])
        self.assertEqual(client.profile_states[path].profile_path, "/profiles/game.yaml")
        self.assertEqual(interface._applied_input_modes[path], InputMode.GAME)

    def test_readback_corrects_shell_drift_from_game_profile(self) -> None:
        path = "/org/shadowblip/InputPlumber/CompositeDevice0"
        client = RecordingInputPlumber({path: ("045e_0291", ("/dev/input/event13",))})
        interface = input_mode_interface(client)
        interface._applied_input_modes[path] = InputMode.SHELL
        client.profile_states[path] = CompositeProfileState("/profiles/game.yaml", "Lulu GAME", 1)

        interface._reconcile_input_mode(client.composites, InputMode.SHELL)

        self.assertEqual(client.loads, [(InputMode.SHELL, path)])
        self.assertEqual(client.profile_states[path].profile_path, "/profiles/shell.yaml")

    def test_active_managed_osk_owns_temporary_intercept_mode(self) -> None:
        path = "/org/shadowblip/InputPlumber/CompositeDevice0"
        client = RecordingInputPlumber({path: ("045e_0291", ("/dev/input/event13",))})
        client.profile_states[path] = CompositeProfileState(
            "/profiles/osk.yaml", "Lulu OSK", 2,
        )
        interface = input_mode_interface(client)

        with patch("lulu.sessiond._managed_osk_visible", return_value=True):
            interface._reconcile_input_mode(client.composites, InputMode.SHELL)

        self.assertEqual(client.loads, [])
        self.assertNotIn(path, interface._applied_input_modes)

    def test_matching_readback_avoids_profile_reload_even_if_cache_is_empty(self) -> None:
        path = "/org/shadowblip/InputPlumber/CompositeDevice0"
        client = RecordingInputPlumber({path: ("045e_0291", ("/dev/input/event13",))})
        client.profile_states[path] = CompositeProfileState("/profiles/game.yaml", "Lulu GAME", 1)
        interface = input_mode_interface(client)

        interface._reconcile_input_mode(client.composites, InputMode.GAME)

        self.assertEqual(client.loads, [])
        self.assertEqual(interface._applied_input_modes[path], InputMode.GAME)

    def test_unverified_successful_mutation_does_not_populate_applied_cache(self) -> None:
        path = "/org/shadowblip/InputPlumber/CompositeDevice0"
        client = RecordingInputPlumber({path: ("045e_0291", ("/dev/input/event13",))})
        client.reported_mutation_profile = "/profiles/shell.yaml"
        interface = input_mode_interface(client)
        interface._applied_input_modes[path] = InputMode.SHELL

        with self.assertRaisesRegex(RuntimeError, "verification failed"):
            interface._reconcile_input_mode(client.composites, InputMode.GAME)

        self.assertNotIn(path, interface._applied_input_modes)
        self.assertEqual(client.loads, [(InputMode.GAME, path)])

    def test_unchanged_topology_external_drift_is_corrected_on_next_reconcile(self) -> None:
        path = "/org/shadowblip/InputPlumber/CompositeDevice0"
        signature = ("045e_0291", ("/dev/input/event13",))
        client = RecordingInputPlumber({path: signature})
        interface = input_mode_interface(client)
        interface.model.state.input_mode = InputMode.GAME
        interface._reconcile_input_mode(client.composites, InputMode.GAME)
        self.assertEqual(client.loads, [(InputMode.GAME, path)])

        client.profile_states[path] = CompositeProfileState("/profiles/shell.yaml", "Lulu SHELL", 1)
        self.assertEqual(client.composites[path], signature)
        interface._reconcile_input_mode(client.composites, interface.model.state.input_mode)

        self.assertEqual(client.loads[-1], (InputMode.GAME, path))
        self.assertEqual(client.profile_states[path].profile_path, "/profiles/game.yaml")

    def test_existing_controller_monitor_cycle_repairs_unchanged_topology_drift(self) -> None:
        path = "/org/shadowblip/InputPlumber/CompositeDevice0"
        signature = ("045e_0291", ("/dev/input/event13",))
        client = RecordingInputPlumber({path: signature})
        interface = input_mode_interface(client)
        interface.model.state.input_mode = InputMode.GAME
        interface._initialized_composites = {path: signature}
        interface._inputplumber_event = asyncio.Event()
        interface._controller_inventory_snapshot = lambda: (client.composites, {}, {})
        client.profile_states[path] = CompositeProfileState("/profiles/shell.yaml", "Lulu SHELL", 1)
        interface._inputplumber_event.set()

        async def exercise() -> None:
            task = asyncio.create_task(interface._monitor_controller_events())
            try:
                for _ in range(20):
                    if client.loads:
                        break
                    await asyncio.sleep(0.01)
                self.assertEqual(client.loads, [(InputMode.GAME, path)])
            finally:
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)

        asyncio.run(exercise())
        self.assertEqual(client.composites[path], signature)
        self.assertEqual(client.profile_states[path].profile_path, "/profiles/game.yaml")

    def test_service_restart_same_composite_signature_does_not_trust_cache(self) -> None:
        path = "/org/shadowblip/InputPlumber/CompositeDevice0"
        signature = ("045e_0291", ("/dev/input/event13",))
        client = RecordingInputPlumber({path: signature})
        interface = input_mode_interface(client)
        interface.model.state.input_mode = InputMode.GAME
        interface._reconcile_input_mode(client.composites, InputMode.GAME)
        interface._applied_input_modes[path] = InputMode.GAME

        # Simulate InputPlumber restarting and restoring its default profile
        # while reusing the same runtime object and source signature.
        client.profile_states[path] = CompositeProfileState(DEFAULT_PROFILE_PATH, "Default", 1)
        interface._reconcile_input_mode(client.composites, interface.model.state.input_mode)

        self.assertEqual(client.composites[path], signature)
        self.assertEqual(client.loads[-1], (InputMode.GAME, path))
        self.assertEqual(client.profile_states[path].profile_path, "/profiles/game.yaml")

    def test_disappearing_composite_during_profile_readback_is_fail_soft(self) -> None:
        path = "/org/shadowblip/InputPlumber/CompositeDevice0"
        client = RecordingInputPlumber({path: ("045e_0291", ("/dev/input/event13",))})
        interface = input_mode_interface(client)
        interface._applied_input_modes[path] = InputMode.GAME
        client.disappear_on_read.add(path)
        lifecycle = interface.model.state.lifecycle

        interface._reconcile_input_mode(client.composites, InputMode.GAME)

        self.assertNotIn(path, interface._applied_input_modes)
        self.assertEqual(interface.model.state.lifecycle, lifecycle)
        self.assertEqual(client.loads, [])

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

    def test_recreated_composite_reapplies_automatic_unfocused_compatibility(self) -> None:
        path = "/org/shadowblip/InputPlumber/CompositeDevice0"
        client = RecordingInputPlumber({path: ("045e_0291", ("/dev/input/event13",))})
        interface = input_mode_interface(client)
        token = interface.model.request_launch("game-1")
        interface.model.launch_starting(token)
        interface.model.primary_started(token)
        interface.model.set_input_mode(InputMode.COMPAT)
        interface._initialized_composites = {}

        asyncio.run(interface._initialize_composite(path, client.composites[path]))

        self.assertEqual(interface.model.state.input_mode, InputMode.COMPAT)
        self.assertEqual(client.baselines, [path])

    def test_recreated_utility_composite_reapplies_compat_after_default_baseline(self) -> None:
        path = "/org/shadowblip/InputPlumber/CompositeDevice0"
        composite = ("045e_0291", ("/dev/input/event13",))
        client = RecordingInputPlumber({path: composite})
        interface = input_mode_interface(client)
        descriptor = LaunchDescriptor(
            primary_id="utility:flatpak:app.devsuite.Ptyxis",
            classification=SessionClassification.UTILITY,
            title="Ptyxis",
        )
        token = interface.model.request_launch(descriptor)
        interface.model.launch_starting(token)
        interface.model.primary_started(token, presentation=Presentation.FOREIGN_UI,
                                        input_mode=InputMode.COMPAT)
        # Reproduce an already-applied mode cached for the reused object path.
        interface._applied_input_modes[path] = InputMode.COMPAT
        interface._initialized_composites = {}

        asyncio.run(interface._initialize_composite(path, composite))

        self.assertEqual(client.baselines, [path])
        self.assertEqual(client.loads[-1], (InputMode.COMPAT, path))
        self.assertEqual(interface.model.state.input_mode, InputMode.COMPAT)

    def test_shell_bootstrap_does_not_require_a_controller_then_initializes_late_composite(self) -> None:
        class ShellSupervisor:
            def __init__(self) -> None:
                self.commands = []

            def set_delegated_launch_environment(self, values):
                self.environment = dict(values)

            async def launch_shell(self, command, timeout, select_shell=False):
                self.commands.append((command, timeout, select_shell))

        client = RecordingInputPlumber({})
        interface = input_mode_interface(client)
        interface._initialized_composites = {}
        interface._bootstrap_output = "HDMI-A-1"
        interface.supervisor = ShellSupervisor()

        async def exercise() -> None:
            with patch("lulu.sessiond.has_connected_presentation_output", return_value=True), \
                    patch("lulu.sessiond.connected_presentation_outputs", return_value=("HDMI-A-1",)), \
                    patch("lulu.sessiond.discover_presentation_output", return_value="HDMI-A-1"):
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
            first_failure = threading.Event()

            def runtime_composite_statuses(self):
                self.attempts += 1
                if self.attempts == 1:
                    self.first_failure.set()
                    raise subprocess.CalledProcessError(1, "busctl")
                return {path: ("045e_0291", ("/dev/input/event20",))}

        client = FlakyInputPlumber({})
        interface = input_mode_interface(client)
        interface._inputplumber_event = asyncio.Event()
        interface._initialized_composites = {}
        interface._inputplumber_event.set()

        async def exercise() -> None:
            state_changed = asyncio.Event()

            async def notify_state_changed() -> None:
                state_changed.set()

            interface._state_changed = notify_state_changed
            with patch("lulu.sessiond.sdl_gamepad_inventory", return_value=[]):
                task = asyncio.create_task(interface._monitor_controller_events())
                try:
                    # Wait until the first failed query is observed, then
                    # deliver a second event explicitly instead of relying on
                    # monitor startup or polling/sleep timing.
                    self.assertTrue(await asyncio.to_thread(client.first_failure.wait, 2))
                    interface._inputplumber_event.set()
                    await asyncio.wait_for(state_changed.wait(), timeout=2)
                finally:
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
