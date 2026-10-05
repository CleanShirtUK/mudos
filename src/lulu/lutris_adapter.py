"""Narrow adapter around the installed Lutris APIs and CLI."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import asyncio
import copy
import json
import os
import shlex
import threading
from types import MethodType
from urllib.parse import urlparse
from typing import Any

from .pc_install import PcInstallSource, RecipeMatch, recipe_requirements, match_required_files


class LutrisAdapterError(RuntimeError):
    pass


class LutrisInstallCancelled(LutrisAdapterError):
    """The user explicitly cancelled an owned interactive child."""


@dataclass(frozen=True, slots=True)
class LutrisRecipe:
    game_slug: str
    installer_slug: str
    title: str
    runner: str
    raw: dict[str, Any]

    @property
    def requirements(self):
        return recipe_requirements(self.raw)


class LutrisAdapter:
    """Keep private Lutris imports out of Mudos catalogue/job code."""

    def installed_games(self) -> tuple[dict[str, object], ...]:
        """Read Lutris's supported game/config objects as one installed snapshot."""
        try:
            from lutris import settings
            from lutris.database.games import get_games
            from lutris.game import Game
            # Headless services may be the first Lutris process after boot.
            # Initialize Lutris's own schema through its migration API.
            from lutris.database.schema import syncdb

            Path(settings.DB_PATH).parent.mkdir(parents=True, exist_ok=True)
            Path(settings.GAME_CONFIG_DIR).mkdir(parents=True, exist_ok=True)
            Path(settings.RUNNERS_CONFIG_DIR).mkdir(parents=True, exist_ok=True)
            syncdb()
            result: list[dict[str, object]] = []
            for row in get_games(filters={"installed": 1}):
                try:
                    game = Game(row["id"])
                    config = game.config
                    game_options = config.game_config if config else {}
                    result.append({
                        "lutris_id": str(row["id"]), "slug": str(game.slug or row.get("slug") or ""),
                        "title": str(game.name or row.get("name") or ""),
                        "runner": str(game.runner_name or row.get("runner") or ""),
                        "platform": str(game.platform or row.get("platform") or "PC"),
                        "directory": str(game.directory or row.get("directory") or ""),
                        "config_id": str(game.game_config_id or row.get("configpath") or ""),
                        "executable": str(game_options.get("exe") or ""),
                        "arguments": str(game_options.get("args") or ""),
                        "working_directory": str(game_options.get("working_dir") or ""),
                        "installed": bool(game.is_installed),
                    })
                except Exception:
                    # A broken individual Lutris record must not hide the rest
                    # of the provider's installed-game snapshot.
                    continue
            return tuple(result)
        except Exception as error:
            raise LutrisAdapterError("Lutris installed-game inventory is unavailable") from error

    def register_local_game(self, *, title: str, directory: Path, executable: Path,
                            runner: str | None = None, arguments: str = "",
                            working_directory: Path | None = None) -> dict[str, object]:
        """Register an existing game through Lutris's own model/config save APIs."""
        directory = directory.expanduser().resolve(strict=True)
        executable = executable.expanduser().resolve(strict=True)
        if not directory.is_dir() or not executable.is_file():
            raise LutrisAdapterError("game directory or executable does not exist")
        try:
            executable.relative_to(directory)
        except ValueError as error:
            raise LutrisAdapterError("executable must be inside the selected game directory") from error
        runner = runner or ("wine" if executable.suffix.casefold() == ".exe" else "linux")
        if runner not in {"linux", "wine"}:
            raise LutrisAdapterError("local registration supports native Linux and Wine games")
        if not os.access(executable, os.X_OK) and runner == "linux":
            raise LutrisAdapterError("native Linux executable is not executable")
        try:
            from lutris import settings
            from lutris.config import LutrisConfig, make_game_config_id
            from lutris.database.schema import syncdb
            from lutris.game import Game
            from lutris.util.strings import slugify

            Path(settings.DB_PATH).parent.mkdir(parents=True, exist_ok=True)
            Path(settings.GAME_CONFIG_DIR).mkdir(parents=True, exist_ok=True)
            Path(settings.RUNNERS_CONFIG_DIR).mkdir(parents=True, exist_ok=True)
            syncdb()
            slug = slugify(title)
            if not slug:
                raise LutrisAdapterError("game title does not produce a valid Lutris identity")
            config = LutrisConfig(runner_slug=runner, level="game")
            config.game_config_id = make_game_config_id(slug)
            game_config = config.game_level["game"]
            game_config.update({
                "exe": str(executable.relative_to(directory)),
                "args": arguments,
                "working_dir": str(working_directory.resolve(strict=True) if working_directory else directory),
            })
            game = Game()
            game.name = title.strip()
            game.sortname = title.strip()
            game.slug = slug
            game.runner_name = runner
            game.directory = str(directory)
            game.is_installed = True
            game.config = config
            game.save()
            row = __import__("lutris.database.games", fromlist=["get_game_by_field"]).get_game_by_field(
                str(game.id), "id")
            if not row:
                raise LutrisAdapterError("Lutris registration could not be read back")
            return {
                "lutris_id": str(game.id), "config_id": str(game.game_config_id), "slug": slug,
                "title": game.name, "runner": runner, "platform": str(game.platform or "Linux"),
                "directory": str(directory), "executable": str(executable.relative_to(directory)),
                "arguments": arguments, "working_directory": str(working_directory or directory),
                "installed": True,
            }
        except LutrisAdapterError:
            raise
        except Exception as error:
            raise LutrisAdapterError("Lutris could not register the local game") from error

    def search(self, title: str) -> tuple[dict[str, Any], ...]:
        try:
            from lutris.api import search_games
            value = search_games(title)
        except Exception as error:  # Lutris/network failures are provider-local
            raise LutrisAdapterError("Lutris game search failed") from error
        results = value.get("results", []) if isinstance(value, dict) else []
        return tuple(item for item in results if isinstance(item, dict))

    def recipes(self, game_slug: str) -> tuple[LutrisRecipe, ...]:
        try:
            from lutris.api import get_game_installers
            values = get_game_installers(game_slug)
        except Exception as error:
            raise LutrisAdapterError("Lutris installer lookup failed") from error
        return tuple(LutrisRecipe(str(item.get("game_slug", game_slug)),
                                  str(item.get("slug", "")), str(item.get("name", "")),
                                  str(item.get("runner", "")), item)
                     for item in values if isinstance(item, dict) and item.get("slug"))

    def match(self, source: PcInstallSource, candidates: tuple[LutrisRecipe, ...]) -> LutrisRecipe:
        if source.lutris_installer_slug:
            selected = [item for item in candidates if item.installer_slug == source.lutris_installer_slug]
            if len(selected) != 1:
                raise LutrisAdapterError("selected Lutris recipe is unavailable")
            match_required_files(source, selected[0].requirements)
            return selected[0]
        applicable: list[LutrisRecipe] = []
        for recipe in candidates:
            try:
                match_required_files(source, recipe.requirements)
            except ValueError:
                continue
            applicable.append(recipe)
        if len(applicable) != 1:
            raise LutrisAdapterError("Lutris recipe selection is ambiguous or unavailable")
        return applicable[0]

    @staticmethod
    def classify_interactive_commands(source: PcInstallSource, recipe: LutrisRecipe) -> tuple[int, ...]:
        """Identify likely user-facing Wine installer commands conservatively."""
        if not recipe.runner.casefold().startswith("wine"):
            return ()
        local_ids = {item.file_id for item in recipe.requirements if item.local}
        quiet = ("/s", "/silent", "/verysilent", "/qn", "/quiet", "--silent",
                 "--unattended", "--no-interactive", "-silent")
        script = recipe.raw.get("script", {})
        commands = script.get("installer", []) if isinstance(script, dict) else []
        marked: list[int] = []
        for index, command in enumerate(commands):
            if not isinstance(command, dict):
                continue
            data = command.get("execute") or command.get("task")
            if not isinstance(data, dict):
                continue
            task_name = str(data.get("name", "")).casefold()
            if "task" in command and task_name not in {"wine.wineexec", "wineexec"}:
                continue
            executable = str(data.get("file") or data.get("executable") or "")
            args = str(data.get("args", "")).casefold().split()
            if executable in local_ids and not any(flag in args for flag in quiet):
                marked.append(index)
        return tuple(marked)

    def execute(self, source: PcInstallSource, recipe: LutrisRecipe, destination: Path,
                *, status: callable | None = None, transaction_id: str | None = None) -> dict[str, object]:
        """Run Lutris's ScriptInterpreter with a non-GTK delegate.

        Lutris still requires a GLib main loop because its AsyncCall scheduler
        drives commands and runner setup.  The delegate below supplies only
        installer callbacks; it never creates the Lutris GTK application.
        """
        try:
            from gi.repository import GLib
            from lutris.database.games import get_game_by_field
            from lutris.database.schema import syncdb
            from lutris.installer.interpreter import ScriptInterpreter
            from lutris import settings
        except Exception as error:
            raise LutrisAdapterError("Lutris installer runtime is unavailable") from error

        # Acquisitiond is a headless service and Lutris does not create its
        # XDG data directory until the GTK application has started.  Establish
        # only Lutris's normal per-user directories; no database is mutated by
        # Mudos directly.
        Path(settings.DB_PATH).parent.mkdir(parents=True, exist_ok=True)
        Path(settings.CACHE_DIR).mkdir(parents=True, exist_ok=True)
        Path(settings.GAME_CONFIG_DIR).mkdir(parents=True, exist_ok=True)
        Path(settings.RUNNERS_CONFIG_DIR).mkdir(parents=True, exist_ok=True)
        # This is Lutris's own schema migration entry point, normally called
        # by its GTK application startup.  Mudos does not issue SQL itself.
        syncdb()

        result: dict[str, object] = {}
        loop = GLib.MainLoop()

        class Delegate:
            service = None
            appid = None

            def report_error(self, error):
                result["error"] = str(error)
                loop.quit()

            def report_status(self, value):
                if status:
                    status(str(value))

            def attach_log(self, _command):
                return None

            def begin_disc_prompt(self, _message, _requires, _installer, _callback):
                result["interaction"] = "disc"
                loop.quit()

            def begin_input_menu(self, _alias, _options, _preselect, _callback):
                result["interaction"] = "input"
                loop.quit()

            def report_finished(self, game_id, _status):
                result["game_id"] = game_id
                loop.quit()

        delegate = Delegate()
        try:
            runtime_recipe = copy.deepcopy(recipe.raw)
            for index in self.classify_interactive_commands(source, recipe):
                command = runtime_recipe.get("script", {}).get("installer", [])[index]
                data = command.get("execute") if isinstance(command, dict) else None
                if isinstance(data, dict):
                    data["env"] = {**dict(data.get("env", {}) or {}), "MUDOS_INTERACTIVE": "1"}
                task = command.get("task") if isinstance(command, dict) else None
                if isinstance(task, dict):
                    task["mudos_interactive"] = True
            interpreter = ScriptInterpreter(runtime_recipe, delegate)
            # Lutris keeps an uninstalled registration row so reinstalling a
            # retained PC source must update that row rather than insert a
            # second record with the same provider/slug.
            existing = get_game_by_field(recipe.game_slug, "slug")
            if existing and hasattr(interpreter, "installer"):
                interpreter.installer.game_id = int(existing["id"])
            if len(getattr(interpreter, "current_resolution", ())) != 2:
                interpreter.current_resolution = ("1920", "1080")
            interpreter.target_path = str(destination)
            destination.mkdir(parents=True, exist_ok=True)
            interpreter.installer.prepare_game_files([])
            local = match_required_files(source, recipe.requirements)
            interpreter.game_files.update(local)
            self._prepare_remote_files(interpreter, local, status=status)
            original_execute = interpreter.execute
            original_task = interpreter.task

            def execute_with_delegation(instance, data):
                values = dict(data) if isinstance(data, dict) else data
                marker = isinstance(values, dict) and str((values.get("env") or {}).get("MUDOS_INTERACTIVE", "")) == "1"
                if not marker or not transaction_id:
                    return original_execute(values)
                if status:
                    status("awaiting_interaction")
                return self._execute_interactive(
                    interpreter, values, transaction_id, loop, result, status=status
                )

            interpreter.execute = MethodType(execute_with_delegation, interpreter)

            def task_with_delegation(instance, data):
                values = dict(data) if isinstance(data, dict) else data
                if isinstance(values, dict) and values.pop("mudos_interactive", False) and transaction_id:
                    if status:
                        status("awaiting_interaction")
                    values["file"] = values.get("executable")
                    values["env"] = values.get("env") or {}
                    values["env"]["MUDOS_INTERACTIVE"] = "1"
                    values["_mudos_wine"] = True
                    return self._execute_interactive(
                        interpreter, values, transaction_id, loop, result, status=status
                    )
                return original_task(values)

            interpreter.task = MethodType(task_with_delegation, interpreter)
            # The signal is the supported seam used by Lutris's installer
            # window after runner preparation completes.
            interpreter.connect("runners-installed", lambda *_: interpreter.launch_installer_commands())
            interpreter.launch_install(delegate)
            loop.run()
        except Exception as error:
            raise LutrisAdapterError(str(error)) from error
        if "error" in result:
            raise LutrisAdapterError(str(result["error"]))
        if result.get("cancelled"):
            raise LutrisInstallCancelled("interactive installation cancelled")
        if "interaction" in result:
            raise LutrisAdapterError(f"interactive installer required: {result['interaction']}")
        if "game_id" not in result:
            raise LutrisAdapterError("Lutris installer ended without registration")
        row = get_game_by_field(str(result["game_id"]), "id")
        if not row:
            raise LutrisAdapterError("Lutris registration could not be read back")
        return {"lutris_id": str(result["game_id"]), "config_id": str(row.get("configpath", "")),
                "slug": str(row.get("slug", recipe.game_slug)), "title": str(row.get("name", recipe.title)),
                "runner": str(row.get("runner", recipe.runner)), "directory": str(row.get("directory", destination))}

    def _execute_interactive(self, interpreter, data, transaction_id, loop, result, *, status=None):
        """Route explicitly marked execute commands through sessiond ownership.

        The marker is recipe metadata for a potentially graphical command; all
        ordinary Lutris commands remain upstream implementations unchanged.
        """
        values = dict(data)
        env = dict(values.pop("env", {}) or {})
        env.pop("MUDOS_INTERACTIVE", None)
        executable = values.get("file") or values.get("command")
        if not executable:
            raise LutrisAdapterError("interactive command has no executable")
        executable = interpreter._substitute(str(executable))
        args = [interpreter._substitute(value) for value in shlex.split(str(values.get("args", "")))]
        command = [executable, *args]
        if values.pop("_mudos_wine", False):
            command = [interpreter._substitute(str(interpreter.get_wine_path())), executable, *args]
        if str(values.get("command", "")) and not values.get("file"):
            command = ["/usr/bin/env", "bash", "-c", interpreter._substitute(str(values["command"]))]

        def wait_for_child():
            try:
                outcome = asyncio.run(self._wait_for_interactive_child(transaction_id, command, result))
                result["child_outcome"] = outcome
                if status:
                    status("interaction_complete")
                if outcome == "cancelled":
                    result["cancelled"] = True
                elif outcome != "success":
                    result["error"] = f"interactive child exited with outcome {outcome}"
                from gi.repository import GLib
                GLib.idle_add(interpreter._iter_commands, None, None) if outcome == "success" else GLib.idle_add(loop.quit)
            except Exception as error:
                result["error"] = str(error)
                from gi.repository import GLib
                GLib.idle_add(loop.quit)

        threading.Thread(target=wait_for_child, name="mudos-lutris-interactive", daemon=True).start()
        return "STOP"

    async def _wait_for_interactive_child(self, transaction_id: str, command: list[str], result: dict[str, object]) -> str:
        from dbus_next.aio import MessageBus

        bus = await MessageBus().connect()
        try:
            intro = await bus.introspect("org.lulu.ConsoleSessiond", "/org/lulu/ConsoleSession")
            session = bus.get_proxy_object("org.lulu.ConsoleSessiond", "/org/lulu/ConsoleSession", intro).get_interface("org.lulu.ConsoleSession")
            context = {key: value for key in (
                "DISPLAY", "WAYLAND_DISPLAY", "XDG_RUNTIME_DIR", "XDG_SESSION_TYPE",
                "DBUS_SESSION_BUS_ADDRESS", "XAUTHORITY", "HOME", "USER",
            ) if (value := __import__("os").environ.get(key))}
            await session.call_set_delegated_launch_context(json.dumps(context, sort_keys=True))
            token = await session.call_request_interactive_launch(transaction_id, command, 30000)
            result["session_token"] = token
            while True:
                state = json.loads(await session.call_get_state())
                if state.get("launch_token") != token and state.get("lifecycle") == "shell":
                    last = state.get("last_result") or {}
                    if last.get("token") == token:
                        outcome = str(last.get("outcome", "failed"))
                        return "cancelled" if outcome == "cancelled" else ("success" if outcome == "success" else "failed")
                await asyncio.sleep(0.1)
        finally:
            bus.disconnect()

    @staticmethod
    def _prepare_remote_files(interpreter, local: dict[str, str], *, status=None) -> None:
        """Use Lutris's Downloader for recipe URLs without creating GTK widgets."""
        from lutris.util.downloader import Downloader

        for installer_file in interpreter.installer.files:
            if installer_file.id in local:
                continue
            if installer_file.url.casefold().startswith("n/a"):
                raise LutrisAdapterError(f"local Lutris file is not mapped: {installer_file.id}")
            if isinstance(installer_file._file_meta, dict) and not installer_file._file_meta.get("filename"):
                installer_file._file_meta["filename"] = Path(urlparse(installer_file.url).path).name or installer_file.id
            installer_file.prepare()
            destination = Path(installer_file.dest_file)
            temporary = Path(installer_file.download_file)
            destination.parent.mkdir(parents=True, exist_ok=True)
            if not destination.is_file() or destination.stat().st_size == 0:
                if status:
                    status(f"Downloading {installer_file.id}")
                downloader = Downloader(installer_file.url, str(temporary), referer=installer_file.referer)
                downloader.start()
                downloader.join()
                temporary.replace(destination)
            installer_file.check_hash()
            interpreter.game_files[installer_file.id] = str(destination)

    def output_script(self, game_slug: str, destination: Path) -> Path:
        destination.parent.mkdir(parents=True, exist_ok=True)
        try:
            import gi
            gi.require_version("Gtk", "3.0")
            from lutris.database.games import get_game_by_field
            from lutris.game import Game

            row = get_game_by_field(game_slug, "slug")
            if not row and str(game_slug).isdigit():
                row = get_game_by_field(int(game_slug), "id")
            if not row:
                raise LutrisAdapterError("Lutris game registration is unavailable")

            class Delegate:
                def select_game_launch_config(self, _game):
                    return {}

            # This is Lutris's own script exporter, without starting the
            # Lutris GTK application or parsing its generated shell text.
            Game(row["id"]).write_script(str(destination), Delegate())
        except LutrisAdapterError:
            raise
        except Exception as error:
            raise LutrisAdapterError("Lutris could not generate a launch script") from error
        destination.chmod(destination.stat().st_mode | 0o100)
        return destination

    def uninstall(self, lutris_id: str, *, delete_files: bool = False) -> dict[str, str]:
        try:
            import gi
            gi.require_version("Gtk", "3.0")
            from lutris.database.games import get_game_by_field
            from lutris.game import Game
            row = (get_game_by_field(int(lutris_id), "id") if str(lutris_id).isdecimal()
                   else get_game_by_field(str(lutris_id), "slug"))
            if not row:
                raise LutrisAdapterError("Lutris game registration is unavailable")
            game = Game(row["id"])
            directory = str(game.directory or "")
            slug = str(game.slug or "")
            game.uninstall(delete_files=delete_files)
            return {"directory": directory, "slug": slug}
        except Exception as error:
            raise LutrisAdapterError("Lutris uninstall failed") from error
