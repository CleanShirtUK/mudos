"""Minimal local D-Bus service for console-sessiond lifecycle authority."""

import argparse
import asyncio
import logging
import subprocess
from dataclasses import asdict
import os
import json
from pathlib import Path
import signal as os_signal

from dbus_next import BusType, DBusError, MessageType
from dbus_next.aio import MessageBus
from dbus_next.service import ServiceInterface, method, signal

from .console_sessiond import SessionStateModel
from .controllerd import ControllerRegistry, default_inputplumber_client
from .gamescope import GamescopeInvocation, GamescopePresentation, discover_presentation_output
from .contracts import InputMode, Lifecycle
from .launch_identity import LaunchIdentity
from .process_supervisor import ProcessSupervisor
from .process_supervisor import ProcessResult
from .paths import PATHS


BUS_NAME = "org.lulu.ConsoleSessiond"
OBJECT_PATH = "/org/lulu/ConsoleSession"
INTERFACE_NAME = "org.lulu.ConsoleSession"
LOGGER = logging.getLogger("lulu.sessiond")


class ConsoleSessionInterface(ServiceInterface):
    # Temporary Steam baseline: retain the implementation but do not reassert
    # Lulu's Gamescope shell selection.
    _presentation_watchdog_enabled = True

    def __init__(self, model: SessionStateModel) -> None:
        super().__init__(INTERFACE_NAME)
        self.model = model
        inputplumber = default_inputplumber_client(
            Path(__file__).resolve().parents[2] / "config" / "inputplumber"
        )
        self.controller_registry = ControllerRegistry(Path.home() / ".config/lulu/controller-policy.json")
        self._inputplumber = inputplumber
        self._native_controller = os.environ.get("LULU_NATIVE_CONTROLLER", "0") == "1"
        self._applied_input_modes: dict[str, InputMode] = {}
        self._local_identity: LaunchIdentity | None = None
        self._controller_monitor_task: asyncio.Task[None] | None = None
        self._inputplumber_bus: MessageBus | None = None
        self._inputplumber_proxy: object | None = None
        self._inputplumber_properties: object | None = None
        self._inputplumber_event: asyncio.Event | None = None
        self._initialized_composites: dict[str, tuple[str, tuple[str, ...]]] = {}
        self._presentation_watchdog_task: asyncio.Task[None] | None = None
        self._shell_selection_task: asyncio.Task[None] | None = None
        self._bootstrap_output = os.environ.get("LULU_OUTPUT_CONNECTOR")
        self.supervisor = ProcessSupervisor(
            model,
            self._state_changed,
            presentation=GamescopePresentation(),
            input_mode_changed=None if self._native_controller else self._apply_input_mode,
        )

    def _state_json(self) -> str:
        state = asdict(self.model.state)
        state.update(
            {
                "lifecycle": self.model.state.lifecycle.value,
                "presentation": self.model.state.presentation.value,
                "overlay": self.model.state.overlay.value,
                "input_mode": self.model.state.input_mode.value,
                "last_failure_reason": self.model.last_failure_reason,
                "controller": {
                    "navigation_controller_id": self.controller_registry.navigation_controller_id,
                    "controllers": {
                        controller_id: {
                            "connected": controller.connected,
                            "player": controller.player,
                            "physical_identity": controller.physical_identity,
                            "battery": {
                                "kind": controller.battery.kind.value,
                                "percentage": controller.battery.percentage,
                                "state": controller.battery.state,
                            },
                        }
                        for controller_id, controller in self.controller_registry.controllers.items()
                    },
                },
                **self.supervisor.state_details(),
            }
        )
        if self._local_identity is not None:
            state["active_identity"] = asdict(self._local_identity)
        return json.dumps(state, sort_keys=True)

    def _error(self, error: ValueError) -> DBusError:
        return DBusError("org.lulu.ConsoleSession.Error.InvalidState", str(error))

    async def _state_changed(self) -> None:
        self.StateChanged(self._state_json())

    async def start_controller_monitor(self) -> None:
        composites = await asyncio.to_thread(self._inputplumber.runtime_composite_statuses)
        self.controller_registry.observe_runtime_composites(composites)
        for object_path, composite in composites.items():
            _, source_paths = composite
            if source_paths:
                try:
                    await self._initialize_composite(object_path, composite)
                except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as error:
                    logging.getLogger("lulu.sessiond").warning(
                        "controller initialization pending path=%s error=%s", object_path, error
                    )
        self._inputplumber_event = asyncio.Event()
        self._inputplumber_bus = await MessageBus(bus_type=BusType.SYSTEM).connect()
        introspection = await self._inputplumber_bus.introspect(
            "org.shadowblip.InputPlumber", "/org/shadowblip/InputPlumber/Manager"
        )
        proxy = self._inputplumber_bus.get_proxy_object(
            "org.shadowblip.InputPlumber", "/org/shadowblip/InputPlumber/Manager", introspection
        )
        self._inputplumber_proxy = proxy
        self._inputplumber_bus._add_match_rule(
            "type='signal',sender='org.shadowblip.InputPlumber',"
            "path='/org/shadowblip/InputPlumber/Manager',"
            "interface='org.freedesktop.DBus.Properties',member='PropertiesChanged'"
        )
        self._inputplumber_bus.add_message_handler(self._handle_inputplumber_signal)
        self._controller_monitor_task = asyncio.create_task(self._monitor_controller_events())
        if self._presentation_watchdog_enabled:
            self._presentation_watchdog_task = asyncio.create_task(self._monitor_presentation())

    async def _initialize_composite(
        self, object_path: str, composite: tuple[str, tuple[str, ...]] | None = None
    ) -> None:
        if composite is None:
            composite = await asyncio.to_thread(self._inputplumber.composite_status, object_path)
        if not composite[1] or self._initialized_composites.get(object_path) == composite:
            return
        await asyncio.to_thread(
            self._inputplumber.ensure_default_intercept,
            object_path,
        )
        # A recreated composite always starts from the safe gamepad baseline;
        # Compatibility Mode must never survive a device rebuild.
        reset_mode = InputMode.SHELL if self.model.state.lifecycle.value == "shell" else InputMode.GAME
        self._apply_input_mode(reset_mode)
        self.model.set_input_mode(reset_mode)
        self._initialized_composites[object_path] = composite
        logging.getLogger("lulu.sessiond").info(
            "initialized InputPlumber profile=Default InterceptMode=1 composite=%s", object_path
        )

    async def _monitor_presentation(self) -> None:
        while True:
            try:
                if self.model.state.lifecycle.value != "game":
                    self.supervisor.ensure_shell_presentation()
            except (OSError, RuntimeError, TimeoutError, subprocess.SubprocessError) as error:
                logging.getLogger("lulu.sessiond").warning("shell presentation check failed: %s", error)
            await asyncio.sleep(0.5)

    def _reconcile_input_mode(
        self,
        composites: dict[str, tuple[str, tuple[str, ...]]],
        mode: InputMode,
    ) -> None:
        connected_paths = {
            runtime_path
            for runtime_path, (_, source_paths) in composites.items()
            if source_paths
        }
        for runtime_path in set(self._applied_input_modes) - connected_paths:
            del self._applied_input_modes[runtime_path]

        for runtime_path in sorted(connected_paths):
            if self._applied_input_modes.get(runtime_path) is mode:
                continue
            if getattr(self, "_native_controller", False) and mode is not InputMode.COMPAT:
                self._inputplumber.ensure_default_intercept(runtime_path)
            else:
                self._inputplumber.load_mode(mode, runtime_path)
            self._applied_input_modes[runtime_path] = mode

    def _apply_input_mode(self, mode: InputMode) -> None:
        composites = self._inputplumber.runtime_composite_statuses()
        if composites:
            self._reconcile_input_mode(composites, mode)
        else:
            # Preserve the no-controller path; a future composite will converge
            # through the monitor when it appears.
            if getattr(self, "_native_controller", False) and mode is not InputMode.COMPAT:
                self._inputplumber.ensure_default_intercept()
            else:
                self._inputplumber.load_mode(mode)

    async def _monitor_controller_events(self) -> None:
        if self._inputplumber_event is None:
            return
        while True:
            try:
                await asyncio.wait_for(self._inputplumber_event.wait(), timeout=1.0)
                self._inputplumber_event.clear()
            except asyncio.TimeoutError:
                pass
            try:
                composites = await asyncio.to_thread(self._inputplumber.runtime_composite_statuses)
            except (OSError, RuntimeError, ValueError, subprocess.SubprocessError):
                continue
            self._initialized_composites = {
                path: signature
                for path, signature in self._initialized_composites.items()
                if path in composites and composites[path] == signature
            }
            before = self.controller_registry.navigation_controller_id, tuple(
                (key, value.connected, value.player)
                for key, value in self.controller_registry.controllers.items()
            )
            self.controller_registry.observe_runtime_composites(composites)
            for object_path, composite in composites.items():
                if composite[1]:
                    try:
                        await self._initialize_composite(object_path, composite)
                    except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as error:
                        logging.getLogger("lulu.sessiond").warning(
                            "controller initialization pending path=%s error=%s", object_path, error
                        )
            after = self.controller_registry.navigation_controller_id, tuple(
                (key, value.connected, value.player)
                for key, value in self.controller_registry.controllers.items()
            )
            if before != after:
                await self._state_changed()
            await asyncio.sleep(0.25)

    async def bootstrap_shell(self) -> None:
        output = self._bootstrap_output or discover_presentation_output()
        invocation = GamescopeInvocation.from_environment()
        invocation = GamescopeInvocation(
            steam=False,
            output=output,
            output_width=invocation.output_width,
            output_height=invocation.output_height,
            output_refresh=invocation.output_refresh,
            nested_width=invocation.nested_width,
            nested_height=invocation.nested_height,
        )
        shell = str(Path(__file__).resolve().parents[2] / "scripts" / "console-ui.sh")
        await self.supervisor.launch_shell(invocation.argv([shell]), 15000, select_shell=False)
        self._shell_selection_task = asyncio.create_task(self._select_ready_shell())

    async def _select_ready_shell(self) -> None:
        marker = PATHS.runtime_root / "mudos-shell.pid"
        try:
            deadline = asyncio.get_running_loop().time() + 15
            while asyncio.get_running_loop().time() < deadline:
                try:
                    pid = int(marker.read_text().strip())
                except (FileNotFoundError, ValueError):
                    await asyncio.sleep(0.05)
                    continue
                try:
                    await asyncio.to_thread(self.supervisor._presentation.select_shell, pid)
                    return
                except (OSError, RuntimeError, TimeoutError, subprocess.SubprocessError) as error:
                    logging.getLogger("lulu.sessiond").warning("shell window selection pending: %s", error)
                    await asyncio.sleep(0.05)
            logging.getLogger("lulu.sessiond").error("Mudos shell readiness window was not found")
        except asyncio.CancelledError:
            raise

    async def stop_controller_monitor(self) -> None:
        if self._shell_selection_task is not None:
            self._shell_selection_task.cancel()
            await asyncio.gather(self._shell_selection_task, return_exceptions=True)
            self._shell_selection_task = None
        if self._controller_monitor_task is not None:
            self._controller_monitor_task.cancel()
            await asyncio.gather(self._controller_monitor_task, return_exceptions=True)
            self._controller_monitor_task = None
        if self._inputplumber_bus is not None:
            self._inputplumber_bus.remove_message_handler(self._handle_inputplumber_signal)
            self._inputplumber_bus.disconnect()
            self._inputplumber_bus = None
            self._inputplumber_proxy = None
            self._inputplumber_properties = None
        if self._presentation_watchdog_task is not None:
            self._presentation_watchdog_task.cancel()
            await asyncio.gather(self._presentation_watchdog_task, return_exceptions=True)
            self._presentation_watchdog_task = None

    def _handle_inputplumber_signal(self, message: object) -> None:
        if (
            getattr(message, "message_type", None) is MessageType.SIGNAL
            and getattr(message, "path", None) == "/org/shadowblip/InputPlumber/Manager"
            and getattr(message, "interface", None) == "org.freedesktop.DBus.Properties"
            and getattr(message, "member", None) == "PropertiesChanged"
        ):
            body = getattr(message, "body", ())
            if len(body) > 1 and body[0] == "org.shadowblip.InputManager" and "GamepadOrder" in body[1]:
                order = body[1]["GamepadOrder"]
                order = getattr(order, "value", order)
                if not order:
                    # Clear lifetime state before a fast disconnect/reconnect can
                    # reuse the same object path.
                    self._initialized_composites.clear()
                if self._inputplumber_event is not None:
                    self._inputplumber_event.set()

    @method()
    def GetState(self) -> "s":
        return self._state_json()

    @method()
    def SetControllerPlayer(self, controller_id: "s", player: "i") -> "s":
        self.controller_registry.assign_player(controller_id, None if player <= 0 else player)
        state = self._state_json()
        self.StateChanged(state)
        return state

    @method()
    def SetNavigationController(self, controller_id: "s") -> "s":
        self.controller_registry.set_navigation_controller(controller_id or None)
        state = self._state_json()
        self.StateChanged(state)
        return state

    @method()
    def BeginLocalSession(self, game_id: "s", pid: "u", pgid: "u", executable: "s", argv: "as") -> "s":
        if self._local_identity is not None:
            raise self._error(ValueError("another local session owns the session"))
        token: str | None = None
        try:
            token = self.model.request_launch(game_id)
            self.model.launch_starting(token)
            self._local_identity = LaunchIdentity(token, pid, pgid, executable, tuple(argv))
            self._apply_input_mode(InputMode.GAME)
            self.model.primary_started(token, input_mode=InputMode.GAME)
        except (OSError, ValueError, TimeoutError) as error:
            self._local_identity = None
            if token is not None and self.model.state.lifecycle is not Lifecycle.SHELL:
                self.model.fail(token, f"local launch failed: {error}")
                self.model.return_complete(token)
            raise self._error(ValueError(str(error))) from error
        self.StateChanged(self._state_json())
        return token

    @method()
    def BeginProviderSession(self, provider_id: "s", controller_mode: "s", pid: "u", pgid: "u", executable: "s", argv: "as") -> "s":
        if controller_mode not in {"game", "compat"}:
            raise self._error(ValueError("invalid provider controller mode"))
        if self._local_identity is not None:
            raise self._error(ValueError("another local session owns the session"))
        token: str | None = None
        try:
            token = self.model.request_launch(f"provider:{provider_id}:standalone")
            self.model.state.controller_mode = controller_mode
            self.model.launch_starting(token)
            self._local_identity = LaunchIdentity(token, pid, pgid, executable, tuple(argv))
            self._apply_input_mode(InputMode.GAME)
            self.model.primary_started(token, input_mode=InputMode.GAME)
        except (OSError, ValueError, TimeoutError) as error:
            self._local_identity = None
            if token is not None and self.model.state.lifecycle is not Lifecycle.SHELL:
                self.model.fail(token, f"provider launch failed: {error}")
                self.model.return_complete(token)
            raise self._error(ValueError(str(error))) from error
        self.StateChanged(self._state_json())
        return token

    @method()
    def EndLocalSession(self, token: "s", exit_code: "i") -> "":
        if self._local_identity is None or self._local_identity.token != token:
            return
        identity = self._local_identity
        if self.model.state.lifecycle is Lifecycle.GAME:
            self.model.primary_exited(token, success=exit_code == 0)
            self.model.record_result(ProcessResult(
                token=token,
                pid=identity.pid,
                pgid=identity.pgid,
                executable=identity.executable,
                argv=identity.argv,
                exit_code=exit_code if exit_code >= 0 else None,
                signal=-exit_code if exit_code < 0 else None,
                outcome="success" if exit_code == 0 else "failed",
                error=None if exit_code == 0 else f"process exited with status {exit_code}",
            ))
            self._apply_input_mode(InputMode.SHELL)
            self.model.set_input_mode(InputMode.SHELL)
            self.model.return_complete(token)
        self._local_identity = None
        self.StateChanged(self._state_json())

    @method()
    async def RequestLaunch(self, command: "as", startup_timeout_ms: "u") -> "s":
        try:
            token = await self.supervisor.launch(list(command), startup_timeout_ms)
        except ValueError as error:
            raise self._error(error) from error
        return token

    @method()
    async def RequestShellLaunch(self, command: "as", startup_timeout_ms: "u") -> "s":
        try:
            return await self.supervisor.launch_shell(list(command), startup_timeout_ms)
        except ValueError as error:
            raise self._error(error) from error

    @method()
    def RequestSteamLaunch(self, app_id: "s", startup_timeout_ms: "u") -> "s":
        try:
            return self.supervisor.queue_steam_launch(app_id, startup_timeout_ms)
        except ValueError as error:
            raise self._error(error) from error

    @method()
    async def CancelLaunch(self) -> "":
        task = asyncio.current_task()
        LOGGER.info("CANCEL_DBUS_ENTER task=%s task_id=%s", task.get_name() if task is not None else "none", id(task) if task is not None else None)
        try:
            await self.supervisor.cancel_launch()
        except ValueError as error:
            raise self._error(error) from error
        finally:
            LOGGER.info("CANCEL_DBUS_FINALLY task=%s task_id=%s", task.get_name() if task is not None else "none", id(task) if task is not None else None)

    @method()
    async def RequestSteamStore(self, startup_timeout_ms: "u") -> "s":
        try:
            return await self.supervisor.launch_steam_store(startup_timeout_ms)
        except (OSError, TimeoutError, ValueError) as error:
            raise self._error(ValueError(str(error))) from error

    @method()
    async def RequestSteamInstall(self, app_id: "s", startup_timeout_ms: "u") -> "s":
        try:
            return await self.supervisor.launch_steam_install(app_id, startup_timeout_ms)
        except (OSError, TimeoutError, ValueError) as error:
            raise self._error(ValueError(str(error))) from error

    @method()
    async def RequestMudosDownloads(self) -> "":
        self.model.request_surface("downloads")
        await self._state_changed()

    @method()
    async def ClearRequestedSurface(self) -> "":
        self.model.clear_requested_surface()
        await self._state_changed()

    @method()
    async def RequestSteamStoreSurface(self) -> "s":
        try:
            return await self.supervisor.open_steam_store_surface()
        except ValueError as error:
            raise self._error(error) from error

    @method()
    async def QuitDelegated(self) -> "":
        try:
            await self.supervisor.quit_delegated()
        except ValueError as error:
            raise self._error(error) from error

    @method()
    async def ResetMudos(self) -> "s":
        asyncio.create_task(self._reset_mudos())
        return "reset-requested"

    async def _reset_mudos(self) -> None:
        LOGGER.warning("session stop attribution source=ResetMudos reason=controlled-reset")
        await self.stop_controller_monitor()
        await self.supervisor.stop()
        os.kill(os.getpid(), os_signal.SIGTERM)

    @method()
    async def Reboot(self) -> "s":
        LOGGER.warning("controlled reboot requested")
        await asyncio.create_subprocess_exec("systemctl", "reboot")
        return "reboot-requested"

    @method()
    async def Shutdown(self) -> "s":
        LOGGER.warning("controlled shutdown requested")
        await asyncio.create_subprocess_exec("systemctl", "poweroff")
        return "shutdown-requested"

    @method()
    def SetInputMode(self, mode: "s") -> "":
        try:
            requested = InputMode(mode)
            if requested is InputMode.COMPAT and self.model.state.lifecycle.value != "game":
                raise ValueError("Compatibility Mode requires an active application")
            self._apply_input_mode(requested)
            self.model.set_input_mode(requested)
        except (ValueError, KeyError) as error:
            raise self._error(ValueError(str(error))) from error
        self.StateChanged(self._state_json())

    @signal()
    def StateChanged(self, state: "s") -> "s":
        return state


