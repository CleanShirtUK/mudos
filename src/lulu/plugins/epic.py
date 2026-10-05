"""Epic provider backed by Legendary's structured CLI."""

from __future__ import annotations

import asyncio
import json
import logging
import os
from pathlib import Path
import re
import subprocess
from dataclasses import replace

from ..paths import PATHS
from ..job_manager import JobExecutionError
from ..jobs import JobState
from ..windows_runtime import WindowsRuntime
from .external import (CliAcquisitionExecutor, CliProviderAuthentication,
                       OwnedProviderGame, SnapshotEntitlementSource,
                       normalize_game)


LOGGER = logging.getLogger("lulu.epic")


def _third_party_managed_store(config_dir: Path, app_id: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9._-]+", app_id):
        return ""
    metadata_path = config_dir / "metadata" / f"{app_id}.json"
    try:
        metadata = json.loads(metadata_path.read_text()).get("metadata", {})
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        return ""
    attributes = metadata.get("customAttributes", {}) if isinstance(metadata, dict) else {}
    value = attributes.get("ThirdPartyManagedProvider", "") if isinstance(attributes, dict) else ""
    if isinstance(value, dict):
        value = value.get("value", "")
    return str(value).strip()


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
            owned = []
            for item in records:
                game = normalize_game(item, provider_id_keys=("app_name", "appName", "id"),
                                      title_keys=("app_title", "appTitle", "title", "name"))
                if game is not None:
                    store = _third_party_managed_store(self.config_dir, game.provider_id)
                    owned.append(replace(game, availability_state="unavailable" if store else "available"))
            self.update(owned, self.installed())
        except (OSError, subprocess.SubprocessError, TypeError, ValueError, json.JSONDecodeError) as error:
            self.last_error = str(error)
            LOGGER.warning("Epic entitlement refresh failed; retaining snapshot: %s", error)
        return self.snapshot

    def installed(self) -> tuple[OwnedProviderGame, ...]:
        discovered: dict[str, OwnedProviderGame] = {}
        root = PATHS.epic_library_root.resolve(strict=False)
        try:
            value = self._json(["legendary", "list-installed", "--json", "--show-dirs"])
            records = value if isinstance(value, list) else []
            for item in records:
                game = normalize_game(item, provider_id_keys=("app_name", "appName", "id"),
                                      title_keys=("app_title", "appTitle", "title", "name"))
                if (game is None or
                        not self._is_canonical_directory(game.install_dir, root, game.provider_id)):
                    continue
                discovered[game.provider_id] = game
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
                if (game is not None and not marker.parent.is_symlink()
                        and self._is_canonical_directory(str(marker.parent), root, game.provider_id)
                        and Path(game.install_dir).resolve(strict=False) == marker.parent.resolve(strict=False)
                        and any(item.is_file() and item.name != ".mudos-game.json"
                                for item in marker.parent.rglob("*"))):
                    discovered[game.provider_id] = game
            except (OSError, TypeError, ValueError, json.JSONDecodeError):
                continue
        return tuple(sorted(discovered.values(), key=lambda item: item.title.casefold()))

    @staticmethod
    def _is_canonical_directory(raw_path: str, root: Path, app_id: str) -> bool:
        if not raw_path:
            return False
        original = Path(raw_path)
        if original.is_symlink():
            return False
        target = original.resolve(strict=False)
        try:
            target.relative_to(root)
        except ValueError:
            return False
        return (target != root and target.parent == root and target.name == app_id
                and target.is_dir())


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
    supports_uninstall = True
    uninstall_progress_supported = True

    def __init__(self) -> None:
        root = PATHS.epic_library_root
        config_dir = PATHS.provider_config_root("epic") / "legendary"
        self.config_dir = config_dir
        super().__init__("epic", "legendary", root, self._install_command,
                         lambda identity, destination: ["legendary", "-y", "uninstall", identity.removeprefix("epic:")])
        self.environment = {**os.environ, "LEGENDARY_CONFIG_PATH": str(config_dir)}

    def _json(self, command: list[str]) -> object:
        executable = self._require()
        result = subprocess.run([executable, *command[1:]], check=True,
                                capture_output=True, text=True, timeout=60,
                                env=self.environment)
        return json.loads(result.stdout)

    @staticmethod
    def _app_id(identity: str) -> str:
        app_id = identity.removeprefix("epic:")
        if not re.fullmatch(r"[A-Za-z0-9._-]+", app_id):
            raise JobExecutionError("epic-invalid-identity", "Epic app identity is invalid", retryable=False)
        return app_id

    def _third_party_store(self, app_id: str) -> str:
        return _third_party_managed_store(self.config_dir, app_id)

    def can_uninstall(self, game_id: str) -> bool:
        try:
            app_id = self._app_id(game_id)
        except JobExecutionError:
            return False
        if self._third_party_store(app_id):
            return False
        root = PATHS.epic_library_root.resolve(strict=False)
        directory = root / app_id
        if directory.is_symlink():
            return False
        resolved = directory.resolve(strict=False)
        return resolved != root and resolved.parent == root and (not resolved.exists() or resolved.is_dir())

    def uninstall_capability(self, game) -> dict[str, object]:
        if (getattr(game, "provider", "") != "epic"
                or getattr(game, "install_state", "") != "installed"):
            return {"supported": False, "reason": "Epic title is not installed."}
        try:
            app_id = self._app_id(str(game.provider_id))
        except (AttributeError, JobExecutionError):
            return {"supported": False, "reason": "Epic app identity is invalid."}
        if self._third_party_store(app_id):
            return {"supported": False,
                    "reason": "This title is managed by another Epic provider; remove it there."}
        root = PATHS.epic_library_root.resolve(strict=False)
        if not EpicEntitlementSource._is_canonical_directory(str(getattr(game, "install_dir", "")),
                                                             root, app_id):
            return {"supported": False,
                    "reason": "Legendary does not report a verified Mudos-managed Epic install path."}
        return {"supported": True, "description": "Uninstall this Epic title through Legendary."}

    async def run(self, job, reporter) -> None:
        if job.operation.value != "remove":
            await super().run(job, reporter)
            return
        app_id = self._app_id(job.content_identity)
        # A service restart can replay a removal after Legendary already
        # completed it. Query the authoritative installed inventory; a
        # missing game is a successful idempotent removal, while provider/API
        # errors remain failures and never trigger local recursive deletion.
        await reporter.state(JobState.STARTING, stage="checking-installation")
        try:
            value = await asyncio.to_thread(self.provider_installed_record, app_id)
        except Exception as error:
            raise JobExecutionError("epic-inventory-unavailable",
                                    "Legendary could not confirm the installed Epic title",
                                    retryable=True) from error
        if value is None:
            await reporter.state(JobState.FINALIZING, stage="reconciling")
            return
        if self._third_party_store(app_id):
            raise JobExecutionError("epic-third-party-managed",
                                    "This title is managed by another Epic provider; remove it there.",
                                    retryable=False)
        if not EpicEntitlementSource._is_canonical_directory(
                str(value.get("install_dir", "")), PATHS.epic_library_root.resolve(strict=False), app_id):
            raise JobExecutionError("unsafe-uninstall-path",
                                    "Legendary reports an Epic install outside Mudos' managed library",
                                    retryable=False)
        await super().run(job, reporter)

    def provider_installed_record(self, app_id: str) -> dict[str, object] | None:
        value = self._json(["legendary", "list-installed", "--json", "--show-dirs"])
        rows = value if isinstance(value, list) else []
        for item in rows:
            game = normalize_game(item, provider_id_keys=("app_name", "appName", "id"),
                                  title_keys=("app_title", "appTitle", "title", "name"))
            if game is not None and game.provider_id == app_id:
                return {"provider_id": game.provider_id, "install_dir": game.install_dir}
        return None

    def _install_command(self, identity: str, destination: Path) -> list[str]:
        app_id = self._app_id(identity)
        third_party = self._third_party_store(app_id)
        if third_party:
            raise JobExecutionError(
                "epic-third-party-managed",
                f"This Epic entitlement must be installed through {third_party}; Legendary cannot install it directly",
                retryable=False,
                details={"app_id": app_id, "required_provider": third_party},
            )
        return self._command_for_install(identity, destination)

    def _command_for_install(self, identity: str, destination: Path) -> list[str]:
        app_id = self._app_id(identity)
        return ["legendary", "-y", "install", app_id,
                "--base-path", str(destination), "--game-folder", app_id,
                "--skip-sdl", "--skip-dlcs"]

    def _diagnostic_line(self, line: str) -> str:
        value = re.sub(r"(?i)\b(access[_ -]?token|refresh[_ -]?token|auth[_ -]?(?:password|token)|password|secret)\b(\s*[=:]\s*)\S+",
                       r"\1\2<redacted>", line)
        value = re.sub(r"(?i)\bBearer\s+\S+", "Bearer <redacted>", value)
        return value[-400:]

    def _process_failure(self, returncode: int, provider_message: str) -> JobExecutionError:
        details: dict[str, object] = {"return_code": returncode}
        message = f"Legendary exited with status {returncode}"
        if provider_message:
            details["provider_message"] = provider_message
            message += f": {provider_message}"
        return JobExecutionError("epic-failed", message, retryable=True, details=details)

    def _validation_failure(self, error: JobExecutionError, returncode: int,
                            provider_message: str) -> JobExecutionError:
        details = dict(error.details or {})
        details["return_code"] = returncode
        if provider_message:
            details["provider_message"] = provider_message
        message = str(error)
        if provider_message:
            message += f" (Legendary reported: {provider_message})"
        return JobExecutionError(error.code, message, retryable=error.retryable, details=details)


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
