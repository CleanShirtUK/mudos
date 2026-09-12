#!/bin/sh
set -eu

if [ "$(id -u)" -ne 958 ] || [ "$(id -un)" != lulu ]; then
    printf '%s\n' 'steam-bootstrap must run as the lulu appliance user' >&2
    exit 1
fi

runtime_dir=${XDG_RUNTIME_DIR:-/run/user/958}
wayland_display=${WAYLAND_DISPLAY:-gamescope-0}
wayland_socket="$runtime_dir/$wayland_display"
if [ ! -S "$wayland_socket" ]; then
    printf 'active Lulu Wayland session not found: %s\n' "$wayland_socket" >&2
    exit 1
fi

export HOME=/var/lib/lulu
export USER=lulu
export LOGNAME=lulu
export XDG_RUNTIME_DIR="$runtime_dir"
export WAYLAND_DISPLAY="$wayland_display"
export DISPLAY=${DISPLAY:-:0}
export DBUS_SESSION_BUS_ADDRESS=${DBUS_SESSION_BUS_ADDRESS:-unix:path=/run/user/958/bus}
export XDG_CURRENT_DESKTOP=gamescope

# Steam is a provider here, not the initial presentation. Navigation is
# requested explicitly by a delegated surface after startup.
exec /usr/bin/steam -silent
