#!/bin/sh
set -eu

# Install the official Valve Linux SteamCMD runtime without touching Steam's
# authenticated client/cache. The runtime is mutable appliance state.
if [ "$(id -u)" -ne 0 ]; then
    exec sudo -n "$0" "$@"
fi

root=${LULU_STEAMCMD_ROOT:-/var/lib/lulu/steamcmd}
user=${LULU_STEAMCMD_USER:-lulu}
url=${LULU_STEAMCMD_URL:-https://steamcdn-a.akamaihd.net/client/installer/steamcmd_linux.tar.gz}
expected=${LULU_STEAMCMD_SHA256:-}
archive=$(mktemp /var/tmp/lulu-steamcmd.XXXXXX.tar.gz)
stage=$(mktemp -d /var/tmp/lulu-steamcmd.XXXXXX)
trap 'rm -f "$archive"; rm -rf "$stage"' EXIT

getent passwd "$user" >/dev/null
install -d -o "$user" -g "$user" -m 0755 "$(dirname "$root")"

if [ -x "$root/steamcmd.sh" ]; then
    echo "SteamCMD already provisioned at $root/steamcmd.sh"
    exit 0
fi

curl --fail --location --proto '=https' --tlsv1.2 --silent --show-error "$url" -o "$archive"
if [ -n "$expected" ]; then
    printf '%s  %s\n' "$expected" "$archive" | sha256sum --check --status -
fi
tar -xzf "$archive" -C "$stage"
[ -f "$stage/steamcmd.sh" ]
chmod 0755 "$stage/steamcmd.sh"
chown -R "$user:$user" "$stage"

temporary=${root}.new.$$
rm -rf "$temporary"
mv "$stage" "$temporary"
if [ -e "$root" ]; then
    backup=${root}.previous.$$
    mv "$root" "$backup"
    mv "$temporary" "$root"
    rm -rf "$backup"
else
    mv "$temporary" "$root"
fi
chown -R "$user:$user" "$root"

# +quit validates startup. No login command is supplied, so authentication is
# neither created nor migrated.
runuser -u "$user" -- env HOME="$(getent passwd "$user" | cut -d: -f6)" \
    "$root/steamcmd.sh" +quit >/dev/null
echo "provisioned and verified $root/steamcmd.sh"
