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

    def test_content_activity_uses_current_paired_evidence_not_historical_log(self):
        evidence = {
            "staging_entries": (), "evidence_fresh": True,
            "queued_appids": (), "write_descriptors": (0, 0),
            "staging_changed": False, "recent_events": (),
            "service_invocations": ("invocation-a", "invocation-a"),
        }
        self.assertEqual(classify_steam_content_activity(None, **evidence), "unknown")
        self.assertEqual(classify_steam_content_activity("", **evidence), "unknown")
        self.assertEqual(classify_steam_content_activity(
            "old completed scheduler records\n", **{**evidence, "evidence_fresh": False}), "unknown")

        # Completed historical updates and stable, empty/stale temp entries are
        # context, not current activity.
        self.assertEqual(classify_steam_content_activity(
            "old scheduler update; later removed from schedule\n", **evidence), "idle")
        stable_temp = {**evidence, "staging_entries": ("temp/1712830", "temp/48000")}
        self.assertEqual(classify_steam_content_activity(
            "old completed records\n", **stable_temp), "idle")

        # A queued-but-not-transferring operation remains safety-relevant.
        self.assertEqual(classify_steam_content_activity(
            "historical log\n", **{**evidence, "queued_appids": ("2225070",)}), "active")
        # Current transfer/staging, commit, or a relevant writer is active.
        self.assertEqual(classify_steam_content_activity(
            "historical log\n", **{**evidence, "staging_changed": True}), "active")
        self.assertEqual(classify_steam_content_activity(
            "historical log\n", **{**evidence, "recent_events": ("download",)}), "active")
        self.assertEqual(classify_steam_content_activity(
            "historical log\n", **{**evidence, "recent_events": ("commit",)}), "active")
        self.assertEqual(classify_steam_content_activity(
            "historical log\n", **{**evidence, "write_descriptors": (1, 1)}), "active")

        # Incomplete, malformed, restarting, or contradictory snapshots fail
        # closed rather than being rewritten as idle.
        self.assertEqual(classify_steam_content_activity(
            "historical log\n", **{**evidence, "recent_events": ("malformed",)}), "unknown")
        self.assertEqual(classify_steam_content_activity(
            "historical log\n", **{**evidence, "service_invocations": ("old", "new")}), "unknown")
        self.assertEqual(classify_steam_content_activity(
            "historical log\n", **{**evidence, "recent_events": ("queued",)}), "unknown")
        self.assertEqual(classify_steam_content_activity(
            "historical log\n", **{**evidence, "recent_events": ("download",),
                                  "staging_entries": ("temp/unknown",)}), "unknown")


if __name__ == "__main__":
    unittest.main()
