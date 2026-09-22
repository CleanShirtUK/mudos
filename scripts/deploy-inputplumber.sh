#!/usr/bin/env bash
set -eu

repo_root="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
sudo install -d -m 0755 /etc/inputplumber/devices.d
sudo "$repo_root/scripts/provision-inputplumber-gamepads.py" \
  /etc/inputplumber/devices.d/lulu-composite.yaml
sudo systemctl restart inputplumber.service
