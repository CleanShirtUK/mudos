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
from ...credential import SecretStore


@dataclass(slots=True)
class SteamAuthentication:
    provider: SteamProvider
    acquisition: SteamCmdExecutor | None = None

    def status(self) -> dict[str, object]:
        client = bool(self.provider._steam_client_pids())
        secrets = SecretStore()
        username = secrets.get("steam", "username") or ""
        password_configured = secrets.configured("steam", "password")
        executable = Path(PATHS.steamcmd_executable).is_file()
        acquisition = bool(username and password_configured and executable)
        return {"provider_id": "steam", "status": "configured" if acquisition else "authentication_required",
                "client": "signed_in" if client else "authentication_required",
                "acquisition": "configured" if acquisition else "authentication_required",
                "acquisition_usable": acquisition, "account": username,
                "username_configured": bool(username), "password_configured": password_configured,
                "entitlement_configured": bool(SteamEntitlementConfig.from_file()),
                "methods": ["auth_credentials", "auth_2fa", "auth_browser"]}

    def begin(self) -> dict[str, object]:
        # The Steam client owns credential entry and Guard challenges. Mudos
        # launches its declared interactive surface; the existing compatibility
        # handoff then routes controller/OSK input without exposing secrets.
        return {"provider_id": "steam", "surface": "interactive"}

    def begin_admin_auth(self) -> dict[str, object]:
        # Steam web identity/client approval does not establish a SteamCMD
        # acquisition session. Admin therefore drives the credential boundary
        # and leaves Steam Guard as an ephemeral SteamCMD challenge.
        return {"provider_id": "steam", "auth_method": "auth_credentials",
                "surface": "credentials"}

    def sign_out(self) -> None:
        store = SecretStore()
        store.clear("steam", "username")
        store.clear("steam", "password")

    async def verify_acquisition(self) -> dict[str, str]:
        if self.acquisition is None:
            return {"status": "unavailable"}
        return await self.acquisition.authenticate()
