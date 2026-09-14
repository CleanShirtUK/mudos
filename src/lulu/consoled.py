"""Unified game catalogue and game/content intent boundary."""

import asyncio
from dataclasses import replace
import logging
import os
from pathlib import Path
import signal
import subprocess
import tempfile
import shlex
import json
import time

from dbus_next import BusType, Variant
from dbus_next.aio import MessageBus
from dbus_next.service import ServiceInterface, method, signal as dbus_signal

from .catalogue import CatalogueGame, CatalogueStore
from .artwork import LocalArtworkCache, SteamGridDBArtwork
from .contracts import ServiceDescriptor, ServiceName
from .controller_provisioning import ensure_provider_controller_config
from .emulator_runtime import EmulatorRuntimeAdapter
from .emulation import PLATFORMS, ROM_ROOT, ensure_storage
from .inputplumber import InputPlumberClient
from .local_content import LocalContentProvider
from .metadata import MetadataMatcher, SteamGridDBMetadata, clean_local_title
from .romm import RommApiError, RommClient, RommConfig, RommGame
from .steam_provider import SteamProvider
from .system_settings import CATEGORIES as SYSTEM_CATEGORIES, SystemSettingsProvider


DESCRIPTOR = ServiceDescriptor(
    name=ServiceName.CONSOLED,
    authority="unified game catalogue and game/platform intent",
    owned_state=(
        "normalized provider records",
        "content installation metadata",
        "game profiles",
        "compatibility intent",
        "emulator configuration intent",
    ),
    notes=("External runtime configuration is generated output, not authority.",),
)


