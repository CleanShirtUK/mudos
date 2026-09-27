"""Small command adapter for the documented InputPlumber D-Bus API."""

from dataclasses import dataclass
import hashlib
import logging
from pathlib import Path
import re
import subprocess
import ctypes

from .contracts import InputMode


DEFAULT_PROFILE_PATH = "/usr/share/inputplumber/profiles/default.yaml"
LOGGER = logging.getLogger("lulu.inputplumber")


def sdl_gamepad_inventory() -> list[dict[str, object]]:
    """Return current SDL gamepad connection identities, when SDL is available."""
    try:
        library = ctypes.CDLL("libSDL3.so")
        library.SDL_Init.argtypes = [ctypes.c_uint32]
        library.SDL_Init.restype = ctypes.c_bool
        library.SDL_GetGamepads.argtypes = [ctypes.POINTER(ctypes.c_int)]
        library.SDL_GetGamepads.restype = ctypes.POINTER(ctypes.c_uint32)
        library.SDL_GetGamepadNameForID.argtypes = [ctypes.c_uint32]
        library.SDL_GetGamepadNameForID.restype = ctypes.c_char_p
        library.SDL_GetGamepadPathForID.argtypes = [ctypes.c_uint32]
        library.SDL_GetGamepadPathForID.restype = ctypes.c_char_p

        class SDLGuid(ctypes.Structure):
            _fields_ = [("data", ctypes.c_ubyte * 16)]

        library.SDL_GetGamepadGUIDForID.argtypes = [ctypes.c_uint32]
        library.SDL_GetGamepadGUIDForID.restype = SDLGuid
        library.SDL_GUIDToString.argtypes = [SDLGuid, ctypes.c_char_p, ctypes.c_int]
        library.SDL_free.argtypes = [ctypes.c_void_p]
        library.SDL_free.restype = None
        library.SDL_QuitSubSystem.argtypes = [ctypes.c_uint32]
        if not library.SDL_Init(0x2000):
            return []
        count = ctypes.c_int()
        ids = library.SDL_GetGamepads(ctypes.byref(count))
        if not ids:
            library.SDL_QuitSubSystem(0x2000)
            return []
        result: list[dict[str, object]] = []
        try:
            for index in range(count.value):
                instance_id = ids[index]
                guid_buffer = ctypes.create_string_buffer(33)
                library.SDL_GUIDToString(library.SDL_GetGamepadGUIDForID(instance_id), guid_buffer, 33)
                name = library.SDL_GetGamepadNameForID(instance_id) or b""
                path = library.SDL_GetGamepadPathForID(instance_id) or b""
                path_text = path.decode("utf-8", errors="replace")
                udev_properties: set[str] = set()
                if path_text:
                    properties = subprocess.run(
                        ["udevadm", "info", "--query=property", "--name", path_text],
                        check=False, capture_output=True, text=True,
                    )
                    udev_properties = set(properties.stdout.splitlines())
                result.append({
                    "sdl_index": index,
                    "sdl_instance_id": int(instance_id),
                    "sdl_guid": guid_buffer.value.decode("ascii"),
                    "sdl_name": name.decode("utf-8", errors="replace"),
                    "sdl_path": path_text,
                    "inputplumber_target": "ID_INPUT_WIDTH_MM=65535" in udev_properties,
                })
        finally:
            if ids:
                library.SDL_free(ids)
            library.SDL_QuitSubSystem(0x2000)
        return result
    except (OSError, AttributeError, RuntimeError, ValueError):
        LOGGER.warning("SDL gamepad inventory unavailable", exc_info=True)
        return []


def associate_sdl_targets(
    runtime_targets: list[tuple[str, str]],
    sdl_devices: list[dict[str, object]],
) -> dict[str, int]:
    """Align ordered InputPlumber composites only with their virtual SDL pads.

    SDL can enumerate an un-intercepted physical controller between two
    InputPlumber outputs. Target suffixes and raw SDL indices are different
    namespaces; filter by the udev virtual-target marker, then align the live
    ordered sets. If either side is incomplete, refuse a guessed association.
    """
    virtual_devices = sorted(
        (device for device in sdl_devices if device.get("inputplumber_target") is True),
        key=lambda device: int(device.get("sdl_index", -1)),
    )
    if len(virtual_devices) != len(runtime_targets):
        return {}
    return {
        runtime_id: int(device["sdl_index"])
        for (runtime_id, _target_path), device in zip(runtime_targets, virtual_devices)
        if isinstance(device.get("sdl_index"), int)
    }


