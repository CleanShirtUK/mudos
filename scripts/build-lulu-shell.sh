#!/bin/sh
set -eu

repo_root=${LULU_INSTALL_ROOT:-$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)}
output=${1:-"$repo_root/build/lulu-shell"}

if ! pkg-config --exists Qt6Gui Qt6Qml Qt6Quick xcb; then
    printf '%s\n' 'lulu-shell build requires Qt6 Gui/Qml/Quick and xcb pkg-config files' >&2
    exit 1
fi

mkdir -p "$(dirname -- "$output")"
exec g++ -std=c++17 -O2 -fPIC -Wall -Wextra \
    "$repo_root/native/lulu-shell.cpp" \
    -o "$output" \
    $(pkg-config --cflags --libs Qt6Gui Qt6Qml Qt6Quick xcb) \
    -no-pie
