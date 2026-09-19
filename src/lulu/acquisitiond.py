"""Dedicated provider-neutral acquisition/job D-Bus service."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
from pathlib import Path

from dbus_next import BusType, DBusError
from dbus_next.aio import MessageBus
from dbus_next.service import ServiceInterface, method, signal

from .job_manager import JobManager, job_to_dict
from .contracts import ServiceDescriptor, ServiceName
from .acquisition_store import AcquisitionStore
from .paths import PATHS
from .plugins import PluginRegistry
from .credential import CredentialInput
from .catalogue import CatalogueStore
from .local_uninstall import LocalUninstallExecutor
from .jobs import JobOperation


BUS_NAME = "org.lulu.Acquisitiond"
OBJECT_PATH = "/org/lulu/Acquisition"
INTERFACE_NAME = "org.lulu.Acquisition"
DESCRIPTOR = ServiceDescriptor(
    name=ServiceName.ACQUISITIOND,
    authority="provider-neutral acquisition jobs and normalized progress",
    owned_state=("job snapshots", "job lifecycle", "provider scheduling", "cancellation"),
    notes=("Provider adapters execute work; this service owns normalized state.",),
)
LOGGER = logging.getLogger("lulu.acquisitiond")


class AcquisitionInterface(ServiceInterface):
    def __init__(self, manager: JobManager, catalogue: CatalogueStore) -> None:
        super().__init__(INTERFACE_NAME)
        self.manager = manager
        self.catalogue = catalogue
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
            executor = self.manager.executors.get(provider)
            return self.manager.submit(provider, content_identity, title,
                                       cancellation_supported=True,
                                       pause_supported=bool(getattr(executor, "supports_pause", False))).job_id
        except ValueError as error:
            raise DBusError("org.lulu.Acquisition.Error.Unavailable", str(error)) from error

    def _uninstall_target(self, game_id: str) -> tuple[object, str, str, str]:
        game = self.catalogue.get_game(game_id)
        if game is None:
            raise DBusError("org.lulu.Acquisition.Error.NotFound", "game was not found")
        target = game
        if game.provider == "romm" and game.installed_game_id:
            target = self.catalogue.get_game(game.installed_game_id) or game
        if target.install_state != "installed":
            raise DBusError("org.lulu.Acquisition.Error.NotInstalled", "game is not installed")
        provider = str(target.provider)
        identity = str(target.game_id if provider == "local" else f"steam:{target.provider_id}")
        executor = self.manager.executors.get(provider)
        if executor is None or not hasattr(executor, "uninstall"):
            raise DBusError("org.lulu.Acquisition.Error.Unsupported", "uninstall is not supported")
        return target, provider, identity, str(target.title)

    @method()
    def CanUninstall(self, game_id: "s") -> "s":
        try:
            target, provider, identity, title = self._uninstall_target(game_id)
            description = "Remove local installed content" if provider == "local" else "Remove Steam installation"
            return json.dumps({"supported": True, "installed": True, "provider": provider,
                               "operation": "remove", "description": description,
                               "target_game_id": target.game_id}, sort_keys=True)
        except DBusError:
            return json.dumps({"supported": False, "installed": False}, sort_keys=True)

    @method()
    def UninstallGame(self, game_id: "s") -> "s":
        try:
            target, provider, identity, title = self._uninstall_target(game_id)
            return self.manager.submit(provider, identity, title,
                                       operation=JobOperation.REMOVE,
                                       cancellation_supported=False).job_id
        except DBusError:
            raise
        except ValueError as error:
            raise DBusError("org.lulu.Acquisition.Error.Conflict", str(error)) from error

    @method()
    async def CancelJob(self, job_id: "s") -> "":
        try:
            await self.manager.cancel(job_id)
        except KeyError as error:
            raise DBusError("org.lulu.Acquisition.Error.UnknownJob", str(error)) from error

    @method()
    async def PauseJob(self, job_id: "s") -> "":
        try:
            await self.manager.pause(job_id)
        except KeyError as error:
            raise DBusError("org.lulu.Acquisition.Error.UnknownJob", str(error)) from error

    @method()
    async def ResumeJob(self, job_id: "s") -> "":
        try:
            await self.manager.resume(job_id)
        except KeyError as error:
            raise DBusError("org.lulu.Acquisition.Error.UnknownJob", str(error)) from error

    @method()
    def RetryJob(self, job_id: "s") -> "s":
        try:
            return self.manager.retry(job_id).job_id
        except (KeyError, ValueError) as error:
            raise DBusError("org.lulu.Acquisition.Error.Unavailable", str(error)) from error

    @method()
    def ClearFailedJob(self, job_id: "s") -> "":
        try:
            self.manager.retire(job_id)
        except KeyError as error:
            raise DBusError("org.lulu.Acquisition.Error.UnknownJob", str(error)) from error
        except ValueError as error:
            raise DBusError("org.lulu.Acquisition.Error.Unavailable", str(error)) from error

    @signal()
    def StateChanged(self, snapshot: "s") -> "s":
        return snapshot


async def serve(bus_type: BusType = BusType.SESSION) -> None:
    LOGGER.info("acquisitiond_lifecycle event=start pid=%s uid=%s", os.getpid(), os.geteuid())
    bus = await MessageBus(bus_type=bus_type).connect()
    database = Path(os.environ.get("LULU_ACQUISITION_DB", str(PATHS.data_root / "acquisition.sqlite3")))
    store = AcquisitionStore(database)
    plugin_root = PATHS.plugins_root
    installed_plugins = PATHS.install_root / "config" / "plugins"
    if (not plugin_root.is_dir() or not any(plugin_root.glob("*/plugin.toml"))) and installed_plugins.is_dir():
        plugin_root = installed_plugins
    plugins = PluginRegistry(plugin_root)
    plugins.discover()
    contributions = plugins.with_capability("acquisition")
    manager = JobManager(provider_limits={
        item["provider"]: int(item.get("limit", 1)) for item in contributions
        if isinstance(item, dict) and item.get("provider")
    }, store=store)
    catalogue = CatalogueStore(PATHS.catalogue_db)
    manager.register_executor("local", LocalUninstallExecutor(catalogue), limit=1)
    for item in contributions:
        if isinstance(item, dict) and item.get("provider") and item.get("executor"):
            executor = item["executor"]
            if hasattr(executor, "request_credential"):
                provider_name = str(item["provider"])
                async def request_credential(input_type: CredentialInput, title: str, prompt: str,
                                             min_length: int, max_length: int,
                                             owner: dict[str, object] | None = None) -> str:
                    owner = dict(owner or {})
                    owner.setdefault("provider", provider_name)
                    owner_id = f"{owner['provider']}:{owner.get('job_id', '')}"
                    owner["owner_id"] = owner_id
                    request_id = ""
                    introspection = await bus.introspect("org.lulu.Consoled", "/org/lulu/Console")
                    proxy = bus.get_proxy_object("org.lulu.Consoled", "/org/lulu/Console", introspection)
                    consoled = proxy.get_interface("org.lulu.Console")
                    request = json.loads(await consoled.call_begin_owned_credential_request(
                        title, prompt, input_type.value, input_type is CredentialInput.SECRET,
                        min_length, max_length, owner_id, json.dumps(owner, sort_keys=True),
                        json.dumps(["enter-code"] if input_type is CredentialInput.WAITING else [])))
                    request_id = request["id"]
                    try:
                        while True:
                            state = json.loads(await consoled.call_get_credential_state())
                            if state.get("id") != request_id:
                                raise RuntimeError("credential request was replaced")
                            if state.get("status") == "submitted":
                                return await consoled.call_take_credential_value(request_id)
                            if state.get("status") in {"cancelled", "failed"}:
                                raise RuntimeError("credential request ended")
                            await asyncio.sleep(0.25)
                    finally:
                        try:
                            await consoled.call_withdraw_owned_credential_request(
                                request_id, owner_id, "provider request ended")
                        except Exception:
                            pass
                executor.request_credential = request_credential
            manager.register_executor(item["provider"], executor, limit=int(item.get("limit", 1)))
    interface = AcquisitionInterface(manager, catalogue)
    bus.export(OBJECT_PATH, interface)
    await bus.request_name(BUS_NAME)
    interface.StateChanged(interface._snapshot())
    await asyncio.Event().wait()


def main() -> None:
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s %(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("--system-bus", action="store_true")
    args = parser.parse_args()
    asyncio.run(serve(BusType.SYSTEM if args.system_bus else BusType.SESSION))


if __name__ == "__main__":
    main()