class ConsoleCatalog:
    """Consoled-owned normalized catalogue."""

    descriptor = DESCRIPTOR

    def __init__(self, store: CatalogueStore | None = None, provider: SteamProvider | None = None,
                 local_provider: LocalContentProvider | None = None,
                 metadata: SteamGridDBMetadata | None = None,
                 romm: RommClient | None = None) -> None:
        self.store = store or CatalogueStore()
        self.provider = provider or SteamProvider()
        self.local_provider = local_provider or LocalContentProvider()
        self.artwork = SteamGridDBArtwork()
        self.romm_artwork = LocalArtworkCache()
        self.metadata = metadata or SteamGridDBMetadata()
        self.matcher = MetadataMatcher(self.metadata)
        config = RommConfig.from_file()
        self.romm = romm or (RommClient(config) if config else None)

    def refresh(self) -> list[dict[str, object]]:
        self.store.reconcile_steam(self.provider)
        ensure_storage()
        self.store.reconcile_local(self.local_provider, ROM_ROOT)
        if self.romm is not None:
            try:
                romm_games = self.romm.list_games()
                installed = {game.app_id: game for game in self.provider.list_installed()}
                normalized: dict[str, object] = {}
                for game in romm_games:
                    app_id = self._steam_manifest_app_id(game)
                    entry = CatalogueGame.from_romm(
                        game, installed.get(app_id) if app_id else None, app_id
                    )
                    artwork = self.romm_artwork.cache_remote(entry.game_id, game.artwork_url)
                    entry = replace(
                        entry, artwork_url=artwork, last_seen_at=int(time.time()),
                        last_synced_at=int(time.time())
                    )
                    normalized[entry.game_id] = entry
                self.store.reconcile_romm(list(normalized.values()))
            except RommApiError as error:
                LOGGER.warning("RomM refresh failed; retaining previous snapshot: %s", error)
        for game in self.store.list_games():
            if self.store.needs_metadata_match(game.game_id):
                self.store.apply_metadata_match(
                    game.game_id, self.matcher.match(game.source_title or game.title, game.platform)
                )
        games = self.store.list_games()
        for game_id, artwork_url in self.artwork.enrich(games).items():
            self.store.set_artwork_url(game_id, artwork_url)
        return [game.as_dict() for game in self.store.list_games()]

    def _steam_manifest_app_id(self, game: object) -> str | None:
        if not isinstance(game, RommGame) or game.platform_slug.casefold() != "steam":
            return None
        manifest_files = [item for item in game.files if item.name.casefold().endswith(".json")]
        if not manifest_files or self.romm is None:
            return None
        try:
            return self.romm.read_steam_manifest(manifest_files[0]).app_id
        except RommApiError as error:
            LOGGER.warning("Ignoring invalid RomM Steam manifest rom_id=%s: %s", game.rom_id, error)
            return None

    def set_metadata_match(self, game_id: str, provider: str, metadata_game_id: str,
                           canonical_title: str) -> None:
        self.store.set_metadata_match(game_id, provider, metadata_game_id, canonical_title)

    def clear_metadata_match(self, game_id: str) -> None:
        self.store.clear_metadata_match(game_id)

    def metadata_search(self, game_id: str, query: str) -> list[dict[str, object]]:
        game = self.store.get_game(game_id)
        if game is None:
            raise ValueError("game does not exist")
        search_title = query.strip() or game.canonical_title or game.normalized_search_title or clean_local_title(game.source_title or game.title)
        candidates = self.metadata.search(search_title, game.platform)
        if candidates is None:
            return []
        return [{
            "id": candidate.game_id,
            "title": candidate.title,
            "aliases": list(candidate.aliases),
            "platforms": list(candidate.platforms),
        } for candidate in candidates]

    def _refresh_game_artwork(self, game_id: str) -> None:
        game = self.store.get_game(game_id)
        if game is None:
            raise ValueError("game does not exist")
        for refreshed_id, artwork_url in self.artwork.enrich([game]).items():
            if refreshed_id == game_id:
                self.store.set_artwork_url(game_id, artwork_url)

    def apply_metadata_match(self, game_id: str, provider: str, metadata_game_id: str,
                             canonical_title: str) -> None:
        self.store.set_metadata_match(game_id, provider, metadata_game_id, canonical_title)
        self._refresh_game_artwork(game_id)

    def set_title_override(self, game_id: str, title: str) -> None:
        self.store.set_display_title_override(game_id, title)

    def clear_title_override(self, game_id: str) -> None:
        self.store.clear_display_title_override(game_id)

    def suppress_artwork(self, game_id: str) -> None:
        self.store.suppress_artwork(game_id)

    def restore_artwork(self, game_id: str) -> None:
        self.store.restore_artwork(game_id)
        self._refresh_game_artwork(game_id)

    def platform_categories(self) -> list[dict[str, str]]:
        return [{"scope": f"platform:{platform}", "platform": platform, "label": label}
                 for platform, label in self.store.list_platforms()]

    def available_games(self, provider: str | None = None) -> list[dict[str, object]]:
        return [game.as_dict() for game in self.store.list_available_games(provider)]

    def resolve_steam_install(self, game_id: str) -> str:
        game = self.store.get_game(game_id)
        if game is None or game.provider != "steam":
            raise ValueError("game is not a Steam catalogue entry")
        if game.install_state != "available" or game.availability_state != "available":
            raise ValueError("game is not available to install")
        if not game.provider_id.isdecimal() or int(game.provider_id) < 1:
            raise ValueError("Steam AppID is invalid")
        return game.provider_id


BUS_NAME = "org.lulu.Consoled"
OBJECT_PATH = "/org/lulu/Console"
INTERFACE_NAME = "org.lulu.Console"
LOGGER = logging.getLogger("lulu.consoled")


