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
    "l": 9,
    "r": 10,
    "minus": 4,
    "plus": 6,
    "lstick": 7,
    "rstick": 8,
}
_AXES = {"zl": 4, "zr": 5}
_DPAD = {"dup": "up", "ddown": "down", "dleft": "left", "dright": "right"}
EDEN_FLATPAK_ID = "dev.eden_emu.eden"


def eden_flatpak_config_root(home: Path | None = None) -> Path:
    return (home or PATHS.home) / ".var" / "app" / EDEN_FLATPAK_ID / "config" / "eden"


def eden_flatpak_data_root(home: Path | None = None) -> Path:
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
    ) -> None:
        self.executable = str(executable or os.environ.get("LULU_EDEN", "/usr/bin/eden"))
        self.config_root = config_root or _config_root()
        self.active_config_root = active_config_root or self.config_root
        self.data_root = data_root

    @property
    def config_path(self) -> Path:
        return self.config_root / "lulu-switch.ini"

    @property
    def active_config_path(self) -> Path:
        return self.active_config_root / "qt-config.ini"

    def ensure_controller_config(
        self,
        player_count: int | None = None,
        device_indices: dict[int, int] | None = None,
        controller_identities: dict[int, object] | None = None,
    ) -> Path:
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
            # Eden 0.2.x writes the SDL selector in port,guid order. The
            # parser is semantically key/value based, but matching the native
            # donor avoids relying on the older serialized ordering.
            controller = (controller_identities or {}).get(player)
            getter = controller.get if isinstance(controller, dict) else lambda key, default=None: getattr(controller, key, default)
            index = getter("sdl_index")
            index = index if isinstance(index, int) else device_indices.get(player, player - 1)
            guid = getter("sdl_guid") or os.environ.get("LULU_SWITCH_SDL_GUID")
            # Eden 0.2.1 SDL2 clears the joystick-name CRC in GUID bytes 2-3
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
        if self.data_root is not None:
            self.ensure_managed_system_files()
        return self.active_config_path

    def ensure_managed_system_files(self) -> tuple[Path, ...]:
        """Project keys and install canonical firmware into Eden's writable NAND.

        Eden 0.2.1's installer copies source NCAs by basename into
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

    def _update_active_config(self, profile: str) -> None:
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
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")

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
