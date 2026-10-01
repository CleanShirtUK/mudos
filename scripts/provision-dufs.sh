#!/usr/bin/env bash
set -euo pipefail

# DUFS is a core Mudos service, not an OOBE-selected provider. Build its
# checksum-pinned upstream binary package as the appliance user, then install
# through pacman so package ownership and future upgrades remain truthful.
script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
repo_root=$(CDPATH= cd -- "$script_dir/.." && pwd)
build_dir=$(mktemp -d /var/tmp/lulu-dufs-build.XXXXXX)
trap 'rm -rf "$build_dir"' EXIT
chown lulu:lulu "$build_dir"
install -m 0644 "$repo_root/packages/dufs/PKGBUILD" "$build_dir/PKGBUILD"
runuser -u lulu -- makepkg --cleanbuild --noconfirm --nodeps --dir "$build_dir"
package=$(find "$build_dir" -maxdepth 1 -type f -name 'dufs-*.pkg.tar.*' -print -quit)
if [[ -z "$package" ]]; then
    echo 'DUFS package build produced no installable package' >&2
    exit 1
fi
pacman -U --needed --noconfirm "$package"

config=/etc/lulu/file-browser.env
install -d -o root -g root -m 0755 /etc/lulu
if [[ ! -e "$config" ]]; then
    password=$(od -An -N24 -tx1 /dev/urandom | tr -d ' \n')
    temporary=$(mktemp /etc/lulu/.file-browser.env.XXXXXX)
    cat >"$temporary" <<EOF
# Mudos-managed DUFS configuration. Do not expose host paths beyond /srv.
DUFS_BIND=0.0.0.0
DUFS_PORT=8080
DUFS_AUTH=admin:${password}@/:rw
DUFS_ALLOW_UPLOAD=true
DUFS_ALLOW_DELETE=true
DUFS_ALLOW_SEARCH=true
DUFS_ALLOW_ARCHIVE=true
DUFS_ALLOW_SYMLINK=false
DUFS_HIDDEN=.*,*~
EOF
    chown root:root "$temporary"
    chmod 0600 "$temporary"
    mv -n "$temporary" "$config"
fi
chown root:root "$config"
chmod 0600 "$config"

# DUFS listens on 8080; expose it only to the current LAN subnet/interface.
"$repo_root/scripts/configure-acquisition-firewall.sh"
