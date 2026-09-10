#!/bin/sh
set -eu

repo_root=${LULU_INSTALL_ROOT:-$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)}
steam_bootstrap=${LULU_STEAM_BOOTSTRAP:-"$repo_root/scripts/steam-bootstrap.sh"}

if [ ! -x "$steam_bootstrap" ]; then
    printf '%s\n' "Steam bootstrap is not executable: $steam_bootstrap" >&2
    exit 1
fi

steam_log=${LULU_STEAM_BOOTSTRAP_LOG:-/tmp/lulu-steam-bootstrap.log}
"$steam_bootstrap" >>"$steam_log" 2>&1 &
