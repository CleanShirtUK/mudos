#!/bin/sh
set -eu

repo_root=${LULU_INSTALL_ROOT:-$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)}
export QT_QPA_PLATFORM=xcb
exec python "$repo_root/scripts/console-ui-bridge.py"
