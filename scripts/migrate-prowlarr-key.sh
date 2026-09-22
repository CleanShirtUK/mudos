#!/usr/bin/env bash
set -euo pipefail

if [[ $(id -u) -ne 0 ]]; then
    exec sudo -n "$0" "$@"
fi

source=${PROWLARR_HANDOFF:-/home/josh/PROWLARR_API_KEY.rtf}
user=${LULU_PROVIDER_CONFIG_USER:-lulu}
pythonpath=${LULU_INSTALL_ROOT:-/opt/lulu/dev-current}/lib
key=$(python - "$source" <<'PY'
from pathlib import Path
import re
import sys

keys = re.findall(r"[A-Za-z0-9_-]{32}", Path(sys.argv[1]).read_text(errors="ignore"))
if len(keys) != 1:
    raise SystemExit("Prowlarr handoff did not contain exactly one API key")
print(keys[0])
PY
)

printf '%s' "$key" | sudo -n -u "$user" env HOME="/home/$user" USER="$user" \
    XDG_CONFIG_HOME="/home/$user/.config" XDG_DATA_HOME="/home/$user/.local/share" \
    PYTHONPATH="$pythonpath" python -c '
import sys
from lulu.provider_config import ProviderConfigurationService

value = sys.stdin.read()
ProviderConfigurationService.from_environment().update_provider(
    "providers.prowlarr",
    {"enabled": True, "endpoint": "http://192.168.0.197:9696/",
     "secrets": {"api_key": "prowlarr/api-key"}},
    {"api_key": value},
)
'
unset key
echo "migrated Prowlarr credential into Mudos SecretStore"
