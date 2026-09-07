#!/bin/sh
set -eu

repo_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
export QT_QPA_PLATFORM=xcb
exec qmlscene6 "$repo_root/ui/ConsoleShell.qml"
