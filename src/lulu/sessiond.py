"""Minimal local D-Bus service for console-sessiond lifecycle authority."""

import argparse
import asyncio
from dataclasses import asdict
import json
import signal as os_signal

from dbus_next import BusType, DBusError
from dbus_next.aio import MessageBus
from dbus_next.service import ServiceInterface, method, signal

from .console_sessiond import SessionStateModel
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
        self.supervisor = ProcessSupervisor(model, self._state_changed, presentation=GamescopePresentation())

    def _state_json(self) -> str:
        state = asdict(self.model.state)
        state.update(
            {
                "lifecycle": self.model.state.lifecycle.value,
                "presentation": self.model.state.presentation.value,
                "overlay": self.model.state.overlay.value,
                "input_mode": self.model.state.input_mode.value,
                "last_failure_reason": self.model.last_failure_reason,
                **self.supervisor.state_details(),
            }
        )
        return json.dumps(state, sort_keys=True)

    def _error(self, error: ValueError) -> DBusError:
        return DBusError("org.lulu.ConsoleSession.Error.InvalidState", str(error))

    async def _state_changed(self) -> None:
        self.StateChanged(self._state_json())

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
    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for stop_signal in (os_signal.SIGINT, os_signal.SIGTERM):
        loop.add_signal_handler(stop_signal, stop_event.set)
    await stop_event.wait()
    await interface.supervisor.stop()
    bus.disconnect()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--system-bus", action="store_true", help="Use the system D-Bus")
    args = parser.parse_args()
    asyncio.run(serve(BusType.SYSTEM if args.system_bus else BusType.SESSION))


if __name__ == "__main__":
    main()
