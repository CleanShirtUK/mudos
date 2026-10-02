#!/usr/bin/env python3
"""Initialize Aurelia's private config and canonical Mudos library setting."""
from __future__ import annotations

import os
import sys

from lulu.plugins.steam.aurelia import AureliaClient


def main() -> int:
    if os.geteuid() == 0:
        print("run as the Mudos user, not root", file=sys.stderr)
        return 1
    client = AureliaClient(executable=os.environ.get("LULU_AURELIA_EXECUTABLE", "/usr/bin/aurelia"))
    if not client.available:
        print("pinned Aurelia executable is unavailable", file=sys.stderr)
        return 1
    client._ensure_config_dir()
    print(f"Aurelia state initialized at {client.config_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
