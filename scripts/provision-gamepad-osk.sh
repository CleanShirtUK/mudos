#!/bin/sh
set -eu

if [ "$(id -u)" -ne 0 ]; then
    exec sudo -n "$0" "$@"
fi

version=${LULU_GAMEPAD_OSK_VERSION:-v2.1.1}
url=${LULU_GAMEPAD_OSK_URL:-https://github.com/0x90shell/gamepad-osk/releases/download/$version/gamepad-osk}
sha=${LULU_GAMEPAD_OSK_SHA256:-4bc9b0f4fbb73da1c67a06cdbc08ef7300a2031b2d5e2a3d70e007490db7c1cc}
root=${LULU_GAMEPAD_OSK_ROOT:-/var/lib/lulu/gamepad-osk}
repo_root=${LULU_INSTALL_ROOT:-/opt/lulu/current}
archive=$(mktemp /var/tmp/lulu-gamepad-osk.XXXXXX)
trap 'rm -f "$archive"' EXIT

pacman --needed --noconfirm -S sdl3 sdl3_ttf
install -d -o lulu -g lulu -m 0755 "$root"
if [ ! -x "$root/gamepad-osk" ]; then
    curl --fail --location --proto '=https' --tlsv1.2 --silent --show-error "$url" -o "$archive"
    printf '%s  %s\n' "$sha" "$archive" | sha256sum --check --status
    install -o lulu -g lulu -m 0755 "$archive" "$root/gamepad-osk"
fi
sudo -n -u lulu "$root/gamepad-osk" --version >/dev/null
if [ -f "$repo_root/packaging/udev/80-lulu-osk.rules" ]; then
    install -D -o root -g root -m 0644 "$repo_root/packaging/udev/80-lulu-osk.rules" \
        /etc/udev/rules.d/80-lulu-osk.rules
    udevadm control --reload-rules
fi
echo "provisioned $root/gamepad-osk ($version)"