async def _wait_for_stop(stop_event: asyncio.Event) -> None:
    LOGGER.info("sessiond idle; waiting for stop signal")
    await stop_event.wait()
    LOGGER.info("sessiond stop requested; beginning shutdown")


async def serve(bus_type: BusType = BusType.SESSION, bootstrap_shell: bool = False) -> None:
    bus = await MessageBus(bus_type=bus_type).connect()
    model = SessionStateModel()
    interface = ConsoleSessionInterface(model)
    bus.export(OBJECT_PATH, interface)
    await bus.request_name(BUS_NAME)
    await interface.start_controller_monitor()
    if bootstrap_shell:
        await interface.bootstrap_shell()
    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    def request_stop(stop_signal: os_signal.Signals) -> None:
        LOGGER.warning("session stop attribution source=process-signal signal=%s pid=%s ppid=%s",
                       stop_signal.name, os.getpid(), os.getppid())
        stop_event.set()

    for stop_signal in (os_signal.SIGINT, os_signal.SIGTERM):
        loop.add_signal_handler(stop_signal, request_stop, stop_signal)
    await _wait_for_stop(stop_event)
    await interface.stop_controller_monitor()
    await interface.supervisor.stop()
    bus.disconnect()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--system-bus", action="store_true", help="Use the system D-Bus")
    parser.add_argument("--bootstrap-shell", action="store_true", help="Start the Gamescope-backed Lulu shell")
    args = parser.parse_args()
    asyncio.run(serve(BusType.SYSTEM if args.system_bus else BusType.SESSION, args.bootstrap_shell))


if __name__ == "__main__":
    main()
