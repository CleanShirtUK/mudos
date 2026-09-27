from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import tempfile
import sys
import unittest
from unittest.mock import patch

from lulu.dolphin_passthrough import (
    ADAPTER_PRODUCT_ID,
    ADAPTER_VENDOR_ID,
    DolphinBluetoothLease,
    adapter_present,
)


ROOT = Path(__file__).parents[1]
SPEC = importlib.util.spec_from_file_location(
    "dolphin_bluetooth_lease", ROOT / "scripts/dolphin-bluetooth-lease.py",
)
assert SPEC is not None and SPEC.loader is not None
HELPER = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = HELPER
SPEC.loader.exec_module(HELPER)


class DolphinPassthroughTests(unittest.TestCase):
    def test_adapter_detection_requires_exactly_one_configured_usb_adapter(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            adapter = root / "1-2"
            adapter.mkdir()
            (adapter / "idVendor").write_text(ADAPTER_VENDOR_ID)
            (adapter / "idProduct").write_text(ADAPTER_PRODUCT_ID)
            self.assertTrue(adapter_present(root))
            second = root / "2-3"
            second.mkdir()
            (second / "idVendor").write_text(ADAPTER_VENDOR_ID)
            (second / "idProduct").write_text(ADAPTER_PRODUCT_ID)
            self.assertFalse(adapter_present(root))

    def test_root_lease_stops_and_restores_only_previously_active_bluez(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            adapter = root / "1-4"
            adapter.mkdir()
            (adapter / "idVendor").write_text(ADAPTER_VENDOR_ID)
            (adapter / "idProduct").write_text(ADAPTER_PRODUCT_ID)
            state = root / "run/lulu/lease.json"
            calls: list[tuple[str, ...]] = []
            is_active = True

            def command(*args: str):
                nonlocal is_active
                calls.append(args)
                if args[:2] == ("systemctl", "is-active"):
                    return type("Result", (), {"returncode": 0 if is_active else 3, "stderr": ""})()
                if args[:2] == ("systemctl", "stop"):
                    is_active = False
                elif args[:2] == ("systemctl", "start"):
                    is_active = True
                return type("Result", (), {"returncode": 0, "stderr": ""})()

            token = "a" * 32
            state.parent.mkdir(parents=True)
            with patch.object(HELPER, "STATE", state), patch.object(HELPER, "require_adapter", return_value=adapter), \
                    patch.object(HELPER, "run", command), \
                    patch.object(HELPER, "prepare_state_directory"):
                with patch.object(HELPER, "process_starttime", return_value="123"):
                    HELPER.acquire(token, 900)
                self.assertFalse(is_active)
                self.assertEqual(json.loads(state.read_text())["bluetooth_was_active"], True)
                HELPER.release(token)
            self.assertTrue(is_active)
            self.assertFalse(state.exists())
            self.assertEqual(calls.count(("systemctl", "stop", "bluetooth.service")), 1)
            self.assertEqual(calls.count(("systemctl", "start", "bluetooth.service")), 1)

    def test_root_lease_leaves_previously_inactive_bluez_inactive(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            adapter = root / "1-4"
            adapter.mkdir()
            (adapter / "idVendor").write_text(ADAPTER_VENDOR_ID)
            (adapter / "idProduct").write_text(ADAPTER_PRODUCT_ID)
            state = root / "run/lulu/lease.json"
            calls: list[tuple[str, ...]] = []

            def command(*args: str):
                calls.append(args)
                return type("Result", (), {"returncode": 3 if args[:2] == ("systemctl", "is-active") else 0,
                                             "stderr": ""})()

            state.parent.mkdir(parents=True)
            with patch.object(HELPER, "STATE", state), patch.object(HELPER, "require_adapter", return_value=adapter), \
                    patch.object(HELPER, "run", command), \
                    patch.object(HELPER, "prepare_state_directory"):
                with patch.object(HELPER, "process_starttime", return_value="123"):
                    HELPER.acquire("b" * 32, 901)
                HELPER.release("b" * 32)
            self.assertFalse(any(call[:2] in {("systemctl", "stop"), ("systemctl", "start")} for call in calls))

    def test_stale_owner_recovery_restores_bluez_and_removes_the_lease(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory) / "lease.json"
            state.write_text(json.dumps({
                "token": "d" * 32,
                "owner_pid": 901,
                "owner_starttime": "before-crash",
                "bluetooth_was_active": True,
                "unbound_interfaces": [],
            }))
            calls: list[tuple[str, ...]] = []

            def command(*args: str):
                calls.append(args)
                return type("Result", (), {"returncode": 3 if args[:2] == ("systemctl", "is-active") else 0,
                                             "stderr": ""})()

            with patch.object(HELPER, "STATE", state), patch.object(HELPER, "run", command), \
                    patch.object(HELPER, "process_starttime", return_value=None), \
                    patch.object(HELPER, "bind_interfaces"):
                HELPER.recover()
            self.assertFalse(state.exists())
            self.assertIn(("systemctl", "start", "bluetooth.service"), calls)

    def test_recovery_refuses_to_take_adapter_from_live_dolphin(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory) / "lease.json"
            state.write_text(json.dumps({
                "token": "e" * 32,
                "owner_pid": 902,
                "owner_starttime": "old-owner",
                "dolphin_pid": 903,
                "dolphin_starttime": "live-dolphin",
                "bluetooth_was_active": True,
                "unbound_interfaces": [],
            }))

            def starttime(pid: int | None) -> str | None:
                return "live-dolphin" if pid == 903 else None

            with patch.object(HELPER, "STATE", state), patch.object(HELPER, "process_starttime", starttime):
                with self.assertRaisesRegex(RuntimeError, "Dolphin still owns"):
                    HELPER.recover()
            self.assertTrue(state.exists())

    def test_lease_restores_previous_dolphin_flags_and_device_access_is_uaccess(self) -> None:
        rule = (ROOT / "packaging/udev/82-lulu-dolphin-bluetooth.rules").read_text()
        provider = (ROOT / "config/providers/dolphin/provider.toml").read_text()
        self.assertIn('ATTR{idVendor}=="0bda", ATTR{idProduct}=="8771", TAG+="uaccess"', rule)
        self.assertIn('id = "dolphin-quit"', provider)
        self.assertIn('target = "process-group-terminate"', provider)
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "Dolphin.ini"
            config.write_text("[BluetoothPassthrough]\nEnabled = False\n[Core]\nWiimoteSource0 = 1\n")
            lease = DolphinBluetoothLease(Path("/helper"), config, "c" * 32, "False", "1")
            lease.acquired = False
            lease.release()
            self.assertIn("Enabled=False", config.read_text())
            self.assertIn("WiimoteSource0=1", config.read_text())


if __name__ == "__main__":
    unittest.main()
