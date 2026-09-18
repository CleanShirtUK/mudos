#!/bin/sh
set -eu

repo_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
qsb=/usr/lib/qt6/bin/qsb
for axis in horizontal vertical; do
    "$qsb" --qt6 --batchable \
        -o "$repo_root/ui/shaders/mudos-blur-$axis.frag.qsb" \
        "$repo_root/ui/shaders/mudos-blur-$axis.frag"
done
