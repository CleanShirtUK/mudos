#!/bin/sh
set -eu

# Create the ordinary provider configuration boundary without replacing an
# operator's configuration. Secrets are deliberately not provisioned here.
if [ "$(id -u)" -ne 0 ]; then
    exec sudo -n "$0" "$@"
fi

root=${LULU_PROVIDER_CONFIG_ROOT:-/home/lulu/.config/lulu}
user=${LULU_PROVIDER_CONFIG_USER:-lulu}
destination="$root/provider-services.toml"
template=${LULU_PROVIDER_CONFIG_TEMPLATE:-"$(CDPATH= cd -- "$(dirname -- "$0")/../config" && pwd)/provider-services.toml.example"}

install -d -o "$user" -g "$user" -m 0750 "$root"
if [ -e "$destination" ]; then
    echo "provider configuration already exists: $destination"
    exit 0
fi
install -o "$user" -g "$user" -m 0640 "$template" "$destination"
echo "provisioned provider configuration: $destination"
