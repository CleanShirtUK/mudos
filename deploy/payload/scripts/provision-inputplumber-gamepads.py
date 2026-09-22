#!/usr/bin/env python3
"""Install capability-selected InputPlumber gamepad source definitions.

InputPlumber's device schema has no capability predicate.  Select Linux
event devices here, using their advertised absolute axes and gamepad/joystick
buttons, and let InputPlumber match the resulting physical paths.
"""

from pathlib import Path
import os
import re
import subprocess
import sys


def _has_bit(path: Path, bit: int) -> bool:
    try:
        words = path.read_text(encoding="ascii").split()
    except OSError:
        return False
    # sysfs prints the capability bitmap most-significant word first.
    word = bit // 64
    words = list(reversed(words))
    return word < len(words) and bool(int(words[word], 16) & (1 << (bit % 64)))


def gamepad_devices() -> list[tuple[str, str]]:
    devices: list[tuple[str, str]] = []
    for event in sorted(Path("/sys/class/input").glob("event*/device")):
        capabilities = event / "capabilities"
        # BTN_JOYSTICK through BTN_GAMEPAD covers standard Linux gamepads;
        # axes distinguish them from ordinary button-only devices.
        has_gamepad_button = any(
            _has_bit(capabilities / "key", code)
            for code in range(288, 319)
        )
        has_axes = bool((capabilities / "abs").read_text(encoding="ascii").strip()) \
            if (capabilities / "abs").is_file() else False
        phys_file = event / "phys"
        if not has_gamepad_button or not has_axes or not phys_file.is_file():
            continue
        phys = phys_file.read_text(encoding="utf-8").strip()
        if phys:
            devices.append((event.parent.name, phys))
    return devices


def render(event: str, phys: str) -> str:
    return (
        "# Generated from Linux input capabilities; identity is intentionally not used.\n"
        "version: 1\n"
        "kind: CompositeDevice\n"
        "name: Lulu Controller\n"
        "maximum_sources: 1\n"
        "matches: []\n"
        "source_devices:\n"
        "  - group: gamepad\n"
        "    unique: true\n"
        "    evdev:\n"
        "      handler: event*\n"
        f"      dev_node: /dev/{event}\n"
        f"      phys_path: {phys!r}\n"
        "options:\n"
        "  auto_manage: true\n"
        "  persist: false\n"
        "target_devices:\n"
        "  - gamepad\n"
        "  - keyboard\n"
        "  - mouse\n"
    )


def render_empty() -> str:
    return (
        "# No physical standard gamepad is currently present.\n"
        "version: 1\n"
        "kind: CompositeDevice\n"
        "name: Lulu Controller\n"
        "maximum_sources: 1\n"
        "matches: []\n"
        "source_devices: []\n"
        "options:\n"
        "  auto_manage: true\n"
        "  persist: false\n"
        "target_devices:\n"
        "  - gamepad\n"
        "  - keyboard\n"
        "  - mouse\n"
    )


def _write(path: Path, content: str) -> bool:
    if path.exists() and path.read_text(encoding="utf-8") == content:
        return False
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(content, encoding="utf-8")
    temporary.replace(path)
    return True


def _activate(output: Path, profiles: list[Path]) -> None:
    """Create only composites that are not already represented at runtime."""
    tree = subprocess.run(
        ["busctl", "tree", "org.shadowblip.InputPlumber"],
        check=False, capture_output=True, text=True,
    ).stdout
    composites = re.findall(r"(/org/shadowblip/InputPlumber/CompositeDevice\d+)", tree)
    existing: set[str] = set()
    for composite in set(composites):
        result = subprocess.run(
            ["busctl", "get-property", "org.shadowblip.InputPlumber", composite,
             "org.shadowblip.Input.CompositeDevice", "SourceDevicePaths"],
            check=False, capture_output=True, text=True,
        ).stdout
        existing.update(re.findall(r'"(/dev/input/event\d+)"', result))
    for profile in profiles:
        content = profile.read_text(encoding="utf-8")
        event = re.search(r"dev_node: /dev/(event\d+)", content)
        if event and f"/dev/input/{event.group(1)}" in existing:
            continue
        subprocess.run(
            ["busctl", "call", "org.shadowblip.InputPlumber",
             "/org/shadowblip/InputPlumber/Manager",
             "org.shadowblip.InputManager", "CreateCompositeDevice", "s", str(profile)],
            check=False,
        )


def main() -> int:
    if len(sys.argv) not in (2, 3):
        print(f"usage: {sys.argv[0]} OUTPUT", file=sys.stderr)
        return 2
    output = Path(sys.argv[1])
    output.parent.mkdir(parents=True, exist_ok=True)
    devices = gamepad_devices()
    profiles: list[Path] = []
    for index, (event, phys) in enumerate(devices):
        # Keep the established filename for the first device. Additional
        # devices get independent files so each profile creates one composite.
        profile = output if index == 0 else output.parent / f"lulu-gamepad-{event}.yaml"
        _write(profile, render(event, phys))
        profiles.append(profile)
    for stale in output.parent.glob("lulu-gamepad-event*.yaml"):
        if stale not in profiles:
            stale.unlink()
    # Keep the historical path as the first generated profile for diagnostics
    # and compatibility with existing tooling. It is never a static wildcard.
    if profiles:
        _write(output, profiles[0].read_text(encoding="utf-8"))
    else:
        _write(output, render_empty())
    if len(sys.argv) == 3 and sys.argv[2] == "--activate":
        _activate(output, profiles)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
