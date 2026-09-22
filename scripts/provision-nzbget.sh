#!/usr/bin/env bash
set -euo pipefail

repo_root=${LULU_SOURCE_ROOT:-$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)}
games=/home/lulu/Games
usenet="$games/.acquisition/usenet"
config=/var/lib/nzbget/nzbget.conf
secret_helper=${LULU_SECRET_HELPER_ROOT:-$repo_root}
if [[ -d "$secret_helper/lib" ]]; then secret_pythonpath="$secret_helper/lib"; else secret_pythonpath="$secret_helper/src"; fi

if [[ $(id -u) -ne 0 ]]; then
    exec sudo -n "$0" "$@"
fi

getent passwd nzbget >/dev/null || useradd --system --home-dir /var/lib/nzbget \
    --create-home --shell /usr/bin/nologin nzbget
install -d -o nzbget -g nzbget -m 0750 /var/lib/nzbget
setfacl -m u:lulu:rwx /var/lib/nzbget
install -d -o lulu -g lulu -m 2770 "$games/.acquisition" "$usenet"
setfacl -m u:lulu:rwx,u:nzbget:rwx "$games/.acquisition" "$usenet"
for directory in incomplete complete nzb ownership; do
    install -d -o nzbget -g lulu -m 2770 "$usenet/$directory"
    setfacl -m u:lulu:rwx,u:nzbget:rwx "$usenet/$directory"
done

secret_dir=/home/lulu/.local/share/lulu/secrets/usenet
secret_path="$secret_dir/rpc-password.cred"
if [[ ! -f "$secret_path" ]]; then
    password=$(python -c 'import secrets; print(secrets.token_urlsafe(32))')
    temporary=$(mktemp)
    trap 'rm -f "$temporary"' EXIT
    printf '%s' "$password" >"$temporary"
    chown lulu:lulu "$temporary"
    chmod 600 "$temporary"
    sudo -u lulu env HOME=/home/lulu USER=lulu LOGNAME=lulu \
        XDG_CONFIG_HOME=/home/lulu/.config XDG_DATA_HOME=/home/lulu/.local/share \
        LULU_SECRET_INPUT="$temporary" PYTHONPATH="$secret_pythonpath" \
        /usr/bin/python -c 'import os; from pathlib import Path; from lulu.credential import SecretStore; SecretStore().put("usenet", "rpc-password", Path(os.environ["LULU_SECRET_INPUT"]).read_text())'
    rm -f "$temporary"
else
    password=$(sudo -u lulu env HOME=/home/lulu USER=lulu LOGNAME=lulu \
        XDG_CONFIG_HOME=/home/lulu/.config XDG_DATA_HOME=/home/lulu/.local/share \
        PYTHONPATH="$secret_pythonpath" /usr/bin/python -c \
        'from lulu.credential import SecretStore; print(SecretStore().get("usenet", "rpc-password") or "")')
fi
[[ -n "$password" ]]
rpc_username=$(sudo -u lulu env HOME=/home/lulu USER=lulu LOGNAME=lulu \
    XDG_CONFIG_HOME=/home/lulu/.config XDG_DATA_HOME=/home/lulu/.local/share \
    PYTHONPATH="$secret_pythonpath" /usr/bin/python -c \
    'from lulu.provider_config import ProviderConfigurationService; print(ProviderConfigurationService.from_environment().provider("providers.usenet").get("username", "mudos"))')
[[ -n "$rpc_username" && "$rpc_username" != *$'\n'* ]]

install -d -m 0755 /etc/lulu
provider_config=/etc/lulu/provider-services.toml
if [[ ! -f "$provider_config" ]]; then
    cat >"$provider_config" <<'EOF'
[providers.usenet]
enabled = true
endpoint = "http://127.0.0.1:6789/jsonrpc"
username = "mudos"
category = "mudos"
dupe_prefix = "mudos:"

[providers.usenet.server]
host = ""
port = 563
tls = true
connections = 8

[providers.usenet.server.secrets]
username = "usenet/server-username"
password = "usenet/server-password"

[providers.usenet.secrets]
rpc_password = "usenet/rpc-password"
EOF
elif ! grep -q '^\[providers\.usenet\]$' "$provider_config"; then
    cat >>"$provider_config" <<'EOF'

[providers.usenet]
enabled = true
endpoint = "http://127.0.0.1:6789/jsonrpc"
username = "mudos"
category = "mudos"
dupe_prefix = "mudos:"

[providers.usenet.server]
host = ""
port = 563
tls = true
connections = 8

[providers.usenet.server.secrets]
username = "usenet/server-username"
password = "usenet/server-password"

[providers.usenet.secrets]
rpc_password = "usenet/rpc-password"
EOF
fi
if ! grep -q '^\[providers\.usenet\.server\]$' "$provider_config"; then
    cat >>"$provider_config" <<'EOF'

[providers.usenet.server]
host = ""
port = 563
tls = true
connections = 8

[providers.usenet.server.secrets]
username = "usenet/server-username"
password = "usenet/server-password"
EOF
fi

cat >"$config" <<EOF
MainDir=$usenet
DestDir=$usenet/complete
InterDir=$usenet/incomplete
NzbDir=$usenet/nzb
QueueDir=/var/lib/nzbget/queue
ScriptDir=/var/lib/nzbget/scripts
LogFile=/var/lib/nzbget/nzbget.log
ControlIP=0.0.0.0
ControlPort=6789
ControlUsername=$rpc_username
ControlPassword=$password
SecureControl=no
AppendCategoryDir=no
Category1.Name=mudos
Category1.DestDir=$usenet/complete
Category1.Unpack=yes
PostStrategy=balanced
Unpack=yes
WriteLog=none
OutputMode=log
EOF
sudo -u lulu env HOME=/home/lulu USER=lulu LOGNAME=lulu \
    XDG_CONFIG_HOME=/home/lulu/.config XDG_DATA_HOME=/home/lulu/.local/share \
    PYTHONPATH="$secret_pythonpath" /usr/bin/python -c \
    'from lulu.nzbget_admin import apply_packaged_paths; apply_packaged_paths()'
chown nzbget:nzbget "$config"
usermod --append --groups lulu nzbget
chown nzbget:lulu "$config"
chmod 0660 "$config"
sudo -u lulu env HOME=/home/lulu USER=lulu LOGNAME=lulu \
    XDG_CONFIG_HOME=/home/lulu/.config XDG_DATA_HOME=/home/lulu/.local/share \
    PYTHONPATH="$secret_pythonpath" /usr/bin/python - <<'PY'
from lulu.provider_config import ProviderConfigurationService
from lulu.nzbget_admin import apply_news_server
service = ProviderConfigurationService.from_environment()
server = service.provider("providers.usenet.server")
if server.get("host"):
    apply_news_server(str(server.get("host")), int(server.get("port", 563)),
                      bool(server.get("tls", True)), int(server.get("connections", 8)),
                      server.secret("username") or "", server.secret("password") or "",
                      bool(server.get("enabled", True)))
PY
chown nzbget:lulu "$config"
chmod 0660 "$config"
systemctl daemon-reload
systemctl enable --now nzbget.service
systemctl restart nzbget.service
echo "provisioned NZBGet $(pacman -Q nzbget | awk '{print $2}') with LAN-authenticated RPC"
