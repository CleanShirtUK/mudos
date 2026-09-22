#!/bin/sh
set -eu

repo_root=${LULU_INSTALL_ROOT:-$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)}
output=${1:-"$repo_root/build/lulu-shell"}

if ! pkg-config --exists Qt6DBus Qt6Gui Qt6Multimedia Qt6Qml Qt6Quick Qt6WebEngineQuick xcb xcb-xtest xcb-keysyms sdl3; then
    printf '%s\n' 'lulu-shell build requires Qt6 DBus/Gui/Multimedia/Qml/Quick/WebEngineQuick, xcb, and sdl3 pkg-config files' >&2
    exit 1
fi

mkdir -p "$(dirname -- "$output")"
repo_build=$(dirname -- "$output")
/usr/lib/qt6/moc "$repo_root/native/lulu-shell.cpp" -o "$repo_build/lulu-shell.moc"
/usr/lib/qt6/moc "$repo_root/native/mudos-glass-item.h" -o "$repo_build/mudos-glass-item_moc.cpp"
/usr/lib/qt6/moc "$repo_root/native/catalogue-model.h" -o "$repo_build/catalogue-model_moc.cpp"
/usr/lib/qt6/moc "$repo_root/native/recent-model.h" -o "$repo_build/recent-model_moc.cpp"
g++ -std=c++17 -O2 -fPIC -Wall -Wextra -I"$repo_build" \
    "$repo_root/native/lulu-shell.cpp" \
    "$repo_root/native/catalogue-model.cpp" \
    "$repo_root/native/recent-model.cpp" \
    "$repo_root/native/mudos-glass-item.cpp" \
    "$repo_build/catalogue-model_moc.cpp" \
    "$repo_build/recent-model_moc.cpp" \
    "$repo_build/mudos-glass-item_moc.cpp" \
    -o "$output" \
    $(pkg-config --cflags --libs Qt6DBus Qt6Gui Qt6Multimedia Qt6Qml Qt6Quick Qt6WebEngineQuick xcb xcb-keysyms sdl3) \
    -no-pie

g++ -std=c++17 -O2 -fPIC -Wall -Wextra \
    "$repo_root/native/mudos-guide.cpp" \
    -o "$repo_build/mudos-guide" \
    $(pkg-config --cflags --libs Qt6DBus Qt6Gui Qt6Qml Qt6Quick xcb xcb-xtest xcb-keysyms) \
    -no-pie
