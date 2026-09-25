#!/usr/bin/env python3
"""Start the independent local Recovery UI after repeated session failures."""

import logging
import subprocess

from lulu.recovery import recovery_required


def main() -> int:
    logging.basicConfig(level=logging.INFO)
    if not recovery_required():
        return 0
    result = subprocess.run(
        ["systemctl", "--no-block", "start", "mudos-recovery-ui.service"],
        stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=5, check=False,
    )
    if result.returncode:
        logging.error("could not start independent Recovery UI")
        return result.returncode
    logging.warning("repeated Mudos session failures reached threshold; Recovery UI requested")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
