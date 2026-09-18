#!/bin/sh
set -eu

repo_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
/usr/lib/qt6/bin/qsb --qt6 --batchable \
    -o "$repo_root/ui/shaders/depth-gaussian-blur.frag.qsb" \
    "$repo_root/ui/shaders/depth-gaussian-blur.frag"
