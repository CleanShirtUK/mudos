from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import tempfile
import sys
import unittest
import asyncio
from unittest.mock import AsyncMock, patch
from types import SimpleNamespace

from lulu.dolphin_passthrough import (
    ADAPTER_PRODUCT_ID,
    ADAPTER_VENDOR_ID,
    DolphinBluetoothLease,
    adapter_present,
    dolphin_config_lease_path,
    _restore_persisted_config,
)
from lulu.providers.config import NativeConfigAdapter
from lulu.consoled import ConsoleInterface


ROOT = Path(__file__).parents[1]
SPEC = importlib.util.spec_from_file_location(
    "dolphin_bluetooth_lease", ROOT / "scripts/dolphin-bluetooth-lease.py",
)
assert SPEC is not None and SPEC.loader is not None
HELPER = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = HELPER
SPEC.loader.exec_module(HELPER)


class DolphinPassthroughTests(unittest.TestCase):
    def _local_wii_fixture(self, *, launch_error: Exception | None = None):
        from lulu.paths import PATHS

        events = []
        tasks = []

        class Process:
            pid = 7721

            async def wait(self):
                events.append("dolphin-exit")
                return 139

        process = Process()
        lease = SimpleNamespace(
            acquire_async=AsyncMock(side_effect=lambda: events.append("lease-acquired")),
            attach_async=AsyncMock(side_effect=lambda pid: events.append(("dolphin-attached", pid))),
            release_async=AsyncMock(side_effect=lambda: events.append("lease-released")),
        )
        game = SimpleNamespace(
            game_id="local:wii:fixture", launchable=True, provider="local", provider_id="",
            catalogue_source="local", platform="wii", install_dir="/fixture/game.rvz",
        )
        store = SimpleNamespace(
            list_games=lambda: [game], mark_played=lambda _game_id: {"played": True},
        )
        interface = ConsoleInterface.__new__(ConsoleInterface)
        interface.catalogue = SimpleNamespace(store=store)
        interface._plugins = SimpleNamespace(with_capability=lambda _capability: ())
        interface.local_runtime = SimpleNamespace(launch_intent=lambda *args, **kwargs: SimpleNamespace(
            executable="/usr/bin/dolphin-emu",
            arguments=(
                "--user", str(PATHS.provider_config_root("dolphin")), "--batch",
                "-C", "Display.Fullscreen=True", "-e", "/fixture/game.rvz",
            ),
            provider="dolphin", platform="wii",
        ))
        interface.sessiond = SimpleNamespace(
            call_begin_local_session=AsyncMock(side_effect=lambda *args: events.append("session-begun") or "wii-token"),
            call_end_local_session=AsyncMock(side_effect=lambda *args: events.append(("session-ended", args[-1]))),
        )
        interface._local_process = None
        interface._local_token = None
        interface._publish_delta = lambda _delta: None
        interface.CatalogueChanged = lambda: None

        async def spawn(*_args, **_kwargs):
            events.append("dolphin-spawn-attempt")
            if launch_error is not None:
                raise launch_error
            return process

        async def inline_thread(function, *args):
            return function(*args)

        return interface, lease, process, events, tasks, spawn, inline_thread

    def test_wii_process_crash_reaps_session_then_restores_adapter_lease(self) -> None:
        from lulu.paths import PATHS

        interface, lease, _process, events, tasks, spawn, inline_thread = self._local_wii_fixture()
        provisioned = []
        commands = []

        def capture_profile(*args):
            provisioned.append(args)
            return Path("/tmp/GCPadNew.ini")

        async def capture_spawn(*args, **kwargs):
            commands.append(args)
            return await spawn(*args, **kwargs)

        async def exercise_launch() -> str:
            with patch("lulu.consoled.DolphinBluetoothLease.create", return_value=lease), \
                    patch("lulu.consoled._mudos_provider_device_indices", return_value={1: 0}), \
                    patch("lulu.consoled._mudos_provider_controller_identities", return_value={}), \
                    patch("lulu.consoled.ensure_provider_controller_config", side_effect=capture_profile), \
                    patch("lulu.consoled.SettingsStore", return_value=SimpleNamespace(
                        get=lambda _key: "passthrough", connection=SimpleNamespace(close=lambda: None),
                    )), \
                    patch("lulu.consoled.asyncio.to_thread", side_effect=inline_thread), \
                    patch("lulu.consoled.asyncio.create_subprocess_exec", side_effect=capture_spawn), \
                    patch("lulu.consoled.asyncio.create_task", side_effect=lambda coroutine: tasks.append(coroutine)), \
                    patch("lulu.consoled.os.getpgid", return_value=7721), \
                    patch("lulu.consoled.os.path.realpath", return_value="/usr/bin/dolphin-emu"):
                return await ConsoleInterface.LaunchGame.__wrapped__(interface, "local:wii:fixture", 15000)

        self.assertEqual(asyncio.run(exercise_launch()), "wii-token")
        self.assertEqual(provisioned[0][4], PATHS.provider_config_root("dolphin") / "Config")
        self.assertEqual(commands[0][1:3], ("--user", str(PATHS.provider_config_root("dolphin"))))
        self.assertLess(events.index("lease-acquired"), events.index("dolphin-spawn-attempt"))
        self.assertLess(events.index(("dolphin-attached", 7721)), events.index("session-begun"))
        self.assertEqual(len(tasks), 1)
        asyncio.run(tasks.pop())
        lease.release_async.assert_awaited_once_with()
        interface.sessiond.call_end_local_session.assert_awaited_once_with("wii-token", 139)
        self.assertLess(events.index(("session-ended", 139)), events.index("lease-released"))

    def test_failed_dolphin_spawn_releases_acquired_adapter_before_return(self) -> None:
        interface, lease, _process, events, tasks, spawn, inline_thread = self._local_wii_fixture(
            launch_error=FileNotFoundError("Dolphin unavailable"),
        )

        async def exercise_launch() -> None:
            with patch("lulu.consoled.DolphinBluetoothLease.create", return_value=lease), \
                    patch("lulu.consoled._mudos_provider_device_indices", return_value={1: 0}), \
                    patch("lulu.consoled._mudos_provider_controller_identities", return_value={}), \
                    patch("lulu.consoled.ensure_provider_controller_config", return_value=Path("/tmp/GCPadNew.ini")), \
                    patch("lulu.consoled.SettingsStore", return_value=SimpleNamespace(
                        get=lambda _key: "passthrough", connection=SimpleNamespace(close=lambda: None),
                    )), \
                    patch("lulu.consoled.asyncio.to_thread", side_effect=inline_thread), \
                    patch("lulu.consoled.asyncio.create_subprocess_exec", side_effect=spawn), \
                    patch("lulu.consoled.os.getpgid", return_value=7721), \
                    patch("lulu.consoled.os.path.realpath", return_value="/usr/bin/dolphin-emu"):
                with self.assertRaisesRegex(FileNotFoundError, "Dolphin unavailable"):
                    await ConsoleInterface.LaunchGame.__wrapped__(interface, "local:wii:fixture", 15000)

        asyncio.run(exercise_launch())
        lease.acquire_async.assert_awaited_once_with()
        lease.attach_async.assert_not_awaited()
        lease.release_async.assert_awaited_once_with()
        interface.sessiond.call_begin_local_session.assert_not_awaited()
        self.assertNotIn("session-begun", events)
        self.assertEqual(tasks, [])

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

    def test_lease_restores_previous_dolphin_flags_and_adapter_has_service_access(self) -> None:
        rule = (ROOT / "packaging/udev/82-lulu-dolphin-bluetooth.rules").read_text()
        provider = (ROOT / "config/providers/dolphin/provider.toml").read_text()
        self.assertIn('ATTR{idVendor}=="0bda", ATTR{idProduct}=="8771", GROUP="lulu", MODE="0660", TAG+="uaccess"', rule)
        self.assertIn('id = "dolphin-quit"', provider)
        self.assertIn('target = "process-group-terminate"', provider)
        polkit_rule = (ROOT / "packaging/polkit-1/rules.d/61-lulu-dolphin-bluetooth.rules").read_text()
        self.assertIn("/opt\\/lulu\\/releases\\/", polkit_rule)
        self.assertIn("dolphin-bluetooth-lease\\.py$", polkit_rule)
        self.assertNotIn('action.lookup("program") == "/opt/lulu/current/', polkit_rule)
        provisioner = (ROOT / "scripts/provision-admin.sh").read_text()
        self.assertIn("61-lulu-dolphin-bluetooth.rules", provisioner)
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "Dolphin.ini"
            original = (
                "[BluetoothPassthrough]\nEnabled = False\nVID = 1\nPID = 2\n"
                "[Core]\nUnrelated = keep\n"
            )
            config.write_text(original)
            lease = DolphinBluetoothLease(Path("/helper"), config, "c" * 32, {
                "BluetoothPassthrough.Enabled": "False",
                "BluetoothPassthrough.VID": "1",
                "BluetoothPassthrough.PID": "2",
            })
            with patch("lulu.dolphin_passthrough.subprocess.run") as run:
                run.return_value = type("Result", (), {"returncode": 0})()
                lease.acquire()
                self.assertEqual(NativeConfigAdapter(config).get("BluetoothPassthrough", "Enabled"), "True")
                self.assertEqual(
                    NativeConfigAdapter(config).get("BluetoothPassthrough", "VID"),
                    str(int(ADAPTER_VENDOR_ID, 16)),
                )
                self.assertEqual(
                    NativeConfigAdapter(config).get("BluetoothPassthrough", "PID"),
                    str(int(ADAPTER_PRODUCT_ID, 16)),
                )
                self.assertEqual(NativeConfigAdapter(config).get("Core", "Unrelated"), "keep")
                lease.release()
            self.assertEqual(config.read_text(), original)
            self.assertFalse(dolphin_config_lease_path(config).exists())

    def test_lease_selects_configured_adapter_then_restores_automatic_selection(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "Dolphin.ini"
            original = "[BluetoothPassthrough]\nEnabled = True\n[Core]\nUnrelated = keep\n"
            config.write_text(original)
            lease = DolphinBluetoothLease(Path("/helper"), config, "d" * 32, {
                "BluetoothPassthrough.Enabled": "True",
                "BluetoothPassthrough.VID": None,
                "BluetoothPassthrough.PID": None,
            })
            with patch("lulu.dolphin_passthrough.subprocess.run") as run:
                run.return_value = type("Result", (), {"returncode": 0})()
                lease.acquire()
                active = NativeConfigAdapter(config)
                self.assertEqual(active.get("BluetoothPassthrough", "Enabled"), "True")
                self.assertEqual(active.get("BluetoothPassthrough", "VID"), str(int(ADAPTER_VENDOR_ID, 16)))
                self.assertEqual(active.get("BluetoothPassthrough", "PID"), str(int(ADAPTER_PRODUCT_ID, 16)))
                lease.release()
            self.assertEqual(config.read_text(), original)

    def test_failed_launch_acquisition_rolls_back_every_temporary_config_key(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "Dolphin.ini"
            original = "[Interface]\nLanguageCode = en\n[Core]\nUnrelated = keep\n"
            config.write_text(original)
            lease = DolphinBluetoothLease(Path("/helper"), config, "f" * 32, {
                "BluetoothPassthrough.Enabled": None,
                "BluetoothPassthrough.VID": None,
                "BluetoothPassthrough.PID": None,
            })
            with patch("lulu.dolphin_passthrough.subprocess.run", side_effect=[
                __import__("subprocess").CalledProcessError(1, "pkexec"),
                type("Result", (), {"returncode": 0})(),
            ]):
                with self.assertRaisesRegex(RuntimeError, "could not acquire"):
                    lease.acquire()
            self.assertEqual(config.read_text(), original)
            self.assertFalse(dolphin_config_lease_path(config).exists())

    def test_unattempted_lease_does_not_release_another_sessions_token(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "Dolphin.ini"
            lease_path = dolphin_config_lease_path(config)
            lease_path.parent.mkdir(parents=True, exist_ok=True)
            lease_path.write_text(json.dumps({"token": "a" * 32, "values": {}}))
            lease = DolphinBluetoothLease(Path("/helper"), config, "b" * 32, {})
            with patch("lulu.dolphin_passthrough.subprocess.run") as run:
                lease.release()
            run.assert_not_called()
            self.assertTrue(lease_path.exists())

    def test_config_recovery_restores_after_consoled_restart(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "Dolphin.ini"
            config.write_text(
                "[BluetoothPassthrough]\nEnabled = True\nVID = 3034\nPID = 34673\n"
                "[Core]\nUnrelated = keep\n"
            )
            lease_path = dolphin_config_lease_path(config)
            lease_path.write_text(json.dumps({"token": "g" * 32, "values": {
                "BluetoothPassthrough.Enabled": "False",
                "BluetoothPassthrough.VID": None,
                "BluetoothPassthrough.PID": None,
            }}))
            self.assertTrue(_restore_persisted_config(config))
            restored = NativeConfigAdapter(config)
            self.assertEqual(restored.get("BluetoothPassthrough", "Enabled"), "False")
            self.assertIsNone(restored.get("BluetoothPassthrough", "VID"))
            self.assertIsNone(restored.get("BluetoothPassthrough", "PID"))
            self.assertEqual(restored.get("Core", "Unrelated"), "keep")
            self.assertFalse(lease_path.exists())

    def test_session_recovery_restores_adapter_then_persisted_dolphin_config(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "Dolphin.ini"
            config.write_text(
                "[BluetoothPassthrough]\nEnabled = True\nVID = 3034\nPID = 34673\n"
                "[Core]\nUnrelated = keep\n"
            )
            dolphin_config_lease_path(config).write_text(json.dumps({"token": "j" * 32, "values": {
                "BluetoothPassthrough.Enabled": "False",
                "BluetoothPassthrough.VID": "3034",
                "BluetoothPassthrough.PID": "34673",
            }}))
            async def recover() -> None:
                with patch("lulu.dolphin_passthrough.dolphin_config_path", return_value=config), \
                        patch("lulu.dolphin_passthrough.subprocess.run") as run:
                    run.return_value = type("Result", (), {"returncode": 0})()
                    await DolphinBluetoothLease.recover_stale_async()
                    self.assertEqual(run.call_args.args[0][-1], "recover")
            asyncio.run(recover())
            restored = NativeConfigAdapter(config)
            self.assertEqual(restored.get("BluetoothPassthrough", "Enabled"), "False")
            self.assertEqual(restored.get("Core", "Unrelated"), "keep")
            self.assertFalse(dolphin_config_lease_path(config).exists())

    def test_active_passthrough_release_retries_transient_adapter_restore_failure(self) -> None:
        lease = DolphinBluetoothLease(Path("/helper"), Path("/unused/Dolphin.ini"), "h" * 32, {})
        lease.attempted = True
        import subprocess
        results = [
            subprocess.CalledProcessError(1, "pkexec"),
            type("Result", (), {"returncode": 0})(),
        ]

        async def exercise() -> None:
            with patch("lulu.dolphin_passthrough.subprocess.run", side_effect=results) as run, \
                    patch("lulu.dolphin_passthrough.asyncio.sleep", new=AsyncMock()):
                await lease.release_async()
                self.assertEqual(run.call_count, 2)

        asyncio.run(exercise())

    def test_adapter_restore_failure_retains_root_recovery_record(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory) / "lease.json"
            state.write_text(json.dumps({
                "token": "i" * 32,
                "owner_pid": 901,
                "owner_starttime": "dead-owner",
                "bluetooth_was_active": False,
                "unbound_interfaces": ["1-4:1.0"],
            }))
            with patch.object(HELPER, "STATE", state), \
                    patch.object(HELPER, "process_starttime", return_value=None), \
                    patch.object(HELPER, "bind_interfaces", side_effect=OSError("bind failed")):
                with self.assertRaisesRegex(RuntimeError, "adapter restoration incomplete"):
                    HELPER.recover()
            self.assertTrue(state.exists())


if __name__ == "__main__":
    unittest.main()
