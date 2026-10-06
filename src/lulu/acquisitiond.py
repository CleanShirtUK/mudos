"""Dedicated provider-neutral acquisition/job D-Bus service."""

from __future__ import annotations

import argparse
import asyncio
from dataclasses import asdict
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
from .jobs import JobOperation, JobState
from .notifications import NotificationBroker, NotificationPresenter
from .lutris_install import LutrisInstallExecutor
from .pc_install import PcInstallSource, PcSourceType
from .pc_install_store import PcInstallSourceStore


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


async def _wait_for_bus_disconnect(bus: MessageBus) -> None:
    """Fail the service if its D-Bus reader stops, rather than serving stale state.

    dbus-next finalizes a bus connection when its reader encounters a protocol or
    socket error. The process must not keep its well-known name after that: the
    shell would otherwise continue showing its last acquisition snapshot while
    every request to Acquisitiond hangs.
    """
    try:
        await bus.wait_for_disconnect()
    except asyncio.CancelledError:
        raise
    except Exception:
        LOGGER.exception("acquisitiond_dbus event=connection-lost")
        raise
    raise RuntimeError("Acquisitiond D-Bus connection closed unexpectedly")


def _completed_job_refresh_stages(provider: str) -> list[str]:
    """Return catalogue stages invalidated by a completed provider job."""
    if provider == "steam-aurelia":
        # Aurelia is a distinct acquisition identity, but Steam's installed
        # catalogue remains authoritative for the shared Steam library.
        return ["steam"]
    stages = [provider]
    if provider == "romm":
        # RomM downloads are materialized into the local ROM library. Refresh
        # that filesystem-backed catalogue too so the RomM row can be linked
        # to its newly installed local content record.
        stages.append("local")
    return stages


async def _reconcile_completed_usenet_paths(manager: JobManager) -> None:
    """Repair completed Mudos path metadata from NZBGet's owned history rows."""
    executor = manager.executors.get("usenet")
    reconcile = getattr(executor, "reconcile_completion_path", None)
    if reconcile is None:
        return
    for job in manager.snapshot():
        if job.provider != "usenet" or job.state.value != "completed" or job.backend != "nzbget":
            continue
        try:
            completion = await reconcile(job)
            if completion and completion != job.completion_path:
                manager.update_metadata(job.job_id, completion_path=completion)
                LOGGER.info("acquisitiond_provider provider=usenet stage=completion-path-reconciled job=%s",
                            job.job_id)
        except Exception:
            LOGGER.exception("completed Usenet path reconciliation failed job=%s", job.job_id)


