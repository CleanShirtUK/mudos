#!/bin/sh
set -eu

repo_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
output=${1:-"$repo_root/ui/shaders/presentation-motion-blur.frag.qsb"}

/usr/lib/qt6/bin/qsb --qt6 --batchable -o "$output" \
    "$repo_root/ui/shaders/presentation-motion-blur.frag"
