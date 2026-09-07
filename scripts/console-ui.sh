#!/bin/sh
set -eu

repo_root=${LULU_INSTALL_ROOT:-$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)}
export QT_QPA_PLATFORM=xcb
exec qmlscene6 "${LULU_UI_FILE:-$repo_root/ui/ConsoleShell.qml}"
