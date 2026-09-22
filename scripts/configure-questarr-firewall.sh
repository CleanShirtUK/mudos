#!/bin/sh
set -eu

command -v ufw >/dev/null 2>&1 || exit 0
systemctl is-active --quiet ufw || exit 0

interface=${LULU_LAN_INTERFACE:-$(ip -4 route show default | awk 'NR == 1 {print $5}')}
subnet=${LULU_LAN_SUBNET:-$(ip -4 route show dev "$interface" proto kernel scope link | awk 'NR == 1 {print $1}')}
[ -n "$interface" ] || exit 0
[ -n "$subnet" ] || subnet=192.168.0.0/24

ufw allow in on "$interface" from "$subnet" to any port 5000 proto tcp comment 'Mudos Questarr'
