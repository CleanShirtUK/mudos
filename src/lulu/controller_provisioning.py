"""Native controller profiles for local emulator providers."""

from pathlib import Path
import os

from .paths import PATHS
from .controller_policy import nintendo_face_binding


DEFAULT_CONTROLLER_NAME = "SDL Gamepad"


def _identity(controller: object | None, index: int) -> tuple[str, int]:
    getter = controller.get if isinstance(controller, dict) else lambda key, default=None: getattr(controller, key, default)
    name = getter("sdl_name") or DEFAULT_CONTROLLER_NAME
    value = getter("sdl_index")
    return str(name), value if isinstance(value, int) else index


def _replace_section(text: str, section: str, values: dict[str, str]) -> str:
    """Replace one INI section while leaving all other sections untouched."""
    lines = text.splitlines()
    header = f"[{section}]"
    start = next((index for index, line in enumerate(lines) if line == header), None)
    rendered = [header, *(f"{key} = {value}" for key, value in values.items())]
    if start is None:
        if lines and lines[-1] != "":
            lines.append("")
        lines.extend(rendered)
    else:
        end = next(
            (index for index in range(start + 1, len(lines)) if lines[index].startswith("[")),
            len(lines),
        )
        separator = [""] if end > start + 1 and lines[end - 1] == "" else []
        lines[start:end] = [*rendered, *separator]
    return "\n".join(lines) + "\n"


def _update_section_values(text: str, section: str, values: dict[str, str]) -> str:
    """Update selected INI keys without discarding unrelated settings."""
    lines = text.splitlines()
    header = f"[{section}]"
    start = next((index for index, line in enumerate(lines) if line == header), None)
    if start is None:
        if lines and lines[-1] != "":
            lines.append("")
        lines.extend([header, *(f"{key} = {value}" for key, value in values.items())])
        return "\n".join(lines) + "\n"

    end = next(
        (index for index in range(start + 1, len(lines)) if lines[index].startswith("[")),
        len(lines),
    )
    remaining = dict(values)
    updated = []
    for line in lines[start + 1 : end]:
        key = line.split("=", 1)[0].strip() if "=" in line else None
        if key in remaining:
            updated.append(f"{key} = {remaining.pop(key)}")
        else:
            updated.append(line)
    updated.extend(f"{key} = {value}" for key, value in remaining.items())
    lines[start + 1 : end] = updated
    return "\n".join(lines) + "\n"


def _remove_section(text: str, section: str) -> str:
    """Remove one generated INI section while leaving other profiles intact."""
    lines = text.splitlines()
    header = f"[{section}]"
    start = next((index for index, line in enumerate(lines) if line == header), None)
    if start is None:
        return text
    end = next(
        (index for index in range(start + 1, len(lines)) if lines[index].startswith("[")),
        len(lines),
    )
    del lines[start:end]
    while start < len(lines) and lines[start] == "":
        del lines[start]
    return "\n".join(lines) + ("\n" if lines else "")


def _write_if_changed(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_text(encoding="utf-8") == content:
        return
    path.write_text(content, encoding="utf-8")


def _pcsx2_values(sdl_player: int) -> dict[str, str]:
    device = f"SDL-{sdl_player}"
    return {
        "Type": "DualShock2",
        "InvertL": "0",
        "InvertR": "0",
        "Deadzone": "0",
        "AxisScale": "1.33",
        "LargeMotorScale": "1",
        "SmallMotorScale": "1",
        "ButtonDeadzone": "0",
        "PressureModifier": "0.5",
        "Up": f"{device}/DPadDown",
        "Right": f"{device}/DPadLeft",
        "Down": f"{device}/DPadUp",
        "Left": f"{device}/DPadRight",
        "Triangle": f"{device}/FaceNorth",
        "Circle": f"{device}/FaceEast",
        "Cross": f"{device}/FaceSouth",
        "Square": f"{device}/FaceWest",
        "Select": f"{device}/Back",
        "Start": f"{device}/Start",
        "L1": f"{device}/LeftShoulder",
        "L2": f"{device}/+LeftTrigger",
        "R1": f"{device}/RightShoulder",
        "R2": f"{device}/+RightTrigger",
        "L3": f"{device}/LeftStick",
        "R3": f"{device}/RightStick",
        "LUp": f"{device}/-LeftY",
        "LRight": f"{device}/+LeftX",
        "LDown": f"{device}/+LeftY",
        "LLeft": f"{device}/-LeftX",
        "RUp": f"{device}/-RightY",
        "RRight": f"{device}/+RightX",
        "RDown": f"{device}/+RightY",
        "RLeft": f"{device}/-RightX",
    }


def _dolphin_values(device: str, sdl_index: int) -> dict[str, str]:
    prefix = f"SDL/{sdl_index}/{device}"
    return {
        "Device": prefix,
        # Match Dolphin's installed "SDL Gamepad (Stock)" profile.
        "Buttons/A": f"`{nintendo_face_binding('a')}`",
        "Buttons/B": f"`{nintendo_face_binding('b')}`",
        "Buttons/X": f"`{nintendo_face_binding('x')}`",
        "Buttons/Y": f"`{nintendo_face_binding('y')}`",
        "Buttons/Z": "`Shoulder R`",
        "Buttons/Start": "`Start`",
        "Main Stick/Up": "`Left Y+`",
        "Main Stick/Down": "`Left Y-`",
        "Main Stick/Left": "`Left X-`",
        "Main Stick/Right": "`Left X+`",
        "Main Stick/Calibration": "100.00",
        "C-Stick/Up": "`Right Y+`",
        "C-Stick/Down": "`Right Y-`",
        "C-Stick/Left": "`Right X-`",
        "C-Stick/Right": "`Right X+`",
        "C-Stick/Calibration": "100.00",
        "Triggers/L": "`Trigger L`",
        "Triggers/R": "`Trigger R`",
        "Triggers/L-Analog": "`Trigger L`",
        "Triggers/R-Analog": "`Trigger R`",
        "D-Pad/Up": "`Pad N`",
        "D-Pad/Down": "`Pad S`",
        "D-Pad/Left": "`Pad W`",
        "D-Pad/Right": "`Pad E`",
        "Rumble/Motor": "`Motor L` | `Motor R`",
    }


def _dolphin_classic_values(device: str, sdl_index: int) -> dict[str, str]:
    prefix = f"SDL/{sdl_index}/{device}"
    return {
        "Device": prefix,
        "Extension": "Classic Controller",
        "Classic/Buttons/A": f"`{nintendo_face_binding('a')}`",
        "Classic/Buttons/B": f"`{nintendo_face_binding('b')}`",
        "Classic/Buttons/X": f"`{nintendo_face_binding('x')}`",
        "Classic/Buttons/Y": f"`{nintendo_face_binding('y')}`",
        "Classic/Buttons/ZL": "`Left Shoulder`",
        "Classic/Buttons/ZR": "`Right Shoulder`",
        "Classic/Buttons/-": "`Back`",
        "Classic/Buttons/+": "`Start`",
        "Classic/Buttons/Home": "`Guide`",
        "Classic/Left Stick/Up": "`Left Y+`",
        "Classic/Left Stick/Down": "`Left Y-`",
        "Classic/Left Stick/Left": "`Left X-`",
        "Classic/Left Stick/Right": "`Left X+`",
        "Classic/Left Stick/Calibration": "100.00",
        "Classic/Right Stick/Up": "`Right Y+`",
        "Classic/Right Stick/Down": "`Right Y-`",
        "Classic/Right Stick/Left": "`Right X-`",
        "Classic/Right Stick/Right": "`Right X+`",
        "Classic/Right Stick/Calibration": "100.00",
        "Classic/Triggers/L": "`Left Trigger`",
        "Classic/Triggers/R": "`Right Trigger`",
        "Classic/Triggers/L-Analog": "`Left Trigger`",
        "Classic/Triggers/R-Analog": "`Right Trigger`",
        "Classic/D-Pad/Up": "`Pad N`",
        "Classic/D-Pad/Down": "`Pad S`",
        "Classic/D-Pad/Left": "`Pad W`",
        "Classic/D-Pad/Right": "`Pad E`",
    }


def _config_root() -> Path:
    return Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))).expanduser()


