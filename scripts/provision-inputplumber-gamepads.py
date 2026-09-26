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
import time


def _has_bit(path: Path, bit: int) -> bool:
    try:
        words = path.read_text(encoding="ascii").split()
    except OSError:
        return False
    # sysfs prints the capability bitmap most-significant word first.
    word = bit // 64
    words = list(reversed(words))
    return word < len(words) and bool(int(words[word], 16) & (1 << (bit % 64)))


def _udev_properties(event: str) -> set[str]:
    result = subprocess.run(
        ["udevadm", "info", "--query=property", "--name", f"/dev/input/{event}"],
        check=False,
        capture_output=True,
        text=True,
    )
    return set(result.stdout.splitlines())


def _is_joystick(properties: set[str]) -> bool:
    """Use udev's capability classification, including generic virtual pads."""
    return "ID_INPUT_JOYSTICK=1" in properties


def _is_virtual_source(properties: set[str]) -> bool:
    """Accept generic virtual sources while excluding composite outputs.

    InputPlumber's generated evdev targets acquire udev's tablet-like size
    properties, whereas generic uinput gamepad sources do not. This is a
    source/output distinction, not a controller identity rule, and keeps an
    output from being fed back as a new source during reconciliation.
    """
    return "ID_INPUT_WIDTH_MM=65535" not in properties


def logical_device_key(sysfs_path: str) -> str:
    """Collapse event interfaces on one Linux device without merging slots."""
    path = Path(sysfs_path)
    if "virtual" in path.parts:
        return str(path)
    return re.sub(r"/input/input\d+$", "", str(path))


def gamepad_devices() -> list[str]:
    devices: dict[str, str] = {}
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
        properties = _udev_properties(event.parent.name)
        if not has_gamepad_button or not has_axes or not _is_joystick(properties):
            continue
        # A physical source has a stable sysfs path. A generic virtual source
        # has no phys path, so retain it only while IP marks it as a source;
        # otherwise it is an output composite and would recurse forever.
        if not _is_virtual_source(properties):
            continue
        sysfs_path = event.resolve()
        # Multiple event interfaces on one Linux input device belong to a
        # single pad. Receiver slots expose separate USB interfaces, so their
        # interface parent (for example :1.0 vs :1.2) keeps them distinct.
        logical_device = logical_device_key(str(sysfs_path))
        devices.setdefault(logical_device, event.parent.name)
    return sorted(devices.values())


def render(event: str) -> str:
    return (
        "# Generated from Linux input capabilities and logical sysfs device.\n"
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
        f"      dev_node: /dev/input/{event}\n"
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


def wait_for_source_composite(source: str, probe, *, timeout: float = 12.0,
                              poll_interval: float = 0.25,
                              clock=time.monotonic, sleep=time.sleep) -> bool:
    """Wait for configured auto-management to publish a logical source.

    Calling CreateCompositeDevice as well races InputPlumber's auto-manager
    and attempts to open the same evdev node a second time, which can tear
    down composites with EBUSY. InputPlumber alone owns composite lifecycle.
    """
    deadline = clock() + timeout
    while True:
        if source in probe():
            return True
        remaining = deadline - clock()
        if remaining <= 0:
            return False
        sleep(min(poll_interval, remaining))


def _activate(output: Path, profiles: list[Path]) -> None:
    """Reconcile this generator's composites with the current source set."""
    time.sleep(0.25)  # Let udev and InputPlumber finish handling the device event.

    def composite_snapshot() -> list[set[str]]:
        tree = subprocess.run(
            ["busctl", "tree", "org.shadowblip.InputPlumber"],
            check=False, capture_output=True, text=True,
        ).stdout
        result: list[set[str]] = []
        for composite in set(re.findall(r"(/org/shadowblip/InputPlumber/CompositeDevice\d+)", tree)):
            sources = subprocess.run(
                ["busctl", "get-property", "org.shadowblip.InputPlumber", composite,
                 "org.shadowblip.Input.CompositeDevice", "SourceDevicePaths"],
                check=False, capture_output=True, text=True,
            ).stdout
            result.append(set(re.findall(r'"(/dev/input/event\d+)"', sources)))
        return result

    def active_sources() -> set[str]:
        return set().union(*composite_snapshot())

    for profile in profiles:
        content = profile.read_text(encoding="utf-8")
        event = re.search(r"dev_node: /dev/input/(event\d+)", content)
        if not event:
            continue
        source = f"/dev/input/{event.group(1)}"

        if not wait_for_source_composite(source, active_sources):
            print(f"InputPlumber did not activate logical gamepad source {source}", file=sys.stderr)


def main() -> int:
    if len(sys.argv) not in (2, 3):
        print(f"usage: {sys.argv[0]} OUTPUT", file=sys.stderr)
        return 2
    output = Path(sys.argv[1])
    output.parent.mkdir(parents=True, exist_ok=True)
    devices = gamepad_devices()
    profiles: list[Path] = []
    for index, event in enumerate(devices):
        # Keep the established filename for the first device. Additional
        # devices get independent files so each profile creates one composite.
        profile = output if index == 0 else output.parent / f"lulu-gamepad-{event}.yaml"
        _write(profile, render(event))
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
