"""Fail-closed Steam namespace evidence helpers (prototype, not production-wired)."""

from __future__ import annotations

from dataclasses import dataclass
import re
from pathlib import PurePosixPath


class SteamBoundaryError(ValueError):
    """Namespace evidence does not prove the expected content boundary."""


def _unescape_mountinfo(value: str) -> str:
    return re.sub(r"\\([0-7]{3})", lambda match: chr(int(match.group(1), 8)), value)


@dataclass(frozen=True)
class Mount:
    mount_id: int
    parent_id: int
    device: str
    root: str
    point: str
    options: frozenset[str]
    optional: tuple[str, ...]
    filesystem: str
    source: str
    super_options: frozenset[str]


def parse_mountinfo(text: str) -> tuple[Mount, ...]:
    mounts: list[Mount] = []
    for line in text.splitlines():
        fields = line.split()
        if "-" not in fields:
            raise SteamBoundaryError("malformed mountinfo record")
        separator = fields.index("-")
        if separator < 6 or len(fields) < separator + 4:
            raise SteamBoundaryError("incomplete mountinfo record")
        try:
            mounts.append(Mount(
                mount_id=int(fields[0]), parent_id=int(fields[1]), device=fields[2],
                root=_unescape_mountinfo(fields[3]), point=_unescape_mountinfo(fields[4]),
                options=frozenset(fields[5].split(",")),
                optional=tuple(fields[6:separator]), filesystem=fields[separator + 1],
                source=_unescape_mountinfo(fields[separator + 2]),
                super_options=frozenset(fields[separator + 3].split(",")),
            ))
        except (ValueError, IndexError) as error:
            raise SteamBoundaryError("malformed mountinfo fields") from error
    if not mounts:
        raise SteamBoundaryError("mountinfo is empty")
    return tuple(mounts)


def _inside(path: str, parent: str) -> bool:
    candidate, root = PurePosixPath(path), PurePosixPath(parent)
    return candidate == root or root in candidate.parents


def validate_mount_boundary(mountinfo: str, protected: tuple[str, ...],
                            writable_allowlist: tuple[str, ...] = ()) -> tuple[Mount, ...]:
    """Require exact read-only roots and reject unapproved writable descendants."""
    mounts = parse_mountinfo(mountinfo)
    by_point: dict[str, list[Mount]] = {}
    for mount in mounts:
        by_point.setdefault(mount.point, []).append(mount)
    for root in protected:
        exact = by_point.get(root, [])
        if not exact or any("ro" not in mount.options or "rw" in mount.options for mount in exact):
            raise SteamBoundaryError(f"protected root is not proven read-only: {root}")
        for mount in mounts:
            if not _inside(mount.point, root) or mount.point == root:
                continue
            if mount.point in writable_allowlist:
                continue
            if "rw" in mount.options or "ro" not in mount.options:
                raise SteamBoundaryError(f"writable child mount defeats protected root: {mount.point}")
    for allowed in writable_allowlist:
        records = by_point.get(allowed, [])
        if len(records) != 1 or "rw" not in records[0].options or "ro" in records[0].options:
            raise SteamBoundaryError(f"expected writable runtime exception is missing: {allowed}")
        if not any(allowed != root and _inside(allowed, root) for root in protected):
            raise SteamBoundaryError(f"writable runtime exception is outside the protected tree: {allowed}")
    return mounts


@dataclass(frozen=True)
class ProcessEvidence:
    pid: int
    cgroup: str
    mount_namespace: str
    executable: str


def validate_steam_process_tree(processes: tuple[ProcessEvidence, ...],
                                expected_cgroup: str, expected_namespace: str,
                                namespace_mountinfo: dict[str, str],
                                protected: tuple[str, ...],
                                writable_allowlist: tuple[str, ...] = ()) -> None:
    """Require the Steam cgroup and prove every distinct child namespace is restricted."""
    if not processes or not expected_cgroup or not expected_namespace or not namespace_mountinfo:
        raise SteamBoundaryError("process/cgroup/namespace evidence is incomplete")
    steam = tuple(p for p in processes if "steam" in PurePosixPath(p.executable).name.casefold())
    if not steam:
        raise SteamBoundaryError("no resident Steam process was identified")
    unexpected = [p.pid for p in steam if p.cgroup != expected_cgroup]
    if unexpected:
        raise SteamBoundaryError(f"Steam processes outside the service cgroup: {unexpected}")
    if any(not p.executable or not p.cgroup or not p.mount_namespace for p in processes):
        raise SteamBoundaryError("process evidence contains unknown fields")
    if not any(p.mount_namespace == expected_namespace for p in steam):
        raise SteamBoundaryError("the resident Steam process is not in the expected service namespace")
    namespaces = {p.mount_namespace for p in processes if p.cgroup == expected_cgroup}
    if namespaces - namespace_mountinfo.keys():
        raise SteamBoundaryError("mount evidence is missing for a process namespace")
    for namespace in namespaces:
        try:
            validate_mount_boundary(namespace_mountinfo[namespace], protected, writable_allowlist)
        except SteamBoundaryError as error:
            raise SteamBoundaryError(f"service process namespace {namespace} is not restricted: {error}") from error


def classify_steam_content_activity(content_log: str | None, *,
                                    staging_entries: tuple[str, ...] | None,
                                    evidence_fresh: bool = False) -> str:
    """Return active/idle/unknown; missing, stale-shaped or contradictory evidence fails closed."""
    if content_log is None or staging_entries is None or evidence_fresh is not True:
        return "unknown"
    if not content_log.strip():
        return "unknown"
    pending: dict[str, bool] = {}
    observed: set[str] = set()
    for line in content_log.splitlines():
        match = re.search(r"AppID\s+(\d+)\s+state changed\s*:\s*(.*)", line, re.IGNORECASE)
        if match:
            app_id, state = match.group(1), match.group(2)
            observed.add(app_id)
            pending[app_id] = bool(re.search(
                r"Update Queued|Update Running|Update Started|Update Staging|Update Committing|Downloading|Staging|Committing",
                state, re.IGNORECASE,
            ))
            continue
        match = re.search(r"AppID\s+(\d+)\s+(.*)", line, re.IGNORECASE)
        if not match:
            continue
        app_id, event = match.group(1), match.group(2)
        if re.search(r"scheduler update|update started|starting commit", event, re.IGNORECASE):
            observed.add(app_id)
            pending[app_id] = True
        elif re.search(r"scheduler finished\s*:\s*removed from schedule|finished update|update canceled\s*:.*\(Suspended\)",
                       event, re.IGNORECASE):
            observed.add(app_id)
            # A suspended operation remains queued and is not safely idle.
            pending[app_id] = "staying in schedule" in event.casefold() or "suspended" in event.casefold()
    if any(pending.values()):
        return "active"
    if staging_entries:
        return "active"
    if not observed:
        return "unknown"
    return "idle"