def _mudos_provider_device_indices() -> dict[int, int]:
    """Resolve logical players to current InputPlumber gamepad target indices."""
    client = InputPlumberClient("/org/shadowblip/InputPlumber/CompositeDevice0", {})
    slots = client.runtime_gamepad_slots()
    state = subprocess.run(
        [
            "busctl",
            "--user",
            "call",
            "org.lulu.ConsoleSessiond",
            "/org/lulu/ConsoleSession",
            "org.lulu.ConsoleSession",
            "GetState",
        ],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    state_json = json.loads(state.removeprefix("s ").strip())
    if isinstance(state_json, str):
        state_json = json.loads(state_json)
    assignments = state_json.get("controller", {}).get("controllers", {})
    result: dict[int, int] = {}
    for runtime_path, _persistent_id, target_index in slots:
        player = assignments.get(runtime_path, {}).get("player")
        if isinstance(player, int) and player in range(1, 5):
            result[player] = target_index
    if not result:
        raise RuntimeError("Mudos has no assigned InputPlumber gamepad slots")
    return result


def _retroarch_child_config(device_indices: dict[int, int]) -> str:
    directory = Path(os.environ.get("XDG_RUNTIME_DIR", "/tmp"))
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="ascii",
        prefix="lulu-retroarch-",
        suffix=".cfg",
        dir=directory,
        delete=False,
    ) as config:
        config.write(
            "".join(
                f'input_player{player}_joypad_index = "{device_indices[player]}"\n'
                for player in range(1, 5)
                if player in device_indices
            ) + 'network_cmd_enable = "true"\n'
            'network_cmd_port = "55355"\n'
            'quit_on_close_content = "true"\n'
            'config_save_on_exit = "false"\n'
        )
        return config.name


