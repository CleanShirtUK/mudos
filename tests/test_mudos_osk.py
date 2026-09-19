import hashlib
from pathlib import Path
import unittest


ROOT = Path(__file__).parents[1]


class MudosOskProvisioningTests(unittest.TestCase):
    def test_pinned_artifact_and_runtime_provisioning(self) -> None:
        script = (ROOT / "scripts/provision-gamepad-osk.sh").read_text()
        self.assertIn("v2.1.1", script)
        self.assertIn("9b4082f2abe8a13adbbfd7c7079b227b3ad5384a9e4ae2d1a22a19169a6287a8", script)
        self.assertIn("gamepad-osk-gamescope-overlay.patch", script)
        self.assertIn("go build -o gamepad-osk .", script)
        self.assertIn("sdl3_ttf", script)
        self.assertIn("--version", script)

    def test_payload_osk_files_are_mirrored_and_manifested(self) -> None:
        names = (
            "scripts/mudos-osk-device",
            "scripts/mudos-osk-bridge",
            "scripts/mudos-osk-service",
            "scripts/mudos-keyboard",
            "scripts/provision-gamepad-osk.sh",
            "packaging/lulu-osk@.service",
            "packaging/udev/80-lulu-osk.rules",
            "packaging/gamepad-osk-gamescope-overlay.patch",
        )
        manifest = (ROOT / "deploy/payload/manifest.sha256").read_text()
        for name in names:
            source = ROOT / name
            payload = ROOT / "deploy/payload" / name
            self.assertEqual(source.read_bytes(), payload.read_bytes(), name)
            self.assertIn(f"  {name}", manifest)
            digest = hashlib.sha256(payload.read_bytes()).hexdigest()
            self.assertIn(f"{digest}  {name}", manifest)

    def test_service_forces_x11_and_binds_to_mudos_session(self) -> None:
        service = (ROOT / "packaging/lulu-osk@.service").read_text()
        wrapper = (ROOT / "scripts/mudos-osk-service").read_text()
        self.assertIn("BindsTo=lulu-session@%i.service", service)
        self.assertIn("ExecStart=/opt/lulu/current/scripts/mudos-osk-service", service)
        self.assertIn("SDL_VIDEODRIVER=x11", wrapper)
        self.assertIn("WAYLAND_DISPLAY=", wrapper)
        self.assertIn("mudos-osk-bridge", wrapper)
        self.assertNotIn("--layer-shell", wrapper)
        session = (ROOT / "packaging/lulu-session@.service").read_text()
        self.assertIn("lulu-osk@%i.service", session)

    def test_bridge_uses_existing_normalized_actions_and_private_device(self) -> None:
        bridge = (ROOT / "scripts/mudos-osk-bridge").read_text()
        for action in (
            '"ui_up"', '"ui_down"', '"ui_left"', '"ui_right"',
            '"ui_accept"', '"ui_back"', '"ui_context"', '"ui_option"',
            '"ui_l2"', '"ui_r2"',
        ):
            self.assertIn(action, bridge)
        self.assertIn('"gamepad-osk-bridge"', bridge)
        self.assertIn('Variant("u", mode)', bridge)
        self.assertIn("self.pad.reset()", bridge)

    def test_keyboard_boundary_has_explicit_operations(self) -> None:
        wrapper = (ROOT / "scripts/mudos-keyboard").read_text()
        consoled = (ROOT / "src/lulu/consoled.py").read_text()
        self.assertIn("show|hide", wrapper)
        self.assertIn("KeyboardVisible", consoled)
        self.assertIn("ShowKeyboard", consoled)
        self.assertIn("HideKeyboard", consoled)
        self.assertIn("mudos-osk-bridge.sock", wrapper)
        self.assertNotIn("--toggle", wrapper)
        self.assertNotIn("xdotool", wrapper)

    def test_keyboard_boundary_never_uses_unmanaged_raw_device(self) -> None:
        wrapper = (ROOT / "scripts/mudos-keyboard").read_text()
        self.assertNotIn("--toggle", wrapper)
        self.assertNotIn("/dev/input/event", wrapper)


if __name__ == "__main__":
    unittest.main()
