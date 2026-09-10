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
from .contracts import InputMode
from .process_supervisor import ProcessSupervisor


BUS_NAME = "org.lulu.ConsoleSessiond"
OBJECT_PATH = "/org/lulu/ConsoleSession"
INTERFACE_NAME = "org.lulu.ConsoleSession"


class ConsoleSessionInterface(ServiceInterface):
    # Temporary Steam baseline: retain the implementation but do not reassert
    # Lulu's Gamescope shell selection.
    _presentation_watchdog_enabled = False

    def __init__(self, model: SessionStateModel) -> None:
        super().__init__(INTERFACE_NAME)
        self.model = model
        inputplumber = default_inputplumber_client(
            Path(__file__).resolve().parents[2] / "config" / "inputplumber"
        )
        self.controller_registry = ControllerRegistry()
        self._inputplumber = inputplumber
        self._native_controller = os.environ.get("LULU_NATIVE_CONTROLLER", "0") == "1"
        self._applied_input_modes: dict[str, InputMode] = {}
        self._controller_monitor_task: asyncio.Task[None] | None = None
        self._inputplumber_bus: MessageBus | None = None
        self._inputplumber_proxy: object | None = None
        self._inputplumber_properties: object | None = None
        self._inputplumber_event: asyncio.Event | None = None
        self._initialized_composites: set[str] = set()
        self._presentation_watchdog_task: asyncio.Task[None] | None = None
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
                        }
                        for controller_id, controller in self.controller_registry.controllers.items()
                    },
                },
                **self.supervisor.state_details(),
            }
        )
        return json.dumps(state, sort_keys=True)

    def _error(self, error: ValueError) -> DBusError:
        return DBusError("org.lulu.ConsoleSession.Error.InvalidState", str(error))

    async def _state_changed(self) -> None:
        self.StateChanged(self._state_json())

    async def start_controller_monitor(self) -> None:
        composites = await asyncio.to_thread(self._inputplumber.runtime_composite_statuses)
        if self._inputplumber.object_path not in composites:
            raise RuntimeError("persistent InputPlumber composite is unavailable")
        self.controller_registry.observe_runtime_composites(composites)
        await self._initialize_composite(self._inputplumber.object_path)
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

    async def _initialize_composite(self, object_path: str) -> None:
        if object_path in self._initialized_composites:
            return
        await asyncio.to_thread(
            self._inputplumber.set_intercept_mode,
            1,
            object_path,
        )
        self._initialized_composites.add(object_path)
        logging.getLogger("lulu.sessiond").info(
            "initialized InputPlumber InterceptMode=1 composite=%s", object_path
        )

    async def _monitor_presentation(self) -> None:
        while True:
            try:
                self.supervisor.ensure_shell_presentation()
            except (OSError, RuntimeError, TimeoutError, subprocess.SubprocessError) as error:
                logging.getLogger("lulu.sessiond").warning("shell presentation check failed: %s", error)
            await asyncio.sleep(0.5)

    def _reconcile_input_mode(
        self,
        composites: dict[str, tuple[str, tuple[str, ...]]],
        mode: InputMode,
    ) -> None:
        if getattr(self, "_native_controller", False):
            return
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
            self._inputplumber.load_mode(mode, runtime_path)
            self._applied_input_modes[runtime_path] = mode

    def _apply_input_mode(self, mode: InputMode) -> None:
        composites = self._inputplumber.runtime_composite_statuses()
        if composites:
            self._reconcile_input_mode(composites, mode)
        else:
            # Preserve the no-controller path; a future composite will converge
            # through the monitor when it appears.
            self._inputplumber.load_mode(mode)

    async def _monitor_controller_events(self) -> None:
        if self._inputplumber_event is None:
            return
        while True:
            await self._inputplumber_event.wait()
            self._inputplumber_event.clear()
            try:
                composites = await asyncio.to_thread(self._inputplumber.runtime_composite_statuses)
            except (OSError, RuntimeError, ValueError):
                continue
            self._initialized_composites.intersection_update(composites)
            before = self.controller_registry.navigation_controller_id, tuple(
                (key, value.connected) for key, value in self.controller_registry.controllers.items()
            )
            self.controller_registry.observe_runtime_composites(composites)
            for object_path, (_, source_paths) in composites.items():
                if source_paths and object_path not in self._initialized_composites:
                    await self._initialize_composite(object_path)
            after = self.controller_registry.navigation_controller_id, tuple(
                (key, value.connected) for key, value in self.controller_registry.controllers.items()
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
        await self.supervisor.launch_shell(invocation.argv([shell]), 15000, select_shell=True)

    async def stop_controller_monitor(self) -> None:
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
                if self._inputplumber_event is not None:
                    self._inputplumber_event.set()

    @method()
    def GetState(self) -> "s":
        return self._state_json()

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
    def SetInputMode(self, mode: "s") -> "":
        try:
            self.model.set_input_mode(InputMode(mode))
        except (ValueError, KeyError) as error:
            raise self._error(ValueError(f"invalid input mode: {mode}")) from error
        self.StateChanged(self._state_json())

    @signal()
    def StateChanged(self, state: "s") -> "s":
        return state


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
    for stop_signal in (os_signal.SIGINT, os_signal.SIGTERM):
        loop.add_signal_handler(stop_signal, stop_event.set)
    await stop_event.wait()
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
