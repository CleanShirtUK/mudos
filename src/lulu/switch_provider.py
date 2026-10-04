"""Eden Nintendo Switch provider and deterministic controller configuration."""

from pathlib import Path
import hashlib
import json
import os
import shutil
import re

from .paths import PATHS

# SDL's standard gamepad order. Eden's SDL backend consumes these values in
# the serialized input parameter packages.
_BUTTONS = {
    # Match Eden's previously captured native profile for the SDL buttons
    # exposed by Mudos: shoulders are SDL buttons 4/5 and Back/Start are 6/7.
    # Keep this emulator-owned; do not rewrite the shared InputPlumber layout.
    "l": 4,
    "r": 5,
    "minus": 6,
    "plus": 7,
    "lstick": 7,
    "rstick": 8,
}
_AXES = {"zl": 4, "zr": 5}
_DPAD = {"dup": "up", "ddown": "down", "dleft": "left", "dright": "right"}
EDEN_FLATPAK_ID = "dev.eden_emu.eden"  # Legacy import source only.


def eden_native_config_root(home: Path | None = None) -> Path:
    return (home / ".config" / "eden") if home is not None else PATHS.config_home / "eden"


def eden_native_data_root(home: Path | None = None) -> Path:
    return (home / ".local" / "share" / "eden") if home is not None else PATHS.data_home / "eden"


def eden_flatpak_config_root(home: Path | None = None) -> Path:
    """Read-only legacy import location retained for one-way migration."""
    return (home or PATHS.home) / ".var" / "app" / EDEN_FLATPAK_ID / "config" / "eden"


def eden_flatpak_data_root(home: Path | None = None) -> Path:
    """Read-only legacy import location retained for one-way migration."""
    return (home or PATHS.home) / ".var" / "app" / EDEN_FLATPAK_ID / "data" / "eden"


def _config_root() -> Path:
    configured = os.environ.get("LULU_SWITCH_CONFIG_ROOT")
    if configured:
        return Path(configured).expanduser()
    return PATHS.provider_config_root("eden")