class ConsoleInterface(ServiceInterface):
    def __init__(self, catalogue: ConsoleCatalog, local_runtime: EmulatorRuntimeAdapter | None = None,
                 system_settings: SystemSettingsProvider | None = None,
                 sessiond: object | None = None) -> None:
        super().__init__(INTERFACE_NAME)
        self.catalogue = catalogue
        self.local_runtime = local_runtime
        self.system_settings = system_settings or SystemSettingsProvider()
        self.sessiond = sessiond
        self._local_process: asyncio.subprocess.Process | None = None
        self._local_token: str | None = None

    
    @staticmethod
    def _variant(key: str, value: object) -> Variant:
        if isinstance(value, bool):
            return Variant("b", value)
        if isinstance(value, str):
            return Variant("s", value)
        if isinstance(value, int):
            return Variant("x", value)
        if isinstance(value, float):
            return Variant("d", value)
        if isinstance(value, list) and all(isinstance(item, str) for item in value):
            return Variant("as", value)
        if value is None:
            raise TypeError(f"catalogue field {key!r} cannot be None in D-Bus output")
        raise TypeError(f"unsupported catalogue field {key!r} type: {type(value).__name__}")

    
    @classmethod
    def _variants(cls, game: dict[str, object]) -> dict[str, Variant]:
        # D-Bus has no nullable primitive signature; omission represents an
        # unknown optional metadata field while SQLite/JSON retain NULL.
        return {key: cls._variant(key, value) for key, value in game.items() if value is not None}


    @method()
    def Refresh(self) -> "u":
        count = len(self.catalogue.refresh())
        self.CatalogueChanged()
        return count

    @method()
    def ListGames(self, scope: "s") -> "aa{sv}":
        if scope == "recent":
            games = self.catalogue.store.list_recent()
        else:
            games = self.catalogue.store.list_games(scope)
        return [self._variants(game.as_dict()) for game in games]

    @method()
    def ListPlatformCategories(self) -> "aa{sv}":
        return [self._variants(category) for category in self.catalogue.platform_categories()]

    @method()
    def ListAvailableGames(self, provider: "s") -> "aa{sv}":
        return [self._variants(game) for game in self.catalogue.available_games(provider or None)]

    @method()
    def ResolveSteamInstall(self, game_id: "s") -> "s":
        try:
            return self.catalogue.resolve_steam_install(game_id)
        except ValueError as error:
            raise self._error(error) from error

    @method()
    def ListSystemSettings(self, category: "s") -> "aa{sv}":
        return [self._variants(item) for item in self.system_settings.list_settings(category)]

    @method()
    def ListSystemCategories(self) -> "as":
        return list(SYSTEM_CATEGORIES)

    @method()
    def SearchMetadata(self, game_id: "s", query: "s") -> "aa{sv}":
        return [self._variants(item) for item in self.catalogue.metadata_search(game_id, query)]

    @method()
    def SetMetadataMatch(self, game_id: "s", provider: "s", metadata_game_id: "s",
                         canonical_title: "s") -> "":
        self.catalogue.apply_metadata_match(game_id, provider, metadata_game_id, canonical_title)
        self.CatalogueChanged()

    @method()
    def ClearMetadataMatch(self, game_id: "s") -> "":
        self.catalogue.clear_metadata_match(game_id)
        self.CatalogueChanged()

    @method()
    def SetTitleOverride(self, game_id: "s", title: "s") -> "":
        self.catalogue.set_title_override(game_id, title)
        self.CatalogueChanged()

    @method()
    def ClearTitleOverride(self, game_id: "s") -> "":
        self.catalogue.clear_title_override(game_id)
        self.CatalogueChanged()

    @method()
    def SuppressArtwork(self, game_id: "s") -> "":
        self.catalogue.suppress_artwork(game_id)
        self.CatalogueChanged()

    @method()
    def RestoreArtwork(self, game_id: "s") -> "":
        self.catalogue.restore_artwork(game_id)
        self.CatalogueChanged()

    @method()
    async def LaunchGame(self, game_id: "s", timeout_ms: "u") -> "s":
        games = {game.game_id: game for game in self.catalogue.store.list_games()}
        game = games.get(game_id)
        if game is None or not game.launchable:
            raise ValueError("game is not installed and launchable")
        LOGGER.info("launch dispatch game_id=%s provider=%s provider_id=%s", game_id, game.provider, game.provider_id)
        if game.provider == "steam":
            details_uri = self.catalogue.provider.open_game_details(game.provider_id)
            launch_uri = self.catalogue.provider.launch_gamepad_title(game.provider_id)
            LOGGER.info(
                "Steam contextual launch submitted game_id=%s details=%s launch=%s",
                game_id,
                details_uri,
                launch_uri,
            )
            return details_uri
        if game.provider == "local" and self.local_runtime is not None:
            device_indices = None
            if game.platform == "switch":
                device_indices = await asyncio.to_thread(_mudos_provider_device_indices)
            intent = self.local_runtime.launch_intent(game, device_indices=device_indices)
            command = [intent.executable, *intent.arguments]
            is_pcsx2 = intent.platform == "ps2"
            if is_pcsx2:
                LOGGER.info("[PCSX2] selected game=%s path=%s", game_id, game.install_dir)
                LOGGER.info("[PCSX2] resolved executable=%s", intent.executable)
            child_config_path: str | None = None
            if intent.platform in {"ps2", "wii"}:
                controller_provider = {"ps2": "pcsx2", "wii": "dolphin"}[intent.platform]
                device_indices = await asyncio.to_thread(_mudos_provider_device_indices)
                controller_config_path = await asyncio.to_thread(
                    ensure_provider_controller_config,
                    controller_provider,
                    None,
                    max(device_indices),
                    device_indices,
                )
                LOGGER.info(
                    "local runtime controller profile provider=%s path=%s",
                    controller_provider,
                    controller_config_path,
                )
            if intent.platform in {"nes", "genesis"}:
                device_indices = await asyncio.to_thread(_mudos_provider_device_indices)
                child_config_path = await asyncio.to_thread(_retroarch_child_config, device_indices)
                command[1:1] = [
                    "--appendconfig",
                    child_config_path,
                ]
                LOGGER.info(
                    "local runtime controller game_id=%s device_indices=%s",
                    game_id,
                    device_indices,
                )
            LOGGER.info(
                "local runtime dispatch game_id=%s runtime=%s core=%s rom=%s command=%r",
                game_id,
                intent.executable,
                intent.arguments[1] if intent.platform in {"nes", "genesis"} else "",
                intent.arguments[-1],
                command,
            )
            if is_pcsx2:
                LOGGER.info("[PCSX2] command line=%s", shlex.join(command))
            child_environment = os.environ.copy()
            if intent.platform in {"nes", "genesis", "ps2"}:
                child_environment.pop("WAYLAND_DISPLAY", None)
            if intent.platform in {"nes", "genesis"}:
                child_environment["LIBRETRO_AUTOCONFIG_DIRECTORY"] = (
                    "/opt/lulu/config/retroarch/autoconfig"
                )
                child_environment["MUDOS_PROVIDER_MENU_COMMAND"] = shlex.join(
                    self.local_runtime.open_provider_menu(intent.platform)
                )
            process = await asyncio.create_subprocess_exec(
                *command,
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
                env=child_environment,
                cwd="/home/lulu" if intent.platform == "switch" else None,
                start_new_session=True,
            )
            if is_pcsx2:
                LOGGER.info("[PCSX2] process PID=%s", process.pid)
            try:
                if self.sessiond is not None:
                    self._local_token = await self.sessiond.call_begin_local_session(
                        game_id,
                        process.pid,
                        os.getpgid(process.pid),
                        os.path.realpath(f"/proc/{process.pid}/exe"),
                        command,
                    )
                self._local_process = process
            except Exception:
                try:
                    os.killpg(os.getpgid(process.pid), signal.SIGTERM)
                except (ProcessLookupError, OSError):
                    pass
                await process.wait()
                raise

            async def reap() -> None:
                exit_code = await process.wait()
                if child_config_path is not None:
                    try:
                        os.unlink(child_config_path)
                    except FileNotFoundError:
                        pass
                if self.sessiond is not None and self._local_token is not None:
                    try:
                        await self.sessiond.call_end_local_session(self._local_token, exit_code)
                    except Exception as error:
                        LOGGER.error("local session end failed game_id=%s token=%s error=%s", game_id, self._local_token, error)
                self._local_process = None
                self._local_token = None
                LOGGER.info("local runtime exit game_id=%s pid=%s exit_code=%s", game_id, process.pid, exit_code)
                if is_pcsx2:
                    LOGGER.info("[PCSX2] process exit pid=%s exit_code=%s", process.pid, exit_code)
                    LOGGER.info("[PCSX2] lifecycle return game_id=%s", game_id)

            asyncio.create_task(reap())
            token = self._local_token or f"local:{process.pid}"
            LOGGER.info("local runtime started game_id=%s pid=%s token=%s", game_id, process.pid, token)
        else:
            raise ValueError(f"provider launch is unavailable: {game.provider}")
        self.catalogue.store.mark_played(game.game_id)
        LOGGER.info("launch returned game_id=%s token=%s", game_id, token)
        self.CatalogueChanged()
        return token

    @method()
    async def CancelLocalLaunch(self) -> "":
        process = self._local_process
        if process is None:
            return
        try:
            os.killpg(os.getpgid(process.pid), signal.SIGTERM)
        except (ProcessLookupError, OSError):
            pass
        await process.wait()

    @dbus_signal()
    def CatalogueChanged(self) -> "":
        return


