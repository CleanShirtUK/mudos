#!/usr/bin/env bash
set -euo pipefail

source=/opt/lulu/current/scripts/bc250-fancurve
target=/usr/local/bin/bc250-fancurve

if [[ ! -f "$source" ]]; then
    echo "BC-250 fan curve controller is missing from the active release: $source" >&2
    exit 1
fi

if cmp -s "$source" "$target"; then
    echo "BC-250 fan curve controller is already current"
    exit 0
fi

install -o root -g root -m 0755 "$source" "$target"
systemctl restart bc250-fancurve.service
