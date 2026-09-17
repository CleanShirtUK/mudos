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
from lulu.contracts import InputMode, Lifecycle, Overlay, Role, ServiceName
from lulu.gamescope import GamescopeInvocation, discover_presentation_output
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
            catalogue.artwork = type("Artwork", (), {"enrich": lambda self, games: {}})()
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
        registry.observe_runtime_composites(
            {
                "CompositeDevice0": ("045e_0291", ("/dev/input/event18",)),
                "CompositeDevice1": ("045e_0291", ("/dev/input/event22",)),
            }
        )
        self.assertEqual(registry.navigation_controller_id, "CompositeDevice0")
        self.assertEqual(registry.controllers["CompositeDevice0"].player, 1)
        self.assertEqual(registry.controllers["CompositeDevice1"].player, 2)

        registry.observe_runtime_composites(
            {"CompositeDevice1": ("045e_0291", ("/dev/input/event22",))}
        )
        self.assertFalse(registry.controllers["CompositeDevice0"].connected)
        self.assertTrue(registry.controllers["CompositeDevice1"].connected)
        self.assertEqual(registry.controllers["CompositeDevice0"].player, 1)
        self.assertEqual(registry.navigation_controller_id, "CompositeDevice1")
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
        self.assertEqual(interface.controller_registry.navigation_controller_id, path)

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
