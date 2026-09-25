#!/usr/bin/env python3
"""Launch the standalone controller-capable Recovery QML in Gamescope."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys

from lulu.gamescope import GamescopeInvocation, discover_presentation_output


def main() -> int:
    install_root = Path(os.environ.get("LULU_INSTALL_ROOT", "/opt/lulu/current"))
    shell = Path(os.environ.get("LULU_SHELL_EXECUTABLE", str(install_root / "bin/lulu-shell")))
    qml = install_root / "ui/Recovery.qml"
    if not shell.is_file() or not qml.is_file():
        print("Mudos Recovery UI files are unavailable", file=sys.stderr)
        return 2
    os.environ["QT_QPA_PLATFORM"] = "xcb"
    os.environ["LULU_RECOVERY_STANDALONE"] = "1"
    os.environ["LULU_INSTALL_ROOT"] = str(install_root)
    os.environ["LULU_UI_FILE"] = str(qml)
    invocation = GamescopeInvocation.from_environment()
    if invocation.output is None:
        invocation = GamescopeInvocation(
            steam=False, output=discover_presentation_output(),
            output_width=invocation.output_width, output_height=invocation.output_height,
            output_refresh=invocation.output_refresh, nested_width=invocation.nested_width,
            nested_height=invocation.nested_height,
        )
    command = invocation.argv([str(shell), str(qml)])
    return subprocess.run(command, check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
