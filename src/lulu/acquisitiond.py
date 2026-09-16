"""Dedicated provider-neutral acquisition/job D-Bus service."""

from __future__ import annotations

import argparse
import asyncio
import json

from dbus_next import BusType, DBusError
from dbus_next.aio import MessageBus
from dbus_next.service import ServiceInterface, method, signal

from .job_manager import JobManager, job_to_dict
from .contracts import ServiceDescriptor, ServiceName
from .steam_cmd import SteamCmdExecutor
from .romm import RommClient, RommConfig
from .romm_executor import RommExecutor


BUS_NAME = "org.lulu.Acquisitiond"
OBJECT_PATH = "/org/lulu/Acquisition"
INTERFACE_NAME = "org.lulu.Acquisition"
DESCRIPTOR = ServiceDescriptor(
    name=ServiceName.ACQUISITIOND,
    authority="provider-neutral acquisition jobs and normalized progress",
    owned_state=("job snapshots", "job lifecycle", "provider scheduling", "cancellation"),
    notes=("Provider adapters execute work; this service owns normalized state.",),
)


class AcquisitionInterface(ServiceInterface):
    def __init__(self, manager: JobManager) -> None:
        super().__init__(INTERFACE_NAME)
        self.manager = manager
        manager._on_change = self._publish

    def _snapshot(self) -> str:
        return json.dumps({
            "jobs": [job_to_dict(job) for job in self.manager.snapshot()],
            "activeDownloadCount": self.manager.active_download_count,
        }, sort_keys=True)

    def _publish(self, *_: object) -> None:
        self.StateChanged(self._snapshot())

    @method()
    def GetSnapshot(self) -> "s":
        return self._snapshot()

    @method()
    def GetActiveDownloadCount(self) -> "u":
        return self.manager.active_download_count

    @method()
    def SubmitJob(self, provider: "s", content_identity: "s", title: "s") -> "s":
        try:
            return self.manager.submit(provider, content_identity, title).job_id
        except ValueError as error:
            raise DBusError("org.lulu.Acquisition.Error.Unavailable", str(error)) from error

    @method()
    async def CancelJob(self, job_id: "s") -> "":
        try:
            await self.manager.cancel(job_id)
        except KeyError as error:
            raise DBusError("org.lulu.Acquisition.Error.UnknownJob", str(error)) from error

    @signal()
    def StateChanged(self, snapshot: "s") -> "s":
        return snapshot


async def serve(bus_type: BusType = BusType.SESSION) -> None:
    bus = await MessageBus(bus_type=bus_type).connect()
    manager = JobManager(provider_limits={"steam": 1})
    manager.register_executor("steam", SteamCmdExecutor(), limit=1)
    romm_config = RommConfig.from_file()
    manager.register_executor(
        "romm", RommExecutor(RommClient(romm_config) if romm_config else None), limit=1
    )
    interface = AcquisitionInterface(manager)
    bus.export(OBJECT_PATH, interface)
    await bus.request_name(BUS_NAME)
    interface.StateChanged(interface._snapshot())
    await asyncio.Event().wait()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--system-bus", action="store_true")
    args = parser.parse_args()
    asyncio.run(serve(BusType.SYSTEM if args.system_bus else BusType.SESSION))


if __name__ == "__main__":
    main()
