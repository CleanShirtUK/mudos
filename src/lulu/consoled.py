"""Unified game catalogue and game/content intent boundary."""

import asyncio

from dbus_next import BusType, Variant
from dbus_next.aio import MessageBus
from dbus_next.service import ServiceInterface, method, signal

from .catalogue import CatalogueStore
from .contracts import ServiceDescriptor, ServiceName
from .steam_provider import SteamProvider


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

    def __init__(self, store: CatalogueStore | None = None, provider: SteamProvider | None = None) -> None:
        self.store = store or CatalogueStore()
        self.provider = provider or SteamProvider()

    def refresh(self) -> list[dict[str, object]]:
        self.store.reconcile_steam(self.provider)
        return [game.as_dict() for game in self.store.list_games()]


BUS_NAME = "org.lulu.Consoled"
OBJECT_PATH = "/org/lulu/Console"
INTERFACE_NAME = "org.lulu.Console"


class ConsoleInterface(ServiceInterface):
    def __init__(self, catalogue: ConsoleCatalog) -> None:
        super().__init__(INTERFACE_NAME)
        self.catalogue = catalogue

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
    async def LaunchGame(self, game_id: "s", timeout_ms: "u") -> "s":
        games = {game.game_id: game for game in self.catalogue.store.list_games()}
        game = games.get(game_id)
        if game is None or not game.launchable or game.provider != "steam":
            raise ValueError("game is not installed and launchable")
        bus = await MessageBus(bus_type=BusType.SESSION).connect()
        introspection = await bus.introspect("org.lulu.ConsoleSessiond", "/org/lulu/ConsoleSession")
        proxy = bus.get_proxy_object("org.lulu.ConsoleSessiond", "/org/lulu/ConsoleSession", introspection)
        session = proxy.get_interface("org.lulu.ConsoleSession")
        token = await session.call_request_steam_launch(game.provider_id, timeout_ms)
        self.catalogue.store.mark_played(game.game_id)
        bus.disconnect()
        self.CatalogueChanged()
        return token

    @signal()
    def CatalogueChanged(self) -> "":
        return


async def serve() -> None:
    catalogue = ConsoleCatalog()
    catalogue.refresh()
    bus = await MessageBus(bus_type=BusType.SESSION).connect()
    bus.export(OBJECT_PATH, ConsoleInterface(catalogue))
    await bus.request_name(BUS_NAME)
    await asyncio.Event().wait()


def main() -> None:
    asyncio.run(serve())


if __name__ == "__main__":
    main()
