#!/usr/bin/env bash
set -euo pipefail

# Normal appliance policy: local administration services are LAN-only. This is
# deliberately separate from Sunshine so installs without remote streaming
# still receive the service firewall policy.
command -v ufw >/dev/null 2>&1 || exit 0
systemctl is-active --quiet ufw || exit 0

interface=${LULU_LAN_INTERFACE:-}
if [[ -z "$interface" ]]; then
    interface=$(ip -4 route show default | awk 'NR == 1 {print $5}')
fi
subnet=$(ip -4 route show dev "$interface" proto kernel scope link | awk 'NR == 1 {print $1}')
subnet=${subnet:-192.168.0.0/24}

ufw allow in on "$interface" from "$subnet" to any port 6789 proto tcp
ufw allow in on "$interface" from "$subnet" to any port 9091 proto tcp
ufw allow in on "$interface" from "$subnet" to any port 80 proto tcp
ufw allow in on "$interface" from "$subnet" to any port 8080 proto tcp comment 'Mudos file browser'
