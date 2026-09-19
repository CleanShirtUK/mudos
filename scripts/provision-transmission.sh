#!/bin/sh
set -eu

# Provision the Mudos-owned Transmission daemon.  This script is intentionally
# idempotent: it never replaces an existing daemon settings.json or provider
# configuration.  RPC credentials are generated once and stored in SecretStore
# as well as the daemon's private settings file (Transmission needs the latter
# to authenticate incoming RPC requests).

if [ "$(id -u)" -ne 0 ]; then
    exec sudo -n "$0" "$@"
fi

user=${LULU_TRANSMISSION_USER:-lulu-transmission}
group=${LULU_TRANSMISSION_GROUP:-$user}
state=${LULU_TRANSMISSION_STATE:-/var/lib/lulu-transmission}
service=${LULU_TRANSMISSION_SERVICE:-lulu-transmission.service}
lulu_user=${LULU_PROVIDER_CONFIG_USER:-lulu}

pacman -S --needed --noconfirm transmission-cli
if ! getent group "$group" >/dev/null; then groupadd --system "$group"; fi
if ! id "$user" >/dev/null 2>&1; then
    useradd --system --gid "$group" --home-dir "$state" --shell /usr/bin/nologin "$user"
fi
usermod --append --groups "$group" "$lulu_user"

game_root=$(sudo -n -u "$lulu_user" env PYTHONPATH=/opt/lulu/dev-current/lib \
    python -c 'from lulu.paths import PATHS; print(PATHS.game_install_root)')
root="$game_root/.acquisition/torrents"
incomplete="$root/incomplete"
complete="$root/complete"
metainfo="$root/metainfo"
ownership="$root/ownership"
install -d -o "$user" -g "$group" -m 0750 "$state" "$incomplete" "$complete" "$metainfo" "$ownership"
install -d -o "$lulu_user" -g "$group" -m 0770 "$(dirname "$root")/.acquisition" "$root"
chgrp -R "$group" "$root"
chmod -R g+rwX,o-rwx "$root"
if command -v setfacl >/dev/null 2>&1; then
    # Transmission may apply its own 0644/0755 modes to completed content;
    # default ACLs keep the Mudos service able to remove only this provider
    # root without making the daemon run as the Mudos user.
    setfacl -R -m "u:$lulu_user:rwX,m:rwX" "$root"
    for child in "$incomplete" "$complete" "$metainfo" "$ownership"; do
        setfacl -m "u:$lulu_user:rwx,m:rwx" "$child"
        setfacl -d -m "u:$lulu_user:rwx,g::rwx,m:rwx" "$child"
    done
fi

settings="$state/settings.json"
if [ ! -e "$settings" ]; then
    rpc_user=lulu-mudos
    rpc_password=$(od -An -N24 -tx1 /dev/urandom | tr -d ' \n')
    cat >"$settings" <<EOF
{
    "rpc-enabled": true,
    "rpc-bind-address": "127.0.0.1",
    "rpc-port": 9091,
    "rpc-authentication-required": true,
    "rpc-username": "$rpc_user",
    "rpc-password": "$rpc_password",
    "rpc-whitelist-enabled": true,
    "rpc-whitelist": "127.0.0.1",
    "rpc-host-whitelist-enabled": true,
    "rpc-host-whitelist": "localhost,127.0.0.1",
    "download-dir": "$complete",
    "incomplete-dir": "$incomplete",
    "incomplete-dir-enabled": true,
    "watch-dir-enabled": false,
    "script-torrent-added-enabled": false,
    "script-torrent-done-enabled": false,
    "script-torrent-done-seeding-enabled": false,
    "start-added-torrents": true,
    "umask": "007",
    "peer-port-random-on-start": false,
    "port-forwarding-enabled": true
}
EOF
    chown "$user:$group" "$settings"
    chmod 0600 "$settings"
    sudo -n -u "$lulu_user" env PYTHONPATH=/opt/lulu/dev-current/lib \
        RPC_USER="$rpc_user" RPC_PASSWORD="$rpc_password" python - <<'PY'
import os
from lulu.credential import SecretStore
store = SecretStore()
store.put("torrent", "rpc-username", os.environ["RPC_USER"])
store.put("torrent", "rpc-password", os.environ["RPC_PASSWORD"])
PY
fi

provider_config=${LULU_PROVIDER_CONFIG:-/home/lulu/.config/lulu/provider-services.toml}
install -d -o "$lulu_user" -g "$lulu_user" -m 0750 "$(dirname "$provider_config")"
if ! grep -q '^\[providers\.torrent\]$' "$provider_config" 2>/dev/null; then
    cat >>"$provider_config" <<EOF

[providers.torrent]
enabled = true
backend = "transmission"
endpoint = "http://127.0.0.1:9091/transmission/rpc"
timeout_seconds = 10
label = "mudos"

[providers.torrent.secrets]
username = "torrent/rpc-username"
password = "torrent/rpc-password"
EOF
    chown "$lulu_user:$lulu_user" "$provider_config"
    chmod 0640 "$provider_config"
fi

unit=/etc/systemd/system/$service
if [ ! -e "$unit" ]; then
    cat >"$unit" <<EOF
[Unit]
Description=Mudos Transmission downloader
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$user
Group=$group
ExecStart=/usr/bin/transmission-daemon --foreground --config-dir=$state
Restart=on-failure
RestartSec=3
NoNewPrivileges=true
UMask=0007
PrivateTmp=true
ProtectSystem=full
ProtectHome=read-only
ReadWritePaths=$state $root

[Install]
WantedBy=multi-user.target
EOF
fi
systemctl daemon-reload
systemctl enable --now "$service"
echo "provisioned Transmission service=$service user=$user root=$root"
