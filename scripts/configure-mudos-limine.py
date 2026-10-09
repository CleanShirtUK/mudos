#!/usr/bin/env python3
"""Apply audited Mudos Limine defaults without regenerating kernel entries."""

from __future__ import annotations

import argparse
import re
from pathlib import Path
import sys


class BootConfigError(RuntimeError):
    pass


def configure(text: str) -> str:
    lines = text.splitlines()
    entry_path: str | None = None
    default_entry: str | None = None
    path_re = re.compile(r"^\s*/\+([^\n]+)$")
    kernel_re = re.compile(r"^(\s*)//([^/\n][^\n]*)$")
    for index, line in enumerate(lines):
        directory = path_re.match(line)
        if directory:
            entry_path = "+" + directory.group(1).strip()
            continue
        kernel = kernel_re.match(line)
        if not kernel:
            continue
        name = kernel.group(2).strip()
        end = next((offset for offset, child in enumerate(lines[index + 1:], start=index + 1)
                    if kernel_re.match(child) or re.match(r"^/", child)), len(lines))
        body = lines[index + 1:end]
        if (name == "linux-cachyos-bc250"
                and any(re.match(r"^\s*protocol:\s*linux\s*$", child) for child in body)
                and any(re.match(r"^\s*path:\s*boot\(\):/.+", child) for child in body)):
            default_entry = f"{entry_path}/{name}" if entry_path else name
            break
    if not default_entry:
        raise BootConfigError("no bootable linux-cachyos-bc250 Limine entry was found")

    timeout_indexes = [i for i, line in enumerate(lines) if re.match(r"^\s*timeout\s*:", line)]
    if timeout_indexes:
        lines[timeout_indexes[0]] = "timeout: 5"
        for index in reversed(timeout_indexes[1:]):
            del lines[index]
    else:
        insert_at = 0
        while insert_at < len(lines) and (not lines[insert_at].strip()
                                          or lines[insert_at].lstrip().startswith("#")):
            insert_at += 1
        lines.insert(insert_at, "timeout: 5")

    default_indexes = [i for i, line in enumerate(lines)
                       if re.match(r"^\s*default_entry\s*:", line)]
    if default_indexes:
        lines[default_indexes[0]] = f"default_entry: {default_entry}"
        for index in reversed(default_indexes[1:]):
            del lines[index]
    else:
        lines.insert(1, f"default_entry: {default_entry}")
    remember_indexes = [i for i, line in enumerate(lines)
                        if re.match(r"^\s*remember_last_entry\s*:", line)]
    if remember_indexes:
        lines[remember_indexes[0]] = "remember_last_entry: no"
        for index in reversed(remember_indexes[1:]):
            del lines[index]
    result = "\n".join(lines).rstrip() + "\n"
    if not re.search(r"(?m)^timeout:\s*5\s*$", result):
        raise BootConfigError("Limine timeout was not set to five seconds")
    if not re.search(r"(?m)^remember_last_entry:\s*no\s*$", result):
        raise BootConfigError("Limine must honor the explicit Mudos default rather than remembered selection")
    return result


def validate_kernel_defaults(path: Path) -> None:
    if not path.is_file():
        raise BootConfigError(f"CachyOS Limine defaults are missing: {path}")
    text = path.read_text()
    assignments = [line for line in text.splitlines()
                   if "KERNEL_CMDLINE[default]" in line and not line.lstrip().startswith("#")]
    if not assignments or not all(token in " ".join(assignments) for token in ("quiet", "splash")):
        raise BootConfigError(
            "supported Limine defaults must retain both quiet and splash in KERNEL_CMDLINE[default]"
        )


def validate_bc250_files(text: str, boot_root: Path = Path("/boot")) -> None:
    """Require the named BC250 entry's kernel and initramfs to exist."""
    lines = text.splitlines()
    found = False
    paths: list[str] = []
    for index, line in enumerate(lines):
        if not re.match(r"^\s*//linux-cachyos-bc250\s*$", line):
            continue
        end = next((offset for offset, child in enumerate(lines[index + 1:], start=index + 1)
                    if re.match(r"^\s*//[^/].*", child) or re.match(r"^/", child)), len(lines))
        body = lines[index + 1:end]
        found = any(re.match(r"^\s*protocol:\s*linux\s*$", child) for child in body)
        paths = [match.group(1).split("#", 1)[0] for child in body
                 if (match := re.match(r"^\s*(?:path|module_path):\s*boot\(\):(/[^\s]+)", child))]
        break
    if not found or len(paths) < 2:
        raise BootConfigError("BC250 Limine entry is missing its Linux kernel or initramfs path")
    missing = [path for path in paths if not (boot_root / path.lstrip("/")).is_file()]
    if missing:
        raise BootConfigError("BC250 Limine entry references missing boot files: " + ", ".join(missing))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path("/boot/limine.conf"))
    parser.add_argument("--limine-defaults", type=Path, default=Path("/etc/default/limine"))
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    try:
        validate_kernel_defaults(args.limine_defaults)
        before = args.config.read_text()
        validate_bc250_files(before, args.config.parent)
        after = configure(before)
        if args.check:
            if before != after:
                raise BootConfigError("Limine config needs Mudos defaults (timeout: 0 and explicit Linux entry)")
        elif before != after:
            temporary = args.config.with_name(f".{args.config.name}.mudos-tmp")
            temporary.write_text(after)
            temporary.chmod(args.config.stat().st_mode & 0o777)
            temporary.replace(args.config)
        print(f"Limine config valid: default is linux-cachyos-bc250; timeout=5 ({args.config})")
        return 0
    except (OSError, BootConfigError) as error:
        print(f"configure-mudos-limine: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
