"""Epic provider backed by Legendary's structured CLI."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
import subprocess

from ..paths import PATHS
from ..windows_runtime import WindowsRuntime
from .external import (CliAcquisitionExecutor, CliProviderAuthentication,
                       OwnedProviderGame, SnapshotEntitlementSource,
                       normalize_game)


LOGGER = logging.getLogger("lulu.epic")


class EpicEntitlementSource(SnapshotEntitlementSource):
    provider_id = "epic"

    def __init__(self) -> None:
        super().__init__("epic", PATHS.provider_root("epic") / "entitlements.json", LOGGER)
        self.config_dir = PATHS.provider_config_root("epic") / "legendary"
        self.config_path = self.config_dir / "user.json"

    def _environment(self) -> dict[str, str]:
        return {**os.environ, "LEGENDARY_CONFIG_PATH": str(self.config_dir)}

    def _json(self, command: list[str]) -> object:
        result = subprocess.run(command, check=True, capture_output=True, text=True,
                                timeout=60, env=self._environment())
        return json.loads(result.stdout)

    def refresh(self) -> tuple[OwnedProviderGame, ...]:
        try:
            value = self._json(["legendary", "list", "--json"])
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
        discovered: dict[str, OwnedProviderGame] = {}
        try:
            value = self._json(["legendary", "list-installed", "--json", "--show-dirs"])
            records = value if isinstance(value, list) else []
            discovered.update((game.provider_id, game) for item in records
                              if (game := normalize_game(item,
                                   provider_id_keys=("app_name", "appName", "id"),
                                   title_keys=("app_title", "appTitle", "title", "name"))) is not None)
        except (OSError, subprocess.SubprocessError, TypeError, ValueError, json.JSONDecodeError):
            pass
        # A successful acquisition writes an identity marker only after its
        # CLI returns success. Use that same durable authority if Legendary's
        # optional list-installed JSON omits a just-installed item.
        for marker in PATHS.epic_library_root.glob("*/.mudos-game.json"):
            try:
                value = json.loads(marker.read_text())
                game = normalize_game(value, provider_id_keys=("provider_id", "id"),
                                      title_keys=("title", "name"))
                if game is not None:
                    discovered[game.provider_id] = game
            except (OSError, TypeError, ValueError, json.JSONDecodeError):
                continue
        return tuple(sorted(discovered.values(), key=lambda item: item.title.casefold()))


class EpicAuthentication(CliProviderAuthentication):
    def __init__(self) -> None:
        self.config_dir = PATHS.provider_config_root("epic") / "legendary"
        super().__init__("epic", "legendary", self.config_dir / "user.json")

    def authentication_methods(self) -> tuple[str, ...]:
        return ("auth_browser",)

    def begin(self) -> dict[str, object]:
        return {"provider_id": "epic", "auth_method": "auth_browser",
                "verification_url": "https://legendary.gl/epiclogin", "surface": "browser"}

    def complete_code(self, code: str) -> dict[str, object]:
        self.config_dir.mkdir(parents=True, exist_ok=True)
        result = subprocess.run(["legendary", "auth", "--code", code],
                                capture_output=True, text=True, timeout=60,
                                env={**os.environ, "LEGENDARY_CONFIG_PATH": str(self.config_dir)})
        if result.returncode != 0 or not self.config_path.is_file():
            raise RuntimeError("Epic authorization code was rejected by Legendary")
        return self.status()


class EpicAcquisitionExecutor(CliAcquisitionExecutor):
    def __init__(self) -> None:
        root = PATHS.epic_library_root
        config_dir = PATHS.provider_config_root("epic") / "legendary"
        super().__init__("epic", "legendary", root,
                         lambda identity, destination: ["legendary", "-y", "install", identity.removeprefix("epic:"),
                                                        "--base-path", str(destination),
                                                        "--game-folder", identity.removeprefix("epic:"),
                                                        "--skip-sdl", "--skip-dlcs"],
                         lambda identity, destination: ["legendary", "-y", "uninstall", identity.removeprefix("epic:")])
        self.environment = {**os.environ, "LEGENDARY_CONFIG_PATH": str(config_dir)}


class EpicLauncher:
    provider_ids = ("epic",)

    def launch_command(self, provider_id: str) -> list[str]:
        game_id = provider_id.removeprefix("epic:")
        result = subprocess.run(
            ["legendary", "launch", game_id, "--json"],
            check=True, capture_output=True, text=True, timeout=60,
            env={**os.environ,
                 "LEGENDARY_CONFIG_PATH": str(PATHS.provider_config_root("epic") / "legendary")},
        )
        payload = next((json.loads(line) for line in reversed(result.stdout.splitlines())
                        if line.lstrip().startswith("{")), None)
        if not isinstance(payload, dict):
            raise RuntimeError("Legendary did not return structured launch metadata")
        executable = Path(str(payload.get("game_directory", ""))) / str(payload.get("game_executable", ""))
        arguments = [str(item) for item in (
            payload.get("egl_parameters", []) + payload.get("game_parameters", [])
            + payload.get("user_parameters", []))]
        exchange_code = next((value.split("=", 1)[1] for value in arguments
                              if value.startswith("-AUTH_PASSWORD=")), "")
        if not exchange_code:
            raise RuntimeError("Legendary did not return a fresh Epic launch credential")
        if not executable.is_file():
            raise RuntimeError("Legendary launch executable is unavailable")
        return WindowsRuntime(game_id, store="egs").command(executable, arguments)
