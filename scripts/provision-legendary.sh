#!/usr/bin/env bash
set -Eeuo pipefail

readonly ROOT=${LULU_PROVIDER_TOOL_ROOT:-/var/lib/lulu/provider-tools/legendary}
readonly VENV="$ROOT/venv"
mkdir -p "$ROOT"
if [[ ! -x "$VENV/bin/legendary" ]]; then
    python3 -m venv "$VENV"
    "$VENV/bin/pip" install --upgrade legendary-gl
fi
test -x "$VENV/bin/legendary"
"$VENV/bin/legendary" --version
install -Dm755 "$VENV/bin/legendary" /usr/local/bin/legendary
echo "provisioned Legendary at $VENV/bin/legendary"
