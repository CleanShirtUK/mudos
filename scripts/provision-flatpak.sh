#!/usr/bin/env bash
set -euo pipefail

# Controlled native dependency boundary for the optional Flatpak component.
# This script is intentionally separate from QML and application launch code.
pacman -S --needed --noconfirm flatpak python-gobject

# Flathub is added only to the Mudos user scope and only when absent. Existing
# remotes in either scope are preserved. Flatpak owns repository state.
if id lulu >/dev/null 2>&1; then
    runuser -u lulu -- env HOME=/home/lulu XDG_DATA_HOME=/home/lulu/.local/share \
        flatpak --user remote-add --if-not-exists flathub \
        https://dl.flathub.org/repo/flathub.flatpakrepo
fi

echo "provisioned Flatpak $(flatpak --version)"
