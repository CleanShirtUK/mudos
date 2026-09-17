"""Steam plugin authentication capability descriptors.

Authentication is intentionally surfaced as two audiences. The GUI client is
authoritative for interactive Store use; SteamCMD has independent credentials
and session material for acquisition.
"""

from dataclasses import dataclass
from pathlib import Path

from .provider import SteamProvider
from .entitlements import SteamEntitlementConfig
from ...paths import PATHS
from .cmd import SteamCmdExecutor


@dataclass(slots=True)
class SteamAuthentication:
    provider: SteamProvider
    acquisition: SteamCmdExecutor | None = None

    def status(self) -> dict[str, object]:
        client = bool(self.provider._steam_client_pids())
        acquisition = bool(SteamEntitlementConfig.from_file()) and Path(PATHS.steamcmd_executable).is_file()
        return {"client": "signed_in" if client else "authentication_required",
                "acquisition": "configured" if acquisition else "authentication_required"}

    def begin(self) -> dict[str, object]:
        # The Steam client owns credential entry and Guard challenges. Mudos
        # launches its declared interactive surface; the existing compatibility
        # handoff then routes controller/OSK input without exposing secrets.
        return {"provider_id": "steam", "surface": "interactive"}

    async def verify_acquisition(self) -> dict[str, str]:
        if self.acquisition is None:
            return {"status": "unavailable"}
        return await self.acquisition.authenticate()
