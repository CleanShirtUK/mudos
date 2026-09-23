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


class GogAcquisitionExecutor(CliAcquisitionExecutor):
    def __init__(self) -> None:
        root = PATHS.gog_library_root
        auth_path = PATHS.provider_config_root("gog") / "heroic/gog_store/auth.json"
        super().__init__("gog", "gogdl", root,
                         lambda identity, destination: ["gogdl", "--auth-config-path", str(auth_path),
                                                        "download", identity,
                                                        "--path", str(destination / identity.removeprefix("gog:")),
                                                        "--with-dlcs"],
                         lambda identity, destination: ["gogdl", "--auth-config-path", str(auth_path), "import",
                                                        str(destination / identity.removeprefix("gog:"))])


class GogLauncher:
    provider_ids = ("gog",)

    def launch_command(self, provider_id: str) -> list[str]:
        game_id = provider_id.removeprefix("gog:")
        return ["gogdl", "--auth-config-path", str(PATHS.provider_config_root("gog") / "heroic/gog_store/auth.json"),
                "launch", str(PATHS.gog_library_root / game_id), game_id,
                "--platform", "linux"]