def ensure_provider_controller_config(
    provider: str,
    config_root: Path | None = None,
    player_count: int | None = None,
    device_indices: dict[int, int] | None = None,
    native_user_root: Path | None = None,
    controller_identities: dict[int, object] | None = None,
) -> Path:
    """Provision native profiles for the active logical player slots."""
    if player_count is None:
        player_count = 2 if provider == "pcsx2" else 4
    if player_count not in range(1, 5):
        raise ValueError("player_count must be between 1 and 4")
    device_indices = device_indices or {player: player - 1 for player in range(1, player_count + 1)}
    root = config_root or _config_root()
    if provider == "pcsx2":
        path = root / "PCSX2" / "inis" / "PCSX2.ini"
        source = path.read_text(encoding="utf-8") if path.exists() else ""
        source = _update_section_values(
            source,
            "Folders",
            {"Bios": str(PATHS.bios_root / "ps2")},
        )
        source = _update_section_values(
            source,
            "UI",
            {
                "ConfirmShutdown": "false",
                "StartFullscreen": "true",
                "StartBigPictureMode": "false",
                "OpenPauseMenu": "Keyboard/F12",
            },
        )
        for player in range(1, min(player_count, 2) + 1):
            source = _replace_section(
                source,
                f"Pad{player}",
                _pcsx2_values(device_indices.get(player, player - 1)),
            )
        _write_if_changed(path, source)
        return path
    if provider == "dolphin":
        # Dolphin 5.x resolves --user/<root> native settings under Config/.
        dolphin_root = (native_user_root or (root / "dolphin-emu")) / "Config"
        path = dolphin_root / "GCPadNew.ini"
        source = path.read_text(encoding="utf-8") if path.exists() else ""
        for player in range(1, player_count + 1):
            source = _replace_section(
                source,
                f"GCPad{player}",
                _dolphin_values(
                    *_identity((controller_identities or {}).get(player), device_indices.get(player, player - 1)),
                ),
            )
        _write_if_changed(path, source)
        wiimote_path = dolphin_root / "WiimoteNew.ini"
        wiimote_source = wiimote_path.read_text(encoding="utf-8") if wiimote_path.exists() else ""
        wiimote_source = _replace_section(
            wiimote_source, "Wiimote1", _dolphin_classic_values(
                *_identity((controller_identities or {}).get(1), device_indices.get(1, 0)),
            ),
        )
        _write_if_changed(wiimote_path, wiimote_source)
        dolphin_path = dolphin_root / "Dolphin.ini"
        dolphin_source = dolphin_path.read_text(encoding="utf-8") if dolphin_path.exists() else ""
        sidevices = {f"SIDevice{port}": "6" if port < player_count else "0" for port in range(4)}
        # Emulate a Wii Remote with a Classic Controller extension; a real
        # Bluetooth Wii Remote is deliberately not required.
        sidevices["WiimoteSource0"] = "1"
        dolphin_source = _update_section_values(
            dolphin_source, "Interface", {"ConfirmStop": "false"},
        )
        _write_if_changed(
            dolphin_path,
            _update_section_values(dolphin_source, "Core", sidevices),
        )
        return path
    raise ValueError(f"unsupported controller provider: {provider}")
