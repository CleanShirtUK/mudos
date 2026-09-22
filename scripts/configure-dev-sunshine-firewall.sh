#!/usr/bin/env bash
set -euo pipefail

# Development-only Sunshine LAN policy. Keep this explicit and scoped to the
# trusted home subnet; do not enable UPnP or expose Sunshine beyond wlan0.
if ! command -v ufw >/dev/null 2>&1 || ! systemctl is-active --quiet ufw; then
    exit 0
fi

"$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)/configure-acquisition-firewall.sh"

interface=${LULU_LAN_INTERFACE:-wlan0}
subnet=$(ip -4 route show dev "$interface" proto kernel scope link | awk 'NR == 1 {print $1}')
subnet=${subnet:-192.168.0.0/24}
ufw allow in on "$interface" from "$subnet" to any port 47984:47990 proto tcp
ufw allow in on "$interface" from "$subnet" to any port 48010 proto tcp
ufw allow in on "$interface" from "$subnet" to any port 47998:48000 proto udp
ufw allow in on "$interface" from "$subnet" to any port 48002 proto udp
ufw allow in on "$interface" from "$subnet" to any port 48010 proto udp
