#!/usr/bin/env bash
set -eu

config_root="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)/config/inputplumber"
sudo install -d -m 0755 /etc/inputplumber/devices.d
sudo ln -sfn "$config_root/devices/lulu-composite.yaml" \
  /etc/inputplumber/devices.d/lulu-composite.yaml
sudo systemctl restart inputplumber.service
