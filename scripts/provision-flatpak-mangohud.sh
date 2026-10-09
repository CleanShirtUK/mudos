#!/usr/bin/env bash
set -euo pipefail

# Provision only the extension branch declared by the selected application's
# runtime. This adds no Flatpak override and grants no additional permissions.
scope=${1:---user}
app=${2:?usage: provision-flatpak-mangohud.sh [--user|--system] APP_ID}
case "$scope" in --user|--system) ;; *) echo "invalid Flatpak scope: $scope" >&2; exit 64 ;; esac

runtime=$(flatpak "$scope" info --show-runtime "$app")
metadata=$(flatpak "$scope" info --show-metadata "$runtime")
branch=$(printf '%s\n' "$metadata" | python -c '
import configparser, sys
metadata = configparser.ConfigParser(interpolation=None, strict=False)
metadata.read_string(sys.stdin.read())
print(metadata.get("Extension org.freedesktop.Platform.VulkanLayer", "version", fallback=""))
')
if [[ -z $branch ]]; then
    echo "Runtime for $app does not expose the Freedesktop VulkanLayer extension point" >&2
    exit 2
fi

extension=org.freedesktop.Platform.VulkanLayer.MangoHud
if flatpak list "$scope" --runtime --columns=application,branch \
        | grep -Fqx "$extension$(printf '\t')$branch"; then
    exit 0
fi
flatpak install "$scope" --noninteractive --assumeyes flathub "$extension//$branch"
