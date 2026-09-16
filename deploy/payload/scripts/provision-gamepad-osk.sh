#!/bin/sh
set -eu

if [ "$(id -u)" -ne 0 ]; then
    exec sudo -n "$0" "$@"
fi

version=${LULU_GAMEPAD_OSK_VERSION:-v2.1.1}
url=${LULU_GAMEPAD_OSK_URL:-https://github.com/0x90shell/gamepad-osk/archive/refs/tags/$version.tar.gz}
sha=${LULU_GAMEPAD_OSK_SHA256:-9b4082f2abe8a13adbbfd7c7079b227b3ad5384a9e4ae2d1a22a19169a6287a8}
root=${LULU_GAMEPAD_OSK_ROOT:-/var/lib/lulu/gamepad-osk}
repo_root=${LULU_INSTALL_ROOT:-/opt/lulu/current}
archive=$(mktemp /var/tmp/lulu-gamepad-osk.XXXXXX)
build_root=$(mktemp -d /var/tmp/lulu-gamepad-osk-build.XXXXXX)
trap 'rm -f "$archive"; rm -rf "$build_root"' EXIT

pacman --needed --noconfirm -S go sdl3 sdl3_ttf libx11
install -d -o lulu -g lulu -m 0755 "$root"
curl --fail --location --proto '=https' --tlsv1.2 --silent --show-error "$url" -o "$archive"
printf '%s  %s\n' "$sha" "$archive" | sha256sum --check --status
tar -xzf "$archive" --strip-components=1 -C "$build_root"
patch -d "$build_root" -p1 < "$repo_root/packaging/gamepad-osk-gamescope-overlay.patch"
chown -R lulu:lulu "$build_root"
sudo -n -u lulu sh -c "cd '$build_root' && go build -o gamepad-osk ."
install -o lulu -g lulu -m 0755 "$build_root/gamepad-osk" "$root/gamepad-osk"
sudo -n -u lulu "$root/gamepad-osk" --version >/dev/null
if [ -f "$repo_root/packaging/udev/80-lulu-osk.rules" ]; then
    install -D -o root -g root -m 0644 "$repo_root/packaging/udev/80-lulu-osk.rules" \
        /etc/udev/rules.d/80-lulu-osk.rules
    udevadm control --reload-rules
fi
echo "provisioned $root/gamepad-osk ($version, Gamescope X11 overlay)"
