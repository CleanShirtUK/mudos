"""Eden Nintendo Switch provider and deterministic controller configuration."""

from pathlib import Path
import json
import os

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
            if not guid:
                raise ValueError(f"missing live SDL GUID for player {player}")
            prefix = f'engine:sdl,port:{index},guid:{guid}'
            sections.append(f"player_{config_player}_type=0")
            sections.append(f"player_{config_player}_connected\\default=false")
            sections.append(f"player_{config_player}_connected=true")
            for name, button in buttons.items():
                key = name
                sections.append(f'player_{config_player}_button_{key}="{prefix},button:{button}"')
            for name, axis in _AXES.items():
                sections.append(f'player_{config_player}_button_{name}="{prefix},axis:{axis},threshold:0.5,invert:+"')
            for key, direction in _DPAD.items():
                sections.append(
                    f'player_{config_player}_button_{key}="{prefix},hat:0,direction:{direction}"'
                )
            sections.extend([
                f'player_{config_player}_lstick="{prefix},axis_x:0,axis_y:1,invert_x:+,invert_y:+"',
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
        """Project canonical Mudos keys/firmware into Eden's required user-data layout.

        Eden resolves these locations below its user-data root and has no
        portable path setting for the keys directory. Symlinks preserve the
        canonical Mudos files without duplicating sensitive/system material.
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
        if firmware_directory.is_dir():
            registered = nand_directory / "system" / "Contents" / "registered"
            for source in sorted(firmware_directory.iterdir()):
                if source.is_file():
                    targets.append((f"firmware/{source.name}", registered / source.name, source))

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

        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = manifest_path.with_name(f".{manifest_path.name}.{os.getpid()}.tmp")
        temporary.write_text(json.dumps(projected, sort_keys=True) + "\n", encoding="utf-8")
        temporary.replace(manifest_path)
        return tuple(destination for _, destination, _ in targets)

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
