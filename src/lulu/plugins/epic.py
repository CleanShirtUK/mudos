"""Epic provider backed by Legendary's structured CLI."""

from __future__ import annotations

import json
import logging
from pathlib import Path
import subprocess

from ..paths import PATHS
from .external import (CliAcquisitionExecutor, CliProviderAuthentication,
                       OwnedProviderGame, SnapshotEntitlementSource,
                       normalize_game)


LOGGER = logging.getLogger("lulu.epic")


class EpicEntitlementSource(SnapshotEntitlementSource):
    provider_id = "epic"

    def __init__(self) -> None:
        super().__init__("epic", PATHS.provider_root("epic") / "entitlements.json", LOGGER)
        self.config_path = PATHS.provider_config_root("epic") / "legendary/user.json"

    @staticmethod
    def _json(command: list[str]) -> object:
        result = subprocess.run(command, check=True, capture_output=True, text=True, timeout=60)
        return json.loads(result.stdout)

    def refresh(self) -> tuple[OwnedProviderGame, ...]:
        try:
            value = self._json(["legendary", "-c", str(self.config_path), "list-games", "--json"])
            records = value if isinstance(value, list) else []
            owned = [game for item in records
                      if (game := normalize_game(item,
                           provider_id_keys=("app_name", "appName", "id"),
                           title_keys=("app_title", "appTitle", "title", "name"))) is not None]
            self.update(owned, self.installed())
        except (OSError, subprocess.SubprocessError, TypeError, ValueError, json.JSONDecodeError) as error:
            self.last_error = str(error)
            LOGGER.warning("Epic entitlement refresh failed; retaining snapshot: %s", error)
        return self.snapshot

    def installed(self) -> tuple[OwnedProviderGame, ...]:
        try:
            value = self._json(["legendary", "-c", str(self.config_path), "list-installed", "--json", "--show-dirs"])
            records = value if isinstance(value, list) else []
            return tuple(game for item in records
                         if (game := normalize_game(item,
                              provider_id_keys=("app_name", "appName", "id"),
                              title_keys=("app_title", "appTitle", "title", "name"))) is not None)
        except (OSError, subprocess.SubprocessError, TypeError, ValueError, json.JSONDecodeError):
            return ()


class EpicAuthentication(CliProviderAuthentication):
    def __init__(self) -> None:
        super().__init__("epic", "legendary", PATHS.provider_config_root("epic") / "legendary/user.json")

    def authentication_methods(self) -> tuple[str, ...]:
        return ("auth_browser", "auth_device_code", "auth_2fa")


class EpicAcquisitionExecutor(CliAcquisitionExecutor):
    def __init__(self) -> None:
        root = PATHS.epic_library_root
        config_path = PATHS.provider_config_root("epic") / "legendary/user.json"
        super().__init__("epic", "legendary", root,
                         lambda identity, destination: ["legendary", "-c", str(config_path), "install", identity.removeprefix("epic:"),
                                                        "--base-path", str(destination)],
                         lambda identity, destination: ["legendary", "-c", str(config_path), "uninstall", identity.removeprefix("epic:")])


class EpicLauncher:
    provider_ids = ("epic",)

    def launch_command(self, provider_id: str) -> list[str]:
        return ["legendary", "-c", str(PATHS.provider_config_root("epic") / "legendary/user.json"),
                "launch", provider_id.removeprefix("epic:")]