class SwitchProvider:
    """Build Eden's direct-launch arguments and owned controller profile."""

    def __init__(
        self,
        executable: str | Path | None = None,
        config_root: Path | None = None,
        active_config_root: Path | None = None,
        data_root: Path | None = None,
        external_content_root: Path | None = None,
    ) -> None:
        self.executable = str(executable or os.environ.get("LULU_EDEN", "/usr/bin/eden"))
        self.config_root = config_root or _config_root()
        self.active_config_root = active_config_root or self.config_root
        self.data_root = data_root
        self.external_content_root = external_content_root or PATHS.rom_root / "switch"
        self._legacy_config_root = None
        self._legacy_data_root = None
        if (self.config_root == PATHS.provider_config_root("eden")
                and self.active_config_root == eden_native_config_root()
                and self.data_root == eden_native_data_root()):
            self._legacy_config_root = eden_flatpak_config_root()
            self._legacy_data_root = eden_flatpak_data_root()

    @property
    def config_path(self) -> Path:
        return self.config_root / "lulu-switch.ini"

    @property
    def active_config_path(self) -> Path:
        return self.active_config_root / "qt-config.ini"

    def ensure_standalone_config(self) -> Path:
        """Create the native Eden config without requiring a gamepad or ROM.

        Configure Provider is an intentional native Eden UI launch. Seed only
        first-run/data-location facts; the existing Eden settings remain owned
        by Eden and are preserved.
        """
        self.migrate_legacy_flatpak_state()
        self._update_active_config(None)
        self._ensure_native_nand_directory()
        return self.active_config_path

    def migrate_legacy_flatpak_state(self) -> None:
        """Import Eden user state without deleting or overwriting either tree.

        Config/data under the Flatpak sandbox are treated as user data. A
        destination conflict always keeps the native file; the original tree
        is retained as a recoverable source. The first-run native config is
        backed up before adopting the configured Flatpak profile.
        """
        marker = self.config_root / ".mudos-eden-migration-v1.json"
        if self._legacy_config_root is None or self._legacy_data_root is None:
            return
        if marker.is_file():
            return
        legacy_config = self._legacy_config_root
        legacy_data = self._legacy_data_root
        native_config = self.active_config_root
        native_data = self.data_root
        conflicts: list[str] = []

        old_ini = legacy_config / "qt-config.ini"
        new_ini = native_config / "qt-config.ini"
        if old_ini.is_file():
            if not new_ini.exists():
                new_ini.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(old_ini, new_ini)
            elif self._config_is_first_run(new_ini) and not self._config_is_first_run(old_ini):
                backup = self.config_root / "migration-backup" / "native-qt-config.ini"
                backup.parent.mkdir(parents=True, exist_ok=True)
                if not backup.exists():
                    shutil.copy2(new_ini, backup)
                temporary = new_ini.with_name(f".{new_ini.name}.{os.getpid()}.migration")
                shutil.copy2(old_ini, temporary)
                temporary.replace(new_ini)
            else:
                conflicts.append(str(new_ini))

        if legacy_config.is_dir():
            self._copy_tree_without_overwrite(legacy_config / "custom",
                                              native_config / "custom", conflicts)
            for name in ("window_state.ini",):
                source, destination = legacy_config / name, native_config / name
                if source.is_file():
                    self._copy_file_without_overwrite(source, destination, conflicts)
        if legacy_data.is_dir() and native_data is not None:
            # Import durable user/Eden state only. Logs, crash dumps, dump
            # workspaces, and generated icons are transient or regenerable.
            for name in ("nand", "load", "shader", "sdmc", "amiibo",
                         "play_time", "tas", "screenshots"):
                self._copy_tree_without_overwrite(legacy_data / name,
                                                  native_data / name, conflicts)

        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text(json.dumps({"schema": 1, "legacy_state_retained": True,
                                      "conflicts_preserved_native": conflicts},
                                     sort_keys=True) + "\n", encoding="utf-8")

    @staticmethod
    def _config_is_first_run(path: Path) -> bool:
        section = ""
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            value = line.strip()
            if value.startswith("[") and value.endswith("]"):
                section = value
            elif section == "[UI]" and value.startswith("firstStart="):
                return value.partition("=")[2].strip().lower() == "true"
        return False

    @classmethod
    def _copy_file_without_overwrite(cls, source: Path, destination: Path,
                                     conflicts: list[str]) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.is_symlink():
            conflicts.append(str(destination))
            return
        if destination.exists():
            if source.is_file() and destination.is_file() \
                    and cls._digest(source) == cls._digest(destination):
                return
            conflicts.append(str(destination))
            return
        temporary = destination.with_name(f".{destination.name}.{os.getpid()}.migration")
        shutil.copy2(source, temporary, follow_symlinks=False)
        temporary.replace(destination)

    @classmethod
    def _copy_tree_without_overwrite(cls, source: Path, destination: Path,
                                     conflicts: list[str]) -> None:
        if not source.is_dir():
            return
        destination.mkdir(parents=True, exist_ok=True)
        for entry in sorted(source.iterdir()):
            target = destination / entry.name
            if entry.is_symlink():
                if target.is_symlink() and os.readlink(target) == os.readlink(entry):
                    continue
                if target.exists() or target.is_symlink():
                    conflicts.append(str(target))
                    continue
                target.symlink_to(os.readlink(entry))
            elif entry.is_dir():
                cls._copy_tree_without_overwrite(entry, target, conflicts)
            elif entry.is_file():
                cls._copy_file_without_overwrite(entry, target, conflicts)

    def ensure_controller_config(
        self,
        player_count: int | None = None,
        device_indices: dict[int, int] | None = None,
        controller_identities: dict[int, object] | None = None,
    ) -> Path:
        self.migrate_legacy_flatpak_state()
        if player_count is None:
            player_count = max(device_indices, default=4) if device_indices else 4
        if player_count not in range(1, 5):
            raise ValueError("player_count must be between 1 and 4")
        device_indices = device_indices or {
            player: player - 1 for player in range(1, player_count + 1)
        }
        buttons = {"a": 0, "b": 1, "x": 2, "y": 3, **{
            name: button for name, button in _BUTTONS.items() if name not in {"a", "b", "x", "y"}
        }}
        sections = ["[Controls]"]
        # Eden enumerates port numbers within each SDL2 GUID in joystick
        # index order, not in Mudos player-assignment order.
        ports: dict[str, list[int]] = {}
        for assigned_player in range(1, player_count + 1):
            identity = (controller_identities or {}).get(assigned_player)
            get = identity.get if isinstance(identity, dict) else lambda key, default=None: getattr(identity, key, default)
            live_guid = get("sdl_guid") or os.environ.get("LULU_SWITCH_SDL_GUID")
            if not isinstance(live_guid, str) or not re.fullmatch(r"[0-9a-fA-F]{32}", live_guid):
                raise ValueError(f"missing or invalid live SDL GUID for player {assigned_player}")
            normalized = (live_guid[:4] + "0000" + live_guid[8:]).lower()
            live_index = get("sdl_index")
            live_index = live_index if isinstance(live_index, int) else device_indices.get(assigned_player, assigned_player - 1)
            ports.setdefault(normalized, []).append(live_index)
        for indices in ports.values():
            indices.sort()
        for player in range(1, player_count + 1):
            config_player = player - 1
            # Eden's SDL selector is written in port,guid order. The
            # parser is semantically key/value based, but matching the native
            # donor avoids relying on the older serialized ordering.
            controller = (controller_identities or {}).get(player)
            getter = controller.get if isinstance(controller, dict) else lambda key, default=None: getattr(controller, key, default)
            index = getter("sdl_index")
            index = index if isinstance(index, int) else device_indices.get(player, player - 1)
            guid = getter("sdl_guid") or os.environ.get("LULU_SWITCH_SDL_GUID")
            # Eden's SDL2 GUID clears the joystick-name CRC in bytes 2-3
            # and assigns ports per GUID, not by global SDL joystick index.
            guid = (guid[:4] + "0000" + guid[8:]).lower()
            port = ports[guid].index(index)
            prefix = f'engine:sdl,port:{port},guid:{guid}'
            sections.append(f"player_{config_player}_type=0")
            sections.append(f"player_{config_player}_connected\\default=false")
            sections.append(f"player_{config_player}_connected=true")
            for name, button in buttons.items():
                key = name
                sections.append(f"player_{config_player}_button_{key}\\default=false")
                sections.append(f'player_{config_player}_button_{key}="{prefix},button:{button}"')
            for name, axis in _AXES.items():
                sections.append(f"player_{config_player}_button_{name}\\default=false")
                sections.append(f'player_{config_player}_button_{name}="{prefix},axis:{axis},threshold:0.5,invert:+"')
            for key, direction in _DPAD.items():
                sections.append(f"player_{config_player}_button_{key}\\default=false")
                sections.append(
                    f'player_{config_player}_button_{key}="{prefix},hat:0,direction:{direction}"'
                )
            sections.extend([
                f"player_{config_player}_lstick\\default=false",
                f'player_{config_player}_lstick="{prefix},axis_x:0,axis_y:1,invert_x:+,invert_y:+"',
                f"player_{config_player}_rstick\\default=false",
                f'player_{config_player}_rstick="{prefix},axis_x:2,axis_y:3,invert_x:+,invert_y:+"',
            ])
        content = "\n".join(sections) + "\n"
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.config_path.exists() or self.config_path.read_text(encoding="utf-8") != content:
            self.config_path.write_text(content, encoding="utf-8")
        self._update_active_config(content)
        self._ensure_native_nand_directory()
        if self.data_root is not None:
            self.ensure_managed_system_files()
        self._ensure_external_content_directory()
        return self.active_config_path

    def _ensure_native_nand_directory(self) -> None:
        if self.data_root is None:
            return
        path = self.active_config_path
        path.parent.mkdir(parents=True, exist_ok=True)
        lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
        section = "[Data%20Storage]"
        start = next((i for i, line in enumerate(lines) if line.strip() == section), None)
        if start is None:
            lines.extend(["", section])
            start = len(lines) - 1
        end = next((i for i in range(start + 1, len(lines))
                    if lines[i].startswith("[")), len(lines))
        expected = str(self.data_root / "nand")
        indices = [i for i in range(start + 1, end)
                   if lines[i].split("=", 1)[0].strip() == "nand_directory" and "=" in lines[i]]
        if indices:
            lines[indices[-1]] = f"nand_directory={expected}"
            for index in reversed(indices[:-1]):
                del lines[index]
        else:
            lines.insert(end, f"nand_directory={expected}")
        content = "\n".join(lines) + "\n"
        if path.read_text(encoding="utf-8") != content:
            temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
            temporary.write_text(content, encoding="utf-8")
            temporary.replace(path)

    def ensure_managed_system_files(self) -> tuple[Path, ...]:
        """Project keys and install canonical firmware into Eden's writable NAND.

        Eden's firmware installer copies source NCAs by basename into
        system/Contents/registered, then rescans its content provider. Never
        expose a writable path back to the canonical firmware dump.
        """
        keys_directory = PATHS.bios_root / "switch" / "keys"
        firmware_directory = PATHS.bios_root / "switch" / "firmware"
        prod_key = keys_directory / "prod.keys"
        if not prod_key.is_file():
            raise FileNotFoundError(f"Mudos-managed Eden key is missing: {prod_key}")

        configured_nand = self._qt_value("Data%20Storage", "nand_directory")
        nand_directory = Path(configured_nand).expanduser() if configured_nand else self.data_root / "nand"
        targets: list[tuple[str, Path, Path]] = []
        for source in sorted(keys_directory.glob("*.keys")):
            targets.append((f"keys/{source.name}", self.data_root / "keys" / source.name, source))
        registered = nand_directory / "system" / "Contents" / "registered"

        manifest_path = self.config_root / ".mudos-eden-file-projection.json"
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            manifest = {}
        if not isinstance(manifest, dict):
            raise RuntimeError(f"Eden managed-file projection manifest is invalid: {manifest_path}")

        projected: dict[str, str] = {}
        for relative, destination, source in targets:
            destination.parent.mkdir(parents=True, exist_ok=True)
            source = source.resolve()
            prior_source = manifest.get(relative)
            if destination.is_symlink():
                current_target = destination.resolve()
                if current_target != source:
                    if prior_source != str(current_target):
                        raise FileExistsError(
                            f"refusing to replace unowned Eden path {destination} -> {current_target}"
                        )
                    destination.unlink()
                    destination.symlink_to(source)
            elif destination.exists():
                raise FileExistsError(f"refusing to replace existing Eden file: {destination}")
            else:
                destination.symlink_to(source)
            projected[relative] = str(source)

        self._install_firmware(firmware_directory, registered, manifest, projected)

        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = manifest_path.with_name(f".{manifest_path.name}.{os.getpid()}.tmp")
        temporary.write_text(json.dumps(projected, sort_keys=True) + "\n", encoding="utf-8")
        temporary.replace(manifest_path)
        return tuple(destination for _, destination, _ in targets)

    @staticmethod
    def _digest(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def _install_firmware(
        self, source_dir: Path, registered: Path, old: dict, projected: dict[str, str]
    ) -> None:
        if not source_dir.is_dir():
            raise FileNotFoundError(f"Mudos firmware directory is missing: {source_dir}")
        sources = sorted(source_dir.glob("*.nca"))
        if not sources or any(not source.is_file() or source.is_symlink() for source in sources):
            raise ValueError(f"invalid Mudos firmware source: {source_dir}")
        registered.mkdir(parents=True, exist_ok=True)
        desired = {source.name: (source, self._digest(source)) for source in sources}
        # Refuse to replace any unowned NAND content. Legacy projection links
        # are owned only when they still point to their recorded source.
        for entry in registered.iterdir():
            key = f"firmware/{entry.name}"
            record = old.get(key)
            if not isinstance(record, str):
                raise FileExistsError(f"unowned Eden firmware entry: {entry}")
            if entry.is_symlink():
                if str(entry.resolve()) != record:
                    raise FileExistsError(f"modified Eden firmware link: {entry}")
            elif not entry.is_file() or (
                record != f"sha256:{self._digest(entry)}"
                and (entry.name not in desired or self._digest(entry) != desired[entry.name][1])
            ):
                raise FileExistsError(f"modified Eden firmware file: {entry}")
        for name, (source, digest) in desired.items():
            destination = registered / name
            if destination.is_file() and not destination.is_symlink() and self._digest(destination) == digest:
                projected[f"firmware/{name}"] = f"sha256:{digest}"
                continue
            temporary = registered / f".{name}.{os.getpid()}.tmp"
            try:
                with source.open("rb") as input_file, temporary.open("xb") as output_file:
                    shutil.copyfileobj(input_file, output_file, 1024 * 1024)
                if self._digest(temporary) != digest:
                    raise IOError(f"firmware changed during installation: {source}")
                temporary.replace(destination)
            finally:
                temporary.unlink(missing_ok=True)
            projected[f"firmware/{name}"] = f"sha256:{digest}"
        for entry in registered.iterdir():
            if entry.name not in desired:
                entry.unlink()  # Verified against the old ownership manifest above.

    def _qt_value(self, section: str, key: str) -> str | None:
        if not self.active_config_path.is_file():
            return None
        current_section = None
        for line in self.active_config_path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped.startswith("[") and stripped.endswith("]"):
                current_section = stripped[1:-1]
            elif current_section == section and "=" in line:
                name, value = line.split("=", 1)
                if name.strip() == key:
                    return value.strip().strip('"')
        return None

    def _update_active_config(self, profile: str | None) -> None:
        path = self.active_config_path
        path.parent.mkdir(parents=True, exist_ok=True)
        source = path.read_text(encoding="utf-8") if path.exists() else "[Controls]\n"
        lines = source.splitlines()
        start = next((index for index, line in enumerate(lines) if line == "[Controls]"), None)
        if start is None:
            lines.extend(["", "[Controls]"])
            start = len(lines) - 1
        end = next((index for index in range(start + 1, len(lines)) if lines[index].startswith("[")), len(lines))
        # Replace the owned Controls section rather than merging it. A merge
        # leaves old keyboard/player slots active after a controller count or
        # identity change, allowing Eden to fall back to keyboard input.
        if profile is not None:
            lines[start:end] = profile.splitlines()
        next_section = next((index for index in range(start + 1, len(lines))
                             if lines[index].startswith("[")), len(lines))
        if next_section < len(lines) and next_section > 0 and lines[next_section - 1] != "":
            lines.insert(next_section, "")
        if "[UI]" in lines:
            ui_start = lines.index("[UI]")
            ui_end = next(
                (index for index in range(ui_start + 1, len(lines)) if lines[index].startswith("[")),
                len(lines),
            )
            for key, value in {"firstStart": "false"}.items():
                match = next((index for index in range(ui_start + 1, ui_end)
                              if lines[index].split("=", 1)[0].strip() == key
                              if "=" in lines[index]), None)
                if match is None:
                    lines.insert(ui_end, f"{key}={value}")
                    ui_end += 1
                else:
                    lines[match] = f"{key}={value}"
        else:
            lines.extend(["", "[UI]", "firstStart=false"])
        path.parent.mkdir(parents=True, exist_ok=True)
        content = "\n".join(lines) + "\n"
        if not path.is_file() or path.read_text(encoding="utf-8") != content:
            temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
            temporary.write_text(content, encoding="utf-8")
            temporary.replace(path)

    def _ensure_external_content_directory(self) -> None:
        """Add Mudos' canonical Switch root to Eden's external-content paths.

        Eden reads this QSettings array at startup and scans it for NSP/XCI
        updates and add-on content. Keep existing user-configured directories,
        append the Mudos-owned root once, and leave all acquired files read-only.
        """
        path = self.active_config_path
        path.parent.mkdir(parents=True, exist_ok=True)
        lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
        ui_start = next((index for index, line in enumerate(lines) if line == "[UI]"), None)
        if ui_start is None:
            lines.extend(["", "[UI]"])
            ui_start = len(lines) - 1
        ui_end = next(
            (index for index in range(ui_start + 1, len(lines)) if lines[index].startswith("[")),
            len(lines),
        )

        size_key = r"Paths\external_content_dirs\size"
        size_line = next(
            (index for index in range(ui_start + 1, ui_end)
             if lines[index].split("=", 1)[0].strip() == size_key and "=" in lines[index]),
            None,
        )
        if size_line is None:
            lines.insert(ui_end, f"{size_key}=0")
            size_line = ui_end
            ui_end += 1
        try:
            size = int(lines[size_line].split("=", 1)[1].strip())
        except (IndexError, ValueError) as error:
            raise ValueError(f"invalid Eden external-content array size in {path}") from error

        root = self.external_content_root.expanduser().resolve(strict=False)
        configured: list[Path] = []
        for index in range(1, size + 1):
            key = rf"Paths\external_content_dirs\{index}\path"
            value_line = next(
                (line for line in lines[ui_start + 1:ui_end]
                 if line.split("=", 1)[0].strip() == key and "=" in line),
                None,
            )
            if value_line is None:
                continue
            value = value_line.split("=", 1)[1].strip().strip('"')
            if value:
                configured.append(Path(value).expanduser().resolve(strict=False))
        if root in configured:
            return

        size += 1
        lines[size_line] = f"{size_key}={size}"
        lines.insert(ui_end, rf"Paths\external_content_dirs\{size}\path={root}")
        content = "\n".join(lines) + "\n"
        temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
        temporary.write_text(content, encoding="utf-8")
        temporary.replace(path)

    def launch_arguments(
        self,
        content_path: str,
        player_count: int | None = None,
        device_indices: dict[int, int] | None = None,
        controller_identities: dict[int, object] | None = None,
    ) -> tuple[str, ...]:
        config = self.ensure_controller_config(player_count, device_indices, controller_identities)
        return (
            "--appimage-extract-and-run",
            "--config", str(config), "-f", "--fullscreen", "--game", content_path,
        )