ROMM_SYNC_INTERVAL = 15 * 60


async def serve() -> None:
    catalogue = ConsoleCatalog()
    runtime = EmulatorRuntimeAdapter(
        {platform: definition.executable for platform, definition in PLATFORMS.items()},
        {platform: definition.core for platform, definition in PLATFORMS.items() if definition.core is not None},
    )
    bus = await MessageBus(bus_type=BusType.SESSION).connect()
    session_introspection = await bus.introspect("org.lulu.ConsoleSessiond", "/org/lulu/ConsoleSession")
    session_proxy = bus.get_proxy_object(
        "org.lulu.ConsoleSessiond", "/org/lulu/ConsoleSession", session_introspection
    )
    sessiond = session_proxy.get_interface("org.lulu.ConsoleSession")
    bus.export(OBJECT_PATH, ConsoleInterface(catalogue, runtime, sessiond=sessiond))
    await bus.request_name(BUS_NAME)
    # Publish the D-Bus boundary before the potentially slow provider refresh.
    # sessiond starts the shell during bootstrap, and the bridge must be able to
    # discover Consoled while the catalogue is being populated.
    # Publish the boundary and cached catalogue immediately. Provider sync is
    # deliberately background work so RomM cannot delay shell startup.
    async def synchronize() -> None:
        while True:
            try:
                await asyncio.to_thread(catalogue.refresh)
            except Exception:
                LOGGER.exception("background catalogue synchronization failed")
            await asyncio.sleep(ROMM_SYNC_INTERVAL)

    asyncio.create_task(synchronize(), name="catalogue-sync")
    await asyncio.Event().wait()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    asyncio.run(serve())


if __name__ == "__main__":
    main()
