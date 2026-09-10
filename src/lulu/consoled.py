"""Unified game catalogue and game/content intent boundary."""

import asyncio
import logging

from dbus_next import BusType, Variant
from dbus_next.aio import MessageBus
from dbus_next.service import ServiceInterface, method, signal

from .catalogue import CatalogueStore
from .artwork import SteamGridDBArtwork
from .contracts import ServiceDescriptor, ServiceName
from .emulator_runtime import EmulatorRuntimeAdapter
from .emulation import PLATFORMS, ROM_ROOT, ensure_storage
from .local_content import LocalContentProvider
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
                 local_provider: LocalContentProvider | None = None) -> None:
        self.store = store or CatalogueStore()
        self.provider = provider or SteamProvider()
        self.local_provider = local_provider or LocalContentProvider()
        self.artwork = SteamGridDBArtwork()

    def refresh(self) -> list[dict[str, object]]:
        self.store.reconcile_steam(self.provider)
        ensure_storage()
        self.store.reconcile_local(self.local_provider, ROM_ROOT)
        for game_id, artwork_url in self.artwork.enrich(self.store.list_games()).items():
            self.store.set_artwork_url(game_id, artwork_url)
        return [game.as_dict() for game in self.store.list_games()]

    def platform_categories(self) -> list[dict[str, str]]:
        return [{"scope": f"platform:{platform}", "platform": platform, "label": label}
                for platform, label in self.store.list_platforms()]


BUS_NAME = "org.lulu.Consoled"
OBJECT_PATH = "/org/lulu/Console"
INTERFACE_NAME = "org.lulu.Console"
LOGGER = logging.getLogger("lulu.consoled")


class ConsoleInterface(ServiceInterface):
    def __init__(self, catalogue: ConsoleCatalog, local_runtime: EmulatorRuntimeAdapter | None = None,
                 system_settings: SystemSettingsProvider | None = None) -> None:
        super().__init__(INTERFACE_NAME)
        self.catalogue = catalogue
        self.local_runtime = local_runtime
        self.system_settings = system_settings or SystemSettingsProvider()

    @staticmethod
    def _variants(game: dict[str, object]) -> dict[str, Variant]:
        return {key: Variant("s" if isinstance(value, str) else "b" if isinstance(value, bool) else "x", value) for key, value in game.items()}

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
    def ListSystemSettings(self, category: "s") -> "aa{sv}":
        return [self._variants(item) for item in self.system_settings.list_settings(category)]

    @method()
    def ListSystemCategories(self) -> "as":
        return list(SYSTEM_CATEGORIES)

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
        bus = await MessageBus(bus_type=BusType.SESSION).connect()
        introspection = await bus.introspect("org.lulu.ConsoleSessiond", "/org/lulu/ConsoleSession")
        proxy = bus.get_proxy_object("org.lulu.ConsoleSessiond", "/org/lulu/ConsoleSession", introspection)
        session = proxy.get_interface("org.lulu.ConsoleSession")
        if game.provider == "local" and self.local_runtime is not None:
            intent = self.local_runtime.launch_intent(game)
            token = await session.call_request_launch([intent.executable, *intent.arguments], timeout_ms)
        else:
            raise ValueError(f"provider launch is unavailable: {game.provider}")
        self.catalogue.store.mark_played(game.game_id)
        LOGGER.info("launch returned game_id=%s token=%s", game_id, token)
        bus.disconnect()
        self.CatalogueChanged()
        return token

    @signal()
    def CatalogueChanged(self) -> "":
        return


async def serve() -> None:
    catalogue = ConsoleCatalog()
    catalogue.refresh()
    runtime = EmulatorRuntimeAdapter(
        {platform: definition.executable for platform, definition in PLATFORMS.items()},
        {platform: definition.core for platform, definition in PLATFORMS.items() if definition.core is not None},
    )
    bus = await MessageBus(bus_type=BusType.SESSION).connect()
    bus.export(OBJECT_PATH, ConsoleInterface(catalogue, runtime))
    await bus.request_name(BUS_NAME)
    await asyncio.Event().wait()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    asyncio.run(serve())


if __name__ == "__main__":
    main()
