#!/usr/bin/env bash
set -euo pipefail

if [[ $(id -u) -ne 0 ]]; then
    exec sudo -n "$0" "$@"
fi

repo_root=${LULU_SOURCE_ROOT:-$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)}
data_root=${LULU_QUESTARR_DATA_ROOT:-/var/lib/lulu-questarr}
install -d -o lulu -g lulu -m 0750 "$data_root/data"

pacman -S --needed --noconfirm podman
podman pull ghcr.io/doezer/questarr@sha256:6faaf75f484a20805309315dd9eb9f1550b039a668efb89c13fc028c72b45485

install -m 0644 "$repo_root/packaging/lulu-questarr.service" /etc/systemd/system/lulu-questarr.service
install -m 0644 "$repo_root/packaging/lulu-questarr-auth-proxy.service" /etc/systemd/system/lulu-questarr-auth-proxy.service
chmod 0755 "$repo_root/scripts/configure-questarr-firewall.sh"
"$repo_root/scripts/configure-questarr-firewall.sh"
systemctl daemon-reload
systemctl enable lulu-questarr.service
systemctl restart lulu-questarr.service
systemctl enable --now lulu-questarr-auth-proxy.service

echo "provisioned Questarr data=$data_root endpoint=http://mudos.local:5000/"