def normalized_controller_identity(persistent_id: str, sysfs_device_path: str,
                                   has_device_serial: bool,
                                   device_unique: str | None = None) -> str:
    """Keep stable unique IDs; disambiguate serial-less receiver slots."""
    # Bluetooth input devices expose their stable peer address as UniqueId,
    # but do not have a USB serial/interface path. Hashing the transient UHID
    # sysfs path would change controller identity on every reconnect.
    if has_device_serial or re.fullmatch(r"(?:[0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}", persistent_id):
        return persistent_id
    unique = (device_unique or "").strip()
    if unique:
        return f"{persistent_id}@{hashlib.sha256(unique.encode()).hexdigest()[:16]}"
    path = Path(sysfs_device_path)
    interface = next((parent for parent in (path, *path.parents)
                      if (parent / "bInterfaceNumber").is_file()), None)
    logical_path = str(interface or path)
    logical_path = re.sub(r"/input/input\d+(?:/event\d+)?$", "", logical_path)
    digest = hashlib.sha256(logical_path.encode()).hexdigest()[:16]
    return f"{persistent_id}@{digest}"

@dataclass(frozen=True, slots=True)
class InputPlumberClient:
    """controllerd-side client; InputPlumber remains runtime authority."""

    object_path: str
    profile_paths: dict[InputMode, Path]
    busctl: str = "busctl"

    def load_mode(
        self,
        mode: InputMode,
        object_path: str | None = None,
        *,
        execute: bool = True,
    ) -> list[str]:
        object_path = object_path or self.object_path
        command = [
            self.busctl,
            "call",
            "org.shadowblip.InputPlumber",
            object_path,
            "org.shadowblip.Input.CompositeDevice",
            "LoadProfilePath",
            "s",
            str(self.profile_paths[mode]),
        ]
        if execute:
            tree = subprocess.run(
                [self.busctl, "tree", "org.shadowblip.InputPlumber"],
                check=True,
                capture_output=True,
                text=True,
            ).stdout
            if object_path not in tree:
                return command
            subprocess.run(command, check=True)
        return command

    def set_intercept_mode(
        self,
        mode: int,
        object_path: str | None = None,
        *,
        execute: bool = True,
    ) -> list[str]:
        if mode not in range(4):
            raise ValueError("InputPlumber InterceptMode must be between 0 and 3")
        object_path = object_path or self.object_path
        command = [
            self.busctl,
            "set-property",
            "org.shadowblip.InputPlumber",
            object_path,
            "org.shadowblip.Input.CompositeDevice",
            "InterceptMode",
            "u",
            str(mode),
        ]
        if execute:
            subprocess.run(command, check=True)
        return command

    def ensure_default_intercept(
        self, object_path: str | None = None, *, execute: bool = True
    ) -> list[list[str]]:
        """Restore the controller baseline for one live composite."""
        object_path = object_path or self.object_path
        load_command = [
            self.busctl, "call", "org.shadowblip.InputPlumber", object_path,
            "org.shadowblip.Input.CompositeDevice", "LoadProfilePath", "s",
            DEFAULT_PROFILE_PATH,
        ]
        mode_command = self.set_intercept_mode(1, object_path, execute=False)
        if not execute:
            return [load_command, mode_command]
        profile_path = Path(DEFAULT_PROFILE_PATH)
        profile_exists = profile_path.is_file()
        properties = {}
        for name in ("ProfilePath", "InterceptMode"):
            result = subprocess.run(
                [self.busctl, "get-property", "org.shadowblip.InputPlumber", object_path,
                 "org.shadowblip.Input.CompositeDevice", name],
                check=True, capture_output=True, text=True,
            )
            properties[name] = result.stdout.strip()
        if not profile_exists:
            LOGGER.error("InputPlumber default profile is missing: %s", DEFAULT_PROFILE_PATH)
            raise FileNotFoundError(DEFAULT_PROFILE_PATH)
        if properties["ProfilePath"] == f's "{DEFAULT_PROFILE_PATH}"' and properties["InterceptMode"] == "u 1":
            return []
        try:
            result = subprocess.run(load_command, check=True, capture_output=True, text=True)
        except subprocess.CalledProcessError as error:
            LOGGER.error(
                "InputPlumber LoadProfilePath failed object=%s rc=%s stdout=%r stderr=%r",
                object_path, error.returncode, error.stdout, error.stderr,
            )
            raise
        subprocess.run(mode_command, check=True)
        profile = subprocess.run(
            [self.busctl, "get-property", "org.shadowblip.InputPlumber", object_path,
             "org.shadowblip.Input.CompositeDevice", "ProfileName"],
            check=True, capture_output=True, text=True,
        ).stdout.strip()
        intercept = subprocess.run(
            [self.busctl, "get-property", "org.shadowblip.InputPlumber", object_path,
             "org.shadowblip.Input.CompositeDevice", "InterceptMode"],
            check=True, capture_output=True, text=True,
        ).stdout.strip()
        if profile != 's "Default"' or intercept != "u 1":
            raise RuntimeError(
                f"InputPlumber baseline verification failed: profile={profile!r} mode={intercept!r}"
            )
        return [load_command, mode_command]

    def composite_status(
        self, object_path: str | None = None, *, execute: bool = True
    ) -> tuple[str, tuple[str, ...]]:
        """Read one runtime composite identity and source paths."""
        object_path = object_path or self.object_path
        base = [
            self.busctl,
            "get-property",
            "org.shadowblip.InputPlumber",
            object_path,
            "org.shadowblip.Input.CompositeDevice",
        ]
        if not execute:
            return "", ()
        identity = subprocess.run(
            [*base, "PersistentId"], check=True, capture_output=True, text=True
        ).stdout
        sources = subprocess.run(
            [*base, "SourceDevicePaths"], check=True, capture_output=True, text=True
        ).stdout
        identity_values = re.findall(r'"([^"]*)"', identity)
        source_values = tuple(re.findall(r'"([^"]*)"', sources))
        return (identity_values[0] if identity_values else ""), source_values

    def runtime_composite_statuses(
        self, *, execute: bool = True
    ) -> dict[str, tuple[str, tuple[str, ...]]]:
        """Read the manager's current runtime composite topology."""
        if not execute:
            return {}
        tree = subprocess.run(
            [
                self.busctl,
                "tree",
                "org.shadowblip.InputPlumber",
            ],
            check=True,
            capture_output=True,
            text=True,
        ).stdout
        paths = list(self.gamepad_order())
        if not paths:
            paths = sorted(
                set(
                    re.findall(
                        r"(/org/shadowblip/InputPlumber/CompositeDevice\d+)", tree
                    )
                )
            )
        composites = {path: self.composite_status(path) for path in paths}
        if composites:
            normalized = {}
            for runtime_path, (persistent_id, source_paths) in composites.items():
                identity = persistent_id
                if source_paths:
                    source = Path(source_paths[0]).name
                    device_path = Path("/sys/class/input") / source / "device"
                    try:
                        sysfs_path = str(device_path.resolve(strict=True))
                        interface = next((parent for parent in (Path(sysfs_path), *Path(sysfs_path).parents)
                                          if (parent / "bInterfaceNumber").is_file()), None)
                        serial_path = interface.parent / "serial" if interface else None
                        has_serial = bool(serial_path and serial_path.is_file()
                                          and serial_path.read_text(errors="replace").strip())
                        unique_path = Path(sysfs_path) / "uniq"
                        if not unique_path.is_file():
                            unique_path = device_path / "uniq"
                        device_unique = (unique_path.read_text(errors="replace").strip()
                                         if unique_path.is_file() else "")
                        identity = normalized_controller_identity(
                            persistent_id, sysfs_path, has_serial, device_unique,
                        )
                    except OSError:
                        pass
                normalized[runtime_path] = (identity, source_paths)
            return normalized
        # Retain the existing provisional inventory path for a source exposed
        # before InputPlumber's composite order has converged.
        source = self._source_gamepad_path()
        if source:
            return {
                "/org/shadowblip/InputPlumber/CompositeDevice0":
                    (f"source:{source.rsplit('/', 1)[-1]}", (source,))
            }
        return {}

    def _source_gamepad_path(self, *, execute: bool = True) -> str | None:
        """Find a live joystick source with standard gamepad capabilities."""
        if not execute:
            return None
        tree = subprocess.run(
            [self.busctl, "tree", "org.shadowblip.InputPlumber"],
            check=True, capture_output=True, text=True,
        ).stdout
        sources = sorted(set(re.findall(
            r"(/org/shadowblip/InputPlumber/devices/source/event\d+)", tree
        )))
        for source in sources:
            device_class = subprocess.run(
                [self.busctl, "get-property", "org.shadowblip.InputPlumber", source,
                 "org.shadowblip.Input.Source.EventDevice", "DeviceClass"],
                check=True, capture_output=True, text=True,
            ).stdout
            if '"joystick"' not in device_class:
                continue
            axes = subprocess.run(
                [self.busctl, "get-property", "org.shadowblip.InputPlumber", source,
                 "org.shadowblip.Input.Source.EventDevice", "SupportedAbsoluteAxes"],
                check=False, capture_output=True, text=True,
            ).stdout
            if re.search(r"\baq\s+[1-9]", axes):
                phys = subprocess.run(
                    [self.busctl, "get-property", "org.shadowblip.InputPlumber", source,
                     "org.shadowblip.Input.Source.EventDevice", "PhysPath"],
                    check=False, capture_output=True, text=True,
                ).stdout
                if 's ""' not in phys and 'virtual/' not in phys:
                    return source
        return None

    def gamepad_order(self, *, execute: bool = True) -> tuple[str, ...]:
        """Return InputPlumber's current ordered composite handles."""
        if not execute:
            return ()
        result = subprocess.run(
            [
                self.busctl,
                "get-property",
                "org.shadowblip.InputPlumber",
                "/org/shadowblip/InputPlumber/Manager",
                "org.shadowblip.InputManager",
                "GamepadOrder",
            ],
            check=True,
            capture_output=True,
            text=True,
        ).stdout
        ordered = list(re.findall(r'"(/org/shadowblip/InputPlumber/CompositeDevice\d+)"', result))
        # During startup InputPlumber can publish composites before its
        # GamepadOrder property has converged. Preserve its order, but do not
        # discard live composites omitted by that transient property state.
        tree = subprocess.run(
            [self.busctl, "tree", "org.shadowblip.InputPlumber"],
            check=True, capture_output=True, text=True,
        ).stdout
        for path in sorted(set(re.findall(
                r"(/org/shadowblip/InputPlumber/CompositeDevice\d+)", tree))):
            if path not in ordered:
                ordered.append(path)
        return tuple(ordered)

    def runtime_gamepad_slots(
        self,
        sdl_devices: list[dict[str, object]] | None = None,
        *,
        execute: bool = True,
    ) -> list[tuple[str, str, int]]:
        """Return ordered runtime handles and their current gamepad target indices."""
        if not execute:
            return []
        runtime_paths = self.gamepad_order()
        if not runtime_paths:
            return []
        runtime_targets: list[tuple[str, str, str]] = []
        for runtime_path in runtime_paths:
            persistent_id, source_paths = self.composite_status(runtime_path)
            if not source_paths:
                continue
            targets = subprocess.run(
                [
                    self.busctl,
                    "get-property",
                    "org.shadowblip.InputPlumber",
                    runtime_path,
                    "org.shadowblip.Input.CompositeDevice",
                    "TargetDevices",
                ],
                check=True,
                capture_output=True,
                text=True,
            ).stdout
            gamepad_targets = re.findall(
                r'"(/org/shadowblip/InputPlumber/devices/target/gamepad\d+)"', targets
            )
            if len(gamepad_targets) != 1:
                continue
            runtime_targets.append((runtime_path, persistent_id, gamepad_targets[0]))
        inventory = sdl_devices if sdl_devices is not None else sdl_gamepad_inventory()
        indices = associate_sdl_targets(
            [(runtime_id, target_path) for runtime_id, _persistent_id, target_path in runtime_targets],
            inventory,
        )
        return [
            (runtime_id, persistent_id, indices[runtime_id])
            for runtime_id, persistent_id, _target_path in runtime_targets
            if runtime_id in indices
        ]
