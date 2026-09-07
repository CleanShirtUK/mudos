"""Minimal local D-Bus service for console-sessiond lifecycle authority."""

import argparse
import asyncio
from dataclasses import asdict
import json
from pathlib import Path
import signal as os_signal

from dbus_next import BusType, DBusError
from dbus_next.aio import MessageBus
from dbus_next.service import ServiceInterface, method, signal

from .console_sessiond import SessionStateModel
from .controllerd import ControllerRegistry, default_inputplumber_client
from .gamescope import GamescopePresentation
from .contracts import InputMode
from .process_supervisor import ProcessSupervisor


BUS_NAME = "org.lulu.ConsoleSessiond"
OBJECT_PATH = "/org/lulu/ConsoleSession"
INTERFACE_NAME = "org.lulu.ConsoleSession"


class ConsoleSessionInterface(ServiceInterface):
    def __init__(self, model: SessionStateModel) -> None:
        super().__init__(INTERFACE_NAME)
        self.model = model
        inputplumber = default_inputplumber_client(
            Path(__file__).resolve().parents[2] / "config" / "inputplumber"
        )
        self.controller_registry = ControllerRegistry()
        self._inputplumber = inputplumber
        self._controller_monitor_task: asyncio.Task[None] | None = None
        self.supervisor = ProcessSupervisor(
            model,
            self._state_changed,
            presentation=GamescopePresentation(),
            input_mode_changed=inputplumber.load_mode,
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
        self._controller_monitor_task = asyncio.create_task(self._monitor_controller())

    async def _monitor_controller(self) -> None:
        while True:
            persistent_id, source_paths = await asyncio.to_thread(self._inputplumber.composite_status)
            before = self.controller_registry.navigation_controller_id, tuple(
                (key, value.connected) for key, value in self.controller_registry.controllers.items()
            )
            self.controller_registry.observe_persistent_composite(persistent_id, source_paths)
            after = self.controller_registry.navigation_controller_id, tuple(
                (key, value.connected) for key, value in self.controller_registry.controllers.items()
            )
            if before != after:
                await self._state_changed()
            await asyncio.sleep(0.25)

    async def stop_controller_monitor(self) -> None:
        if self._controller_monitor_task is not None:
            self._controller_monitor_task.cancel()
            await asyncio.gather(self._controller_monitor_task, return_exceptions=True)
            self._controller_monitor_task = None

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
    async def RequestSteamLaunch(self, app_id: "s", startup_timeout_ms: "u") -> "s":
        try:
            return await self.supervisor.launch_steam(app_id, startup_timeout_ms)
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


async def serve(bus_type: BusType = BusType.SESSION) -> None:
    bus = await MessageBus(bus_type=bus_type).connect()
    model = SessionStateModel()
    interface = ConsoleSessionInterface(model)
    bus.export(OBJECT_PATH, interface)
    await bus.request_name(BUS_NAME)
    await interface.start_controller_monitor()
    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for stop_signal in (os_signal.SIGINT, os_signal.SIGTERM):
        loop.add_signal_handler(stop_signal, stop_event.set)
    await stop_event.wait()
    await interface.stop_controller_monitor()
    await interface.supervisor.stop()
    bus.disconnect()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--system-bus", action="store_true", help="Use the system D-Bus")
    args = parser.parse_args()
    asyncio.run(serve(BusType.SYSTEM if args.system_bus else BusType.SESSION))


if __name__ == "__main__":
    main()
