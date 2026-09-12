#!/usr/bin/env bash
set -Eeuo pipefail

log() { printf '[FILE-BROWSER] %s\n' "$*"; }

log "starting uid=$(id -u) gid=$(id -g) bind=${DUFS_BIND:-unset} port=${DUFS_PORT:-unset} roots=/srv/Games,/srv/Recordings,/srv/Replays,/srv/Screenshots command=/usr/bin/dufs /srv config=/etc/lulu/file-browser.env"
/usr/bin/dufs /srv &
child=$!
trap 'log "shutdown pid=${child}"; kill -TERM "$child" 2>/dev/null || true' TERM INT
status=0
wait "$child" || status=$?
log "exit status=${status}"
exit "$status"
