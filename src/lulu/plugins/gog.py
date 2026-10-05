"""GOG provider backed by heroic-gogdl, never by the Heroic frontend."""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
import sys
import subprocess
import shutil
from typing import Any
from urllib.parse import urlencode

from ..job_manager import JobExecutionError
from ..paths import PATHS
from .external import (CliAcquisitionExecutor, CliProviderAuthentication,
                       OwnedProviderGame, SnapshotEntitlementSource,
                       normalize_game)


LOGGER = logging.getLogger("lulu.gog")


class GogEntitlementSource(SnapshotEntitlementSource):
    provider_id = "gog"

    def __init__(self) -> None:
        super().__init__("gog", PATHS.provider_root("gog") / "entitlements.json", LOGGER)
        self.auth_path = PATHS.provider_config_root("gog") / "heroic/gog_store/auth.json"

    def _client(self) -> Any:
        try:
            from gogdl.auth import AuthorizationManager
            from gogdl.api import ApiHandler
        except ImportError as error:
            # Provisioning keeps gogdl and its dependencies in an isolated
            # venv while the Mudos service runs on the system interpreter.
            # Load that provider-owned module path directly; do not parse CLI
            # output or depend on the Heroic frontend.
            executable = shutil.which("gogdl")
            if executable:
                first_line = Path(executable).read_text(errors="replace").splitlines()[0]
                interpreter = Path(first_line.removeprefix("#!").strip())
                site_roots = sorted(interpreter.parent.parent.glob("lib/python*/site-packages"))
                for site_root in reversed(site_roots):
                    if site_root.is_dir() and str(site_root) not in sys.path:
                        sys.path.insert(0, str(site_root))
            try:
                from gogdl.auth import AuthorizationManager
                from gogdl.api import ApiHandler
            except ImportError as nested:
                raise RuntimeError("heroic-gogdl Python module is unavailable") from nested
        return ApiHandler(AuthorizationManager(str(self.auth_path)))

    def refresh(self) -> tuple[OwnedProviderGame, ...]:
        try:
            client = self._client()
            response = client.session.get("https://embed.gog.com/user/data/games")
            response.raise_for_status()
            ids = response.json().get("owned", [])
            owned: list[OwnedProviderGame] = []
            for identity in ids:
                item = client.get_item_data(str(identity)) or {}
                game = normalize_game(item, provider_id_keys=("id", "productId"),
                                      title_keys=("title", "name"))
                if game is not None:
                    owned.append(game)
            self.update(owned, self.installed())
        except Exception as error:
            self.last_error = str(error)
            LOGGER.warning("GOG entitlement refresh failed; retaining snapshot: %s", error)
        return self.snapshot

    def installed(self) -> tuple[OwnedProviderGame, ...]:
        installed: list[OwnedProviderGame] = []
        root = PATHS.gog_library_root
        for marker in root.glob("*/.mudos-game.json"):
            try:
                value = json.loads(marker.read_text())
                game = normalize_game(value, provider_id_keys=("provider_id", "id"),
                                      title_keys=("title", "name"))
                if game is not None:
                    installed.append(game)
            except (OSError, ValueError, json.JSONDecodeError):
                continue
        return tuple(installed)


class GogAuthentication(CliProviderAuthentication):
    def __init__(self) -> None:
        super().__init__("gog", "gogdl", PATHS.provider_config_root("gog") / "heroic/gog_store/auth.json")

    def authentication_methods(self) -> tuple[str, ...]:
        # gogdl accepts the authorization code returned by GOG's browser
        # login. The provider's fixed callback cannot be redirected to Mudos,
        # so the transaction also exposes the external-browser handoff.
        return ("auth_browser", "auth_2fa")

    def status(self) -> dict[str, object]:
        value = super().status()
        value["methods"] = list(self.authentication_methods())
        value["account"] = ""
        try:
            import json
            data = json.loads(self.config_path.read_text())
            credentials = next(iter(data.values()), {}) if isinstance(data, dict) else {}
            value["account"] = str(credentials.get("user_id", credentials.get("account_id", "")))
        except (OSError, ValueError, AttributeError, StopIteration):
            pass
        return value

    def begin(self) -> dict[str, object]:
        url = "https://auth.gog.com/auth?" + urlencode({
            "client_id": "46899977096215655",
            "redirect_uri": "https://embed.gog.com/on_login_success?origin=client",
            "response_type": "code",
        })
        return {"provider_id": "gog", "auth_method": "auth_browser",
                "verification_url": url, "surface": "browser"}

    def complete_code(self, code: str) -> dict[str, object]:
        """Let gogdl exchange the one-time browser code and write its private session."""
        GogEntitlementSource()._client()
        import argparse
        import contextlib
        import io
        from gogdl.auth import AuthorizationManager
        output = io.StringIO()
        args = argparse.Namespace(client_id=None, client_secret=None, authorization_code=code)
        with contextlib.redirect_stdout(output):
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            AuthorizationManager(str(self.config_path)).handle_cli(args, [])
        result = json.loads(output.getvalue() or "{}")
        if result.get("error"):
            raise RuntimeError("GOG authorization code was rejected")
        return self.status()


class GogAcquisitionExecutor(CliAcquisitionExecutor):
    # gogdl provides no uninstall command. Mudos removes only its own marked
    # per-title payload below PATHS.gog_library_root; other GOG installations
    # are deliberately not eligible.
    supports_uninstall = True

    def __init__(self) -> None:
        root = PATHS.gog_library_root
        auth_path = PATHS.provider_config_root("gog") / "heroic/gog_store/auth.json"
        super().__init__("gog", "gogdl", root,
                         lambda identity, destination: ["gogdl", "--auth-config-path", str(auth_path),
                                                        "download", identity.removeprefix("gog:"),
                                                         "--path", str(destination / identity.removeprefix("gog:")),
                                                          "--platform", "linux", "--with-dlcs"])

    def can_uninstall(self, game_id: str) -> bool:
        try:
            target = self._managed_install_directory(game_id)
            return target.is_dir()
        except (JobExecutionError, OSError, ValueError):
            return False

    def uninstall_capability(self, game) -> dict[str, object]:
        if (getattr(game, "provider", "") != "gog"
                or getattr(game, "install_state", "") != "installed"):
            return {"supported": False, "reason": "GOG title is not installed in Mudos."}
        try:
            target = self._managed_install_directory(str(game.game_id))
        except (JobExecutionError, OSError, ValueError):
            return {"supported": False,
                    "reason": "GOG ownership marker does not verify a Mudos-managed installation."}
        if target.exists() and not target.is_dir():
            return {"supported": False, "reason": "GOG install path is not a game directory."}
        return {"supported": True,
                "description": "Remove the marked Mudos-managed GOG game files"}


class GogLauncher:
    provider_ids = ("gog",)

    def launch_command(self, provider_id: str) -> list[str]:
        game_id = provider_id.removeprefix("gog:")
        container = PATHS.gog_library_root / game_id
        game_path = next((item.parent for item in container.glob("*/gameinfo")
                          if item.is_file()), container)
        return ["gogdl", "--auth-config-path", str(PATHS.provider_config_root("gog") / "heroic/gog_store/auth.json"),
                "launch", str(game_path), game_id,
                "--platform", "linux"]
