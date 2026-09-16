import hashlib
from pathlib import Path
import unittest


ROOT = Path(__file__).parents[1]


class MudosOskProvisioningTests(unittest.TestCase):
    def test_pinned_artifact_and_runtime_provisioning(self) -> None:
        script = (ROOT / "scripts/provision-gamepad-osk.sh").read_text()
        self.assertIn("v2.1.1", script)
        self.assertIn("4bc9b0f4fbb73da1c67a06cdbc08ef7300a2031b2d5e2a3d70e007490db7c1cc", script)
        self.assertIn("sdl3_ttf", script)
        self.assertIn("--version", script)

    def test_payload_osk_files_are_mirrored_and_manifested(self) -> None:
        names = (
            "scripts/mudos-osk-device",
            "scripts/mudos-osk-service",
            "scripts/mudos-keyboard",
            "scripts/provision-gamepad-osk.sh",
            "packaging/lulu-osk@.service",
            "packaging/udev/80-lulu-osk.rules",
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
        self.assertNotIn("--layer-shell", wrapper)

    def test_keyboard_boundary_has_explicit_operations(self) -> None:
        wrapper = (ROOT / "scripts/mudos-keyboard").read_text()
        consoled = (ROOT / "src/lulu/consoled.py").read_text()
        self.assertIn("show|hide", wrapper)
        self.assertIn("KeyboardVisible", consoled)
        self.assertIn("ShowKeyboard", consoled)
        self.assertIn("HideKeyboard", consoled)


if __name__ == "__main__":
    unittest.main()
