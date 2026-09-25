"""Steam plugin authentication capability descriptors.

Authentication is intentionally surfaced as two audiences. The GUI client is
authoritative for interactive Store use; SteamCMD has independent credentials
and session material for acquisition.
"""

import asyncio
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
    verification_task: asyncio.Task[dict[str, str]] | None = None

    def status(self) -> dict[str, object]:
        client_running = bool(self.provider._steam_client_pids())
        account = self._active_account() if client_running else None
        secrets = SecretStore()
        entitlement = SteamEntitlementConfig.from_file()
        username = (secrets.get("steam", "username")
                    or str((account or {}).get("account_name", ""))
                    or (entitlement.steam_username if entitlement else ""))
        password_configured = secrets.configured("steam", "password")
        executable = Path(PATHS.steamcmd_executable).is_file()
        steamcmd_session = (Path.home() / ".steam/steam.token").is_file()
        acquisition = bool(username and executable and (password_configured or steamcmd_session))
        authenticated = bool(account)
        return {"provider_id": "steam", "status": "authenticated" if authenticated else "authentication_required",
                "client": "signed_in" if authenticated else "running" if client_running else "stopped",
                "acquisition": "configured" if acquisition else "authentication_required",
                "acquisition_usable": acquisition, "account": username,
                "steamcmd_session": steamcmd_session,
                "steam_id": account.get("steam_id", "") if account else "",
                "persona": account.get("persona", "") if account else "",
                "authenticated": authenticated,
                "client_running": client_running,
                "username_configured": bool(username), "password_configured": password_configured,
                "entitlement_configured": bool(SteamEntitlementConfig.from_file()),
                "methods": ["auth_credentials", "auth_2fa", "auth_browser"]}

    def _active_account(self) -> dict[str, str] | None:
        """Return Steam's selected account only when its GUI session is live."""
        roots = (Path.home() / ".local/share/Steam", Path.home() / ".steam/steam")
        for root in roots:
            path = root / "config/loginusers.vdf"
            try:
                users = SteamProvider._parse_vdf(path.read_text(errors="replace")).get("users", {})
            except OSError:
                continue
            if not isinstance(users, dict):
                continue
            candidates = []
            has_selection_marker = any(isinstance(raw, dict) and "MostRecent" in raw
                                       for raw in users.values())
            for steam_id, raw in users.items():
                if not isinstance(raw, dict):
                    continue
                most_recent = str(raw.get("MostRecent", "")) == "1"
                # Recent Steam clients may omit MostRecent entirely. In that
                # format, infer the active account only when there is exactly
                # one locally complete account; never guess among cached users.
                if has_selection_marker and not most_recent:
                    continue
                account_name = str(raw.get("AccountName", "")).strip()
                persona = str(raw.get("PersonaName", "")).strip()
                localconfig = root / "userdata" / str(int(steam_id) - 76561197960265728) / "config/localconfig.vdf" \
                    if str(steam_id).isdecimal() else Path("/") / "nonexistent"
                if account_name and localconfig.is_file():
                    candidates.append({"steam_id": str(steam_id), "persona": persona,
                                       "account_name": account_name})
            if len(candidates) == 1:
                return candidates[0]
        return None

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
        if not self.acquisition.account:
            account = self._active_account()
            if account is None:
                return {"status": "authentication-required"}
            # SteamCMD remains an independent session, but can use the account
            # identity established by the GUI QR/Guard flow without storing a
            # password or copying GUI authentication files.
            self.acquisition.account = account["account_name"]
        if self.verification_task is None or self.verification_task.done():
            self.verification_task = asyncio.create_task(self.acquisition.authenticate(),
                                                         name="steamcmd-authentication")
        task = self.verification_task
        try:
            return await asyncio.shield(task)
        finally:
            if task.done() and self.verification_task is task:
                self.verification_task = None
