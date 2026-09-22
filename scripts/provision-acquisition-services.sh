#!/usr/bin/env bash
set -euo pipefail

# Standard appliance provisioning entrypoint.  Development refreshes and
# future OOBE/install flows use this same idempotent path.
root=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
"$root/provision-nzbget.sh"
"$root/provision-transmission.sh"
"$root/configure-acquisition-firewall.sh"
