#!/usr/bin/env bash
set -eu

config_root="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)/packaging/pipewire"
target_root=/var/lib/lulu/.config/pipewire/pipewire-pulse.conf.d

sudo install -d -o lulu -g lulu -m 0700 "$target_root"
sudo install -o lulu -g lulu -m 0644 \
  "$config_root/lulu-fallback-input.conf" \
  "$target_root/lulu-fallback-input.conf"

echo "Installed Lulu fallback capture configuration. Restart lulu's pipewire-pulse session to apply it."
