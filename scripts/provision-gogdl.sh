#!/usr/bin/env bash
set -Eeuo pipefail

# Idempotently provision the provider-owned gogdl executable.  The Heroic
# frontend is intentionally not installed; gogdl is used as a library/CLI
# backend only.
readonly ROOT=${LULU_PROVIDER_TOOL_ROOT:-/var/lib/lulu/provider-tools/gogdl}
readonly VENV="$ROOT/venv"
mkdir -p "$ROOT"
if [[ ! -x "$VENV/bin/gogdl" ]]; then
    python3 -m venv "$VENV"
    if ! "$VENV/bin/pip" install --upgrade heroic-gogdl; then
        readonly SOURCE="$ROOT/source"
        if [[ ! -d "$SOURCE/.git" ]]; then
            git clone --depth=1 --recurse-submodules https://github.com/Heroic-Games-Launcher/heroic-gogdl.git "$SOURCE"
        else
            git -C "$SOURCE" pull --ff-only
            git -C "$SOURCE" submodule update --init --recursive
        fi
        "$VENV/bin/pip" install --upgrade "$SOURCE"
    fi
fi
test -x "$VENV/bin/gogdl"
"$VENV/bin/gogdl" --version
install -Dm755 "$VENV/bin/gogdl" /usr/local/bin/gogdl
echo "provisioned gogdl at $VENV/bin/gogdl"
