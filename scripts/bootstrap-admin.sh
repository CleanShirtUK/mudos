#!/usr/bin/env bash
set -euo pipefail
if [[ $(id -u) -ne 0 ]]; then exec sudo -n "$0" "$@"; fi
runtime=${LULU_INSTALL_ROOT:-}
if [[ -z "$runtime" ]]; then
    [[ -d /opt/lulu/dev-current/lib ]] && runtime=/opt/lulu/dev-current || runtime=/opt/lulu/current
fi
if [[ -n "${MUDOS_ADMIN_PASSWORD_FILE:-}" ]]; then
    password=$(cat "$MUDOS_ADMIN_PASSWORD_FILE")
    repeat=$password
else
    read -r -s -p "Mudos admin password: " password; echo
    read -r -s -p "Repeat password: " repeat; echo
fi
[[ -n "$password" && "$password" == "$repeat" ]] || { echo "Passwords do not match or are empty" >&2; exit 1; }
temporary=$(mktemp); trap 'rm -f "$temporary"' EXIT
printf '%s' "$password" > "$temporary"; chown lulu:lulu "$temporary"; chmod 600 "$temporary"
sudo -u lulu env HOME=/home/lulu USER=lulu LOGNAME=lulu \
    XDG_CONFIG_HOME=/home/lulu/.config XDG_DATA_HOME=/home/lulu/.local/share \
    PYTHONPATH="$runtime/lib" ADMIN_PASSWORD_FILE="$temporary" /usr/bin/python - <<'PY'
import base64, hashlib, os, secrets
from pathlib import Path
from lulu.credential import SecretStore
password=Path(os.environ["ADMIN_PASSWORD_FILE"]).read_text()
salt=secrets.token_bytes(16)
digest=hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 240000)
value="pbkdf2-sha256$240000$%s$%s" % (base64.urlsafe_b64encode(salt).decode(), base64.urlsafe_b64encode(digest).decode())
SecretStore().put("admin", "password-hash", value)
PY
systemctl restart lulu-admin.service 2>/dev/null || true
echo "Mudos admin credential configured. Visit http://mudos.local/"
