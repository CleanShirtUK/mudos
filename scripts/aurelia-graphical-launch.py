#!/usr/bin/python3
"""Aurelia --script wrapper that adds only Mudos's live graphical context."""

from __future__ import annotations

import os
from pathlib import Path
import sys


def _load_context_reader():
    # In a release, this script is beside lib/; in a source checkout it is beside
    # src/. Keep the wrapper independent of the daemon's current working directory.
    root = Path(__file__).resolve().parent.parent
    for package_root in (root / "lib", root / "src"):
        if (package_root / "lulu" / "graphical_launch_context.py").is_file():
            sys.path.insert(0, str(package_root))
            from lulu.graphical_launch_context import read_current_context
            return read_current_context
    raise RuntimeError("Mudos graphical launch context support is not installed")


def main(argv: list[str] | None = None) -> int:
    command = list(sys.argv[1:] if argv is None else argv)
    if not command or not command[0]:
        print("Mudos Aurelia launch: Aurelia supplied no resolved command", file=sys.stderr)
        return 126
    try:
        graphical_environment = _load_context_reader()()
    except (OSError, RuntimeError, ValueError) as error:
        print(f"Mudos Aurelia launch: refusing graphical launch: {error}", file=sys.stderr)
        return 125
    environment = os.environ.copy()
    environment.update(graphical_environment)
    try:
        os.execvpe(command[0], command, environment)
    except OSError as error:
        print(f"Mudos Aurelia launch: could not exec resolved command: {error}", file=sys.stderr)
        return 126
    return 126


if __name__ == "__main__":
    raise SystemExit(main())
