#!/usr/bin/env python3
"""Launch the standalone controller-capable Recovery QML in Gamescope."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import time

from lulu.gamescope import (GamescopeInvocation, PresentationOutputUnavailable,
                            connected_presentation_outputs, discover_presentation_output,
                            has_connected_presentation_output)
from lulu.controllerd import default_inputplumber_client
from lulu.recovery_controller import apply_recovery_gamepad_mode


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
    inputplumber = default_inputplumber_client(install_root / "config" / "inputplumber")
    try:
        applied = apply_recovery_gamepad_mode(inputplumber)
        print(f"Recovery controller profile applied to {len(applied)} connected composite(s).",
              file=sys.stderr, flush=True)
    except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as error:
        print(f"Recovery controller profile will be retried by hotplug reconciliation: {error}",
              file=sys.stderr, flush=True)
    invocation = GamescopeInvocation.from_environment()
    while True:
        try:
            if not has_connected_presentation_output():
                raise PresentationOutputUnavailable("no connected DRM output")
            outputs = connected_presentation_outputs()
            output = (invocation.output if invocation.output in outputs
                      else discover_presentation_output())
        except PresentationOutputUnavailable as error:
            print(f"Mudos Recovery is waiting for a display: {error}", file=sys.stderr, flush=True)
            time.sleep(2.0)
            continue
        launch = GamescopeInvocation(
            steam=False, output=output,
            output_width=invocation.output_width, output_height=invocation.output_height,
            output_refresh=invocation.output_refresh, nested_width=invocation.nested_width,
            nested_height=invocation.nested_height,
        )
        command = launch.argv([str(shell), str(qml)])
        result = subprocess.run(command, check=False)
        if not has_connected_presentation_output():
            print("Gamescope ended after display loss; Recovery remains active for display return.",
                  file=sys.stderr, flush=True)
        else:
            print(f"Recovery UI exited with status {result.returncode}; restarting it.",
                  file=sys.stderr, flush=True)
        time.sleep(2.0)


if __name__ == "__main__":
    raise SystemExit(main())
