import importlib.util
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "configure_mudos_limine", ROOT / "scripts/configure-mudos-limine.py")
BOOT = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(BOOT)


class MudosBootConfigTests(unittest.TestCase):
    def test_no_forced_headless_display_kernel_override_is_packaged(self):
        self.assertFalse(
            (ROOT / "packaging/limine-entry-tool.d/60-lulu-headless-display.conf").exists())

    def test_sets_instant_timeout_and_explicit_real_kernel_entry_preserving_other_boot_data(self):
        source = """timeout: 5
default_entry: 2
remember_last_entry: yes
/+CachyOS
  //linux-cachyos
  protocol: linux
  path: boot():/linux/vmlinuz#checksum
  cmdline: quiet nowatchdog splash rw root=UUID=abc zswap.enabled=1
  //linux-cachyos-fallback
  protocol: linux
  path: boot():/linux/fallback#checksum
  cmdline: quiet splash rw root=UUID=abc
  ////Snapshots
"""
        configured = BOOT.configure(source)
        self.assertIn("timeout: 0\n", configured)
        self.assertIn("default_entry: +CachyOS/linux-cachyos\n", configured)
        self.assertIn("remember_last_entry: no", configured)
        self.assertIn("path: boot():/linux/vmlinuz#checksum", configured)
        self.assertIn("cmdline: quiet nowatchdog splash rw root=UUID=abc zswap.enabled=1", configured)
        self.assertIn("//linux-cachyos-fallback", configured)
        self.assertEqual(BOOT.configure(configured), configured)

    def test_rejects_directory_without_bootable_linux_children(self):
        with self.assertRaisesRegex(BOOT.BootConfigError, "no real Limine Linux kernel entry"):
            BOOT.configure("timeout: 5\n/+CachyOS\n  //Snapshots\n")

    def test_installer_requires_supported_quiet_splash_kernel_defaults(self):
        import tempfile
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "limine"
            path.write_text('KERNEL_CMDLINE[default]+="quiet splash rw root=UUID=x"\n')
            BOOT.validate_kernel_defaults(path)
            path.write_text('KERNEL_CMDLINE[default]+="rw root=UUID=x"\n')
            with self.assertRaisesRegex(BOOT.BootConfigError, "quiet and splash"):
                BOOT.validate_kernel_defaults(path)


if __name__ == "__main__":
    unittest.main()
