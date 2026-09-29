#!/usr/bin/env bash
set -euo pipefail

if [[ $(id -u) -ne 0 ]]; then
    exec sudo -n "$0" "$@"
fi

repo_root=${LULU_SOURCE_ROOT:-$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)}
data_root=${LULU_QUESTARR_DATA_ROOT:-/var/lib/lulu-questarr}
install -d -o lulu -g lulu -m 0750 "$data_root/data"

pacman -S --needed --noconfirm podman git
LULU_SOURCE_ROOT="$repo_root" "$repo_root/scripts/build-questarr-image.sh"

install -m 0644 "$repo_root/packaging/lulu-questarr.service" /etc/systemd/system/lulu-questarr.service
install -m 0644 "$repo_root/packaging/lulu-questarr-auth-proxy.service" /etc/systemd/system/lulu-questarr-auth-proxy.service
install -m 0644 "$repo_root/packaging/lulu-questarr-pam-auth.service" /etc/systemd/system/lulu-questarr-pam-auth.service
chmod 0755 "$repo_root/scripts/configure-questarr-firewall.sh"
"$repo_root/scripts/configure-questarr-firewall.sh"
systemctl daemon-reload
systemctl enable lulu-questarr.service
systemctl restart lulu-questarr.service
systemctl enable --now lulu-questarr-pam-auth.service
systemctl enable --now lulu-questarr-auth-proxy.service

echo "provisioned Questarr data=$data_root endpoint=http://mudos.local:5000/"
