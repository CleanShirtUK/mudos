#!/usr/bin/env bash
set -Eeuo pipefail

# UMU is the appliance boundary for non-Steam Windows games.  The distro
# package owns UMU and its runtime/container integration; Mudos only verifies
# the executable and supplies per-game launch environment.
if ! command -v umu-run >/dev/null 2>&1; then
    pacman -S --needed --noconfirm umu-launcher
fi
command -v umu-run >/dev/null
umu-run --version 2>&1 || true
echo "provisioned UMU at $(command -v umu-run)"
