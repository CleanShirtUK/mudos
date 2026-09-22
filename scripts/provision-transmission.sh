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
runtime_root=${LULU_INSTALL_ROOT:-$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)}
if [ -d "$runtime_root/lib" ]; then provider_pythonpath="$runtime_root/lib"; else provider_pythonpath=/opt/lulu/dev-current/lib; fi

pacman -S --needed --noconfirm transmission-cli
if ! getent group "$group" >/dev/null; then groupadd --system "$group"; fi
if ! id "$user" >/dev/null 2>&1; then
    useradd --system --gid "$group" --home-dir "$state" --shell /usr/bin/nologin "$user"
fi
usermod --append --groups "$group" "$lulu_user"
# The acquisition parent is intentionally owned by Mudos (group `lulu`).
# Transmission needs only supplementary traversal/write access to its own
# provider root; it must not own the Games tree.
usermod --append --groups "$lulu_user" "$user"

game_root=$(sudo -n -u "$lulu_user" env HOME="/home/$lulu_user" \
    PYTHONPATH="$provider_pythonpath" \
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
lan_interface=${LULU_LAN_INTERFACE:-$(ip -4 route show default | awk 'NR == 1 {print $5}')}
lan_cidr=$(ip -4 route show dev "$lan_interface" proto kernel scope link \
    | awk 'NR == 1 {print $1}')
lan_prefix=${lan_cidr%/*}
if [ -z "$lan_prefix" ] || [ "$lan_prefix" = "$lan_cidr" ]; then
    lan_prefix=192.168.0
else
    lan_prefix=$(printf '%s' "$lan_prefix" | awk -F. '{print $1 "." $2 "." $3}')
fi
systemctl stop "$service" 2>/dev/null || true
if [ ! -e "$settings" ]; then
    rpc_user=lulu-mudos
    rpc_password=$(od -An -N24 -tx1 /dev/urandom | tr -d ' \n')
    cat >"$settings" <<EOF
{
    "rpc-enabled": true,
    "rpc-bind-address": "0.0.0.0",
    "rpc-port": 9091,
    "rpc-authentication-required": true,
    "rpc-username": "$rpc_user",
    "rpc-password": "$rpc_password",
    "rpc-whitelist-enabled": true,
    "rpc-whitelist": "127.0.0.1,$lan_prefix.*",
    "rpc-host-whitelist-enabled": true,
    "rpc-host-whitelist": "localhost,127.0.0.1,$(hostname -s),$(hostname -f 2>/dev/null || true)",
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
    "port-forwarding-enabled": false
}
EOF
    chown "$user:$group" "$settings"
    chmod 0600 "$settings"
    sudo -n -u "$lulu_user" env HOME="/home/$lulu_user" \
        XDG_CONFIG_HOME=/home/lulu/.config XDG_DATA_HOME=/home/lulu/.local/share \
        PYTHONPATH="$provider_pythonpath" \
        RPC_USER="$rpc_user" RPC_PASSWORD="$rpc_password" python - <<'PY'
import os
from lulu.credential import SecretStore
store = SecretStore()
store.put("torrent", "rpc-username", os.environ["RPC_USER"])
store.put("torrent", "rpc-password", os.environ["RPC_PASSWORD"])
PY
fi

# Apply the appliance LAN policy on every rerun without replacing the
# existing SecretStore-backed credentials or unrelated Transmission settings.
python - "$settings" "$lan_prefix" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
lan_prefix = sys.argv[2]
value = json.loads(path.read_text())
original = dict(value)
value.update({
    "rpc-enabled": True,
    "rpc-bind-address": "0.0.0.0",
    "rpc-authentication-required": True,
    "rpc-whitelist-enabled": True,
    "rpc-whitelist": f"127.0.0.1,{lan_prefix}.*",
    "rpc-host-whitelist-enabled": True,
    "rpc-host-whitelist": "localhost,127.0.0.1," + __import__("socket").gethostname(),
    "port-forwarding-enabled": False,
})
if value != original:
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(value, indent=4, sort_keys=True) + "\n")
    temporary.replace(path)
PY
chown "$user:$group" "$settings"
# lulu is a supplementary member of the daemon group so the narrow Admin
# boundary can materialize credentials without granting generic root access.
chmod 0660 "$settings"

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
SupplementaryGroups=$lulu_user
ExecStart=/usr/bin/transmission-daemon --foreground --config-dir=$state
ExecStartPost=/usr/bin/chmod 0660 $settings
Restart=on-failure
RestartSec=3
TimeoutStopSec=60s
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
# Older generated units omitted the longer clean-stop window. Repair them on
# every provisioning pass without replacing the unit or touching torrent data.
if grep -q '^TimeoutStopSec=' "$unit"; then
    sed -i 's/^TimeoutStopSec=.*/TimeoutStopSec=60s/' "$unit"
else
    sed -i '/^RestartSec=/a TimeoutStopSec=60s' "$unit"
fi
if ! grep -q '^ExecStartPost=/usr/bin/chmod 0660 ' "$unit"; then
    sed -i "/^ExecStart=\/usr\/bin\/transmission-daemon /a ExecStartPost=/usr/bin/chmod 0660 $settings" "$unit"
fi
systemctl daemon-reload
systemctl enable --now "$service"
systemctl start lulu-transmission-config.service 2>/dev/null || true
echo "provisioned Transmission service=$service user=$user root=$root"
