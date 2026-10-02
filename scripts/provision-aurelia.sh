#!/usr/bin/env bash
set -euo pipefail

# Install the pinned upstream CLI as a package-owned executable. The provider
# remains disabled; this script does not authenticate to Steam or touch its
# libraries/session state.
script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
repo_root=$(CDPATH= cd -- "$script_dir/.." && pwd)
build_dir=$(mktemp -d /var/tmp/lulu-aurelia-build.XXXXXX)
trap 'rm -rf "$build_dir"' EXIT
chown lulu:lulu "$build_dir"
install -m 0644 "$repo_root/packages/aurelia/PKGBUILD" "$build_dir/PKGBUILD"
runuser -u lulu -- makepkg --cleanbuild --noconfirm --nodeps --dir "$build_dir"
package=$(find "$build_dir" -maxdepth 1 -type f -name 'aurelia-*.pkg.tar.*' -print -quit)
if [[ -z "$package" ]]; then
    echo 'Aurelia package build produced no installable package' >&2
    exit 1
fi
pacman -U --needed --noconfirm "$package"
