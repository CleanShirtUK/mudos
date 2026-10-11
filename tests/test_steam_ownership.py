"""Fixture tests for guard helpers intentionally kept out of the release package."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).parents[1]
SPEC = importlib.util.spec_from_file_location(
    "steam_ownership_guard_prototype", ROOT / "scripts/steam-ownership-guard-prototype.py")
assert SPEC and SPEC.loader
STEAM_OWNERSHIP = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = STEAM_OWNERSHIP
SPEC.loader.exec_module(STEAM_OWNERSHIP)

ProcessEvidence = STEAM_OWNERSHIP.ProcessEvidence
SteamBoundaryError = STEAM_OWNERSHIP.SteamBoundaryError
classify_steam_content_activity = STEAM_OWNERSHIP.classify_steam_content_activity
parse_mountinfo = STEAM_OWNERSHIP.parse_mountinfo
validate_mount_boundary = STEAM_OWNERSHIP.validate_mount_boundary
validate_steam_process_tree = STEAM_OWNERSHIP.validate_steam_process_tree


def mount(mount_id: int, point: str, options: str, root: str = "/") -> str:
    return (f"{mount_id} 1 8:1 {root} {point} {options} - ext4 /dev/test rw,relatime\n")


class SteamOwnershipTests(unittest.TestCase):
    def test_mount_boundary_accepts_ro_tree_and_exact_runtime_exceptions(self):
        info = mount(1, "/", "rw") + mount(2, "/synthetic/steamapps", "ro")
        info += mount(3, "/synthetic/steamapps/shadercache", "rw")
        info += mount(4, "/synthetic/steamapps/compatdata", "rw")
        mounts = validate_mount_boundary(
            info, ("/synthetic/steamapps",),
            ("/synthetic/steamapps/shadercache", "/synthetic/steamapps/compatdata"),
        )
        self.assertEqual(len(mounts), 4)

    def test_mount_boundary_fails_closed_on_missing_root_or_writable_child(self):
        with self.assertRaisesRegex(SteamBoundaryError, "not proven read-only"):
            validate_mount_boundary(mount(1, "/", "rw"), ("/synthetic/steamapps",))
        info = mount(1, "/", "rw") + mount(2, "/synthetic/steamapps", "ro")
        info += mount(3, "/synthetic/steamapps/downloading", "rw")
        with self.assertRaisesRegex(SteamBoundaryError, "writable child mount"):
            validate_mount_boundary(info, ("/synthetic/steamapps",))

    def test_mount_boundary_rejects_a_writable_duplicate_root_and_bad_exception(self):
        info = mount(1, "/synthetic/steamapps", "ro")
        info += mount(2, "/synthetic/steamapps", "rw")
        with self.assertRaisesRegex(SteamBoundaryError, "not proven read-only"):
            validate_mount_boundary(info, ("/synthetic/steamapps",))
        info = mount(1, "/synthetic/steamapps", "ro")
        with self.assertRaisesRegex(SteamBoundaryError, "exception is missing"):
            validate_mount_boundary(info, ("/synthetic/steamapps",),
                                    ("/synthetic/steamapps/shadercache",))
        with self.assertRaisesRegex(SteamBoundaryError, "outside the protected tree"):
            validate_mount_boundary(info + mount(2, "/tmp/unrelated-state", "rw"),
                                    ("/synthetic/steamapps",), ("/tmp/unrelated-state",))

    def test_mountinfo_escaped_paths_are_decoded(self):
        mounts = parse_mountinfo(mount(1, r"/synthetic/steam\040library", "ro"))
        self.assertEqual(mounts[0].point, "/synthetic/steam library")

    def test_process_tree_checks_each_namespace_and_rejects_unexpected_steam(self):
        processes = (
            ProcessEvidence(10, "/system.slice/lulu-steam-runtime.service", "mnt:[44]", "/usr/bin/steam"),
            ProcessEvidence(11, "/system.slice/lulu-steam-runtime.service", "mnt:[45]", "/usr/bin/steamwebhelper"),
            ProcessEvidence(12, "/system.slice/lulu-steam-runtime.service", "mnt:[45]", "/usr/bin/python"),
        )
        ro_info = mount(1, "/", "rw") + mount(2, "/managed/steamapps", "ro")
        validate_steam_process_tree(
            processes, "/system.slice/lulu-steam-runtime.service", "mnt:[44]",
            {"mnt:[44]": ro_info, "mnt:[45]": ro_info}, ("/managed/steamapps",),
        )
        with self.assertRaisesRegex(SteamBoundaryError, "outside the service cgroup"):
            validate_steam_process_tree(processes + (
                ProcessEvidence(20, "/user.slice/session.scope", "mnt:[44]", "/usr/bin/steam"),
            ), "/system.slice/lulu-steam-runtime.service", "mnt:[44]",
                {"mnt:[44]": ro_info, "mnt:[45]": ro_info}, ("/managed/steamapps",))
        rw_info = ro_info + mount(3, "/managed/steamapps/downloading", "rw")
        with self.assertRaisesRegex(SteamBoundaryError, r"namespace mnt:\[45\] is not restricted"):
            validate_steam_process_tree(
                processes, "/system.slice/lulu-steam-runtime.service", "mnt:[44]",
                {"mnt:[44]": ro_info, "mnt:[45]": rw_info}, ("/managed/steamapps",),
            )

    def test_content_operation_classifier_fails_closed_or_reports_activity(self):
        self.assertEqual(classify_steam_content_activity(None, staging_entries=()), "unknown")
        self.assertEqual(classify_steam_content_activity("", staging_entries=()), "unknown")
        self.assertEqual(classify_steam_content_activity("unrecognized old log\n", staging_entries=()), "unknown")
        self.assertEqual(classify_steam_content_activity(
            "[time] AppID 4 state changed : Fully Installed,\n",
            staging_entries=(), evidence_fresh=False), "unknown")
        self.assertEqual(classify_steam_content_activity(
            "[time] AppID 4 state changed : Update Required,Update Queued,Update Started,\n",
            staging_entries=(), evidence_fresh=True), "active")
        self.assertEqual(classify_steam_content_activity(
            "[time] AppID 4 state changed : Fully Installed,\n",
            staging_entries=("424242",), evidence_fresh=True), "active")
        self.assertEqual(classify_steam_content_activity(
            "[time] AppID 4 state changed : Fully Installed,\n",
            staging_entries=(), evidence_fresh=True), "idle")
        self.assertEqual(classify_steam_content_activity(
            "[time] AppID 4 state changed : Update Required,Update Queued,Update Started, (Suspended)\n"
            "[time] AppID 4 scheduler finished : staying in schedule (result Suspended, state 0x40a)\n",
            staging_entries=(), evidence_fresh=True), "active")


if __name__ == "__main__":
    unittest.main()
