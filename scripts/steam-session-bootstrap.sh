#!/bin/sh
set -eu

repo_root=${LULU_INSTALL_ROOT:-$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)}
steam_bootstrap=${LULU_STEAM_BOOTSTRAP:-"$repo_root/scripts/steam-bootstrap.sh"}
ready_timeout=${LULU_STEAM_READY_TIMEOUT:-60}

if [ ! -x "$steam_bootstrap" ]; then
    printf '%s\n' "Steam bootstrap is not executable: $steam_bootstrap" >&2
    exit 1
fi

steam_log=${LULU_STEAM_BOOTSTRAP_LOG:-/tmp/lulu-steam-bootstrap.log}
"$steam_bootstrap" >>"$steam_log" 2>&1 &

steam_gamepadui_ready() {
    focusable=$(xprop -root GAMESCOPE_FOCUSABLE_WINDOWS 2>/dev/null || true)
    case "$focusable" in
        *' 769,'*) return 0 ;;
    esac
    return 1
}

deadline=$(( $(date +%s) + ready_timeout ))
while ! steam_gamepadui_ready; do
    if [ "$(date +%s)" -ge "$deadline" ]; then
        printf '%s\n' "Steam GamepadUI did not become ready before timeout" >&2
        break
    fi
    sleep 0.1
done
