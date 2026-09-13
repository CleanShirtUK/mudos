"""Eden Nintendo Switch provider and deterministic controller configuration."""

from pathlib import Path
import os


# InputPlumber's virtual Xbox 360 target as reported by SDL2.
DEFAULT_XBOX360_GUID = "030000005e0400008e02000001000000"

# SDL's standard gamepad order. Eden's SDL backend consumes these values in
# the serialized input parameter packages.
_BUTTONS = {
    "a": 0,
    "b": 1,
    "x": 2,
    "y": 3,
    "l": 4,
    "r": 5,
    "minus": 6,
    "plus": 7,
    "lstick": 9,
    "rstick": 10,
}
_AXES = {"zl": 2, "zr": 5}
_DPAD = {"ddup": "up", "ddown": "down", "dleft": "left", "dright": "right"}


def _config_root() -> Path:
    configured = os.environ.get("LULU_SWITCH_CONFIG_ROOT")
    if configured:
        return Path(configured).expanduser()
    return Path(os.environ.get("XDG_CONFIG_HOME", "~/.config")).expanduser() / "eden"


class SwitchProvider:
    """Build Eden's direct-launch arguments and owned controller profile."""

    def __init__(self, executable: str | Path | None = None, config_root: Path | None = None) -> None:
        self.executable = str(executable or os.environ.get("LULU_EDEN", "/usr/bin/eden"))
        self.config_root = config_root or _config_root()

    @property
    def config_path(self) -> Path:
        return self.config_root / "lulu-switch.ini"

    @property
    def active_config_path(self) -> Path:
        return self.config_root / "qt-config.ini"

    def ensure_controller_config(
        self,
        player_count: int | None = None,
        device_indices: dict[int, int] | None = None,
    ) -> Path:
        if player_count is None:
            player_count = max(device_indices, default=4) if device_indices else 4
        if player_count not in range(1, 5):
            raise ValueError("player_count must be between 1 and 4")
        device_indices = device_indices or {
            player: player - 1 for player in range(1, player_count + 1)
        }
        guid = os.environ.get("LULU_SWITCH_SDL_GUID", DEFAULT_XBOX360_GUID)
        sections = ["[Controls]"]
        for player in range(1, player_count + 1):
            config_player = player - 1
            prefix = f'engine:sdl,guid:{guid},port:{device_indices.get(player, player - 1)}'
            sections.append(f"player_{config_player}_type=0")
            sections.append(f"player_{config_player}_connected\\default=false")
            sections.append(f"player_{config_player}_connected=true")
            for name, button in _BUTTONS.items():
                key = name
                sections.append(f'player_{config_player}_button_{key}="{prefix},button:{button}"')
            for name, axis in _AXES.items():
                sections.append(f'player_{config_player}_button_{name}="{prefix},axis:{axis},threshold:0.5,invert:+"')
            for key, direction in _DPAD.items():
                sections.append(f'player_{config_player}_button_{key}="{prefix},direction:{direction},hat:0"')
            sections.extend([
                f'player_{config_player}_lstick="{prefix},axis_x:0,axis_y:1,offset_x:-0.000000,offset_y:0.000000,invert_x:+,invert_y:+,deadzone:0.150000"',
                f'player_{config_player}_rstick="{prefix},axis_x:3,axis_y:4,offset_x:-0.000000,offset_y:0.000000,invert_x:+,invert_y:+,deadzone:0.150000"',
            ])
        content = "\n".join(sections) + "\n"
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.config_path.exists() or self.config_path.read_text(encoding="utf-8") != content:
            self.config_path.write_text(content, encoding="utf-8")
        self._update_active_config(content)
        return self.active_config_path

    def _update_active_config(self, profile: str) -> None:
        path = self.active_config_path
        source = path.read_text(encoding="utf-8") if path.exists() else "[Controls]\n"
        updates = {
            line.split("=", 1)[0]: line for line in profile.splitlines()[1:] if "=" in line
        }
        lines = source.splitlines()
        start = next((index for index, line in enumerate(lines) if line == "[Controls]"), None)
        if start is None:
            lines.extend(["", "[Controls]"])
            start = len(lines) - 1
        end = next((index for index in range(start + 1, len(lines)) if lines[index].startswith("[")), len(lines))
        seen = set()
        for index in range(start + 1, end):
            key = lines[index].split("=", 1)[0] if "=" in lines[index] else ""
            if key in updates:
                lines[index] = updates[key]
                seen.add(key)
        lines[end:end] = [updates[key] for key in updates if key not in seen]
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def launch_arguments(
        self,
        content_path: str,
        player_count: int | None = None,
        device_indices: dict[int, int] | None = None,
    ) -> tuple[str, ...]:
        config = self.ensure_controller_config(player_count, device_indices)
        return (
            "--appimage-extract-and-run",
            "--config", str(config), "-f", "--fullscreen", "--game", content_path,
        )