class AcquisitionInterface(ServiceInterface):
    def __init__(self, manager: JobManager, catalogue: CatalogueStore, plugins: PluginRegistry,
                 notifications: NotificationBroker | None = None,
                 bus: MessageBus | None = None) -> None:
        super().__init__(INTERFACE_NAME)
        self.manager = manager
        self.catalogue = catalogue
        self.plugins = plugins
        self.bus = bus
        from .provider_config import ProviderConfigurationService
        usenet = ProviderConfigurationService.from_environment().provider("providers.usenet")
        self._usenet_startup_config = {
            "enabled": usenet.enabled,
            "configured": usenet.configured,
            "rpc_secret_available": usenet.secret_available("rpc_password"),
            "configuration_loaded": True,
            "reload_requested": False,
        }
        LOGGER.info("acquisitiond_provider provider=usenet stage=configuration-loaded enabled=%s configured=%s rpc_secret_available=%s executor_registered=%s",
                    self._usenet_startup_config["enabled"],
                    self._usenet_startup_config["configured"],
                    self._usenet_startup_config["rpc_secret_available"],
                    "usenet" in manager.executors)
        self.notifications = notifications or NotificationBroker(NotificationPresenter())
        # Historical terminal jobs are already reflected in the catalogue;
        # only completions observed after this interface starts need a
        # provider refresh.
        self._reconciliations: set[str] = {
            job.job_id for job in manager.snapshot()
            if job.state.value == "completed"
        }
        self.notifications.seed(manager.snapshot())
        manager._on_change = self._publish

    def _snapshot(self) -> str:
        return json.dumps({
            "jobs": [job_to_dict(job) for job in self.manager.snapshot()],
            # This legacy field feeds the shell's download badge; its product
            # meaning is the full actionable queue, not only active sockets.
            "activeDownloadCount": self.manager.actionable_download_count,
        }, sort_keys=True)

    def _publish(self, *_: object) -> None:
        snapshot = self.manager.snapshot()
        self.notifications.observe(snapshot)
        self.StateChanged(self._snapshot())
        # Do not reconcile inline: this callback runs inside JobManager's
        # terminal transition and provider refreshes may invoke subprocesses.
        # Schedule the provider/catalogue refresh only after the executor has
        # returned, while retaining the authoritative completed job state.
        for job in snapshot:
            if job.state.value == "completed" and job.job_id not in self._reconciliations:
                self._reconciliations.add(job.job_id)
                asyncio.create_task(self._reconcile_completed_job(job.job_id))

    async def _reconcile_completed_job(self, job_id: str) -> None:
        try:
            job = self.manager.jobs.get(job_id)
            if job is None:
                return
            catalogue_provider = "steam" if job.provider == "steam-aurelia" else job.provider
            source = next((item for item in self.plugins.with_capability("installed_catalogue")
                           if str(getattr(item, "provider_id", "")) == catalogue_provider), None)
            if source is None or self.bus is None:
                return
            # Consoled owns provider refresh and catalogue delta publication.
            # Invoke only the affected stage, outside JobManager's completion
            # callback, so no provider/job lifecycle lock is held.
            introspection = await self.bus.introspect("org.lulu.Consoled", "/org/lulu/Console")
            proxy = self.bus.get_proxy_object("org.lulu.Consoled", "/org/lulu/Console", introspection)
            await proxy.get_interface("org.lulu.Console").call_refresh_stages(
                _completed_job_refresh_stages(job.provider))
        except Exception:
            LOGGER.exception("completed acquisition reconciliation failed job=%s", job_id)

    @method()
    def GetSnapshot(self) -> "s":
        return self._snapshot()

    @method()
    def GetActiveDownloadCount(self) -> "u":
        return self.manager.active_download_count

    @method()
    def GetUsenetReadiness(self) -> "s":
        """Expose secret-free evidence that Acquisitiond loaded Usenet config."""
        return json.dumps({
            "provider": "usenet",
            **self._usenet_startup_config,
            "executor_registered": "usenet" in self.manager.executors,
        }, sort_keys=True)

    @method()
    async def GetAureliaBackendStatus(self) -> "s":
        """Secret-free diagnostics for the explicitly experimental backend."""
        executor = self.manager.executors.get("steam-aurelia")
        if executor is None:
            return json.dumps({"provider": "steam-aurelia", "enabled": False,
                               "status": "disabled", "capabilities": {}}, sort_keys=True)
        client = getattr(executor, "client", None)
        capabilities = getattr(executor, "capabilities", None)
        auth_status = "unavailable"
        if client is not None and client.available:
            try:
                auth_status = await client.auth_status()
            except Exception as error:
                # Expose a normalized, secret-free status only.
                auth_status = "unavailable"
                LOGGER.warning("aurelia status unavailable error_type=%s", type(error).__name__)
        return json.dumps({
            "provider": "steam-aurelia", "enabled": True,
            "status": "available" if client is not None and client.available else "unavailable",
            "authentication": auth_status,
            "session_directory": str(client.config_dir) if client is not None else None,
            "capabilities": asdict(capabilities) if capabilities is not None else {
                "acquisition_progress": True, "acquisition_cancel": True,
                "updates": False, "dlc": False, "launch": False,
                "running_state": True, "authentication_status": True,
                "detailed_launch_progress": False,
            },
        }, sort_keys=True)

    @method()
    async def ReloadUsenetConfiguration(self) -> "s":
        """Reload saved NZBGet credentials and register its executor in place."""
        from .provider_config import ProviderConfigurationService
        from .plugins.usenet import build_executor

        self._usenet_startup_config["reload_requested"] = True
        LOGGER.info("acquisitiond_provider provider=usenet stage=configuration-reload-requested")
        try:
            configuration = ProviderConfigurationService.from_environment().provider("providers.usenet")
            state = {
                "enabled": configuration.enabled,
                "configured": configuration.configured,
                "rpc_secret_available": configuration.secret_available("rpc_password"),
                "configuration_loaded": True,
                "reload_requested": True,
            }
            self._usenet_startup_config.update(state)
            LOGGER.info("acquisitiond_provider provider=usenet stage=configuration-loaded enabled=%s configured=%s",
                        state["enabled"], state["configured"])
            LOGGER.info("acquisitiond_provider provider=usenet stage=rpc-secret-resolved available=%s",
                        state["rpc_secret_available"])
            if not state["enabled"] or not state["configured"] or not state["rpc_secret_available"]:
                self._usenet_startup_config["executor_registered"] = (
                    "usenet" in self.manager.executors)
                raise RuntimeError("saved Usenet provider configuration is incomplete")

            client, executor = build_executor(configuration)
            await asyncio.wait_for(client.health(), timeout=12.0)
            LOGGER.info("acquisitiond_provider provider=usenet stage=rpc-authenticated")
            self.manager.replace_executor("usenet", executor, limit=1)
            self._usenet_startup_config["executor_registered"] = True
            LOGGER.info("acquisitiond_provider provider=usenet stage=executor-registered")
            return json.dumps({"provider": "usenet", **self._usenet_startup_config}, sort_keys=True)
        except Exception as error:
            LOGGER.exception("acquisitiond_provider provider=usenet stage=reload-failed error_type=%s",
                             type(error).__name__)
            raise DBusError("org.lulu.Acquisition.Error.ProviderReload", str(error)) from error

    @method()
    def SubmitJob(self, provider: "s", content_identity: "s", title: "s") -> "s":
        try:
            executor = self.manager.executors.get(provider)
            return self.manager.submit(provider, content_identity, title,
                                       cancellation_supported=True,
                                       pause_supported=bool(getattr(executor, "supports_pause", False))).job_id
        except ValueError as error:
            raise DBusError("org.lulu.Acquisition.Error.Unavailable", str(error)) from error

    @method()
    async def SubmitBrowserHandoff(self, uri: "s", source_origin: "s") -> "s":
        """Resolve a claimed browser URI through the generic handoff registry."""
        claim = self.plugins.claim_browser_handoff(uri, source_origin)
        if claim is None:
            raise DBusError("org.lulu.Acquisition.Error.Unsupported", "No enabled component claims this browser URI")
        component_id, declaration, backend, trusted = claim
        if not trusted:
            raise DBusError("org.lulu.Acquisition.Error.ConfirmationRequired",
                            "This browser source requires explicit confirmation")
        prepare = getattr(backend, "prepare_browser_handoff", None)
        if prepare is None:
            raise DBusError("org.lulu.Acquisition.Error.Unsupported", "The component cannot consume this handoff")
        try:
            prepared = await prepare(uri)
            application_id = str(prepared["application_id"])
            title = str(prepared.get("title") or application_id)
            source_path = str(prepared["path"])
            provider = component_id
            identity = f"{provider}:{application_id}"
            installed = getattr(backend, "installed", None)
            live_installed = None
            if callable(installed):
                live_installed = {
                    str(item.application_id) for item in await installed(user=True)
                }
            if live_installed is None or application_id in live_installed:
                existing = next((job for job in self.manager.snapshot()
                                 if job.provider == provider and job.content_identity == identity
                                 and job.operation == JobOperation.INSTALL
                                 and job.state.value == "completed"), None)
                if existing is not None:
                    return "existing:" + existing.job_id
            return self.manager.submit(provider, identity, title, operation=JobOperation.INSTALL,
                                       provider_job_id=source_path, cancellation_supported=True,
                                       pause_supported=False).job_id
        except (KeyError, ValueError, TypeError) as error:
            raise DBusError("org.lulu.Acquisition.Error.InvalidSource", str(error)) from error

    @method()
    def SubmitContentSet(self, provider: "s", content_identities: "as", title: "s") -> "s":
        """Submit one parent installation transaction for provider components."""
        if provider != "romm" or not content_identities:
            raise DBusError("org.lulu.Acquisition.Error.Unavailable", "content sets require RomM components")
        identity = "romm-set:" + ",".join(str(item).removeprefix("romm:") for item in content_identities)
        try:
            executor = self.manager.executors.get(provider)
            return self.manager.submit(provider, identity, title,
                                       cancellation_supported=True,
                                       pause_supported=bool(getattr(executor, "supports_pause", False))).job_id
        except ValueError as error:
            raise DBusError("org.lulu.Acquisition.Error.Unavailable", str(error)) from error

    @method()
    def RegisterPcSource(self, source_json: "s") -> "s":
        try:
            value = json.loads(source_json)
            source = PcInstallSourceStore.from_dict(value)
            executor = self.manager.executors.get("lutris")
            if not isinstance(executor, LutrisInstallExecutor):
                raise ValueError("Lutris installation is unavailable")
            source_id = executor.register_source(source)
            self.catalogue.register_lutris_source(source)
            return source_id
        except (TypeError, ValueError, json.JSONDecodeError) as error:
            raise DBusError("org.lulu.Acquisition.Error.InvalidSource", str(error)) from error

    @method()
    def SubmitPcInstall(self, source_id: "s", title: "s") -> "s":
        try:
            executor = self.manager.executors.get("lutris")
            if not isinstance(executor, LutrisInstallExecutor):
                raise ValueError("Lutris installation is unavailable")
            return self.manager.submit("lutris", source_id, title, operation=JobOperation.INSTALL,
                                       cancellation_supported=True).job_id
        except ValueError as error:
            raise DBusError("org.lulu.Acquisition.Error.Unavailable", str(error)) from error

    @method()
    def CreateLutrisInstallSource(self, title: "s", game_slug: "s", installer_slug: "s",
                                  file_mapping_json: "s") -> "s":
        """Validate Lutris recipe requirements and serialize a source for RegisterPcSource."""
        try:
            mappings = json.loads(file_mapping_json)
            if not isinstance(mappings, dict):
                raise ValueError("file mapping must be an object")
            recipes = LutrisInstallExecutor().adapter.recipes(game_slug)
            selected = [recipe for recipe in recipes if recipe.installer_slug == installer_slug]
            if len(selected) != 1:
                raise ValueError("selected Lutris recipe is no longer available")
            requirements = selected[0].requirements
            by_id = {item.file_id: item for item in requirements}
            required_local = {item.file_id for item in requirements if item.local and item.required}
            unknown = set(str(key) for key in mappings) - set(by_id)
            if unknown:
                raise ValueError("file was supplied for an unknown Lutris recipe requirement")
            missing = required_local - set(str(key) for key in mappings)
            if missing:
                raise ValueError("required file selection is incomplete")
            from .pc_install import PcSourceFile
            files = []
            selected_paths: list[Path] = []
            for file_id, value in mappings.items():
                requirement = by_id[str(file_id)]
                path = Path(str(value)).expanduser()
                if path.is_symlink():
                    raise ValueError("selected files cannot be symbolic links")
                path = path.resolve(strict=True)
                if not path.is_file():
                    raise ValueError("selected item is not a regular file")
                stat = path.stat()
                files.append(PcSourceFile(str(path), requirement.filename, stat.st_size, "file"))
                selected_paths.append(path)
            if not title.strip() or not game_slug or not installer_slug:
                raise ValueError("game and installer identity are required")
            parent = str(Path(os.path.commonpath([str(path.parent) for path in selected_paths]))) \
                if selected_paths else ""
            source = PcInstallSource(
                canonical_game_id=f"lutris:{game_slug}", title=title.strip(),
                provenance="lutris-recipe", source_type=PcSourceType.UNKNOWN,
                completed_path=parent, files=tuple(files), ready_to_install=True,
                lutris_slug=game_slug, lutris_installer_slug=installer_slug,
            )
            return json.dumps(asdict(source), sort_keys=True)
        except Exception as error:
            raise DBusError("org.lulu.Acquisition.Error.InvalidSource", str(error)) from error

    @method()
    def RegisterLocalLutrisGame(self, title: "s", directory: "s", executable: "s",
                                arguments: "s") -> "s":
        """Register a locally installed native game via Lutris's own model API."""
        try:
            root = (PATHS.game_install_root / "Executables" / "lutris").resolve(strict=True)
            requested_directory = Path(directory).expanduser()
            if requested_directory.is_symlink():
                raise ValueError("selected game directory cannot be a symbolic link")
            target = requested_directory.resolve(strict=True)
            if target.parent != root:
                raise ValueError("selected game directory must be a direct child of the Lutris game root")
            exe = Path(executable).expanduser().resolve(strict=True)
            exe.relative_to(target)
            adapter = LutrisInstallExecutor().adapter
            registration = adapter.register_local_game(
                title=title, directory=target, executable=exe, arguments=arguments,
                working_directory=target,
            )
            source = PcInstallSource(
                canonical_game_id=f"lutris:{registration['slug']}", title=title.strip(),
                provenance="mudos-local", source_type=PcSourceType.DIRECTORY,
                completed_path=str(target), ready_to_install=True, lutris_slug=str(registration["slug"]),
            )
            registration["mudos_owned"] = True
            if self.catalogue is not None:
                self.catalogue.reconcile_lutris(registration, source)
            return json.dumps(registration, sort_keys=True)
        except Exception as error:
            raise DBusError("org.lulu.Acquisition.Error.LocalRegistration", str(error)) from error

    def _uninstall_target(self, game_id: str) -> tuple[object, str, str, str]:
        target, provider, identity, title, capability = self._resolve_uninstall(game_id)
        if not capability["supported"]:
            raise DBusError("org.lulu.Acquisition.Error.Unsupported", str(capability["reason"]))
        return target, provider, identity, title

    @staticmethod
    def _executor_uninstall_capability(executor: object | None, game: object) -> dict[str, object]:
        if executor is None:
            provider = str(getattr(game, "provider", ""))
            reason = {
                "romm": "RomM is a remote library source; only its linked local copy can be removed.",
            }.get(provider, "No safe uninstall implementation is registered for this provider.")
            return {"supported": False, "reason": reason}
        if not getattr(executor, "supports_uninstall", False):
            return {"supported": False, "reason": str(getattr(
                executor, "uninstall_reason", "This provider does not support safe uninstall through Mudos."))}
        describe = getattr(executor, "uninstall_capability", None)
        if callable(describe):
            try:
                result = describe(game)
            except Exception as error:
                return {"supported": False,
                        "reason": f"Provider ownership could not be verified ({type(error).__name__})."}
            if isinstance(result, dict):
                return {"supported": bool(result.get("supported", False)),
                        "reason": str(result.get("reason", "")),
                        "description": str(result.get("description", ""))}
            return {"supported": bool(result), "reason": "Provider ownership could not be verified."}
        capability_check = getattr(executor, "can_uninstall", None)
        if callable(capability_check):
            try:
                if not capability_check(str(getattr(game, "game_id", ""))):
                    return {"supported": False,
                            "reason": "Provider ownership or installation state could not be verified."}
            except Exception as error:
                return {"supported": False,
                        "reason": f"Provider ownership could not be verified ({type(error).__name__})."}
        return {"supported": True}

    def _resolve_uninstall(self, game_id: str):
        game = self.catalogue.get_game(game_id)
        if game is None:
            raise DBusError("org.lulu.Acquisition.Error.NotFound", "game was not found")
        target = game
        if game.provider == "romm" and game.installed_game_id:
            target = self.catalogue.get_game(game.installed_game_id) or game
        if target.install_state != "installed":
            raise DBusError("org.lulu.Acquisition.Error.NotInstalled", "game is not installed")
        provider = ("local" if str(getattr(target, "catalogue_source", "")) == "local"
                    or str(target.provider) == "local" else str(target.provider))
        if provider == "steam":
            provider = "steam-aurelia"
        identity = str(target.game_id if provider == "local" else f"{provider}:{target.provider_id}")
        executor = self.manager.executors.get(provider)
        capability = self._executor_uninstall_capability(executor, target)
        return target, provider, identity, str(target.title), capability

    @method()
    def CanUninstall(self, game_id: "s") -> "s":
        try:
            target, provider, identity, _title, capability = self._resolve_uninstall(game_id)
            active_states = {JobState.QUEUED, JobState.STARTING, JobState.TRANSFERRING,
                             JobState.FINALIZING, JobState.AWAITING_INTERACTION,
                             JobState.PAUSING, JobState.PAUSED, JobState.RESUMING,
                             JobState.CANCELLING}
            active = any(job.provider == provider and job.content_identity == identity
                         and job.operation is JobOperation.REMOVE and job.state in active_states
                         for job in self.manager.jobs.values())
            executor = self.manager.executors.get(provider)
            result = {"supported": bool(capability.get("supported")), "installed": True,
                      "provider": provider, "operation": "remove",
                      "available": executor is not None,
                      "temporarily_unavailable": False,
                      "requires_confirmation": bool(capability.get("supported")),
                      "progress_measurable": bool(getattr(executor, "uninstall_progress_supported", False)),
                      "in_progress": active, "target_game_id": target.game_id}
            descriptions = {
                "local": "Remove the local game content only; saves, BIOS, and shared runtime data are kept.",
                "steam-aurelia": "Uninstall this Steam game through Aurelia; Mudos will refresh its library.",
                "flatpak": "Uninstall the Flatpak application; Flatpak retains its normal app-data policy.",
                "epic": "Uninstall this Epic title through Legendary.",
                "gog": "Remove the marked Mudos-managed GOG game files.",
            }
            description = str(capability.get("description") or descriptions.get(provider, ""))
            if description:
                result["description"] = description
            reason = str(capability.get("reason", ""))
            if reason:
                result["reason"] = reason
            return json.dumps(result, sort_keys=True)
        except DBusError as error:
            return json.dumps({"supported": False, "installed": False,
                               "requires_confirmation": False,
                               "reason": str(error)}, sort_keys=True)

    @method()
    def UninstallGame(self, game_id: "s") -> "s":
        try:
            target, provider, identity, title, capability = self._resolve_uninstall(game_id)
            if not capability.get("supported"):
                raise DBusError("org.lulu.Acquisition.Error.Unsupported",
                                str(capability.get("reason") or "uninstall is not supported"))
            return self.manager.submit(provider, identity, title,
                                       operation=JobOperation.REMOVE,
                                       provider_job_id=target.provider_id,
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
                          json.dumps(["approved", "enter-code"]
                                     if input_type is CredentialInput.WAITING else []),
                         False))
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
    async def reconcile_external_loop() -> None:
        while True:
            try:
                await manager.reconcile_external()
            except Exception:
                LOGGER.exception("external acquisition reconciliation failed")
            await asyncio.sleep(3)
    asyncio.create_task(reconcile_external_loop())
    interface = AcquisitionInterface(manager, catalogue, plugins, bus=bus)
    bus.export(OBJECT_PATH, interface)
    await bus.request_name(BUS_NAME)
    interface.StateChanged(interface._snapshot())
    asyncio.create_task(_reconcile_completed_usenet_paths(manager))
    try:
        await _wait_for_bus_disconnect(bus)
    finally:
        store.close()


def main() -> None:
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s %(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("--system-bus", action="store_true")
    args = parser.parse_args()
    asyncio.run(serve(BusType.SYSTEM if args.system_bus else BusType.SESSION))


if __name__ == "__main__":
    main()
