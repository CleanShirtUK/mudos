"""Eden Nintendo Switch provider and deterministic controller configuration."""

from pathlib import Path
import os


DEFAULT_XBOX360_GUID = "030000005e0400008e02000014010000"

# SDL's standard gamepad order. Eden's SDL backend consumes these values in
# the serialized input parameter packages.
_BUTTONS = {
    "a": 1,
    "b": 0,
    "x": 3,
    "y": 2,
    "l": 9,
    "r": 10,
    "minus": 4,
    "plus": 6,
    "lstick": 7,
    "rstick": 8,
    "dpad_up": 11,
    "dpad_down": 12,
    "dpad_left": 13,
    "dpad_right": 14,
}
_AXES = {"zl": 4, "zr": 5}


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

    def ensure_controller_config(self, player_count: int = 4) -> Path:
        if player_count not in range(1, 5):
            raise ValueError("player_count must be between 1 and 4")
        guid = os.environ.get("LULU_SWITCH_SDL_GUID", DEFAULT_XBOX360_GUID)
        sections = ["[Controls]"]
        for player in range(1, player_count + 1):
            prefix = f'engine:sdl,guid:{guid},port:{player - 1}'
            sections.append(f"player_{player}_type=0")
            sections.append(f"player_{player}_connect=1")
            for name, button in _BUTTONS.items():
                key = name.replace("_", "")
                sections.append(f'player_{player}_button_{key}="{prefix},button:{button}"')
            for name, axis in _AXES.items():
                sections.append(f'player_{player}_button_{name}="{prefix},axis:{axis},threshold:0.5,invert:+"')
            sections.extend([
                f'player_{player}_analog_left="{prefix},axis_x:0,axis_y:1,invert_x:+,invert_y:+"',
                f'player_{player}_analog_right="{prefix},axis_x:2,axis_y:3,invert_x:+,invert_y:+"',
            ])
        content = "\n".join(sections) + "\n"
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.config_path.exists() or self.config_path.read_text(encoding="utf-8") != content:
            self.config_path.write_text(content, encoding="utf-8")
        return self.config_path

    def launch_arguments(self, content_path: str, player_count: int = 4) -> tuple[str, ...]:
        config = self.ensure_controller_config(player_count)
        return (
            "--appimage-extract-and-run",
            "--config", str(config), "--fullscreen", "--game", content_path,
        )
