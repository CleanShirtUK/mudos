#!/usr/bin/env bash
set -Eeuo pipefail

log() { printf '[lulu-file-browser] %s\n' "$*"; }

log "starting uid=$(id -u) bind=${DUFS_BIND:-unset} port=${DUFS_PORT:-unset} roots=/srv/Games,/srv/Recordings,/srv/Replays,/srv/Screenshots config=/etc/lulu/file-browser.env"
/usr/bin/dufs /srv &
child=$!
trap 'log "stopping pid=${child}"; kill -TERM "$child" 2>/dev/null || true' TERM INT
status=0
wait "$child" || status=$?
log "exited status=${status}"
exit "$status"
