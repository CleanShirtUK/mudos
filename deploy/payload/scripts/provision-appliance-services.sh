#!/usr/bin/env bash
set -euo pipefail

# Common normal-install/OOBE provisioning entrypoint.  Frontends remain
# optional: providers can still be configured by other Mudos boundaries.
root=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
# Qt WebEngine and the image-format plugins are shell runtime dependencies,
# not provider dependencies. In particular, animated WebP previews require
# the version-matched Qt image-format plugin.
# Keep installation in the normal provisioning path so releases and the
# development runtime do not depend on an ad-hoc host package install.
pacman -S --needed --noconfirm qt6-webengine qt6-imageformats ffmpeg python-pillow
"$root/provision-admin.sh"
"$root/provision-acquisition-services.sh"
# Optional PC entitlement backends are independently idempotent.  They are
# installed only when explicitly requested so a base appliance remains
# offline-safe and does not pull frontend launchers into the image.
if [[ "${LULU_PROVISION_PC_PROVIDERS:-0}" == "1" ]]; then
    "$root/provision-gogdl.sh"
    "$root/provision-legendary.sh"
    "$root/provision-umu.sh"
fi
